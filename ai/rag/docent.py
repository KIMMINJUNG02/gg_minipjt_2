"""develop Backend 계약을 feature/rag+llm 파이프라인에 연결하는 adapter."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import os
from pathlib import Path
from threading import RLock
from typing import Any

from ai.llm.client import generate_chat
from ai.rag.chat import DocentChatService
from ai.rag.config import ROOT, load_config, project_path
from ai.rag.embeddings import get_embedding
from ai.rag.gold_loader import RelicNotFoundError, get_relic_records_by_label
from ai.rag.ollama import OllamaError
from ai.rag.vector_store import open_chroma


class ArtifactNotFound(LookupError):
    pass


@dataclass
class Answer:
    answer: str
    sources: list[str]
    route: str = "artifact"


@dataclass
class ChatRoute:
    route: str
    reason: str = "feature/rag+llm compatibility adapter"


class _LazyChromaStore:
    """최초 설명에서는 embedding/Chroma를 열지 않고 후속 질문에서만 연다."""

    def __init__(self, config: dict):
        self.config = config
        self._store = None
        self._lock = RLock()

    def _get(self):
        with self._lock:
            if self._store is None:
                vector = dict(self.config["vector_db"])
                vector["persist_directory"] = str(project_path(vector["persist_directory"]))
                vector["embedding_model"] = self.config["embedding"]["model"]
                self._store = open_chroma(vector, get_embedding(self.config["embedding"]))
            return self._store

    def similarity_search_with_score(self, query: str, k: int):
        return self._get().similarity_search_with_score(query, k=k)


class Docent:
    """기존 ``describe``/``chat`` signature를 보존하는 facade.

    Backend는 session_id를 AI 함수에 넘기지 않고 최근 메시지만 넘긴다. adapter는
    그 메시지 꼬리를 feature 세션과 대조해 동일 대화를 복원한다.
    """

    def __init__(
        self,
        *,
        config: dict | None = None,
        store: Any | None = None,
        generate_fn=generate_chat,
        metadata_csv: Path = ROOT / "data" / "metadata.csv",
        **_legacy_options,
    ) -> None:
        selected_config = os.environ.get("DOCENT_CONFIG")
        self.config = config or load_config(selected_config)
        runtime = dict(self.config)
        runtime["data"] = {
            **self.config["data"],
            "gold_path": str(project_path(self.config["data"]["gold_path"])),
        }
        self.service = DocentChatService(
            config=runtime,
            store=store or _LazyChromaStore(self.config),
            generate_fn=generate_fn,
        )
        self.metadata_csv = Path(metadata_csv)
        self._artifact_labels = self._load_artifact_labels()
        self._conversation_sessions: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    def _load_artifact_labels(self) -> dict[str, str]:
        if not self.metadata_csv.is_file():
            return {}
        with self.metadata_csv.open(encoding="utf-8-sig", newline="") as handle:
            return {
                row["artifact_id"].strip(): row["accession_no"].strip()
                for row in csv.DictReader(handle)
                if row.get("artifact_id") and row.get("accession_no")
            }

    def resolve(self, ref: str) -> str:
        label = self._artifact_labels.get(ref.strip(), ref.strip())
        try:
            get_relic_records_by_label(self.service.gold_path, label)
        except (RelicNotFoundError, ValueError) as exc:
            raise ArtifactNotFound(f"'{ref}'에 해당하는 소장품이 Gold 데이터에 없습니다.") from exc
        return label

    @staticmethod
    def _same_tail(stored: list[dict[str, str]], supplied: list[dict[str, str]]) -> bool:
        return bool(supplied) and len(stored) >= len(supplied) and stored[-len(supplied):] == supplied

    def _session_for_history(
        self,
        label: str,
        visitor_type: str,
        history: list[dict[str, str]],
    ) -> str:
        with self._lock:
            if history:
                for session_id, identity in self._conversation_sessions.items():
                    if identity != (label, visitor_type):
                        continue
                    stored = self.service.sessions.get(session_id).history
                    if self._same_tail(stored, history):
                        return session_id
            session = self.service.sessions.create(current_relic_label=label)
            if history:
                self.service.sessions.replace_history(session.session_id, history)
            self._conversation_sessions[session.session_id] = (label, visitor_type)
            return session.session_id

    @staticmethod
    def _sources(result: dict) -> list[str]:
        values = [item["chunk_id"] for item in result.get("retrieved", [])]
        values.extend(result.get("source_chunk_ids", []))
        return list(dict.fromkeys(values))

    def _translate_errors(self, operation):
        try:
            return operation()
        except ArtifactNotFound:
            raise
        except (RelicNotFoundError, ValueError) as exc:
            raise ArtifactNotFound(str(exc)) from exc
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaError(str(exc)) from exc

    def describe(self, ref: str, *, visitor_type: str = "general") -> Answer:
        label = self.resolve(ref)
        result = self._translate_errors(
            lambda: self.service.describe_relic(
                relic_label=label,
                visitor_type=visitor_type,
            )
        )
        return Answer(result["answer"], self._sources(result), "artifact")

    def chat(
        self,
        ref: str,
        question: str,
        *,
        visitor_type: str = "general",
        history: list[dict[str, str]] | None = None,
    ) -> tuple[Answer, ChatRoute]:
        label = self.resolve(ref)
        supplied_history = history or []
        session_id = self._session_for_history(label, visitor_type, supplied_history)
        result = self._translate_errors(
            lambda: self.service.answer_follow_up(
                question,
                session_id=session_id,
                relic_label=label,
                visitor_type=visitor_type,
            )
        )
        answer = Answer(result["answer"], self._sources(result), "search")
        return answer, ChatRoute("search")

    def route_chat(self, ref: str, question: str) -> ChatRoute:
        self.resolve(ref)
        return ChatRoute("search", "모든 후속 질문은 feature Retriever를 사용합니다")

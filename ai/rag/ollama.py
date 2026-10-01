"""Backend 예외 계약을 유지하는 Ollama compatibility module."""

from __future__ import annotations

from ai.llm.client import generate_chat
from ai.rag.config import load_config


class OllamaError(RuntimeError):
    """LLM 또는 AI runtime을 사용할 수 없을 때 Backend가 처리하는 예외."""


def chat(messages: list[dict[str, str]], **overrides) -> str:
    config = dict(load_config()["llm"])
    config.update(overrides)
    try:
        return generate_chat(messages, config)
    except Exception as exc:
        raise OllamaError(str(exc)) from exc

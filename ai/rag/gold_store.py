"""사전 생성 설명을 사용하던 develop Backend를 위한 compatibility module.

새 파이프라인은 최초 설명을 relic_label 기반 Gold 조회와 LLM으로 생성하므로,
기존 캐시 조회에는 명시적으로 miss를 반환해 새 Docent adapter로 위임한다.
"""

from __future__ import annotations


class GoldDataMissing(LookupError):
    pass


def get_cached_description(artifact_id: str, visitor_type: str) -> str:
    raise GoldDataMissing(
        "feature/rag+llm 파이프라인은 사전 생성 설명 대신 Gold 직접 조회를 사용합니다"
    )

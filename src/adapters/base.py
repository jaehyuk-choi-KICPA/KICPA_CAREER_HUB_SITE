"""어댑터 베이스 — 각 소스 어댑터의 공통 인터페이스와 견고성 래퍼.

조서 프로젝트의 `_safe_parse` "전체실패 금지" 원칙을 그대로 차용:
한 소스가 깨져도 빈 결과 + 진단 로그로 넘어가 나머지 소스는 살린다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.record import Posting


class Adapter(ABC):
    """한 채용 소스(게시판/ATS)를 담당. fetch()가 정규 레코드 리스트를 반환."""

    source: str = "base"
    label: str = "base"

    @abstractmethod
    def fetch(self) -> list[Posting]:
        """현재 게시중 공고들을 Posting 리스트로 반환."""
        raise NotImplementedError


@dataclass
class FetchResult:
    """소스별 수집 결과 + 진단."""

    source: str
    label: str
    postings: list[Posting] = field(default_factory=list)
    ok: bool = True
    error: str = ""

    @property
    def count(self) -> int:
        return len(self.postings)


def safe_fetch(adapter: Adapter) -> FetchResult:
    """어댑터를 안전하게 호출. 실패해도 예외를 삼키고 진단만 남긴다."""
    try:
        postings = adapter.fetch()
        return FetchResult(adapter.source, adapter.label, postings, ok=True)
    except Exception as e:  # noqa: BLE001 — 의도적으로 모든 예외 포획(전체실패 금지)
        return FetchResult(
            adapter.source,
            adapter.label,
            postings=[],
            ok=False,
            error=f"{type(e).__name__}: {e}",
        )

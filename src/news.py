"""뉴스/인사이트 공통 레코드 — 채용 Posting과 별개의 정규 레코드.

저작권 안전: 제목·출처·링크·날짜만(본문 전재 없음).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


def _norm(t: str) -> str:
    return " ".join((t or "").split())


@dataclass
class NewsItem:
    source: str          # 내부 키(예: gnews_딜, insight_samil)
    source_label: str    # 표시 출처(언론사/발행처명)
    title: str
    url: str
    published: str = ""  # yyyy-mm-dd (가능하면)
    summary: str = ""    # 1줄(선택)
    category: str = ""   # 딜/세무/회계/기타 또는 인사이트

    def __post_init__(self) -> None:
        self.title = _norm(self.title)
        self.source_label = _norm(self.source_label)
        self.summary = _norm(self.summary)

    def to_dict(self) -> dict:
        return asdict(self)

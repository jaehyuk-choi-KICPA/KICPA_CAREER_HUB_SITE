"""공통 정규 레코드 — 모든 소스 어댑터가 이 형태로 수렴해서 반환한다.

조서 프로젝트의 '이상적 양식 중간다리' 발상과 동일: 사이트마다 HTML이 달라도
이후 단계(필터·중복제거·포맷)는 이 한 가지 스키마만 다루면 된다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256


def _norm(text: str) -> str:
    """공백 정리."""
    return " ".join((text or "").split())


@dataclass
class Posting:
    source: str            # 내부 키: kicpa_susup / kicpa_cpa / samil / samjong / anjin / hanyoung
    source_label: str      # 게시용 라벨: 구인(수습CPA) / 삼정KPMG ...
    title: str
    company: str = ""
    deadline: str = ""     # 가능하면 yyyy-mm-dd, 아니면 원문 그대로
    posted_date: str = ""
    url: str = ""
    body_excerpt: str = ""
    category: str = ""     # 신입/인턴/경력/경력무관 — 소스가 알려주면 채움(필터용)
    location: str = ""     # 근무지(있으면)
    emp_type: str = ""     # 고용형태(정규/계약/인턴 등, 있으면)
    native_id: str = ""    # 소스 고유 ID(KICPA=ijIdNum 등). 비면 URL 해시로 채움

    def __post_init__(self) -> None:
        self.title = _norm(self.title)
        self.company = _norm(self.company)
        self.deadline = _norm(self.deadline)
        self.posted_date = _norm(self.posted_date)
        self.body_excerpt = _norm(self.body_excerpt)
        self.category = _norm(self.category)
        if not self.native_id:
            self.native_id = sha256(self.url.encode("utf-8")).hexdigest()[:16]

    @property
    def uid(self) -> str:
        """전역 식별자 — 중복제거·게시추적의 키."""
        return f"{self.source}:{self.native_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        return d

"""딜로이트 안진 채용 어댑터 (join.deloitte.co.kr, 국내 ATS WiseRecruit2 / ASP.NET).

목록 `WiseRecruit2/User/RecruitList.aspx` 는 서버 렌더링 정적 HTML.
각 행(tr): a[href=RecruitView.aspx?ridx=<n>] 의 텍스트가 깔끔한 제목.
행 텍스트의 날짜 범위 "시작 ~ 마감" → 마감일은 마지막 날짜.

안진 목록엔 신입/경력 구분 컬럼이 따로 없고 **제목에 '경력직/신입' 등이 포함**되므로,
구분 필터는 중앙 filters.py('경력' 제외, '신입/경력무관' 예외)에 맡긴다.
사용자 규칙(신입·경력무관만)은 그 필터로 충족된다.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.adapters.base import Adapter
from src.http_util import get
from src.record import Posting
from src.util import all_iso_dates

_BASE = "https://join.deloitte.co.kr/WiseRecruit2/User/"
_LIST = _BASE + "RecruitList.aspx"
_RIDX_RE = re.compile(r"ridx=(\d+)")


class AnjinAdapter(Adapter):
    source = "anjin"
    label = "딜로이트안진"

    def fetch(self) -> list[Posting]:
        r = get(_LIST)
        return self._parse(r.text)

    def _parse(self, html: str) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[Posting] = []
        for a in soup.find_all("a", href=lambda h: h and "RecruitView" in h):
            m = _RIDX_RE.search(a["href"])
            if not m:
                continue
            ridx = m.group(1)
            title = a.get_text(" ", strip=True)
            if not title:
                continue

            tr = a.find_parent("tr")
            dates = all_iso_dates(tr.get_text(" ", strip=True)) if tr else []
            posted = dates[0] if dates else ""
            deadline = dates[-1] if len(dates) >= 2 else (dates[0] if dates else "")

            out.append(
                Posting(
                    source=self.source,
                    source_label=self.label,
                    title=title,
                    company="딜로이트 안진",
                    deadline=deadline,
                    posted_date=posted,
                    url=f"{_BASE}RecruitView.aspx?ridx={ridx}",
                    native_id=ridx,
                )
            )
        return out

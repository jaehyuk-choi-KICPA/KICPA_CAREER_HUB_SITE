"""삼정 KPMG 채용 어댑터 (career.kr.kpmg.com 자체 ATS).

목록은 init.hr 가 아니라 **search.hr (POST)** 가 HTML 조각으로 반환한다(#list_jobopen_data).
각 항목: li.rec_con_list_li
  - onclick goDetailPage('<jobopen_id>', '<receive_div>')   # receive_div: N=신입, E=경력, O=공채/인턴
  - p.cre  = 구분 라벨(공채/신입/경력/인턴)
  - p.tit  = 제목
  - span.date = "시작 ~ 마감"  → 마감일은 두 번째 날짜
마감일이 목록에 바로 있어 상세 요청이 불필요하다. '경력(E)'은 소스 단계에서 제외.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.adapters.base import Adapter
from src.http_util import post
from src.record import Posting
from src.util import all_iso_dates

_BASE = (
    "https://career.kr.kpmg.com/hr/rec/recruit/jobopen/controller/"
    "candidate/JobOpen310WebController/"
)
_DETAIL = _BASE + "DetailInit.hr"
_SEARCH = _BASE + "search.hr"
_DETAIL_RE = re.compile(r"goDetailPage\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)")


class SamjongAdapter(Adapter):
    source = "samjong"
    label = "삼정KPMG"

    def __init__(self, max_results: int = 100):
        self.max_results = max_results

    def fetch(self) -> list[Posting]:
        # tab_receive_div_cd='' = 전체, 큰 maxresults로 한 번에 수집
        data = {
            "maxresults": str(self.max_results),
            "maxlinks": "10",
            "currentpage": "1",
            "tab_receive_div_cd": "",
            "receive_div_cd": "",
            "jobopen_id": "",
            "sortType": "",
            "sel_field_job": "",
        }
        r = post(_SEARCH, data=data, encoding="utf-8")
        return self._parse(r.text)

    def _parse(self, html: str) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[Posting] = []
        for li in soup.select("li.rec_con_list_li"):
            a = li.select_one("a[onclick*=goDetailPage]")
            if not a:
                continue
            m = _DETAIL_RE.search(a.get("onclick", ""))
            if not m:
                continue
            jobopen_id, receive_div = m.group(1), m.group(2)

            cre = (li.select_one("p.cre").get_text(strip=True) if li.select_one("p.cre") else "")
            # 경력은 소스 단계에서 제외(신입/인턴/공채만)
            if receive_div == "E" or cre == "경력":
                continue

            title_el = li.select_one("p.tit")
            title = title_el.get_text(strip=True) if title_el else ""

            date_el = li.select_one("span.date")
            dates = all_iso_dates(date_el.get_text(" ", strip=True) if date_el else "")
            posted = dates[0] if dates else ""
            deadline = dates[-1] if len(dates) >= 2 else (dates[0] if dates else "")

            url = f"{_DETAIL}?jobopen_id={jobopen_id}&receive_div_cd={receive_div}"
            out.append(
                Posting(
                    source=self.source,
                    source_label=self.label,
                    title=title,
                    company="삼정KPMG",
                    deadline=deadline,
                    posted_date=posted,
                    url=url,
                    category=cre,
                    native_id=jobopen_id,
                )
            )
        return out

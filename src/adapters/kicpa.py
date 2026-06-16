"""KICPA(한국공인회계사회) 구인 게시판 어댑터.

두 보드를 동일 로직으로 처리(보드 경로만 다름):
  - 구인(수습CPA): jobOffrSrchNewGnrl
  - 구인(CPA)   : jobOffrSrchGnrl

목록 `…/{board}/list.face` 는 서버 렌더링 정적 HTML(UTF-8). 컬럼:
  번호 | 제목 | 회사명 | 지역 | 구직완료구분 | 고용형태 | 등록일자 | 조회수
→ 목록의 날짜는 **등록일자(게시일)**다. **마감일은 목록에 없고 상세페이지에만** 있으므로
  상세 `…/{board}/detail.face?ijIdNum=<id>` 의 th '마감일' td에서 보강한다.
  마감일은 한 번 정해지면 안 바뀌므로 native_id로 캐시해 신규 공고만 상세를 받는다.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.adapters.base import Adapter
from src.http_util import get
from src.record import Posting
from src.util import to_iso_date

_BASE = "https://www.kicpa.or.kr/home"
_ID_RE = re.compile(r"fn_detail\(\s*'(\d+)'\s*\)")


class KicpaAdapter(Adapter):
    def __init__(
        self,
        board: str,
        source: str,
        label: str,
        max_pages: int = 2,
        deadline_cache: dict[str, str] | None = None,
    ):
        self.board = board
        self.source = source
        self.label = label
        self.max_pages = max_pages
        # native_id -> deadline(yyyy-mm-dd). 이미 아는 공고는 상세를 다시 안 받는다.
        self.deadline_cache = deadline_cache or {}

    def _list_url(self) -> str:
        return f"{_BASE}/{self.board}/list.face"

    def _detail_url(self, ij_id: str) -> str:
        return f"{_BASE}/{self.board}/detail.face?ijIdNum={ij_id}"

    def fetch(self) -> list[Posting]:
        seen: set[str] = set()
        out: list[Posting] = []
        for page in range(1, self.max_pages + 1):
            r = get(self._list_url(), params={"page": page}, encoding="utf-8")
            rows = self._parse_page(r.text)
            new = [p for p in rows if p.native_id not in seen]
            for p in new:
                seen.add(p.native_id)
            out.extend(new)
            if not new:  # 더 이상 새 행이 없으면 페이지 순회 중단
                break

        # 마감일 보강: 캐시 적용 후, 미보유분만 상세 요청(같은 도메인이라 동시성 ≤4로 제한)
        need: list[Posting] = []
        for p in out:
            cached = self.deadline_cache.get(p.native_id)
            if cached:
                p.deadline = cached
            else:
                need.append(p)
        if need:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(self._enrich_deadline, need))
        return out

    def _parse_page(self, html: str) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        postings: list[Posting] = []
        for a in soup.select("a.subject_title"):
            m = _ID_RE.search(a.get("onclick", ""))
            if not m:
                continue
            ij_id = m.group(1)
            title = a.get_text(strip=True)

            tr = a.find_parent("tr")
            company = ""
            posted = ""
            if tr is not None:
                cells = tr.select("td.txt_l")
                if cells:
                    company = cells[0].get_text(strip=True)
                # 행에 날짜는 등록일자 하나뿐 → 게시일로 기록
                posted = to_iso_date(tr.get_text(" ", strip=True))

            postings.append(
                Posting(
                    source=self.source,
                    source_label=self.label,
                    title=title,
                    company=company,
                    posted_date=posted,
                    url=self._detail_url(ij_id),
                    native_id=ij_id,
                )
            )
        return postings

    def _enrich_deadline(self, p: Posting) -> None:
        """상세페이지에서 마감일·근무지역·고용형태를 채운다. 실패해도 조용히 통과."""
        try:
            r = get(self._detail_url(p.native_id), encoding="utf-8")
            soup = BeautifulSoup(r.text, "html.parser")
            for th in soup.select("th"):
                label = th.get_text(strip=True)
                if label not in ("마감일", "근무지역", "고용형태"):
                    continue
                td = th.find_next_sibling("td")
                if not td:
                    continue
                val = td.get_text(" ", strip=True)
                if label == "마감일":
                    p.deadline = to_iso_date(val)
                elif label == "근무지역":
                    p.location = " ".join(val.split())[:30]
                elif label == "고용형태":
                    p.emp_type = " ".join(val.split())[:20]
        except Exception:  # noqa: BLE001 — 보강 실패는 비치명적
            pass


def build_kicpa_adapters(
    max_pages: int = 2, deadline_cache: dict[str, str] | None = None
) -> list[KicpaAdapter]:
    """KICPA 두 보드 어댑터를 생성. deadline_cache는 native_id->마감일 캐시."""
    cache = deadline_cache or {}
    return [
        KicpaAdapter("jobOffrSrchNewGnrl", "kicpa_susup", "구인(수습CPA)", max_pages, cache),
        KicpaAdapter("jobOffrSrchGnrl", "kicpa_cpa", "구인(CPA)", max_pages, cache),
    ]

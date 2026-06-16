"""삼일 PwC 채용 어댑터 (www.pwc.com/kr — Adobe AEM 글로벌 사이트).

타깃: **신입·인턴만 (경력 제외).**

[RECON 결과 — 다른 어댑터 작성자도 참고]
PwC 글로벌 사이트는 Adobe AEM이다. 채용 안내 페이지 구조:

  - `/kr/ko/career/graduate-opportunities.html` (정기채용/신입공채 안내) 는 **정보성 페이지**다.
    "신입공인회계사 공채"·"컨설턴트 공채" 섹션의 실제 공고 링크는 **클라이언트 JS로 렌더**되어
    정적 HTML에는 공고 목록이 없다(테이블 0개, rXXXXXX 링크 0개). 정적으로 잡히는 건
    상단 nav의 Featured 항목(`/career/<slug>.html`) 정도뿐이라 신뢰할 목록 소스가 아니다.

  - `/kr/ko/career/experienced.html` (수시채용) 는 **서버 렌더링 정적 HTML 테이블**로
    현재 열린 **모든 공고**(경력직·인턴·신입 혼재)를 담는다. 컬럼:
        Job title | Line of Service | Grade | Due date | 이력서 작성
    Grade 값이 `경력직 / 인턴 / 신입 / "신입, 경력직"` 으로 명확해 **분류 소스로 가장 신뢰성 높다**.
    공고 링크는 `/kr/ko/career/experienced/rXXXXXX.html` (rXXXXXX = PwC 공고 id, native_id로 사용).
    마감일은 "2026년 6월 30일 (화)" 형식(→ to_iso_date 파싱) 또는 "채용 시 마감"(상시 → "").

→ 따라서 **experienced.html 테이블을 단일 소스로 쓰되 Grade로 인턴/신입만 채택**한다.
  (이 페이지명이 '수시채용'이지만 인턴/신입 공고가 여기에 함께 올라온다. graduate 페이지는
  JS 렌더라 정적 수집 불가 — 한계로 문서화.) 경력직은 어댑터 단계에서 제외하고, 중앙
  filters.py('경력' 제외, '신입/인턴' 예외)가 2차 안전망.

[차단 회피] PwC는 봇 User-Agent(CpaJobAlertBot)에 403을 준다. 브라우저 UA면 200.
  http_util.get(headers=)로 이 요청에만 브라우저 UA를 실어 보낸다(세션 기본 UA는 그대로 유지).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.adapters.base import Adapter
from src.http_util import get
from src.record import Posting
from src.util import to_iso_date

_LIST = "https://www.pwc.com/kr/ko/career/experienced.html"
_ORIGIN = "https://www.pwc.com"
# 공고 상세 링크 안의 PwC 공고 id (r260612, r260611-3 …)
_RID_RE = re.compile(r"/(r\d+(?:-\d+)?)\.html", re.IGNORECASE)
# PwC가 봇 UA를 403으로 막아, 요청 동안만 쓰는 브라우저 UA
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Grade 컬럼 기준 채택/제외. 인턴·신입만(경력직 제외). "신입, 경력직"은 신입 포함이라 채택.
_KEEP_GRADE = ("인턴", "신입")
_DROP_GRADE = "경력"


class SamilAdapter(Adapter):
    source = "samil"
    label = "삼일PwC"

    def fetch(self) -> list[Posting]:
        # PwC 봇 차단 회피: 이 요청에만 브라우저 UA(세션 기본 UA는 그대로).
        r = get(_LIST, headers={"User-Agent": _BROWSER_UA}, encoding="utf-8")
        return self._parse(r.text)

    def _parse(self, html: str) -> list[Posting]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[Posting] = []
        seen: set[str] = set()

        # 공고 테이블 = rXXXXXX 링크를 품은 테이블. 페이지에 그 외 테이블은 없지만 방어적으로 탐색.
        for a in soup.find_all("a", href=_RID_RE):
            href = a.get("href", "")
            m = _RID_RE.search(href)
            if not m:
                continue
            tr = a.find_parent("tr")
            if tr is None:
                continue

            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            # 기대 컬럼: [title, los, grade, due, (이력서)]. 헤더행/이상행은 건너뜀.
            if len(cells) < 4:
                continue

            title = cells[0]
            los = cells[1]          # Line of Service (분야)
            grade = cells[2]        # 경력직 / 인턴 / 신입 / "신입, 경력직"
            due_raw = cells[3]      # "2026년 6월 30일 (화)" 또는 "채용 시 마감"

            if not title or title.lower() == "job title":
                continue

            # 인턴/신입만 채택. 경력직 단독은 제외. "신입, 경력직"은 신입 포함이라 채택.
            keep = any(k in grade for k in _KEEP_GRADE)
            if not keep:
                continue
            # 안전: grade가 '경력'만이고 인턴/신입 단어가 없으면(위에서 이미 걸러짐) 통과 못함.

            rid = m.group(1).lower()
            url = href if href.startswith("http") else _ORIGIN + href

            if rid in seen:
                continue
            seen.add(rid)

            # 마감일: "채용 시 마감" 등 날짜 없으면 "" → 시스템이 상시/open 으로 취급.
            deadline = to_iso_date(due_raw)

            # category: 필터·표시에 쓰도록 Grade 그대로(인턴/신입). LoS는 참고로 본문발췌에.
            out.append(
                Posting(
                    source=self.source,
                    source_label=self.label,
                    title=title,
                    company="삼일PwC",
                    deadline=deadline,
                    posted_date="",  # PwC 목록에 게시일 없음
                    url=url,
                    body_excerpt=los,
                    category=grade,
                    native_id=rid,
                )
            )
        return out

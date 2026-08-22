"""Big4 인사이트/간행물 어댑터 (헤드리스 렌더 — 제목+링크만, 저작권 안전).

대상 발행처 사이트가 모두 JS(SPA) 렌더라 Chromium(Playwright)으로 렌더 후 개별 글 링크를 추출한다.
Playwright 미설치/실패 시 빈 결과로 수렴(전체실패 금지). 타깃 삼일을 리스트 앞에 둔다.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.adapters.base import Adapter
from src.news import NewsItem
from src.render import render_html

_SKIP = {"자세히 보기", "더보기", "더 보기", "전체보기", "Publication", "인사이트 리포트"}
# 카드 앵커에 섞여 들어오는 부속 텍스트(제목이 아님)
_MONTH_RE = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|"
                       r"November|December)\s+\d{4}$", re.I)
_NOISE = {"read more", "자세히 보기", "더보기", "더 보기", "전체보기", "download", "다운로드"}


def _blocks(a) -> list[str]:
    """앵커 안의 **말단 텍스트 블록** 목록(중첩 컨테이너는 건너뛴다).

    발행처 카드가 대부분 `<p>제목</p><p>요약</p>` 꼴이라, 앵커 텍스트를 통째로 긁으면
    제목과 요약(+발행월·'Read more')이 한 덩어리가 된다. 실측: 48건 중 28건이 그렇게 오염됐다.
    """
    out = []
    for c in a.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "div", "strong"]):
        if c.find(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div"]):
            continue                       # 다른 블록을 품은 컨테이너는 스킵(중복 방지)
        t = " ".join(c.get_text(" ", strip=True).split())
        if t and t not in out:
            out.append(t)
    return out


def split_title(a) -> tuple[str, str]:
    """앵커 → (제목, 요약). 발행월·'Read more' 같은 부속 블록은 버린다.

    블록이 하나뿐이면(마크업이 평평한 경우) 그 텍스트에서 말머리 발행월과 꼬리 'Read more'만 떼어낸다.
    """
    blocks = [b for b in _blocks(a)
              if not _MONTH_RE.match(b) and b.strip().lower() not in _NOISE]
    if not blocks:
        raw = " ".join(a.get_text(" ", strip=True).split())
        raw = _MONTH_RE.sub("", raw)
        return re.sub(r"\s*Read more\s*$", "", raw, flags=re.I).strip(), ""
    title = blocks[0]
    summary = " ".join(blocks[1:])
    summary = re.sub(r"\s*Read more\s*$", "", summary, flags=re.I).strip()
    return title, summary


class JSInsightAdapter(Adapter):
    """JS 렌더 인사이트 페이지 공용 어댑터. 개별 글(깊이 2 이상 경로)만 추출."""

    def __init__(self, source: str, label: str, list_url: str, origin: str,
                 art_pattern: str, limit: int = 12):
        self.source = source
        self.label = label
        self.list_url = list_url
        self.origin = origin
        self.art = re.compile(art_pattern, re.IGNORECASE)
        self.limit = limit

    def fetch(self) -> list[NewsItem]:
        html = render_html(self.list_url, wait_ms=3000)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        out, seen_url, seen_title = [], set(), set()
        for a in soup.find_all("a", href=True):
            href = a["href"].split("?")[0].split("#")[0]
            if not self.art.search(href):
                continue
            title, summary = split_title(a)
            if len(title) < 7 or title in _SKIP:
                continue
            if len(title) > 80:  # 그래도 긴 경우(마크업이 평평한 발행처)만 축약
                title = title[:79].rstrip() + "…"
            if len(summary) > 120:
                summary = summary[:119].rstrip() + "…"
            url = href if href.startswith("http") else self.origin + href
            if url in seen_url or title in seen_title:
                continue
            seen_url.add(url)
            seen_title.add(title)
            out.append(
                NewsItem(source=self.source, source_label=self.label,
                         title=title, url=url, summary=summary, category="인사이트")
            )
            if len(out) >= self.limit:
                break
        return out


def build_insight_adapters(cfg: dict) -> list[Adapter]:
    # 삼일(타깃) 우선. 모두 JS 렌더.
    return [
        JSInsightAdapter("insight_samil", "삼일PwC",
                         "https://www.pwc.com/kr/ko/insights.html",
                         "https://www.pwc.com",
                         r"/kr/ko/insights/[^/]+/[^/?#]+\.html"),
        JSInsightAdapter("insight_samjong", "삼정KPMG",
                         "https://kpmg.com/kr/ko/insights.html",
                         "https://kpmg.com",
                         r"/kr/ko/insights/[^/]+/[^/?#]+"),
        JSInsightAdapter("insight_anjin", "Deloitte안진",
                         "https://www.deloitte.com/kr/ko/our-thinking/deloitte-insights.html",
                         "https://www.deloitte.com",
                         # 실제 발간물은 /our-thinking/ 이 아니라 산업·서비스 하위 perspectives|research|analysis leaf
                         # (예: /kr/ko/services/tax/perspectives/<글>.html). 메뉴/섹션 랜딩 링크와 구분됨.
                         r"/kr/ko/.+/(perspectives|research|analysis|blogs)/[^/?#]+\.html"),
        JSInsightAdapter("insight_hanyoung", "EY한영",
                         "https://www.ey.com/ko_kr/insights",
                         "https://www.ey.com",
                         r"/ko_kr/insights/[^/]+/[^/?#]+"),
    ]

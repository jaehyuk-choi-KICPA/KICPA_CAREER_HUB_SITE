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
            title = " ".join(a.get_text(" ", strip=True).split())
            if len(title) < 7 or title in _SKIP:
                continue
            if len(title) > 80:  # 제목+설명이 붙은 경우 카드용으로 축약
                title = title[:79].rstrip() + "…"
            url = href if href.startswith("http") else self.origin + href
            if url in seen_url or title in seen_title:
                continue
            seen_url.add(url)
            seen_title.add(title)
            out.append(
                NewsItem(source=self.source, source_label=self.label,
                         title=title, url=url, category="인사이트")
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
        JSInsightAdapter("insight_anjin", "딜로이트안진",
                         "https://www.deloitte.com/kr/ko/our-thinking/deloitte-insights.html",
                         "https://www.deloitte.com",
                         r"/kr/ko/our-thinking/[^/]+/[^/?#]+\.html"),
        JSInsightAdapter("insight_hanyoung", "EY한영",
                         "https://www.ey.com/ko_kr/insights",
                         "https://www.ey.com",
                         r"/ko_kr/insights/[^/]+/[^/?#]+"),
    ]

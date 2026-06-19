"""Google News RSS 어댑터 — 카테고리별 쿼리로 회계·세무·딜 이슈 수집.

사이트별 RSS 헌팅 대신 Google News RSS를 쓴다(견고·무료, 제목+출처+링크+날짜만 = 저작권 안전).
카테고리당 어댑터 1개 → fetch_all 병렬 수집에 그대로 올라감.
"""

from __future__ import annotations

import datetime as _dt
import urllib.parse
import xml.etree.ElementTree as ET

from src.adapters.base import Adapter
from src.http_util import get
from src.news import NewsItem

_BASE = "https://news.google.com/rss/search"


def _pub_to_dt(text: str) -> str:
    """RSS pubDate(RFC822) → 'yyyy-mm-ddTHH:MM:SS'(정렬용 — 같은 날 시각까지 보존). 실패하면 빈 문자열.

    published(날짜만)는 같은 날 기사 간 정렬 tiebreaker가 없어 화면이 '뒤죽박죽'으로 보였다.
    pubDate에는 시각이 있으므로 보존해 build_news 정렬이 진짜 최신순이 되게 한다.
    """
    if not text:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = _dt.datetime.strptime(text.strip(), fmt)
            if dt.tzinfo is not None:           # tz 있으면 UTC로 정규화(혼합 정렬 일관성)
                dt = dt.astimezone(_dt.timezone.utc).replace(tzinfo=None)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            continue
    return ""


def _pub_to_iso(text: str) -> str:
    """RSS pubDate → yyyy-mm-dd(표시·보존기간용). published_at[:10]과 동일 기준."""
    dt = _pub_to_dt(text)
    return dt[:10] if dt else ""


class GoogleNewsAdapter(Adapter):
    def __init__(self, category: str, query: str, limit: int = 20):
        self.category = category
        self.query = query
        self.limit = limit
        self.source = f"gnews_{category}"
        self.label = category

    def fetch(self) -> list[NewsItem]:
        q = urllib.parse.quote(self.query)
        url = f"{_BASE}?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        r = get(url, headers={"User-Agent": "Mozilla/5.0"}, encoding="utf-8")
        root = ET.fromstring(r.text)
        out: list[NewsItem] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or not link:
                continue
            src_el = item.find("source")
            source_label = (src_el.text if src_el is not None else "") or "뉴스"
            # Google News 제목은 보통 "헤드라인 - 언론사" → 끝의 출처 표기는 source_label로 대체
            if source_label and title.endswith(f"- {source_label}"):
                title = title[: -(len(source_label) + 2)].strip()
            pub_dt = _pub_to_dt(item.findtext("pubDate") or "")
            out.append(
                NewsItem(
                    source=self.source,
                    source_label=source_label,
                    title=title,
                    url=link,
                    published=pub_dt[:10],     # 날짜만(표시·보존기간)
                    published_at=pub_dt,       # 시각 포함(정렬용)
                    category=self.category,
                )
            )
            if len(out) >= self.limit:
                break
        return out


def build_news_adapters(cfg: dict) -> list[GoogleNewsAdapter]:
    d = cfg["dashboard"]
    limit = d.get("news_per_category", 20)
    adapters = []
    for cat, q in d["news_queries"].items():
        qs = q if isinstance(q, list) else [q]
        for idx, sub_q in enumerate(qs):
            a = GoogleNewsAdapter(cat, sub_q, limit)
            if idx > 0:
                # 같은 카테고리 2번째+ 풀은 source 접미사로 구분(dedup은 URL 기준이라 영향 없음)
                a.source = f"gnews_{cat}_{idx + 1}"
            adapters.append(a)
    return adapters

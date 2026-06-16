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


def _pub_to_iso(text: str) -> str:
    """RSS pubDate(RFC822) → yyyy-mm-dd. 실패하면 빈 문자열."""
    if not text:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return _dt.datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


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
            out.append(
                NewsItem(
                    source=self.source,
                    source_label=source_label,
                    title=title,
                    url=link,
                    published=_pub_to_iso(item.findtext("pubDate") or ""),
                    category=self.category,
                )
            )
            if len(out) >= self.limit:
                break
        return out


def build_news_adapters(cfg: dict) -> list[GoogleNewsAdapter]:
    d = cfg["dashboard"]
    limit = d.get("news_per_category", 20)
    return [GoogleNewsAdapter(cat, q, limit) for cat, q in d["news_queries"].items()]

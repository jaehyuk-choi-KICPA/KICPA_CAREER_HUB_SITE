"""Google News RSS 어댑터 — 카테고리별 쿼리로 회계·세무·딜 이슈 수집.

사이트별 RSS 헌팅 대신 Google News RSS를 쓴다(견고·무료, 제목+출처+링크+날짜만 = 저작권 안전).
카테고리당 어댑터 1개 → fetch_all 병렬 수집에 그대로 올라감.
"""

from __future__ import annotations

import datetime as _dt
import time
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
        # 구글뉴스 RSS는 가끔 200인데 item이 0개인 '빈 피드'를 준다(일시 throttle). 도메인 쿼리는
        # 사실상 항상 결과가 있으므로 0건이면 짧게 쉬고 재시도 — 한 회차 빈응답이 카테고리를 통째로
        # 0건으로 비우는 사고를 막는다(실측: 세무 쿼리가 한 회차 빈응답→세무 0건 발생, 재시도 시 100건 복구).
        items: list = []
        for attempt in range(3):
            r = get(url, headers={"User-Agent": "Mozilla/5.0"}, encoding="utf-8")
            items = list(ET.fromstring(r.text).iter("item"))
            if items:
                break
            if attempt < 2:
                time.sleep(1.5)
        out: list[NewsItem] = []
        for item in items:
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


def _with_window(query: str, window: tuple[str, str] | None) -> str:
    """쿼리에 기간 연산자를 덧붙인다. window=(bgn, end), 둘 다 'yyyy-mm-dd'.

    구글뉴스 RSS의 q는 `after:` / `before:` 날짜 연산자를 지원한다(실측 확인:
    "회계법인 after:2026-04-01 before:2026-04-30" → 4월 기사 80건 반환).
    아카이브 소급 백필이 라이브와 **동일한 어댑터·필터 경로**를 타게 하려고 둔 훅이다.
    window=None이면 원문 그대로 → 기존 동작 완전 불변.
    """
    if not window:
        return query
    bgn, end = window
    return f"{query} after:{bgn} before:{end}"


def _build_from_queries(queries: dict, limit: int, prefix: str,
                        window: tuple[str, str] | None) -> list[GoogleNewsAdapter]:
    """{카테고리: 쿼리 or [쿼리...]} → 어댑터 목록. 값이 리스트면 풀(pool)로 나눈다.

    dict 삽입 순서가 그대로 어댑터 순서 = build_news/build_industry의 dedup 선점 순서다.
    """
    adapters: list[GoogleNewsAdapter] = []
    for cat, q in queries.items():
        qs = q if isinstance(q, list) else [q]
        for idx, sub_q in enumerate(qs):
            a = GoogleNewsAdapter(cat, _with_window(sub_q, window), limit)
            a.source = f"{prefix}{cat}" if idx == 0 else f"{prefix}{cat}_{idx + 1}"
            # 같은 카테고리 2번째+ 풀은 source 접미사로 구분(dedup은 URL 기준이라 영향 없음)
            adapters.append(a)
    return adapters


def build_news_adapters(cfg: dict, window: tuple[str, str] | None = None) -> list[GoogleNewsAdapter]:
    d = cfg["dashboard"]
    return _build_from_queries(d["news_queries"], d.get("news_per_category", 20), "gnews_", window)


def build_industry_adapters(cfg: dict, window: tuple[str, str] | None = None) -> list[GoogleNewsAdapter]:
    """산업별 기사(회계·재무 렌즈) 어댑터 — 뉴스 4분류와 **완전히 별개인 스트림**.

    source 접두사를 `gnews_ind_`로 두어 뉴스 어댑터와 섞이지 않게 한다. 어댑터 자체는
    GoogleNewsAdapter를 그대로 재사용하므로 새 수집 코드가 없다(어댑터 패턴 원칙).
    산업 쿼리를 news_queries에 넣지 않는 이유는 config.py의 산업 블록 주석 참조.
    """
    d = cfg["dashboard"]
    return _build_from_queries(d.get("industry_queries", {}),
                               d.get("industry_per_category", 60), "gnews_ind_", window)

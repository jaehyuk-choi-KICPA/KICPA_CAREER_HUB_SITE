"""누적 아카이브 — 스트림별·월별 샤드에 기사를 멱등 append.

왜 필요한가: `docs/data/news.json`·`industry.json`은 매 수집마다 **전량 덮어쓰기**이고
보존창(21·30일)이 지난 기사는 사라진다. 즉 사이트에는 "지금 이 순간의 스냅샷" 한 장만 남고
'꾸준히 모아왔다'는 누적 이력이 어디에도 없다. 이 모듈이 그 계층이다.

레이아웃 (`docs/data/archive/`):
    index.json                 기간 필터 진입 시 로드하는 유일한 파일(~2KB)
    news/2026-05.json …        스트림별·월별 샤드
    industry/…  insights/…

**월별 + 스트림별 샤딩인 이유**: 매 수집에 바뀌는 파일이 당월 1개뿐이라 git 델타가
"파일 말미에 몇 줄 추가"로 수렴한다. 통짜 파일이면 30분마다 수 MB blob이 통째로 재기록돼
리포가 급속히 부푼다. news(30분)와 industry(3시간)는 갱신 주기가 달라 한 파일에 합치면
서로의 blob을 헛되이 재기록하므로 스트림도 분리한다.

**축약 스키마**: 표시에 쓰지 않는 `summary`(항상 빈 문자열)·`source`(내부 어댑터 키)는 버린다.
저작권 원칙(제목·링크·출처·날짜만 보관)과도 정합한다.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

ARCHIVE_DIR = Path("docs/data/archive")

# 아카이브에 보존할 필드(화이트리스트). 이 목록에 없는 키는 저장하지 않는다.
# `dupes`는 **일부러 뺐다** — 아래 _expand() 참조. 대신 `gid`로 군집 관계만 남긴다.
_KEEP = ("title", "url", "source_label", "published", "published_at",
         "category", "companies", "first_archived", "gid")

_STREAMS = ("news", "industry", "insights")


def norm_url(url: str) -> str:
    """중복 판정용 URL 정규화 — 구글뉴스 RSS 링크의 쿼리(`?oc=5`)를 떼어낸다.

    경로의 base64 토큰이 기사 식별자이고 쿼리는 상수라, 붙은 채로 두면 같은 기사가
    스냅샷 시점에 따라 다른 키로 잡힐 수 있다. 다른 호스트는 쿼리가 의미를 가질 수 있으므로 건드리지 않는다.
    """
    u = (url or "").strip()
    if "news.google.com" in u and "?" in u:
        return u.split("?", 1)[0]
    return u


def norm_title(title: str) -> str:
    """중복 판정용 제목 정규화 — 공백만 접고 소문자화(내용은 건드리지 않는다).

    구글뉴스 RSS는 **같은 기사를 시점에 따라 다른 base64 링크로** 내보낸다. URL만 키로 쓰면
    그때마다 새 레코드가 되어 같은 제목이 화면에 여러 장 뜬다(실측: 업계 아카이브 2,527건 중 481건 = 19%).
    """
    return " ".join((title or "").split()).lower()


def month_key(item: dict, today: str) -> str:
    """아이템이 속할 월(yyyy-mm).

    발행일 → 정렬용 타임스탬프 → 최초 아카이브일 순으로 폴백한다. 인사이트는 발행일이
    **48건 전부 빈 문자열**이라(사이트마다 포맷이 없거나 달라 신뢰 불가) first_archived가 유일한 근거다.
    """
    for key in ("published", "published_at", "first_archived"):
        v = (item.get(key) or "")[:7]
        if len(v) == 7:
            return v
    return today[:7]


def slim(item: dict, today: str) -> dict:
    """라이브 아이템 → 아카이브 아이템(화이트리스트 + first_archived 부여)."""
    out = {k: item[k] for k in _KEEP if item.get(k)}
    out["url"] = norm_url(item.get("url", ""))
    out.setdefault("first_archived", today)
    return out


def _shard_path(stream: str, month: str) -> Path:
    return ARCHIVE_DIR / stream / f"{month}.json"


def _read_shard(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("items") or []
    except Exception:  # noqa: BLE001 — 손상 샤드가 전체 수집을 막지 않게(견고성 원칙)
        return []


def _write_shard(path: Path, month: str, items: list[dict]) -> None:
    """아이템 1건 = 1줄로 기록. 유효 JSON이면서 append가 '순수 추가 라인'이 되어 git 델타가 최소가 된다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(json.dumps(it, ensure_ascii=False, separators=(",", ":")) for it in items)
    head = '{"month":"%s","count":%d,"items":[\n' % (month, len(items))
    path.write_text(head + body + "\n]}", encoding="utf-8")


def _merge_one(old: dict, new: dict) -> dict:
    """기존 레코드에 새 레코드를 보강 병합.

    title·category·first_archived는 **최초값을 유지**한다(과거 판정의 안정성 — 나중에 분류 규칙이
    바뀌어도 그때 화면에 떴던 모습이 보존된다). 비어 있던 값만 채운다.
    """
    out = dict(old)
    for k in ("published", "published_at", "source_label", "companies", "gid"):
        if not out.get(k) and new.get(k):
            out[k] = new[k]
    return out


def _expand(item: dict) -> list[dict]:
    """근접중복 묶음을 **평면화** — 대표 1건 + dupes 각각을 독립 레코드로 승격.

    라이브 화면은 같은 사건을 대표 1건 + `dupes`로 접어 보여주지만, 아카이브에 그 구조를 그대로
    담으면 안 된다. 대표 레코드의 dupes 배열이 스냅샷마다 합쳐지며 **무제한 누적**되기 때문이다
    (실측: 3,090 스냅샷 병합 시 news 아카이브가 11MB까지 부풀었다 — 레코드당 2.2KB).
    아카이브의 일은 '그때 어떤 기사가 있었나'를 평평하게 남기는 것이고, 군집화는 라이브의 관심사다.
    dupes 멤버는 category·companies를 갖고 있지 않으므로 대표에게서 상속받는다.

    다만 **군집 관계까지 버리면** 라이브에서 카드 1장이던 사건이 아카이브에선 5장으로 흩어져
    '중복이 많다'로 보인다. 그래서 배열은 펴되 `gid`(대표 URL)만 남겨, 프론트가 읽을 때
    같은 gid끼리 다시 접어 '동일 주제 기사 N개'로 보여줄 수 있게 한다.
    (gid는 문자열 한 개라 스냅샷마다 누적되지 않는다 — 11MB 사고의 원인은 배열 누적이었다.)
    """
    gid = norm_url(item.get("url", ""))
    out = [dict(item, gid=gid)]
    for d in item.get("dupes") or []:
        if not d.get("url"):
            continue
        out.append({
            "title": d.get("title", ""),
            "url": d.get("url", ""),
            "source_label": d.get("source_label", ""),
            "published": d.get("published") or item.get("published", ""),
            "published_at": d.get("published_at") or "",
            "category": item.get("category", ""),      # 멤버엔 없어 대표에게서 상속
            "gid": gid,
        })
    return out


def merge_items(stream: str, items: list[dict], *, since: str = "",
                today: str | None = None) -> dict[str, int]:
    """월별 샤드에 URL 기준 멱등 upsert. 반환 = {월: 새로 추가된 건수}.

    · `since`(yyyy-mm-dd) 이전 발행분은 버린다 — git 스냅샷에 첫 수집이 끌어온 4월 기사가
      3건 섞여 있어 그대로 두면 월 칩에 "2026-04 · 3건"이 떠 화면만 어수선해진다.
    · 내용이 바뀌지 않은 샤드는 **쓰지 않는다**(불필요한 git blob 재기록 방지).
    """
    today = today or _dt.date.today().isoformat()
    buckets: dict[str, list[dict]] = {}
    flat = [it for raw in items or [] for it in _expand(raw)]
    for it in flat:
        s = slim(it, today)
        if not s.get("url"):
            continue
        if since and (s.get("published") or today) < since:
            continue
        buckets.setdefault(month_key(s, today), []).append(s)

    added: dict[str, int] = {}
    for month, fresh in buckets.items():
        path = _shard_path(stream, month)
        existing = _read_shard(path)
        by_url = {norm_url(x.get("url", "")): x for x in existing}
        # 제목 → 이미 보유한 URL. 구글뉴스가 같은 기사를 새 링크로 다시 내보낼 때
        # 새 레코드로 쌓이지 않도록, URL이 달라도 제목이 같으면 기존 레코드를 보강한다.
        by_title: dict[str, str] = {}
        for u, x in by_url.items():
            t = norm_title(x.get("title", ""))
            if t:
                by_title.setdefault(t, u)
        before = len(by_url)
        changed = False
        for s in fresh:
            key = s["url"]
            title_key = norm_title(s.get("title", ""))
            if key not in by_url and title_key in by_title:
                key = by_title[title_key]          # 같은 기사·다른 링크 → 기존 레코드로 흡수
            if key in by_url:
                merged = _merge_one(by_url[key], s)
                if merged != by_url[key]:
                    by_url[key] = merged
                    changed = True
            else:
                by_url[key] = s
                changed = True
                if title_key:
                    by_title[title_key] = key
        if changed:
            out = sorted(by_url.values(),
                         key=lambda i: (i.get("published_at") or i.get("published") or ""),
                         reverse=True)
            _write_shard(path, month, out)
        added[month] = len(by_url) - before
    return added


def bulk_merge(stream: str, items: list[dict], *, since: str = "",
               today: str | None = None) -> dict[str, int]:
    """백필 전용 — 대량 입력을 월별로 한 번에 모아 샤드당 1회만 write.

    merge_items를 건별로 부르면 같은 샤드를 수천 번 다시 쓰게 된다(백필은 2,900 스냅샷 규모).
    동작·병합 규칙은 merge_items와 동일하다.
    """
    return merge_items(stream, items, since=since, today=today)


def rebuild_index(streams: tuple[str, ...] = _STREAMS, since: str = "") -> dict:
    """전 샤드를 스캔해 archive/index.json 재작성 — 프론트 기간 필터가 이 파일만 먼저 읽는다."""
    out: dict = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "since": since,
        "streams": {},
    }
    for stream in streams:
        d = ARCHIVE_DIR / stream
        months = []
        for path in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
            items = _read_shard(path)
            if items:
                months.append({"m": path.stem, "n": len(items)})
        if months:
            out["streams"][stream] = {"total": sum(m["n"] for m in months), "months": months}
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    (ARCHIVE_DIR / "index.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

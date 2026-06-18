"""대시보드 데이터 생성기 — 스크랩→분류→docs/data/*.json.

진입점: `python -m src.export`  (채용 jobs.json. 뉴스/인사이트는 추가 예정)
- 채용: 6소스 병렬 수집 → 경력 제외 필터 → 법인/직무/상태/D-day 부여 → docs/data/jobs.json
- 견고성: 부분 실패해도 항상 파일 생성(전체실패 금지).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

from src import embeds
from src.adapters.base import safe_fetch
from src.adapters.insights import build_insight_adapters
from src.adapters.news_rss import build_news_adapters
from src.classify import classify_field, classify_firm
from src.config import load_config
from src.filters import filter_postings
from src.sources import build_adapters, fetch_all
from src.state import State
from src.util import dday, is_open, today_iso

_DATA_DIR = Path("docs/data")

# 정렬·요약용 법인 노출 순서(삼일 우선 — 타깃)
_FIRM_ORDER = ["삼일", "삼정", "안진", "한영", "로컬", "기타"]


def _write_json(name: str, payload: dict) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_guarded(name: str, payload: dict, items_key: str) -> bool:
    """수집 0건이면 직전 양호본을 유지(빈 화면 방지) — 사이트가 절대 텅 비지 않게.

    전 소스가 일시 장애로 0건이 나와도, 직전에 정상 데이터가 있으면 덮어쓰지 않는다.
    (전체실패 금지: 한 번의 나쁜 수집이 살아있는 화면을 지우지 못한다.)
    """
    new_n = len(payload.get(items_key) or [])
    path = _DATA_DIR / name
    if new_n == 0 and path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            prev_n = len(prev.get(items_key) or [])
        except Exception:
            prev_n = 0
        if prev_n > 0:
            print(f"  [유지] {name}: 0건 수집 -> 직전본({prev_n}건) 유지(빈 화면 방지, 미커밋)")
            return False
    _write_json(name, payload)
    return True


def build_jobs(cfg: dict, state: State) -> dict:
    """채용 데이터 수집·분류 → jobs payload dict."""
    adapters = build_adapters(cfg, state)
    results = fetch_all(adapters)

    postings = []
    report = []
    for res in results:
        report.append((res.label, res.ok, res.count, res.error))
        postings.extend(res.postings)

    kept = filter_postings(postings, cfg)  # 경력 제외(수습/주니어 타깃)

    # 지속성(grace): KICPA가 살아있는 공고를 목록서 일시적으로 내려 깜빡이는 문제 대응.
    # 이번에 빠졌어도 마감 전·최근 목격분은 복원(상세는 살아있음). grace_days 넘으면 자동 탈락.
    present_uids = {p.uid for p in kept}
    state.update(kept)                      # 본 공고의 last_seen 갱신 + 신규 기록
    grace_days = cfg["dashboard"].get("jobs_grace_days", 2)
    carried = state.carry_forward(present_uids, grace_days)
    state.prune_expired()                   # 마감 지난 좀비 제거
    if carried:
        print(f"  [복원] 목록 일시 누락 {len(carried)}건 유지(grace {grace_days}일)")
    kept = kept + carried

    new_cut = _recent_cutoff(cfg["dashboard"]["new_days"])
    items = []
    for p in kept:
        open_ = is_open(p.deadline)
        firm = classify_firm(p, cfg)
        items.append(
            {
                "source": p.source,
                "source_label": p.source_label,
                "firm": firm,
                "field": classify_field(p, cfg, firm),
                "status": "open" if open_ else "closed",
                "is_new": bool(p.posted_date and p.posted_date >= new_cut),
                "title": p.title,
                "company": p.company,
                "deadline": p.deadline,
                "posted_date": p.posted_date,
                "location": p.location,
                "emp_type": p.emp_type or p.category,  # 고용형태 없으면 구분(신입/인턴) 표시
                "url": p.url,
                "dday": dday(p.deadline),
            }
        )

    # 정렬: 진행중 먼저 → 마감 임박순(dday 작은 순, None=상시는 뒤) → 마감은 최근 게시순
    def _key(it):
        open_first = 0 if it["status"] == "open" else 1
        dd = it["dday"]
        dd_key = dd if dd is not None else 10**6
        return (open_first, dd_key, it["posted_date"] or "")

    items.sort(key=_key)

    soon_days = cfg["dashboard"]["soon_days"]
    counts = {
        "total": len(items),
        "open": sum(1 for it in items if it["status"] == "open"),
        "closed": sum(1 for it in items if it["status"] == "closed"),
        "new": sum(1 for it in items if it["is_new"]),
        "soon": sum(
            1
            for it in items
            if it["status"] == "open" and it["dday"] is not None and 0 <= it["dday"] <= soon_days
        ),
        "by_firm": {f: sum(1 for it in items if it["firm"] == f) for f in _FIRM_ORDER},
    }

    _print_report(report, counts)
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "soon_days": soon_days,
        "counts": counts,
        "postings": items,
    }


def _print_report(report, counts) -> None:
    print(f"\n=== 채용 수집 ({_dt.datetime.now():%Y-%m-%d %H:%M:%S}) ===")
    for label, ok, count, err in report:
        print(f"  - {label}: {count}건" if ok else f"  - {label}: 실패 {err}")
    print(
        f"  필터통과 {counts['total']} (진행중 {counts['open']} / 마감 {counts['closed']} "
        f"/ 임박 {counts['soon']})"
    )


def _recent_cutoff(days: int) -> str:
    return (_dt.date.today() - _dt.timedelta(days=days)).isoformat()


def build_news(cfg: dict) -> dict:
    """회계·세무·딜 이슈 수집(Google News RSS) → news payload. 중복제거(URL)+최근 N일."""
    d = cfg["dashboard"]
    results = fetch_all(build_news_adapters(cfg))
    # 중복제거를 config의 카테고리 순서(좁은→넓은)대로 처리해 좁은 카테고리가 선점하게 함
    order = list(d["news_queries"].keys())
    results.sort(key=lambda r: order.index(r.label) if r.label in order else len(order))
    # 카테고리별 보존기간(저빈도·고관련은 더 길게) — 없으면 기본값
    default_days = d["news_recent_days"]
    by_cat = d.get("news_recent_days_by_category", {})
    cutoffs = {c: _recent_cutoff(by_cat.get(c, default_days)) for c in order}
    exclude = d.get("news_exclude", [])
    excl_src = d.get("news_exclude_sources", [])
    require = [k.lower() for k in d.get("news_require_any", [])]
    # 외국(미국 제외) 세무·감사 이슈 차단 — 외국명/외국매체 있고 한국/미국/국제 마커 없으면 제외
    foreign_cats = set(d.get("news_foreign_filter_categories", []))
    foreign_countries = [k.lower() for k in d.get("news_foreign_countries", [])]
    foreign_sources = [k.lower() for k in d.get("news_foreign_sources", [])]
    keep_markers = [k.lower() for k in d.get("news_keep_markers", [])]
    # 제목 기반 채용·시험 강제 보정 — RSS '감사' 쿼리가 가져온 기사라도 제목에 채용·수습 키워드 있으면 재분류
    hire_kw = [k.lower() for k in d.get("news_hire_title_keywords", [])]
    if hire_kw:
        for res in results:
            for n in res.postings:
                if n.category != "채용·시험" and any(k in n.title.lower() for k in hire_kw):
                    n.category = "채용·시험"
    seen, seen_title, items = set(), set(), []
    for res in results:
        for n in res.postings:
            tkey = " ".join(n.title.split()).lower()  # 같은 헤드라인이 매체만 달라 중복되는 것 제거
            if n.url in seen or tkey in seen_title:
                continue
            if any(s in (n.source_label or "") for s in excl_src):  # 정치색 매체 등 출처 제외
                continue
            if n.published and n.published < cutoffs.get(n.category, _recent_cutoff(default_days)):
                continue
            if any(x in n.title for x in exclude):  # 노이즈(시상·행사 등) 제외
                continue
            if require and not any(k in n.title.lower() for k in require):  # 도메인 무관 기사 제외
                continue
            if foreign_cats and n.category in foreign_cats:   # 외국(미국 제외) 세무·감사 이슈 차단
                tl = n.title.lower()
                sl = (n.source_label or "").lower()
                is_foreign = any(c in tl for c in foreign_countries) or any(s in sl for s in foreign_sources)
                if is_foreign and not any(m in tl for m in keep_markers):
                    continue
            seen.add(n.url)
            seen_title.add(tkey)
            items.append(n.to_dict())
    items.sort(key=lambda i: i.get("published") or "", reverse=True)
    # 의미 관련성 게이트(#1) + 카테고리 보정(#2) — VOYAGE 키 있을 때만(없으면 키워드/쿼리 분류 그대로).
    # 재배정 카테고리에 recency(cutoffs) 재적용 안 함 — over-drop 방지(의도). 표시·일자상한에만 반영.
    items = embeds.enrich(items, _title_sig, cfg)
    before = len(items)
    items = _dedup_near(items, d.get("news_neardup_jaccard", 0.6),
                        d.get("news_neardup_overlap", 0.67), d.get("news_neardup_min_tokens", 4))
    items = embeds.refine(items, _title_sig, cfg)  # 의미 군집 보조(VOYAGE 키 있을 때만, 의심 쌍에 한해)
    cap = d.get("news_max_per_day_per_cat", 0)
    if cap:                                  # 한 사건이 하루치 카테고리를 도배하지 않게 (카테고리,발행일)별 상한
        bucket: dict = {}
        capped = []
        for it in items:                     # 이미 최신순
            key = (it.get("category"), (it.get("published") or "")[:10])
            if bucket.get(key, 0) >= cap:
                continue
            bucket[key] = bucket.get(key, 0) + 1
            capped.append(it)
        items = capped
    print(f"  이슈: {len(items)}건 (원본 {before} → 근접중복·일자상한 적용, 소스 {sum(1 for r in results if r.ok)}/{len(results)})")
    return {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"), "items": items}


def _title_sig(title: str) -> frozenset:
    """제목 → 핵심 단어집합(말머리·끝의 '- 출처' 제거, 2자 이상 토큰). 근접중복 비교용."""
    t = title.lower()
    t = re.sub(r"\[[^\]]*\]", " ", t)        # [말머리] 제거
    t = re.sub(r"\s[-|][^-|]*$", "", t)       # 끝의 '- 출처' / '| 출처' 제거
    return frozenset(re.findall(r"[0-9a-z가-힣]{2,}", t))


def _same_issue(a: frozenset, b: frozenset, th: float, ov_th: float, min_tok: int) -> bool:
    """두 제목 단어집합이 같은 이슈인지. 1차=Jaccard≥th(매체만 다른 거의동일). 2차=포함도(겹침/작은쪽)≥ov_th
    **이면서** 공통토큰≥min_tok (같은 사건을 다른 표현으로 쓴 헤드라인 — 단, 공통토큰 하한으로 오병합 방지)."""
    if not (a and b):
        return False
    inter = len(a & b)
    if inter / len(a | b) >= th:
        return True
    return inter >= min_tok and inter / min(len(a), len(b)) >= ov_th


def _dedup_near(items: list[dict], th: float, ov_th: float = 0.67, min_tok: int = 4) -> list[dict]:
    """제목 단어집합으로 같은 이슈를 **군집화**(`_same_issue`). 입력이 최신순이라 **최신이 대표**로 남고,
    나머지(같은 주제의 이전 매체 기사)는 대표의 `dupes`에 첨부(제목·링크·출처·발행일) → 카드에서
    '동일 주제 기사 N개'로 펼쳐 보여준다. (버리지 않고 통합 — 도배는 줄이되 정보는 보존.)"""
    kept: list[dict] = []
    sigs: list[frozenset] = []
    for it in items:
        sig = _title_sig(it.get("title", ""))
        matched = -1
        if sig:
            for idx, s in enumerate(sigs):
                if _same_issue(sig, s, th, ov_th, min_tok):
                    matched = idx
                    break
        if matched >= 0:
            kept[matched].setdefault("dupes", []).append({
                "title": it.get("title"), "url": it.get("url"),
                "source_label": it.get("source_label"), "published": it.get("published"),
            })
        else:
            sigs.append(sig)
            kept.append(it)
    return kept


def build_insights(cfg: dict) -> dict:
    """Big4 간행물 링크 수집 → insights payload. 헤드리스 렌더라 순차 실행(발행처 순서 유지)."""
    seen, items, ok = set(), [], 0
    adapters = build_insight_adapters(cfg)
    for ad in adapters:
        res = safe_fetch(ad)  # 순차: Playwright sync는 스레드 비안전
        if res.ok:
            ok += 1
        for n in res.postings:
            if n.url in seen:
                continue
            seen.add(n.url)
            items.append(n.to_dict())
    # 트레이니 관련도 순 정렬(제목 내 키워드 수 ↓) — 동점은 발행처 순서 유지(stable)
    rel = [k.lower() for k in cfg["dashboard"].get("insight_relevance_keywords", [])]
    items.sort(key=lambda it: sum(1 for k in rel if k in it["title"].lower()), reverse=True)
    today_count = _mark_insight_new(items)  # 발행일이 없어 first_seen 추적으로 '금일 신규' 판정
    # 금일 신규(is_new)는 그날만큼은 최상단으로 부상 — 관련성 정렬에 묻혀 직관성 떨어지는 문제 해결.
    # stable sort라 신규/비신규 각 그룹 내부의 관련성 순서는 보존(마킹 이후에 재정렬해야 is_new를 안다).
    items.sort(key=lambda it: 0 if it.get("is_new") else 1)
    print(f"  인사이트: {len(items)}건 (발행처 {ok}/{len(adapters)}), 금일 {today_count}")
    return {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "today_count": today_count, "items": items}


_EN_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_RE_EN_MONTH = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(20\d{2})", re.I)
_RE_KO_YM = re.compile(r"(20\d{2})\s*년\s*(\d{1,2})\s*월")
_RE_NUM_YM = re.compile(r"\b(20\d{2})[.\-/](\d{1,2})\b")


def _other_month_only(title: str, cur_ym: tuple[int, int]) -> bool:
    """제목에 '연-월'이 명시돼 있고, 그중 **이번 달이 하나도 없으면** True(금일 후보에서 제외).

    최소 안전장치: 발행월을 알 수 있는 간행물(예: '2026.05', '2026년 5월호', 'May 2026')이 지난 달 것이면
    '금일'에 뜨지 않게 한다. 월 표기가 없으면 판단 보류(False) → 기존 first_seen 로직을 그대로 따른다.
    제목에 이번 달이 한 번이라도 언급되면(예: 본문에 과거 날짜가 섞여도) 최신으로 인정해 오탐을 줄인다.
    """
    t = title or ""
    found: list[tuple[int, int]] = []
    for m in _RE_EN_MONTH.finditer(t):
        mon = _EN_MONTHS.get(m.group(1).lower().rstrip("."))
        if mon:
            found.append((int(m.group(2)), mon))
    for rx in (_RE_KO_YM, _RE_NUM_YM):
        for m in rx.finditer(t):
            yr, mon = int(m.group(1)), int(m.group(2))
            if 1 <= mon <= 12:
                found.append((yr, mon))
    return bool(found) and cur_ym not in found


def _mark_insight_new(items: list[dict]) -> int:
    """각 인사이트에 is_new(오늘 최초 발견) 부여하고 금일 신규수 반환. insights_seen.json에 first_seen 영속.

    인사이트는 발행일이 없어 '최초 발견일'로 신규를 판정한다. **최초 1회(baseline)는 전량 is_new=False**
    (기존 목록을 '오늘 신규'로 오인 방지). 0건 수집 시 상태를 건드리지 않음(베이스라인 보호).
    """
    for it in items:
        it["is_new"] = False
    if not items:
        return 0
    seen_path = Path("insights_seen.json")
    baseline = not seen_path.exists()
    try:
        state = json.loads(seen_path.read_text(encoding="utf-8")) if not baseline else {}
    except Exception:  # noqa: BLE001
        state = {}
    _td = _dt.date.today()
    today = _td.isoformat()
    cur_ym = (_td.year, _td.month)
    # baseline(최초 1회)의 기존 목록은 '과거'(어제)로 백필 → 같은 날 다음 실행에서 전량 신규로 오인되지 않게.
    backfill = (_td - _dt.timedelta(days=1)).isoformat()
    cnt = 0
    for it in items:
        u = it["url"]
        if u not in state:
            state[u] = backfill if baseline else today
        # '금일' = 오늘 최초 발견. 단 제목에 발행월이 명시돼 있고 이번 달이 아니면 금일에서 제외(최소 안전장치).
        it["is_new"] = state[u] == today and not _other_month_only(it["title"], cur_ym)
        if it["is_new"]:
            cnt += 1
    # 현재 목록에 없는 항목도 first_seen을 **보존**한다. 법인별 상한(~12건) 경계에서 새 글이 올라오면
    # 오래된 글이 잠시 목록에서 밀려나는데, 이때 삭제해 버리면 그 글이 재정렬로 다시 올라올 때
    # first_seen=오늘로 재기록돼 **오래된 인사이트가 '금일'로 오인**된다(목록 깜빡임 → 거짓 신규).
    # → 현재 목록은 항상 보존하고, 무한증가는 상한 초과 시 '부재 + first_seen 오래된 것'부터만 정리.
    cur = {it["url"] for it in items}
    MAX_SEEN = 600
    if len(state) > MAX_SEEN:
        evictable = sorted((d, u) for u, d in state.items() if u not in cur)  # first_seen 오래된 순
        for _, u in evictable[: len(state) - MAX_SEEN]:
            del state[u]
    try:
        seen_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return cnt


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="대시보드 데이터 생성")
    ap.add_argument("--part", choices=["all", "jobs", "news", "insights"], default="all",
                    help="갱신할 스트림(워크플로별 분리 실행용)")
    part = ap.parse_args().part

    cfg = load_config()
    ran: dict[str, str] = {}  # 이번에 돈 스트림 → generated_at

    if part in ("all", "jobs"):
        state = State(cfg["runtime"]["state_path"])
        jobs = build_jobs(cfg, state)
        state.save()  # 마감일 캐시 갱신
        _write_guarded("jobs.json", jobs, "postings")
        ran["jobs"] = jobs.get("generated_at", "")
    if part in ("all", "news"):
        news = build_news(cfg)
        _write_guarded("news.json", news, "items")
        ran["news"] = news.get("generated_at", "")
    if part in ("all", "insights"):
        ins = build_insights(cfg)
        _write_guarded("insights.json", ins, "items")
        ran["insights"] = ins.get("generated_at", "")
    _update_status(ran)         # 변화 없어도 '점검 시각(last_run)' 항상 기록
    _update_sitemap_lastmod()   # 검색엔진 재크롤 신호: 사이트맵 lastmod를 오늘로
    print(f"  → docs/data/ ({part})")


def _update_status(ran: dict[str, str]) -> None:
    """docs/data/status.json에 last_run(점검 시각)과 스트림별 생성 시각을 머지 기록.

    수집 0건으로 데이터가 안 바뀌어도 자동화가 돌았다는 사실(last_run)은 항상 남긴다 → 헤더 시각 전진.
    부분 실행(--part)을 고려해 기존 값을 읽고 이번에 돈 스트림만 갱신.
    """
    path = _DATA_DIR / "status.json"
    now = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:  # noqa: BLE001
        cur = {}
    cur["last_run"] = now
    for k, v in ran.items():
        cur[k] = v or now
    try:
        path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _update_sitemap_lastmod() -> None:
    """docs/sitemap.xml의 lastmod를 오늘(KST) 날짜로 갱신(SEO 신선도 신호). 실패는 무시."""
    p = Path("docs/sitemap.xml")
    if not p.exists():
        return
    try:
        txt = p.read_text(encoding="utf-8")
        today = _dt.date.today().isoformat()
        if "<lastmod>" in txt:
            new = re.sub(r"<lastmod>.*?</lastmod>", f"<lastmod>{today}</lastmod>", txt)
        else:
            new = txt.replace("</loc>", f"</loc>\n    <lastmod>{today}</lastmod>", 1)
        if new != txt:
            p.write_text(new, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()

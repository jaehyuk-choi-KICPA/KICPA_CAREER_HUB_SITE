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
from src.classify import classify_emp_kind, classify_field, classify_firm, classify_qualification
from src.config import load_config
from src.filters import filter_postings
from src.record import Posting
from src.sources import build_adapters, fetch_all
from src.state import State
from src.util import dday, is_open, today_iso

_DATA_DIR = Path("docs/data")

# 정렬·요약용 법인 노출 순서(삼일 우선 — 타깃)
_FIRM_ORDER = ["삼일", "삼정", "안진", "한영", "로컬", "기타"]

_FIRM_ATS_SOURCES = {"samil", "samjong", "anjin", "hanyoung"}   # 빅4 자체 ATS(직접 지원 링크)


def _dedup_cross_source(postings: list, cfg: dict) -> list:
    """한공회 재게시 + 빅4 자체 ATS에 같은 공고가 중복되는 것 제거(예: 한공회 '[딜로이트 안진회계법인]
    2026 신입회계사 정기채용' = 안진 ATS '2026 신입회계사 정기채용'). (법인, 정규화제목) 동일하면 1건만.
    한공회 재게시 제목 앞 '[회사명]' 접두는 떼고 비교하고, **빅4 자체 ATS(직접 지원)**를 우선 보존."""
    def _norm(t: str) -> str:
        t = re.sub(r"^\s*\[[^\]]*\]\s*", "", t or "")       # 앞 [회사명] 접두 제거
        return re.sub(r"[\s\[\]()·,./-]", "", t).lower()      # 공백·구두점 제거 + 소문자

    out: list = []
    index: dict = {}        # (firm, norm_title) -> out 인덱스
    for p in postings:
        key = (classify_firm(p, cfg), _norm(p.title))
        if not key[1]:                       # 제목 비면 dedup 불가 → 그대로
            out.append(p)
            continue
        if key in index:
            ex = out[index[key]]
            # 빅4 자체 ATS가 한공회 재게시보다 우선(직접 지원 링크). 그 외엔 먼저 본 것 유지.
            if p.source in _FIRM_ATS_SOURCES and ex.source not in _FIRM_ATS_SOURCES:
                out[index[key]] = p
            continue
        index[key] = len(out)
        out.append(p)
    return out


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


def _load_manual_postings(cfg: dict) -> list[Posting]:
    """ATS 미수집 공고 수동 추가(삼일PwC 등 개별페이지형) — docs/data/manual_jobs.json을 Posting으로 변환.
    매 run 재주입(해당 소스 크롤 0건이라 carry_forward로 못 살림). native_id 고정이라 uid 안정 → 알림 1회.
    파일 없음/형식 이상은 빈 리스트(전체 실패 금지)."""
    path = cfg["dashboard"].get("manual_jobs_path", "docs/data/manual_jobs.json")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for d in data.get("postings", []):
        try:
            out.append(Posting(
                source=d.get("source", "manual"), source_label=d.get("source_label", ""),
                title=d.get("title", ""), company=d.get("company", ""),
                deadline=d.get("deadline", ""), posted_date=d.get("posted_date", ""),
                url=d.get("url", ""), category=d.get("category", ""),
                location=d.get("location", ""), emp_type=d.get("emp_type", ""),
                native_id=d.get("native_id", ""),
            ))
        except Exception:  # noqa: BLE001
            continue
    return out


def build_jobs(cfg: dict, state: State) -> dict:
    """채용 데이터 수집·분류 → jobs payload dict."""
    adapters = build_adapters(cfg, state)
    results = fetch_all(adapters)

    postings = []
    report = []
    for res in results:
        report.append((res.label, res.ok, res.count, res.error))
        postings.extend(res.postings)

    manual = _load_manual_postings(cfg)   # ATS 미수집 수동 공고(삼일 등) 합치기 — 분류·NEW·알림 동일 처리
    if manual:
        postings.extend(manual)
        print(f"  [수동] 큐레이션 공고 {len(manual)}건 추가")

    kept = filter_postings(postings, cfg)  # 경력 제외(수습/주니어 타깃)

    # 지속성(grace): KICPA가 살아있는 공고를 목록서 일시적으로 내려 깜빡이는 문제 대응.
    # 이번에 빠졌어도 마감 전·최근 목격분은 복원(상세는 살아있음). grace_days 넘으면 자동 탈락.
    present_uids = {p.uid for p in kept}
    state.update(kept)                      # 본 공고의 last_seen 갱신 + 신규 기록
    grace_days = cfg["dashboard"].get("jobs_grace_days", 2)
    # grace 복원분도 현재 필터를 통과해야 함 — 경력공고 등 '필터로 빠진' 건이 state에 남아
    # grace로 되살아나는 것 방지(목록서 일시 누락=복원 대상 / 필터 제외=복원 금지).
    carried = filter_postings(state.carry_forward(present_uids, grace_days), cfg)
    state.prune_expired()                   # 마감 지난 좀비 제거
    if carried:
        print(f"  [복원] 목록 일시 누락 {len(carried)}건 유지(grace {grace_days}일)")
    kept = kept + carried

    # 상세 보강 필드 hydrate: 캐시된 공고는 이번 fetch에서 상세 enrich를 스킵해 emp_type·location이
    # 비어 올 수 있다(deadline·body는 캐시 적용되지만 emp_type/location은 미캐시). state에 영속된
    # 값으로 채워 분류·표시를 정확히(예: 고용형태 Part Time → 파트타임). 빈 필드만 보강.
    for p in kept:
        st = state.entries.get(p.uid) or {}
        if not p.emp_type:
            p.emp_type = st.get("emp_type", "")
        if not p.location:
            p.location = st.get("location", "")
        if not p.body_excerpt:
            p.body_excerpt = st.get("body_excerpt", "")
        if not p.deadline:
            p.deadline = st.get("deadline", "")

    kept = _dedup_cross_source(kept, cfg)   # 한공회 재게시 + 빅4 자체 ATS 동일 공고 중복 제거

    # NEW = '올라온 지 24시간 이내'. 게시일은 날짜뿐이라 24h 정밀도가 안 나오므로 발견시각(first_seen) 기준.
    new_ts_cut = (_dt.datetime.now() - _dt.timedelta(hours=24)).isoformat(timespec="seconds")
    new_posted_max = cfg["dashboard"].get("new_posted_max_age_days", 2)
    items = []
    for p in kept:
        open_ = is_open(p.deadline)
        firm = classify_firm(p, cfg)
        first_seen = (state.entries.get(p.uid) or {}).get("first_seen", "")
        # '방금 올라온'=발견 24h 이내 AND 게시일이 오래되지 않음(게시일 모르면 게이트 미적용).
        # 19일 게시 공고를 22일에 처음 수집해도 NEW로 안 뜨게(발견시각만 보던 오표시 차단).
        try:
            _posted_age = (_dt.date.today() - _dt.date.fromisoformat(p.posted_date)).days
        except Exception:  # noqa: BLE001 — 게시일 없음/형식 이상 → 게이트 미적용(발견시각만으로 판정)
            _posted_age = None
        posted_ok = _posted_age is None or _posted_age <= new_posted_max
        items.append(
            {
                "source": p.source,
                "source_label": p.source_label,
                "firm": firm,
                "field": classify_field(p, cfg, firm),         # (레거시) 프론트 자격요건 전환 전까지 병행
                "qualification": classify_qualification(p, cfg),  # 수습CPA / 자격무관
                "emp_kind": classify_emp_kind(p, cfg),            # 인턴 / 계약직 / 파트타임 / 정규직
                "status": "open" if open_ else "closed",
                "is_new": bool(first_seen >= new_ts_cut and posted_ok),  # 발견 24h 이내 + 게시일 최근(오래된 공고 뒤늦은 수집 제외)
                "title": p.title,
                "company": p.company,
                "deadline": p.deadline,
                "posted_date": p.posted_date,
                "location": p.location,
                "emp_type": p.emp_type or p.category,  # 고용형태 없으면 구분(신입/인턴) 표시
                "url": p.url,
                "dday": dday(p.deadline),
                # 발견시각 — '새로 올라온 공고' 패널의 진짜 올라온 순 정렬용(게시일은 날짜뿐이라 같은 날 타이 해소)
                "first_seen": first_seen,
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
        "by_qualification": {q: sum(1 for it in items if it["qualification"] == q)
                             for q in ("수습CPA", "자격무관")},
        "by_emp_kind": {k: sum(1 for it in items if it["emp_kind"] == k)
                        for k in ("인턴", "정규직", "계약직", "파트타임")},
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
    gov_action = d.get("news_local_gov_action", [])      # 지자체 행정 홍보 제외용
    gov_keep = d.get("news_local_gov_keep", [])
    firm_pr_ent = d.get("news_firm_pr_entities", [])     # 법인 개업·개소 PR 제외용(법인어 + 개업/오픈류 AND)
    firm_pr_act = d.get("news_firm_pr_actions", [])
    deal_excl = d.get("news_deal_exclude", [])           # 딜·M&A 한정 부동산성 매각 노이즈 제외
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
            if gov_action and not any(k in n.title for k in gov_keep):  # 지자체 행정 홍보(○○시/군 + 세미나·유예 등) 제외
                toks = n.title.replace(",", " ").replace("…", " ").split()
                has_city = any(len(t) >= 3 and t.endswith(("시", "군")) for t in toks)
                if (has_city and any(a in n.title for a in gov_action)) or \
                   ("보조금" in n.title and ("역량" in n.title or "집행" in n.title)):
                    continue
            if firm_pr_ent and any(e in n.title for e in firm_pr_ent) \
                    and any(a in n.title for a in firm_pr_act):  # 법인 개업·개소 홍보(PR/동정) 제외
                continue
            if n.category == "딜·M&A" and deal_excl and any(x in n.title for x in deal_excl):  # 부동산·압류재산성 매각 노이즈
                continue
            if foreign_cats and n.category in foreign_cats:   # 외국(미국 제외) 세무·감사·딜 이슈 차단
                tl = n.title.lower()
                sl = (n.source_label or "").lower()
                # 외국 매체(번역 애그리게이터)는 keep 마커 무관 무조건 차단 — 외국 공시·주총 번역물은
                # 제목에 '미국' 등이 있어도 한국 독자 무관(예: Investing.com 'EG그룹 미국 IPO').
                if any(s in sl for s in foreign_sources):
                    continue
                # 제목 외국명은 keep 마커(한국·미국·국제 등)가 있으면 유지(한국기업 해외딜·미국 회계제도 등).
                if any(c in tl for c in foreign_countries) and not any(m in tl for m in keep_markers):
                    continue
            seen.add(n.url)
            seen_title.add(tkey)
            items.append(n.to_dict())
    # 시각 포함 published_at로 정렬(같은 날 기사도 진짜 최신순). 없으면 날짜로 폴백.
    items.sort(key=lambda i: i.get("published_at") or i.get("published") or "", reverse=True)
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
    """Big4 간행물 링크 수집 → insights payload. 헤드리스 순차(법인 순서 삼일→삼정→안진→한영 유지).

    v1.09: '금일/신규' 판정 제거. 법인별 스크랩 순서(≈사이트 최신순) 그대로 수집만(URL dedup, 법인당 cap은 어댑터).
    프론트가 source_label로 4박스 그룹핑 → 박스별 랜덤 추천 + 펼치기(최신순)로 노출.
    """
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
    print(f"  인사이트: {len(items)}건 (발행처 {ok}/{len(adapters)})")
    return {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"), "items": items}


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

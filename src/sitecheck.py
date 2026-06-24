"""라이브 사이트 종단(e2e) 검증 — 배포된 화면이 *의도대로* 보이는지 사용자 관점에서 확인.

3층 모니터의 3층:
  1) freshness.py — 자동화가 제때 돌았나(데이터 나이).
  2) canary.py    — 누락 없이 수집됐나(소스 양식/건수).
  3) **sitecheck(여기)** — 그래서 *사용자가 실제로 제대로 보나*. Pages 배포실패·CDN캐시·JS깨짐·캐시버전
     누락 등으로 '데이터는 커밋됐는데 화면은 깨진' 상태를 1·2층은 못 잡는다.

계층:
  - Tier1 결정론(무료): 라이브 URL을 브라우저로 열어 헤더 업데이트시각 최신·탭별 카드>0·데이터건수 대조·
    콘솔에러 검사.
  - Tier2 LLM 비전(키 있을 때만): 스크린샷을 Claude가 보고 레이아웃·깨짐·표시 점검(결정론과 교차).
실패 시 sitecheck_report.md + sitecheck_fail.flag → 워크플로가 GitHub 이슈로 알림(사람 검토, 자동수정 없음).

견고성: 모든 외부 호출 try/except. 판정 실패(브라우저 자체 오류)와 사이트 이상을 구분해 리포트.
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from src.config import load_config

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    recoverable: bool = False   # 실패가 '재실행으로 회복 가능'한 부류면 True(신선도·일시 로드오류)


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    shot: str | None = None

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


def _fetch_json(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------- Tier1 결정론

def run_deterministic(cfg: dict, base_url: str, shot_path: str | None) -> Result:
    res = Result()
    sc = cfg["sitecheck"]
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 — 미설치
        res.checks.append(Check("playwright", False, "Playwright 미설치 — 검증 불가"))
        return res

    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 1600})
            page.on("pageerror", lambda e: errors.append(str(e)[:160]))
            page.goto(base_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1800)

            # 헤더 '최근 서치' 존재·최신 (라벨 텍스트 무관 — _TS_RE로 시각만 추출)
            updated_txt = ""
            try:
                updated_txt = page.inner_text("#updated").strip()
            except Exception:  # noqa: BLE001
                pass
            res.checks.append(Check("헤더 표시", bool(updated_txt), updated_txt or "#updated 비어있음"))
            m = _TS_RE.search(updated_txt)
            if m:
                try:
                    ts = _dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
                    age = (_dt.datetime.now() - ts).total_seconds() / 60.0
                    ok = age <= sc["updated_max_minutes"]
                    res.checks.append(Check("업데이트 신선도", ok,
                                            f"{int(age)}분 전 (임계 {sc['updated_max_minutes']}분)",
                                            recoverable=True))   # 낡음 → 재스크랩으로 회복
                except Exception:  # noqa: BLE001
                    res.notes.append("업데이트 시각 파싱 실패")
            else:
                res.checks.append(Check("업데이트 시각 표기", False, "시각 형식 미발견"))

            # 탭별 카드 수 vs 라이브 데이터 건수 대조
            data = {
                "jobs": _fetch_json(base_url.rstrip("/") + "/data/jobs.json"),
                "news": _fetch_json(base_url.rstrip("/") + "/data/news.json"),
                "insights": _fetch_json(base_url.rstrip("/") + "/data/insights.json"),
            }
            # 탭/뷰별 카드 수 vs 라이브 데이터 건수 대조.
            # UI(v1.13): 기사·인사이트는 '기사/인사이트' 한 탭(data-tab=news) 안에서 책갈피(.subtab)로 전환.
            #   - 기사: 기사 탭 → #news-list .card
            #   - 인사이트: 기사 탭 → 인사이트 책갈피(.subtab[data-subview=insights]) → 법인별 4박스
            #     (#insights-grid 안 <article.insight-firm> > <ul.firm-list><li>. 접힌 <details>도 DOM엔 전체 글이
            #      있어 데이터 items 수와 직접 대조된다.)
            tabs = [("jobs", [], "#jobs-list .card", "postings"),
                    ("news", ['.tab-btn[data-tab="news"]'], "#news-list .card", "items"),
                    ("insights", ['.tab-btn[data-tab="news"]', '.subtab[data-subview="insights"]'],
                     "#insights-grid .firm-list li", "items")]
            for key, clicks, sel, dkey in tabs:
                nav_ok, last = True, ""
                for c in clicks:
                    last = c
                    try:
                        page.click(c)
                        page.wait_for_timeout(600)
                    except Exception:  # noqa: BLE001
                        nav_ok = False
                        break
                if not nav_ok:
                    res.checks.append(Check(f"{key} 보기 전환", False, f"클릭 실패: {last}"))
                    continue
                shown = page.locator(sel).count()
                d = data.get(key) or {}
                have = len(d.get(dkey) or [])
                # 데이터가 있는데 화면 0 = 렌더/배포 깨짐
                ok = not (have > 0 and shown == 0)
                res.checks.append(Check(f"{key} 카드 렌더", ok, f"화면 {shown} / 데이터 {have}"))

            # 파생 지표 타당성('오늘 신규'가 비현실적으로 큰가) — 렌더 검사가 못 잡는 의미 오류(예: 48/48)
            for chk in _plausibility_checks(cfg, data):
                res.checks.append(chk)

            # 스크린샷(LLM·증거용) — 채용 탭으로 복귀 후
            if shot_path:
                try:
                    page.click('.tab-btn[data-tab="jobs"]')
                    page.wait_for_timeout(500)
                    page.screenshot(path=shot_path, full_page=True)
                    res.shot = shot_path
                except Exception:  # noqa: BLE001
                    pass
            browser.close()
    except Exception as e:  # noqa: BLE001 — 사이트 도달 실패 등
        res.checks.append(Check("사이트 로드", False, f"{type(e).__name__}: {str(e)[:120]}"))
        return res

    res.checks.append(Check("콘솔 에러 없음", not errors, "; ".join(errors[:3]) if errors else "없음"))
    return res


# ----------------------------------------------------------------------------- Tier2 LLM 비전(선택)

def run_vision(cfg: dict, shot_path: str) -> Check | None:
    sc = cfg["sitecheck"]
    if not sc.get("use_llm"):
        return None
    try:
        from src.canary import _anthropic_client
        client = _anthropic_client()
    except Exception:  # noqa: BLE001
        client = None
    if not client or not Path(shot_path).exists():
        return None
    try:
        b64 = base64.standard_b64encode(Path(shot_path).read_bytes()).decode()
        prompt = (
            "이 이미지는 회계법인 채용/기사 모음 사이트(회법몬)의 채용 탭 스크린샷입니다. JSON으로만 답하세요: "
            '{"renders_ok": <카드 목록이 정상적으로 보이면 true, 빈 화면·깨짐·레이아웃 붕괴·겹침·오류면 false>, '
            '"updated_shown": <상단에 "최근 서치"(마지막 갱신) 시각이 보이면 true>, '
            '"note": "<이상점 한 줄, 정상이면 빈 문자열>"}'
        )
        msg = client.messages.create(
            model=sc.get("llm_model", "claude-opus-4-8"), max_tokens=300,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        mm = re.search(r"\{.*\}", text, re.DOTALL)
        if not mm:
            return None
        d = json.loads(mm.group(0))
        ok = bool(d.get("renders_ok")) and bool(d.get("updated_shown"))
        note = d.get("note", "") or ""
        return Check("LLM 비전", ok, note or ("정상" if ok else "이상 감지"))
    except Exception as e:  # noqa: BLE001
        return Check("LLM 비전", True, f"(점검 생략: {type(e).__name__})")  # 비전 오류는 실패로 치지 않음


# ----------------------------------------------------------------------------- 타당성/분류/제안

def _plausibility_checks(cfg: dict, data: dict) -> list[Check]:
    """파생 '오늘 신규' 수가 비현실적인지(렌더 검사가 못 보는 의미 오류). 전부 recoverable=False(코드 버그)."""
    sc = cfg["sitecheck"]
    ratio = sc.get("implausible_today_ratio", 0.8)
    min_total = sc.get("min_total_for_ratio", 8)

    def judge(label: str, today_n, total: int) -> Check | None:
        if today_n is None or total <= 0:
            return None
        if today_n < 0 or today_n > total:
            return Check(label, False, f"비정상 값 {today_n}/{total}", recoverable=False)
        if total >= min_total and (today_n >= total or today_n / total > ratio):
            return Check(label, False, f"비현실적 — 오늘 신규 {today_n}/{total}(전량/대부분)", recoverable=False)
        return Check(label, True, f"오늘 {today_n}/{total}", recoverable=False)

    out: list[Check] = []
    # (v1.09) 인사이트 '금일수' 타당성 체크 제거 — 금일/신규 개념 폐기. 뉴스·채용 금일수는 아래 유지.
    news = data.get("news") or {}
    nitems, nday = news.get("items") or [], (news.get("generated_at") or "")[:10]
    if nitems and nday:
        c = judge("기사 금일수 타당성", sum(1 for i in nitems if i.get("published") == nday), len(nitems))
        if c:
            out.append(c)
    jobs = data.get("jobs") or {}
    jitems, jday = jobs.get("postings") or [], (jobs.get("generated_at") or "")[:10]
    if jitems and jday:
        c = judge("채용 금일수 타당성", sum(1 for i in jitems if i.get("posted_date") == jday), len(jitems))
        if c:
            out.append(c)
    return out


def _classify_and_write(cfg: dict, res: Result) -> str:
    """실패를 분류해 result.json 기록. 반환: 'ok'|'recoverable'|'code'."""
    failed = res.failed
    if not failed:
        cls = "ok"
    elif all(c.recoverable for c in failed):
        cls = "recoverable"   # 재실행으로 회복 가능(신선도·일시)
    else:
        cls = "code"          # 코드/배포 버그 — 재실행 무의미, 사람 검토
    try:
        Path(cfg["sitecheck"]["result_path"]).write_text(
            json.dumps({"status": "pass" if cls == "ok" else "fail", "class": cls,
                        "failed": [c.name for c in failed]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return cls


def _suggest_fix(cfg: dict, report_text: str) -> str:
    """실패 리포트 + 관련 소스 일부를 LLM에 주고 수정 *방향*을 제안(사람 검토용). 키 없으면 빈 문자열."""
    try:
        from src.canary import _anthropic_client
        client = _anthropic_client()
    except Exception:  # noqa: BLE001
        client = None
    if not client:
        return ""
    try:
        srcs = []
        for f in ("src/export.py", "src/sitecheck.py", "docs/app.js"):
            try:
                srcs.append(f"[{f}]\n" + Path(f).read_text(encoding="utf-8")[:4500])
            except Exception:  # noqa: BLE001
                pass
        prompt = (
            "회법몬(정적 채용/기사 사이트) 종단 점검이 실패했습니다. 아래 [리포트]의 실패 항목 원인을 진단하고 "
            "어느 파일/함수를 어떻게 고치면 되는지 5줄 이내로 제안하세요. 사람이 검토할 *제안*이며 추정이면 밝히세요.\n\n"
            f"[리포트]\n{report_text}\n\n[관련 소스 일부]\n" + "\n\n".join(srcs)[:12000]
        )
        msg = client.messages.create(
            model=cfg["sitecheck"].get("llm_model", "claude-opus-4-8"), max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:  # noqa: BLE001
        return f"(제안 생성 실패: {type(e).__name__})"


# ----------------------------------------------------------------------------- 리포트/메인

def build_report(res: Result, url: str, llm_on: bool) -> str:
    bad = res.failed
    head = "🚨 종단 점검 실패" if bad else "✅ 라이브 정상"
    lines = [
        f"# 사이트 종단(e2e) 점검 — {head}",
        f"_{_dt.datetime.now():%Y-%m-%d %H:%M} KST · 대상 {url} · 비전(LLM): {'ON' if llm_on else 'OFF'}_",
        "",
        "| 점검 | 결과 | 상세 |",
        "|---|---|---|",
    ]
    for c in res.checks:
        detail = " ".join((c.detail or "").split()).replace("|", "/")  # 표 깨짐 방지(한 줄·파이프 제거)
        lines.append(f"| {c.name} | {'OK' if c.ok else '🚨 FAIL'} | {detail} |")
    if res.notes:
        lines += ["", "_참고: " + "; ".join(res.notes) + "_"]
    if res.shot:
        lines += ["", f"스크린샷: `{res.shot}` (워크플로 아티팩트 참조)"]
    if bad:
        lines += ["", "---",
                  "**자동 생성 알림(Human-in-the-loop).** 라이브 화면이 의도와 다릅니다. "
                  "데이터는 정상인데 화면이 깨졌다면 배포/CDN/JS·캐시버전(`?v=`)을 의심하세요. "
                  "스케줄 미동작은 freshness, 수집 누락은 canary를 함께 확인하세요. 자동 수정은 하지 않습니다."]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="라이브 사이트 종단 검증")
    ap.add_argument("--url", default=None, help="검증 대상 URL(기본: config sitecheck.site_url)")
    ap.add_argument("--no-llm", action="store_true", help="LLM 비전 생략(결정론만)")
    ap.add_argument("--suggest", action="store_true", help="실패 시 LLM 수정 제안을 리포트에 첨부(사람 검토용)")
    ap.add_argument("--explain", action="store_true",
                    help="재점검 없이 기존 리포트에 LLM 수정 제안만 덧붙임(워크플로 루프용)")
    args = ap.parse_args()

    cfg = load_config()
    sc = cfg["sitecheck"]
    url = args.url or sc["site_url"]
    shot = sc["screenshot_path"]

    if args.explain:   # 브라우저 재점검 없이 기존 리포트에 제안만 추가
        rp = Path(sc["report_path"])
        report = rp.read_text(encoding="utf-8") if rp.exists() else "(리포트 없음)"
        sug = _suggest_fix(cfg, report)
        if sug:
            report += "\n## LLM 수정 제안 (사람 검토용 — 확정 아님)\n\n> " + sug.replace("\n", "\n> ") + "\n"
            rp.write_text(report, encoding="utf-8")
        print("explain: 제안 첨부 완료" if sug else "explain: 제안 없음(키 없음/실패)")
        return

    res = run_deterministic(cfg, url, shot)
    llm_on = False
    if not args.no_llm and res.shot:
        vc = run_vision(cfg, res.shot)
        if vc is not None:
            res.checks.append(vc)
            llm_on = True

    cls = _classify_and_write(cfg, res)   # result.json (status·class·failed) — 루프 분기용
    report = build_report(res, url, llm_on)
    report += f"\n_분류: **{cls}**" + ("(재실행으로 회복 가능)" if cls == "recoverable"
                                       else "(코드/배포 — 사람 검토)" if cls == "code" else "") + "_\n"
    if args.suggest and res.failed:
        sug = _suggest_fix(cfg, report)
        if sug:
            report += "\n## LLM 수정 제안 (사람 검토용 — 확정 아님)\n\n> " + sug.replace("\n", "\n> ") + "\n"
    Path(sc["report_path"]).write_text(report, encoding="utf-8")

    fail = bool(res.failed)
    if fail:
        Path("sitecheck_fail.flag").write_text("1", encoding="utf-8")
    try:
        print(report)
    except UnicodeEncodeError:
        import sys
        sys.stdout.buffer.write(report.encode("utf-8", "replace"))
    print(f"\n-> {sc['report_path']} (fail={'YES' if fail else 'no'}, class={cls})")


if __name__ == "__main__":
    main()

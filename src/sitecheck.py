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

            # 헤더 '최근 업데이트' 존재·최신
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
                                            f"{int(age)}분 전 (임계 {sc['updated_max_minutes']}분)"))
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
            tabs = [("jobs", "#jobs-list .card", "postings"),
                    ("news", "#news-list .card", "items"),
                    ("insights", "#insights-list .card", "items")]
            for key, sel, dkey in tabs:
                if key != "jobs":
                    try:
                        page.click(f'.tab-btn[data-tab="{key}"]')
                        page.wait_for_timeout(700)
                    except Exception:  # noqa: BLE001
                        res.checks.append(Check(f"{key} 탭 전환", False, "탭 클릭 실패"))
                        continue
                shown = page.locator(sel).count()
                d = data.get(key) or {}
                have = len(d.get(dkey) or [])
                # 데이터가 있는데 화면 0 = 렌더/배포 깨짐
                ok = not (have > 0 and shown == 0)
                res.checks.append(Check(f"{key} 카드 렌더", ok, f"화면 {shown} / 데이터 {have}"))

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
            '"updated_shown": <상단에 "최근 업데이트" 시각이 보이면 true>, '
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
    args = ap.parse_args()

    cfg = load_config()
    sc = cfg["sitecheck"]
    url = args.url or sc["site_url"]
    shot = sc["screenshot_path"]

    res = run_deterministic(cfg, url, shot)
    llm_on = False
    if not args.no_llm and res.shot:
        vc = run_vision(cfg, res.shot)
        if vc is not None:
            res.checks.append(vc)
            llm_on = True

    report = build_report(res, url, llm_on)
    Path(sc["report_path"]).write_text(report, encoding="utf-8")
    fail = bool(res.failed)
    if fail:
        Path("sitecheck_fail.flag").write_text("1", encoding="utf-8")
    try:
        print(report)
    except UnicodeEncodeError:
        import sys
        sys.stdout.buffer.write(report.encode("utf-8", "replace"))
    print(f"\n-> {sc['report_path']} (fail={'YES' if fail else 'no'})")


if __name__ == "__main__":
    main()

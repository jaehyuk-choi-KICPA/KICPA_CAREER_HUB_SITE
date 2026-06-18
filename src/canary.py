"""자기검증 카나리아 — 하루 1회 소스 양식 변경/공고 누락 감지(감지·진단·알림 자동, 수정은 사람 게이트).

스크래퍼의 숙명적 약점: 소스가 HTML을 바꾸면 예외 없이 조용히 0건/누락이 난다. 이를 매일 감시한다.

계층(설계 원칙 "자기검증 카나리아" 참조):
  1) 구조 체크(무료·LLM 없음): 어제 대비 0건/급감/수집실패. canary_state.json에 카운트 영속.
  2) 시각 체크(하루 1회 LLM, 키 있을 때만): 목록 페이지 스냅샷 → Claude vision로 보이는 공고수·양식 정상여부
     판단 → 스크래퍼 카운트와 대조(누락·양식변경 감지). 키 없으면 자동 비활성(100% 오프라인).
  3) 드리프트 시: canary_report.md(진단 + LLM 수정 *제안*) 작성 + canary_drift.flag 생성 → 워크플로가
     Draft PR 자동 생성. 사람이 Claude Code로 검토·보완·머지(자동 머지·자동 프로덕션 커밋 금지).

보안: API 키는 env(`ANTHROPIC_API_KEY`)에서만. 전송 대상은 공개 채용 페이지 스냅샷·자체 어댑터 코드뿐.
견고성: 모든 외부호출 try/except — 카나리아 자신이 깨져도 전체 실패 금지.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.config import load_config
from src.render import render_html, render_screenshot
from src.sources import build_adapters, fetch_all
from src.state import State

# 소스 키 → 어댑터 소스 파일(수정 제안용 컨텍스트)
_ADAPTER_FILE = {
    "kicpa_susup": "src/adapters/kicpa.py",
    "kicpa_cpa": "src/adapters/kicpa.py",
    "samjong": "src/adapters/samjong.py",
    "anjin": "src/adapters/anjin.py",
    "hanyoung": "src/adapters/hanyoung.py",
    "samil": "src/adapters/samil.py",
}


@dataclass
class SourceCheck:
    key: str
    label: str
    count: int
    prev: int | None
    ok: bool                      # 수집 성공 여부
    error: str = ""
    alerts: list[str] = field(default_factory=list)   # 드리프트 사유(있으면 문제)
    llm_visible: int | None = None
    llm_note: str = ""
    suggestion: str = ""          # LLM 수정 제안(드리프트 시)

    @property
    def drift(self) -> bool:
        return bool(self.alerts)


# ----------------------------------------------------------------------------- 프로젝트 의도

def _project_context(cfg: dict) -> str:
    """이 사이트의 큐레이션 의도(=무엇을 의도적으로 거르고 남기는가)를 config에서 디제스트한다.

    카나리아 오탐의 근본 원인: 라이브 소스 페이지는 경력 공고까지 *전부* 보이지만, 스크래퍼는
    의도적으로 신입/수습만 남긴다. 이 컨텍스트를 LLM 프롬프트에 주입해 '원시 총계'가 아니라
    '신입/수습 관점의 의도된 출력'으로 판정하게 한다(코어 LLM-free 유지 — 여기선 점검용 컨텍스트일 뿐).
    config가 실행 가능한 권위 출처라 CLAUDE.md 산문 대신 cfg에서 디제스트한다.
    """
    f = cfg.get("filters", {})
    drop = list(dict.fromkeys(  # 순서 보존 dedup
        list(f.get("exclude_keywords", [])) + list(f.get("hard_exclude_keywords", []))))
    keep = list(f.get("exclude_exceptions", []))
    return (
        "[프로젝트 의도] 이 사이트(회법몬)는 **수습공인회계사·신입** 대상만 큐레이션합니다. "
        "경력직/시니어/팀장/N년이상 등 명백한 경력 전용 공고는 **의도적으로 제외**하고, "
        "신입/수습/경력무관/무관/인턴(또는 신입·경력 병기) 공고는 **유지**합니다.\n"
        f"- 제외(경력) 키워드: {', '.join(drop)}\n"
        f"- 유지(신입/예외) 키워드: {', '.join(keep)}\n"
        "따라서 라이브 소스 목록 페이지에는 경력 공고도 함께 보이지만 스크래퍼 수집수는 더 적은 게 **정상**입니다. "
        "누락 여부는 '신입/수습이 지원 가능한 공고' 기준으로만 판단하세요."
    )


# ----------------------------------------------------------------------------- LLM (선택)

def _anthropic_client():
    """키+SDK 있을 때만 클라이언트 반환. 없으면 None(오프라인=구조 체크만)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:  # noqa: BLE001 — SDK 미설치 등
        return None


def _vision_check(client, model: str, png_path: str, context: str) -> dict | None:
    """스냅샷을 보고 {entry_visible:int, looks_like_listing:bool, note:str} 반환.

    visible_postings(전부 세기)가 아니라 **신입/수습이 지원 가능한 공고만** 센다(context의 큐레이션 의도 반영).
    이래야 스크래퍼의 필터된 카운트와 사과-대-사과 비교가 되어 상시 거짓 '누락 의심'이 사라진다.
    """
    try:
        img = Path(png_path).read_bytes()
        b64 = base64.standard_b64encode(img).decode()
        prompt = (
            context + "\n\n"
            "이 이미지는 위 사이트가 수집하는 한 회계법인/채용 소스의 '채용공고 목록' 페이지 스크린샷입니다. "
            "다음을 JSON으로만 답하세요(설명 금지): "
            '{"entry_visible": <화면에 보이는 공고 중 **신입/수습이 지원 가능한** 항목 수(정수). '
            "순수 경력직/시니어/팀장/N년이상 공고는 세지 마세요>, "
            '"looks_like_listing": <정상적인 공고 목록 페이지면 true, 오류/점검/빈화면/양식붕괴면 false>, '
            '"note": "<이상점 한 줄, 정상이면 빈 문자열>"}'
        )
        msg = client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None


def _suggest_fix(client, model: str, key: str, html: str | None, context: str) -> str:
    """드리프트 난 소스의 어댑터 코드 + 현재 HTML 일부를 주고 수정 *제안*(텍스트)을 받는다.

    프로젝트 의도(context)를 함께 줘서, 원시 페이지 구조가 아니라 '의도된 큐레이션 출력' 기준으로 진단하게 한다.
    """
    try:
        src_path = _ADAPTER_FILE.get(key)
        adapter_src = Path(src_path).read_text(encoding="utf-8") if src_path else ""
        snippet = (html or "")[:6000]
        prompt = (
            f"채용 스크래퍼의 '{key}' 어댑터가 0건/누락을 내고 있습니다. 소스 사이트가 HTML 구조를 "
            "바꿨을 가능성이 큽니다. 아래 [프로젝트 의도]를 전제로 [어댑터 코드]와 [현재 페이지 HTML 일부]를 비교해, "
            "무엇이 깨졌는지 진단하고 **구체적 수정 방향(바뀐 셀렉터/엔드포인트 등)**을 5줄 이내로 제안하세요. "
            "이건 사람이 검토할 *제안*이며, 확실하지 않으면 추정임을 밝히세요.\n\n"
            f"{context}\n\n[어댑터 코드]\n{adapter_src}\n\n[현재 페이지 HTML 일부]\n{snippet}"
        )
        msg = client.messages.create(
            model=model, max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    except Exception as e:  # noqa: BLE001
        return f"(수정 제안 생성 실패: {type(e).__name__})"


# ----------------------------------------------------------------------------- 체크 본체

def run(cfg: dict) -> list[SourceCheck]:
    cc = cfg["canary"]
    # 1) 현재 수집(코어와 동일 경로 — 그러나 결과는 프로덕션에 안 씀)
    state = State(cfg["runtime"]["state_path"])
    results = fetch_all(build_adapters(cfg, state))

    cstate_path = Path(cc["state_path"])
    prev_counts: dict[str, int] = {}
    if cstate_path.exists():
        try:
            prev_counts = json.loads(cstate_path.read_text(encoding="utf-8")).get("counts", {})
        except Exception:  # noqa: BLE001
            prev_counts = {}

    client = _anthropic_client() if cc.get("use_llm") else None
    model = cc.get("llm_model", "claude-opus-4-8")
    urls = cc.get("source_urls", {})
    context = _project_context(cfg)   # LLM에 큐레이션 의도 주입 → '신입 관점' 판정(오탐 제거)

    checks: list[SourceCheck] = []
    for res in results:
        key = res.source
        prev = prev_counts.get(key)
        chk = SourceCheck(key=key, label=res.label, count=res.count, prev=prev,
                          ok=res.ok, error=res.error)

        # --- 구조 체크(무료) ---
        if not res.ok:
            chk.alerts.append(f"수집 실패: {res.error}")
        elif res.count == 0 and (prev or 0) > 0:
            chk.alerts.append(f"0건 수집 (어제 {prev}건) — 양식 변경 의심")
        elif prev is not None and prev >= cc["min_baseline"] \
                and res.count <= prev * (1 - cc["drop_ratio"]):
            chk.alerts.append(f"급감 {prev}→{res.count}건 (>{int(cc['drop_ratio']*100)}%↓)")

        # --- 시각 체크(LLM, 키 있을 때만) ---
        if client and key in urls:
            png = render_screenshot(urls[key], f"_canary_{key}.png")
            vis = _vision_check(client, model, png, context) if png else None
            if vis:
                chk.llm_visible = vis.get("entry_visible")
                chk.llm_note = vis.get("note", "") or ""
                if vis.get("looks_like_listing") is False:
                    chk.alerts.append(f"화면상 정상 목록 아님: {chk.llm_note or '양식 붕괴/오류 의심'}")
                elif (chk.llm_visible or 0) > 0 and res.ok:
                    thresh = max(res.count * cc["missing_ratio"], res.count + 3)
                    if chk.llm_visible >= thresh:
                        chk.alerts.append(
                            f"누락 의심: 화면 {chk.llm_visible}건 vs 수집 {res.count}건")

        # --- 드리프트 시 수정 제안 ---
        if chk.drift and client and key in urls:
            chk.suggestion = _suggest_fix(client, model, key, render_html(urls[key]), context)

        checks.append(chk)

    # --- 출력물 의도 점검(소스 수집과 별개, 결정론·LLM 불필요) ---
    for extra in (_check_insight_order(cfg), _check_filter_leakage(cfg)):
        if extra:
            checks.append(extra)

    # 오늘 카운트 저장(다음 비교 기준)
    try:
        cstate_path.write_text(json.dumps(
            {"updated": _dt.datetime.now().isoformat(timespec="seconds"),
             "counts": {c.key: c.count for c in checks}},
            ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    return checks


def _load_data(name: str) -> dict | None:
    """docs/data/<name>.json 안전 로드 — 없거나 깨지면 None(카나리아 자신은 절대 안 깨짐)."""
    try:
        p = Path("docs/data") / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _check_insight_order(cfg: dict) -> SourceCheck | None:
    """빅펌 인사이트가 '금일 신규 상단' 규칙을 지키는지 결정론 점검(LLM 불필요).

    관련성 정렬에 신규가 묻히면 직관성이 떨어진다 → 비신규 뒤에 신규(is_new)가 오면 위반.
    """
    data = _load_data("insights.json")
    if not data:
        return None
    items = data.get("items") or []
    chk = SourceCheck(key="insights_order", label="빅펌 인사이트 정렬",
                      count=len(items), prev=None, ok=True)
    seen_non_new = False
    buried = 0
    for it in items:
        if it.get("is_new"):
            if seen_non_new:
                buried += 1
        else:
            seen_non_new = True
    if buried:
        chk.alerts.append(f"신규 인사이트가 상단에 있지 않음(신규 {buried}건이 비신규 뒤에 위치)")
        chk.suggestion = ("export.py build_insights에서 _mark_insight_new 이후 "
                          "`items.sort(key=lambda it: 0 if it.get('is_new') else 1)` (stable) 추가 필요.")
    return chk


def _check_filter_leakage(cfg: dict) -> SourceCheck | None:
    """경력 전용 공고가 채용 목록에 새어들었는지 결정론 점검(LLM 불필요).

    제목에 hard_exclude_keywords가 있고 exclude_exceptions(신입/수습/경력무관/무관 등)가 하나도 없으면
    순수 경력 공고가 누출된 것. 이중타깃(신입 병기) 드롭은 jobs.json에 없어 직접 못 보므로 정보성만.
    """
    if not cfg.get("canary", {}).get("check_filter_leakage", True):
        return None
    data = _load_data("jobs.json")
    if not data:
        return None
    items = data.get("postings") or []   # jobs.json은 'postings' 키
    f = cfg.get("filters", {})
    hard = [k.lower() for k in f.get("hard_exclude_keywords", [])]
    exc = [k.lower() for k in f.get("exclude_exceptions", [])]
    leaked = []
    for it in items:
        title = (it.get("title") or "").lower()
        if any(h in title for h in hard) and not any(e in title for e in exc):
            leaked.append(it.get("title", ""))
    chk = SourceCheck(key="filter_leakage", label="필터 누출(경력 전용 공고)",
                      count=len(items), prev=None, ok=True)
    if leaked:
        sample = "; ".join(leaked[:3])
        chk.alerts.append(f"경력 전용 공고 {len(leaked)}건 누출 의심 — 예: {sample}")
        chk.suggestion = ("filters.passes의 hard-exclude 가드 점검 — 제목에 경력 키워드가 있고 신입/예외 "
                          "병기가 없는 공고가 통과되고 있음. 어댑터 카테고리 단계 누락 가능성도 확인.")
    return chk


def build_report(checks: list[SourceCheck], llm_on: bool) -> str:
    drift = [c for c in checks if c.drift]
    head = "🚨 드리프트 감지" if drift else "✅ 이상 없음"
    lines = [
        f"# 카나리아 자기검증 리포트 — {head}",
        f"_{_dt.datetime.now():%Y-%m-%d %H:%M} · 시각점검(LLM): {'ON' if llm_on else 'OFF(키 없음·구조체크만)'}_",
        "",
        "| 소스 | 수집 | 어제 | 화면-신입(LLM) | 상태 |",
        "|---|---:|---:|---:|---|",
    ]
    for c in checks:
        vis = "-" if c.llm_visible is None else str(c.llm_visible)
        status = "🚨 " + "; ".join(c.alerts) if c.drift else "OK"
        lines.append(f"| {c.label} | {c.count} | {c.prev if c.prev is not None else '-'} | {vis} | {status} |")
    if drift:
        lines += ["", "## 수정 제안 (사람 검토용 — 확정 아님)"]
        for c in drift:
            lines += [f"\n### {c.label} (`{c.key}`)",
                      f"- 사유: {'; '.join(c.alerts)}"]
            if c.llm_note:
                lines.append(f"- 화면 메모: {c.llm_note}")
            if c.suggestion:
                lines += ["- LLM 제안:", "", "> " + c.suggestion.replace("\n", "\n> ")]
        lines += ["", "---",
                  "**이 PR은 자동 생성된 *진단/제안*입니다.** 코드 수정은 Claude Code로 직접 검토·보완 후 머지하세요 "
                  "(자동 머지 금지 — Human-in-the-loop)."]
    return "\n".join(lines) + "\n"


def main() -> None:
    cfg = load_config()
    cc = cfg["canary"]
    checks = run(cfg)
    llm_on = bool(cc.get("use_llm") and os.environ.get("ANTHROPIC_API_KEY"))
    report = build_report(checks, llm_on)
    Path(cc["report_path"]).write_text(report, encoding="utf-8")
    print(report)
    drift = any(c.drift for c in checks)
    if drift:
        Path("canary_drift.flag").write_text("1", encoding="utf-8")
    print(f"\n→ {cc['report_path']} (drift={'YES' if drift else 'no'})")


if __name__ == "__main__":
    main()

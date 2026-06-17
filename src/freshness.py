"""신선도(누락) 모니터 — 스케줄러 드롭으로 데이터가 낡았는지 주기 감지·보고.

카나리아(`src/canary.py`)는 *소스 HTML 양식 변경/공고 누락*을 본다. 이 모듈은 결이 다르다:
**GitHub Actions 스케줄러가 실행을 빼먹어(지연·드롭) 데이터가 낡았는지**(신선도)를 본다.
예: 채용은 30분마다 갱신돼야 하는데 `jobs.json`의 generated_at이 2시간 전이면 → 실행 누락.

동작:
  1) `docs/data/*.json`의 generated_at 나이를 기대 간격(config)과 대조 → STALE 판정(가벼움·오프라인).
  2) STALE이면 `freshness_drift.flag` 기록 → 워크플로가 라이브 사이트 스크린샷(--shot) + Draft PR 생성.
  3) 리포트(`freshness_report.md`)에 신선도 표 + (드리프트 시) 사이트 스크린샷 인라인 임베드.

견고성: 모든 외부/파싱 호출 try/except — 모니터 자신이 깨져도 전체 실패 금지.
주의: 모니터 자신도 스케줄 드롭될 수 있으나 STALE은 *데이터 나이*로 계산하므로 다음 실행이 따라잡는다.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path

from src.config import load_config
from src.render import render_screenshot


@dataclass
class StreamCheck:
    file: str
    label: str
    expected_min: int
    threshold_min: int
    generated_at: str | None     # 파싱된 stamp(문자열) 또는 None(없음/파싱 실패)
    age_min: float | None        # 나이(분) 또는 None
    note: str = ""

    @property
    def stale(self) -> bool:
        if self.age_min is None:       # 파일 없음/파싱 실패 = 문제
            return True
        return self.age_min > self.threshold_min


def _safe_print(s: str) -> None:
    """Windows 콘솔(cp949)에서도 안 죽게 출력(로그용). 파일 기록은 항상 utf-8."""
    try:
        print(s)
    except UnicodeEncodeError:
        import sys
        sys.stdout.buffer.write(s.encode("utf-8", "replace") + b"\n")


def _fmt_age(minutes: float | None) -> str:
    if minutes is None:
        return "-"
    m = int(round(minutes))
    if m < 60:
        return f"{m}분"
    return f"{m // 60}시간 {m % 60}분"


def evaluate(cfg: dict) -> list[StreamCheck]:
    fc = cfg["freshness"]
    data_dir = Path(fc["data_dir"])
    now = _dt.datetime.now()
    mult, grace = fc["stale_multiplier"], fc["grace_minutes"]

    checks: list[StreamCheck] = []
    for fname, meta in fc["streams"].items():
        exp = int(meta["expected_minutes"])
        thresh = exp * mult + grace
        path = data_dir / fname
        stamp, age, note = None, None, ""
        if not path.exists():
            note = "파일 없음"
        else:
            try:
                gen = json.loads(path.read_text(encoding="utf-8")).get("generated_at")
                if gen:
                    stamp = gen
                    age = (now - _dt.datetime.fromisoformat(gen)).total_seconds() / 60.0
                else:
                    note = "generated_at 없음"
            except Exception as e:  # noqa: BLE001
                note = f"파싱 실패: {type(e).__name__}"
        chk = StreamCheck(file=fname, label=meta["label"], expected_min=exp,
                          threshold_min=thresh, generated_at=stamp, age_min=age, note=note)
        if chk.stale and not note:
            chk.note = f"기대 {_fmt_age(exp)} 간격 / 임계 {_fmt_age(thresh)} 초과 — 스케줄 실행 누락 의심"
        checks.append(chk)
    return checks


def _source_counts(cfg: dict) -> dict[str, int]:
    """카나리아 baseline에서 소스별 최신 수집 건수(있으면)."""
    try:
        p = Path(cfg["canary"]["state_path"])
        return json.loads(p.read_text(encoding="utf-8")).get("counts", {}) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def build_report(cfg: dict, checks: list[StreamCheck], shot: str | None = None) -> str:
    stale = [c for c in checks if c.stale]
    head = "🚨 신선도 이상(누락 의심)" if stale else "✅ 모든 스트림 신선"
    lines = [
        f"# 신선도 모니터 리포트 — {head}",
        f"_{_dt.datetime.now():%Y-%m-%d %H:%M} KST · 데이터 나이 vs 기대 갱신 간격_",
        "",
        "| 스트림 | 최근 갱신(generated_at) | 나이 | 기대 간격 | 임계 | 상태 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for c in checks:
        status = "🚨 STALE" if c.stale else "OK"
        note = f" — {c.note}" if (c.stale and c.note) else ""
        lines.append(
            f"| {c.label} | {c.generated_at or '-'} | {_fmt_age(c.age_min)} | "
            f"{_fmt_age(c.expected_min)} | {_fmt_age(c.threshold_min)} | {status}{note} |"
        )

    counts = _source_counts(cfg)
    if counts:
        lines += ["", "**소스별 최근 수집 건수**(카나리아 baseline): "
                  + ", ".join(f"{k} {v}" for k, v in counts.items())]

    if shot and Path(shot).exists():
        lines += ["", "## 라이브 사이트 스냅샷 (시각 증거)", "", f"![freshness]({shot})"]

    if stale:
        lines += [
            "", "---",
            "**자동 생성 알림입니다(Human-in-the-loop).** 데이터가 기대 간격보다 오래 낡았습니다 — ",
            "원인은 대개 **GitHub Actions 스케줄 지연·드롭**입니다. 잦으면 cron 빈도를 더 올리거나 ",
            "외부 핑거(`repository_dispatch`)를 고려하세요. 소스 자체 누락은 카나리아를 확인하세요.",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="신선도(누락) 모니터")
    ap.add_argument("--shot", action="store_true",
                    help="라이브 사이트 스크린샷을 찍어 리포트에 임베드(드리프트 시 워크플로가 호출)")
    args = ap.parse_args()

    cfg = load_config()
    fc = cfg["freshness"]
    checks = evaluate(cfg)
    stale = any(c.stale for c in checks)

    shot = None
    if args.shot:
        shot = render_screenshot(fc["site_url"], fc["screenshot_path"])  # 실패 시 None

    report = build_report(cfg, checks, shot=shot)
    Path(fc["report_path"]).write_text(report, encoding="utf-8")
    if stale:
        Path("freshness_drift.flag").write_text("1", encoding="utf-8")   # print 전에 기록(로직 보장)
    _safe_print(report)
    _safe_print(f"\n-> {fc['report_path']} (stale={'YES' if stale else 'no'})")


if __name__ == "__main__":
    main()

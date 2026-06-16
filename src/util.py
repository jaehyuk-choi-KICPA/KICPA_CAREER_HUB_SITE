"""작은 공통 유틸 — 날짜 정규화 등."""

from __future__ import annotations

import datetime as _dt
import re

_DATE_RE = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")


def to_iso_date(text: str) -> str:
    """문자열에서 첫 날짜를 찾아 yyyy-mm-dd로. 없으면 빈 문자열."""
    if not text:
        return ""
    m = _DATE_RE.search(text)
    if not m:
        return ""
    y, mo, d = (int(g) for g in m.groups())
    try:
        return _dt.date(y, mo, d).isoformat()
    except ValueError:
        return ""


def all_iso_dates(text: str) -> list[str]:
    """문자열의 모든 날짜를 yyyy-mm-dd 리스트로(등장 순서)."""
    out = []
    for m in _DATE_RE.finditer(text or ""):
        y, mo, d = (int(g) for g in m.groups())
        try:
            out.append(_dt.date(y, mo, d).isoformat())
        except ValueError:
            continue
    return out


def today_iso() -> str:
    return _dt.date.today().isoformat()


def is_open(deadline_iso: str, *, today: str | None = None) -> bool:
    """마감일이 오늘 이후(포함)면 게시중. 날짜 파싱 불가('')면 보수적으로 게시중 취급."""
    if not deadline_iso:
        return True
    return deadline_iso >= (today or today_iso())


def dday(deadline_iso: str, *, today: str | None = None) -> int | None:
    """마감까지 남은 일수. 오늘=0, 지났으면 음수. 날짜 없으면 None(상시)."""
    if not deadline_iso:
        return None
    try:
        d = _dt.date.fromisoformat(deadline_iso)
        t = _dt.date.fromisoformat(today) if today else _dt.date.today()
    except ValueError:
        return None
    return (d - t).days

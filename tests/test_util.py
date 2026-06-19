"""util.py — 날짜 파싱·D-day·게시중 판정(파이프라인 전반이 의존하는 순수 로직)."""
from __future__ import annotations

import datetime as _dt

from src.util import all_iso_dates, dday, is_open, to_iso_date, today_iso

TODAY = _dt.date.today().isoformat()
TOMORROW = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
YESTERDAY = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()


class TestIsOpen:
    def test_future_deadline_open(self):
        assert is_open(TOMORROW) is True

    def test_today_is_open(self):
        assert is_open(TODAY) is True   # 마감일 당일은 게시중

    def test_past_deadline_closed(self):
        assert is_open(YESTERDAY) is False

    def test_empty_deadline_treated_open(self):
        # 날짜 파싱 불가('')는 보수적으로 게시중(상시채용 등 유실 방지)
        assert is_open("") is True

    def test_explicit_today_arg(self):
        assert is_open("2026-01-10", today="2026-01-10") is True
        assert is_open("2026-01-09", today="2026-01-10") is False


class TestDday:
    def test_future_positive(self):
        assert dday("2026-01-13", today="2026-01-10") == 3

    def test_today_zero(self):
        assert dday("2026-01-10", today="2026-01-10") == 0

    def test_past_negative(self):
        assert dday("2026-01-08", today="2026-01-10") == -2

    def test_empty_none(self):
        assert dday("") is None         # 상시채용

    def test_invalid_none(self):
        assert dday("상시채용", today="2026-01-10") is None


class TestToIsoDate:
    def test_dash(self):
        assert to_iso_date("2026-06-19") == "2026-06-19"

    def test_korean(self):
        assert to_iso_date("2026년 6월 9일 마감") == "2026-06-09"

    def test_dotted(self):
        assert to_iso_date("등록 2026.6.9") == "2026-06-09"

    def test_no_date(self):
        assert to_iso_date("상시채용") == ""

    def test_invalid_calendar(self):
        assert to_iso_date("2026-13-40") == ""   # 존재하지 않는 날짜는 빈 문자열


class TestAllIsoDates:
    def test_multiple_in_order(self):
        out = all_iso_dates("게시 2026-06-01 ~ 마감 2026-06-30")
        assert out == ["2026-06-01", "2026-06-30"]

    def test_none(self):
        assert all_iso_dates("날짜 없음") == []


def test_today_iso_format():
    s = today_iso()
    assert _dt.date.fromisoformat(s)   # 파싱되면 형식 정상
    assert len(s) == 10

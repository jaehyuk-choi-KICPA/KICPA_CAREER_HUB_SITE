"""state.py — 신규감지·notified 추적·grace(깜빡임 복원)·만료정리(영속 상태기계)."""
from __future__ import annotations

import datetime as _dt

from src.state import State

from tests.conftest import make_posting

TOMORROW = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
NEXT_WEEK = (_dt.date.today() + _dt.timedelta(days=7)).isoformat()
YESTERDAY = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()


def _state(tmp_path):
    return State(str(tmp_path / "state.json"))


def test_update_returns_new_and_persists(tmp_path):
    st = _state(tmp_path)
    p1 = make_posting(source="samil", source_label="삼일PwC", native_id="A1", title="A", deadline=TOMORROW)
    p2 = make_posting(source="samjong", source_label="삼정KPMG", native_id="B2", title="B", deadline=TOMORROW)
    new = st.update([p1, p2])
    assert {p.uid for p in new} == {"samil:A1", "samjong:B2"}
    assert st.entries["samil:A1"]["notified"] is False
    assert "first_seen" in st.entries["samil:A1"]


def test_second_update_no_new_and_updates_fields(tmp_path):
    st = _state(tmp_path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=TOMORROW)])
    # 같은 uid, 마감일만 바뀜 → 신규 아님, 필드 갱신
    new2 = st.update([make_posting(source="samil", native_id="A1", title="A", deadline=NEXT_WEEK)])
    assert new2 == []
    assert st.entries["samil:A1"]["deadline"] == NEXT_WEEK


def test_republish_resets_first_seen(tmp_path):
    # 재게시(posted_date가 더 최신) → first_seen now로 갱신(최신순 1순위·NEW 복귀)
    st = _state(tmp_path)
    st.update([make_posting(source="kicpa_susup", native_id="A1", title="A",
                            posted_date="2026-06-17", deadline=TOMORROW)])
    st.entries["kicpa_susup:A1"]["first_seen"] = "2026-06-17T20:17:10"   # 원래 처음 본 시각
    st.update([make_posting(source="kicpa_susup", native_id="A1", title="A(수정)",
                            posted_date=_dt.date.today().isoformat(), deadline=TOMORROW)])
    assert st.entries["kicpa_susup:A1"]["first_seen"].startswith(_dt.date.today().isoformat())


def test_flicker_keeps_first_seen(tmp_path):
    # 단순 깜빡임(posted_date 동일) → first_seen 유지(좀비/거짓 NEW 방지)
    st = _state(tmp_path)
    st.update([make_posting(source="kicpa_susup", native_id="A1", title="A",
                            posted_date="2026-06-17", deadline=TOMORROW)])
    st.entries["kicpa_susup:A1"]["first_seen"] = "2026-06-17T20:17:10"
    st.update([make_posting(source="kicpa_susup", native_id="A1", title="A",
                            posted_date="2026-06-17", deadline=NEXT_WEEK)])
    assert st.entries["kicpa_susup:A1"]["first_seen"] == "2026-06-17T20:17:10"


def test_mark_notified(tmp_path):
    st = _state(tmp_path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=TOMORROW)])
    st.mark_notified(["samil:A1"], posted_date="2026-06-19")
    assert st.entries["samil:A1"]["notified"] is True
    assert st.entries["samil:A1"]["notified_date"] == "2026-06-19"


def test_carry_forward_restores_open_recent(tmp_path):
    # 살아있는 공고가 이번 스크랩에서 일시 누락(KICPA 깜빡임) → grace 내면 복원
    st = _state(tmp_path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=TOMORROW)])
    restored = st.carry_forward(present_uids=set(), grace_days=2)
    assert [p.uid for p in restored] == ["samil:A1"]


def test_carry_forward_skips_expired(tmp_path):
    st = _state(tmp_path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=YESTERDAY)])
    assert st.carry_forward(present_uids=set(), grace_days=2) == []   # 마감분은 복원 안 함


def test_carry_forward_skips_beyond_grace(tmp_path):
    st = _state(tmp_path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=TOMORROW)])
    # 마지막 목격이 grace보다 오래 전이면 좀비 방지 위해 복원 중단
    st.entries["samil:A1"]["last_seen"] = (_dt.date.today() - _dt.timedelta(days=5)).isoformat()
    assert st.carry_forward(present_uids=set(), grace_days=2) == []


def test_carry_forward_skips_present(tmp_path):
    st = _state(tmp_path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=TOMORROW)])
    # 이번 스크랩에 있으면 복원 대상 아님
    assert st.carry_forward(present_uids={"samil:A1"}, grace_days=2) == []


def test_prune_expired(tmp_path):
    st = _state(tmp_path)
    st.update([
        make_posting(source="samil", native_id="A1", title="open", deadline=TOMORROW),
        make_posting(source="samil", native_id="B2", title="dead", deadline=YESTERDAY),
    ])
    removed = st.prune_expired()
    assert removed == 1
    assert "samil:A1" in st.entries
    assert "samil:B2" not in st.entries


def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    st = State(path)
    st.update([make_posting(source="samil", native_id="A1", title="A", deadline=TOMORROW)])
    st.save()
    st2 = State(path)   # 새 인스턴스로 다시 로드
    assert "samil:A1" in st2.entries

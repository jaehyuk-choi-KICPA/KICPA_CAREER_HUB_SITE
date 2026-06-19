"""record.py — 공통 레코드 정규화·식별자(중복제거·추적의 기반)."""
from __future__ import annotations

from src.record import Posting


def test_whitespace_normalized():
    p = Posting(source="samil", source_label="삼일PwC", title="  감사   스태프  채용 ")
    assert p.title == "감사 스태프 채용"


def test_native_id_from_url_hash_when_missing():
    p = Posting(source="samil", source_label="x", title="t", url="https://example.com/a")
    assert p.native_id and len(p.native_id) == 16   # url sha256 앞 16자


def test_same_url_same_native_id():
    a = Posting(source="samil", source_label="x", title="t1", url="https://e.com/x")
    b = Posting(source="samil", source_label="x", title="t2", url="https://e.com/x")
    assert a.native_id == b.native_id   # 같은 url = 같은 식별자


def test_explicit_native_id_preserved():
    p = Posting(source="kicpa_cpa", source_label="x", title="t", native_id="ij123")
    assert p.native_id == "ij123"
    assert p.uid == "kicpa_cpa:ij123"


def test_to_dict_includes_uid():
    p = Posting(source="samil", source_label="x", title="t", native_id="z9")
    d = p.to_dict()
    assert d["uid"] == "samil:z9"
    assert d["title"] == "t"

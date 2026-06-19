"""formatter.py — 게시 메시지(개별·다이제스트) 생성. dict 입력으로 소스 무관 동작."""
from __future__ import annotations

from src.formatter import _deadline_text, build_digest, format_item


def test_deadline_text_default():
    assert _deadline_text({}) == "상시채용"
    assert _deadline_text({"deadline": "2026-06-30"}) == "2026-06-30"


def test_format_item_contains_fields(cfg):
    d = {"source_label": "삼일PwC", "title": "감사 채용", "company": "삼일회계법인",
         "deadline": "2026-06-30", "url": "https://x/1"}
    s = format_item(d, cfg)
    for token in ("감사 채용", "삼일회계법인", "2026-06-30", "https://x/1"):
        assert token in s


def test_format_item_empty_deadline_is_standing(cfg):
    s = format_item({"title": "t", "url": "u"}, cfg)
    assert "상시채용" in s


def test_build_digest_empty(cfg):
    out = build_digest([], cfg, date="2026-06-19")
    assert len(out) == 1
    assert "없습니다" in out[0]


def test_build_digest_lists_entries(cfg):
    entries = [
        {"source_label": "삼일PwC", "title": "A 채용", "deadline": "2026-06-30", "url": "u1", "source": "samil"},
        {"source_label": "구인(수습CPA)", "title": "B 채용", "deadline": "2026-07-01", "url": "u2", "source": "kicpa_susup"},
    ]
    out = build_digest(entries, cfg, date="2026-06-19")
    joined = "\n".join(out)
    assert "2건" in joined          # 헤더 카운트
    assert "A 채용" in joined and "B 채용" in joined


def test_build_digest_sort_order(cfg):
    # KICPA(수습) 가 Big4보다 앞 순서(_SOURCE_ORDER)
    entries = [
        {"source_label": "삼일PwC", "title": "BIG4", "deadline": "2026-06-30", "url": "u1", "source": "samil"},
        {"source_label": "구인(수습CPA)", "title": "KICPA", "deadline": "2026-06-30", "url": "u2", "source": "kicpa_susup"},
    ]
    out = build_digest(entries, cfg, date="2026-06-19")
    joined = "\n".join(out)
    assert joined.index("KICPA") < joined.index("BIG4")

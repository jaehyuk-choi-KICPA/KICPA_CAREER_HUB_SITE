"""export.py — 뉴스 근접중복 군집(매체만 다른 같은 사건을 대표 1건 + dupes로 통합)."""
from __future__ import annotations

import datetime as _dt

from src.export import _dedup_cross_source, _dedup_near, _recent_cutoff, _same_issue, _title_sig

from tests.conftest import make_posting


class TestDedupCrossSource:
    def test_kicpa_repost_vs_firm_ats(self, cfg):
        # 한공회 재게시('[회사명] 제목') + 빅4 ATS(같은 제목) = 1건, 빅4 ATS(직접 지원) 보존
        kicpa = make_posting(source="kicpa_susup", company="딜로이트 안진회계법인",
                             title="[딜로이트 안진회계법인] 2026 신입회계사 정기채용")
        ats = make_posting(source="anjin", company="딜로이트 안진",
                           title="2026 신입회계사 정기채용")
        for order in ([kicpa, ats], [ats, kicpa]):
            out = _dedup_cross_source(order, cfg)
            assert len(out) == 1
            assert out[0].source == "anjin"

    def test_distinct_titles_kept(self, cfg):
        a = make_posting(source="anjin", title="2026 신입회계사 정기채용")
        b = make_posting(source="anjin", title="2026 경력 컨설턴트 채용")
        assert len(_dedup_cross_source([a, b], cfg)) == 2


class TestTitleSig:
    def test_strips_bracket_and_source_tail(self):
        # [말머리] 제거 + 끝의 '- 출처' 제거 후 2자 이상 토큰만
        assert _title_sig("[속보] 금융감독원 감리 강화 - 한국경제") == frozenset({"금융감독원", "감리", "강화"})

    def test_drops_single_char_tokens(self):
        sig = _title_sig("가 나 다라마")   # 1자 토큰은 버림
        assert "다라마" in sig
        assert "가" not in sig


class TestSameIssue:
    def test_identical_sets_same(self):
        a = frozenset({"x", "y", "z"})
        assert _same_issue(a, a, 0.6, 0.67, 2) is True

    def test_disjoint_not_same(self):
        assert _same_issue(frozenset({"a", "b"}), frozenset({"c", "d"}), 0.6, 0.67, 2) is False

    def test_overlap_branch(self):
        # Jaccard는 낮지만(0.5<0.6) 포함도 높고 공통토큰≥min_tok → 같은 사건
        a = frozenset({"t1", "t2", "t3", "t4", "x", "y", "z"})
        b = frozenset({"t1", "t2", "t3", "t4", "q"})
        assert _same_issue(a, b, 0.6, 0.67, 4) is True

    def test_overlap_blocked_by_min_tokens(self):
        # 공통토큰이 하한 미만이면 오병합 방지
        a = frozenset({"t1", "t2", "x", "y"})
        b = frozenset({"t1", "t2", "q"})
        assert _same_issue(a, b, 0.6, 0.67, 4) is False

    def test_empty_not_same(self):
        assert _same_issue(frozenset(), frozenset({"a"}), 0.6, 0.67, 2) is False


class TestDedupNear:
    def test_clusters_near_dups_keeps_newest_as_rep(self):
        items = [
            {"title": "금융감독원 상장사 감리 30% 확대 예고", "url": "u1", "source_label": "한경", "published": "2026-06-19"},
            {"title": "금융감독원 상장사 감리 30% 확대 - 연합뉴스", "url": "u2", "source_label": "연합", "published": "2026-06-18"},
            {"title": "국세청 세무조사 방향 발표", "url": "u3", "source_label": "세계", "published": "2026-06-18"},
        ]
        out = _dedup_near(items, 0.6)
        assert len(out) == 2                       # 근접중복 1쌍 통합 + 별개 1건
        rep = next(i for i in out if i["url"] == "u1")   # 최신이 대표
        assert len(rep.get("dupes", [])) == 1
        assert rep["dupes"][0]["url"] == "u2"

    def test_distinct_titles_not_merged(self):
        items = [
            {"title": "삼일PwC 딜 자문 수임", "url": "a"},
            {"title": "국세청 세법 개정안 발표", "url": "b"},
        ]
        out = _dedup_near(items, 0.6)
        assert len(out) == 2
        assert all("dupes" not in i for i in out)


def test_recent_cutoff():
    assert _recent_cutoff(0) == _dt.date.today().isoformat()
    assert _recent_cutoff(7) == (_dt.date.today() - _dt.timedelta(days=7)).isoformat()

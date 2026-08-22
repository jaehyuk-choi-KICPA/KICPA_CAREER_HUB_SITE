"""산업 스트림 — 기업 태깅 경계 규칙과 뉴스 파이프라인 분리 불변식.

기업 태깅은 한국어에 단어경계가 없어 부분일치 오탐이 나기 쉽다. 여기 고정된 케이스가
_boundary_ok / 최장일치 마스킹의 사양이다(규칙을 바꾸면 이 테스트부터 갱신할 것).
"""
from __future__ import annotations

import pytest

from src.export import _build_company_index, _cap_per_day, tag_companies


@pytest.fixture(scope="module")
def index(cfg) -> list:
    return _build_company_index(cfg)


class TestTagCompanies:
    def test_basic_hit(self, index):
        assert tag_companies("기아, 3분기 영업이익 2조 돌파", index) == ["기아"]
        assert tag_companies("현대차 영업이익 사상 최대", index) == ["현대차"]

    def test_hangul_boundary_blocks_false_positive(self, index):
        # 짧은 별칭 뒤에 한글이 붙으면 다른 고유명사다
        assert tag_companies("기아대책본부 후원금 전달", index) == []
        assert tag_companies("대상포진 백신 매출 증가", index) == []

    def test_corp_suffix_is_a_different_company(self, index):
        # '현대차'+'증권' = 사전에 없는 현대차증권 → 현대차로 새면 안 됨
        assert tag_companies("현대차증권 유상증자 결정", index) == []
        # 셀트리온제약·현대차그룹은 셀트리온·현대차와 별개 주체다
        assert tag_companies("셀트리온제약, 2분기 매출 증가", index) == []
        assert tag_companies("현대차그룹 지배구조 개편안 발표", index) == []

    def test_longest_match_wins(self, index):
        # '삼성바이오로직스'가 '삼성전자'류 짧은 별칭보다 먼저 소비돼야 한다
        assert tag_companies("삼성바이오로직스, CDMO 수주 확대", index) == ["삼성바이오로직스"]
        assert tag_companies("포스코홀딩스 영업이익 개선", index) == ["포스코홀딩스"]

    def test_latin_alias_boundary(self, index):
        assert tag_companies("KTX 요금 인상 검토", index) == []          # 앞뒤 영숫자 → 탈락
        assert tag_companies("KT, 클라우드 사업 물적분할", index) == ["KT"]

    def test_multiple_companies_in_order(self, index):
        assert tag_companies("SK하이닉스·SK온 실적 희비", index) == ["SK하이닉스", "SK온"]

    def test_max_tags_cap(self, index):
        title = "삼성전자 SK하이닉스 LG디스플레이 삼성전기 실적 발표"
        assert len(tag_companies(title, index, max_tags=3)) == 3

    def test_empty_title(self, index):
        assert tag_companies("", index) == []


class TestCapPerDay:
    def test_caps_per_category_and_day(self):
        items = [{"category": "반도체·전자", "published": "2026-08-20"} for _ in range(6)]
        items += [{"category": "건설·부동산", "published": "2026-08-20"} for _ in range(3)]
        out = _cap_per_day(items, 4)
        assert sum(1 for i in out if i["category"] == "반도체·전자") == 4
        assert sum(1 for i in out if i["category"] == "건설·부동산") == 3

    def test_zero_cap_is_passthrough(self):
        items = [{"category": "a", "published": "2026-08-20"}] * 5
        assert _cap_per_day(items, 0) == items


class TestStreamSeparation:
    """산업 설정이 뉴스 4분류 파이프라인을 오염시키지 않는다는 불변식.

    이걸 어기면 embeds 프로토타입 오염 / _dedup_near 선점 잠식 / 정치어 오차단이 되살아난다.
    """

    def test_industry_not_in_news_queries(self, cfg):
        d = cfg["dashboard"]
        assert set(d["news_queries"]) == {"채용·시험", "딜·M&A", "세무", "감사"}
        assert not set(d["news_queries"]) & set(d["industry_queries"])

    def test_industry_has_own_gates(self, cfg):
        d = cfg["dashboard"]
        assert d["industry_require_any"] is not d["news_require_any"]
        assert d["industry_exclude"] is not d["news_exclude"]
        # 산업 exclude에 정치어가 없어야 한다(산업정책 기사 오차단 방지)
        assert not {"여야", "국정감사", "대통령"} & set(d["industry_exclude"])

    def test_every_company_industry_is_known(self, cfg):
        d = cfg["dashboard"]
        known = set(d["industry_queries"])
        for canon, meta in d["industry_companies"].items():
            for ind in meta.get("industries", []):
                assert ind in known, f"{canon}의 산업 '{ind}'이 industry_queries에 없음"

"""classify.py — 법인(firm)·직무(field) 규칙 분류."""
from __future__ import annotations

from src.classify import classify_emp_kind, classify_field, classify_firm

from tests.conftest import make_posting


class TestClassifyEmpKind:
    def test_parttime_variants(self, cfg):
        # 'PART TIME'(공백)·'PARTTIME'(붙임)·'Part-Time'·emp_type 모두 파트타임으로
        assert classify_emp_kind(make_posting(title="회계 보조 PART TIME 모집"), cfg) == "파트타임"
        assert classify_emp_kind(make_posting(title="회계 보조 PARTTIME"), cfg) == "파트타임"
        assert classify_emp_kind(make_posting(title="세무 도우미", emp_type="Part-Time"), cfg) == "파트타임"

    def test_part_not_overmatched(self, cfg):
        # 바 '파트'/'part'는 오탐 금지 — '수습 파트'(부서)·'Parthenon'(브랜드)
        assert classify_emp_kind(make_posting(title="[한미회계법인] 4본부 수습 파트 채용"), cfg) != "파트타임"
        assert classify_emp_kind(make_posting(title="EY Parthenon VCS팀", emp_type="인턴"), cfg) == "인턴"


class TestClassifyFirm:
    def test_big4_by_source(self, cfg):
        assert classify_firm(make_posting(source="samil"), cfg) == "삼일"
        assert classify_firm(make_posting(source="hanyoung"), cfg) == "한영"

    def test_local_board_big4_correction(self, cfg):
        # KICPA 보드(로컬군) 공고지만 회사명에 Big4 키워드 → 해당 법인으로 보정
        p = make_posting(source="kicpa_cpa", company="삼일PwC", title="채용")
        assert classify_firm(p, cfg) == "삼일"

    def test_local_keyword_to_local(self, cfg):
        p = make_posting(source="kicpa_cpa", company="대박회계법인", title="수습 채용")
        assert classify_firm(p, cfg) == "로컬"

    def test_non_accounting_to_etc(self, cfg):
        p = make_posting(source="kicpa_cpa", company="대한자산공사", title="CPA 채용")
        assert classify_firm(p, cfg) == "기타"


class TestClassifyField:
    def test_audit_keyword(self, cfg):
        assert classify_field(make_posting(title="외부감사 스태프 채용"), cfg) == "감사"

    def test_deal_keyword(self, cfg):
        assert classify_field(make_posting(title="M&A 자문 채용"), cfg) == "딜"

    def test_tax_keyword(self, cfg):
        assert classify_field(make_posting(title="세무조정 담당 채용"), cfg) == "택스"

    def test_local_default_to_audit(self, cfg):
        # 미매칭 + 로컬 회계법인 → 감사 디폴트(수습≈감사)
        assert classify_field(make_posting(title="회계사 모집"), cfg, firm="로컬") == "감사"

    def test_big4_default_to_etc(self, cfg):
        # 미매칭 + Big4 → 기타 유지(자문·디지털 오분류 방지)
        assert classify_field(make_posting(title="일반 사무 지원"), cfg, firm="삼일") == "기타"

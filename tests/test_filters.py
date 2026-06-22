"""filters.py — '경력 제외, 신입·수습·인턴 포함' 규칙(타깃 적합도의 핵심 게이트)."""
from __future__ import annotations

from src.filters import filter_postings, passes

from tests.conftest import make_posting as _make_posting


def make_posting(**kw):
    """필터 로직 검증은 '비-면제' 소스로 — conftest 기본 source가 kicpa_susup인데 이건 bypass_sources라
    필터를 통째로 건너뛰므로, 경력 제외 규칙 자체를 검증하려면 면제되지 않는 소스로 바꿔 준다."""
    kw.setdefault("source", "samil")
    return _make_posting(**kw)


def test_career_only_excluded(cfg):
    # '경력'만 있는 제목 → 제외
    assert passes(make_posting(title="회계 경력직 채용"), cfg) is False


def test_entry_and_career_kept(cfg):
    # 신입·경력 동시모집 → 예외(신입)로 유지(수습 타깃 보존)
    assert passes(make_posting(title="신입·경력 동시 채용"), cfg) is True


def test_hard_exclude_title_only(cfg):
    # 제목이 명백히 경력 전용(hard) → 제외
    assert passes(make_posting(title="회계 경력직 5년 이상 채용"), cfg) is False


def test_hard_exclude_rescued_by_title_exception(cfg):
    # hard라도 제목에 신입/수습 병기 시 유지(이중타깃 보존)
    assert passes(make_posting(title="경력직/신입 채용"), cfg) is True


def test_trainee_kept(cfg):
    assert passes(make_posting(title="수습 공인회계사 채용"), cfg) is True


def test_plain_posting_passes(cfg):
    # 제외 키워드 없으면 통과(include_keywords 비어있음)
    assert passes(make_posting(title="감사 스태프 채용"), cfg) is True


def test_filter_postings_filters_list(cfg):
    items = [
        make_posting(title="수습 공인회계사 채용"),     # 유지
        make_posting(title="시니어 매니저 경력 채용"),   # 제외
        make_posting(title="감사 인턴 채용"),            # 유지
    ]
    kept = filter_postings(items, cfg)
    assert len(kept) == 2
    assert all("수습" in p.title or "인턴" in p.title for p in kept)


def test_bypass_source_kept_despite_career_title(cfg):
    # 수습CPA 보드(kicpa_susup)는 bypass_sources라 경력 필터 면제 — 경력직 제목이어도 그대로 유지
    p = _make_posting(title="회계 경력직 5년 이상 채용", source="kicpa_susup")
    assert passes(p, cfg) is True


def test_bypass_only_applies_to_listed_source(cfg):
    # 면제는 등록된 소스에만 — 다른 보드(kicpa_cpa)의 경력 전용 제목은 여전히 제외
    p = _make_posting(title="회계 경력직 5년 이상 채용", source="kicpa_cpa")
    assert passes(p, cfg) is False


def test_negated_exception_not_rescued(cfg):
    # '신입불가'의 '신입'이 경력 전용 공고를 오구제하면 안 됨(부분일치 버그 회귀 방지).
    # 실측: kicpa_cpa '세무기장 경력 3년이상 모집(신입불가)'가 통과되던 문제.
    assert passes(make_posting(title="세무기장 경력 3년이상 모집(신입불가)"), cfg) is False
    # 단, 진짜 신입 병기는 그대로 유지
    assert passes(make_posting(title="세무기장 경력/신입 모집"), cfg) is True


def test_year_experience_hard_excluded(cfg):
    # 'N년차'·'경력사원' = 경력 전용 → 제외. 단 제목에 신입 병기면 유지.
    assert passes(make_posting(title="회계 경력 3년차 채용"), cfg) is False
    assert passes(make_posting(title="경력사원 모집"), cfg) is False
    assert passes(make_posting(title="회계 신입 3년차까지 환영"), cfg) is True


def test_title_noise_excluded(cfg):
    # 기장직원(사무보조) = 역할 노이즈 → 제외(면제 소스보다 우선). '기장 업무 포함' 수습공고는 유지.
    assert passes(make_posting(title="세무 기장 직원 채용"), cfg) is False
    assert passes(make_posting(title="기장 및 업무지원 직원 모집"), cfg) is False
    assert passes(make_posting(title="경력 기장직원을 모십니다", source="kicpa_susup"), cfg) is False  # 면제보다 우선
    assert passes(make_posting(title="수습 공인회계사 채용(기장 업무 포함)"), cfg) is True

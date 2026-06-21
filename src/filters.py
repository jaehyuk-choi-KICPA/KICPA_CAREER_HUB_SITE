"""규칙 기반 필터 — '경력' 제외, 나머지(인턴/신입/경력무관/수습) 포함.

2단계:
  1) 소스 어댑터가 카테고리 단계에서 경력을 빼는 게 1순위(가장 정확).
  2) 여기 텍스트 필터가 보조망(카테고리가 모호한 소스 대비).
모든 키워드는 config로만 관리(하드코딩 금지).
"""

from __future__ import annotations

from src.record import Posting


def _haystack(p: Posting) -> str:
    return " ".join([p.title, p.company, p.body_excerpt, p.category]).lower()


def _exception_present(s: str, exceptions: list[str], negators: list[str]) -> bool:
    """예외어(신입/수습/경력무관 등)가 '부정 맥락'이 아닌 채로 등장하면 True.
    '신입불가'·'신입 제외'처럼 예외어 바로 뒤에 부정어가 붙으면 예외로 치지 않는다
    — 경력 전용 공고가 '신입' 글자만 보고 오구제되는 부분일치 버그를 막는다."""
    for exc in exceptions:
        start = 0
        while True:
            i = s.find(exc, start)
            if i < 0:
                break
            tail = s[i + len(exc):].lstrip(" )/·,.-")
            if not any(neg and tail.startswith(neg) for neg in negators):
                return True
            start = i + len(exc)
    return False


def passes(p: Posting, cfg: dict) -> bool:
    f = cfg["filters"]

    # 면제 소스: 보드 자체가 타깃 확정(수습CPA 보드 등) → 경력 필터 없이 그대로 수용.
    # 제목이 '경력직'이라도 모집대상에 신입/경력이 병기된 보드 공고를 떨구지 않게 한다.
    if p.source in f.get("bypass_sources", []):
        return True

    text = _haystack(p)

    excludes = [k.lower() for k in f.get("exclude_keywords", [])]
    exceptions = [k.lower() for k in f.get("exclude_exceptions", [])]
    negators = [k.lower() for k in f.get("exception_negators", [])]
    includes = [k.lower() for k in f.get("include_keywords", [])]
    hard = [k.lower() for k in f.get("hard_exclude_keywords", [])]

    # 강한 제외: 제목이 명백히 경력 대상이면 제외. 단 **제목에 신입/수습/경력무관/무관/인턴이 병기**되면
    # 신입+경력 동시모집이므로 유지(예외 단어를 '제목 한정'으로 검사 — 본문만의 신입은 순수 경력 제목을 못 구제).
    # '신입불가'처럼 부정 맥락의 예외어는 _exception_present가 걸러낸다.
    title = p.title.lower()
    if any(h in title for h in hard) and not _exception_present(title, exceptions, negators):
        return False

    # 예외(경력무관 등)가 있으면 제외 규칙을 건너뛴다
    if not _exception_present(text, exceptions, negators):
        if any(bad in text for bad in excludes):
            return False

    # include_keywords가 비어 있으면 "제외에 안 걸린 건 전부 통과"
    if includes:
        return any(inc in text for inc in includes)
    return True


def filter_postings(postings: list[Posting], cfg: dict) -> list[Posting]:
    return [p for p in postings if passes(p, cfg)]

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


def passes(p: Posting, cfg: dict) -> bool:
    f = cfg["filters"]
    text = _haystack(p)

    excludes = [k.lower() for k in f.get("exclude_keywords", [])]
    exceptions = [k.lower() for k in f.get("exclude_exceptions", [])]
    includes = [k.lower() for k in f.get("include_keywords", [])]
    hard = [k.lower() for k in f.get("hard_exclude_keywords", [])]

    # 강한 제외: 제목이 명백히 경력 대상이면 제외. 단 **제목에 신입/수습/경력무관/무관/인턴이 병기**되면
    # 신입+경력 동시모집이므로 유지(예외 단어를 '제목 한정'으로 검사 — 본문만의 신입은 순수 경력 제목을 못 구제).
    title = p.title.lower()
    if any(h in title for h in hard) and not any(exc in title for exc in exceptions):
        return False

    # 예외(경력무관 등)가 있으면 제외 규칙을 건너뛴다
    if not any(exc in text for exc in exceptions):
        if any(bad in text for bad in excludes):
            return False

    # include_keywords가 비어 있으면 "제외에 안 걸린 건 전부 통과"
    if includes:
        return any(inc in text for inc in includes)
    return True


def filter_postings(postings: list[Posting], cfg: dict) -> list[Posting]:
    return [p for p in postings if passes(p, cfg)]

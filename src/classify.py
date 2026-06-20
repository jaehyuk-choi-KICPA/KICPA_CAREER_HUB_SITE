"""채용공고 규칙 분류 — 법인(firm)·직무분야(field). 키워드는 config(dashboard)에서만 관리."""

from __future__ import annotations

from src.record import Posting


def classify_firm(p: Posting, cfg: dict) -> str:
    """법인 라벨: 삼일/삼정/안진/한영/로컬/기타.

    1차: source 기준(Big4 어댑터→해당 법인, KICPA→로컬군).
    2차: 로컬군이면 회사명·제목에 Big4 키워드가 있을 때 그 법인으로 보정(로컬 보드 안의 Big4 공고).
    3차: 그래도 Big4가 아니면 회계·세무 법인(local_keywords)이면 '로컬', 아니면 '기타'(일반기업·공공 등).
    """
    d = cfg["dashboard"]
    firm = d["firm_by_source"].get(p.source, "로컬")
    if firm != "로컬":
        return firm

    text = f"{p.company} {p.title}".lower()
    for label, kws in d["firm_keywords"].items():
        if any(k.lower() in text for k in kws):
            return label
    if any(k.lower() in text for k in d.get("local_keywords", [])):
        return "로컬"
    return "기타"


def classify_field(p: Posting, cfg: dict, firm: str = "기타") -> str:
    """직무분야 라벨: 딜/감사/택스/기타 (제목+회사 키워드 우선, 미매칭은 법인별 디폴트).

    미매칭 시 로컬 회계법인 공고(audit_default_firms)는 '감사'로 — 수습/스태프 직무가 대체로 감사라
    타깃(수습공인회계사)에게 '기타'로 묻히지 않게 한다. Big4·기타는 '기타' 유지(자문·디지털 오분류 방지).
    """
    d = cfg["dashboard"]
    text = f"{p.title} {p.company}".lower()
    for label, kws in d["field_keywords"].items():
        if any(k.lower() in text for k in kws):
            return label
    return "감사" if firm in d.get("audit_default_firms", []) else "기타"


def _detail_text(p: Posting) -> str:
    """판정용 종합 텍스트 — 제목+회사+상세발췌+고용형태+구분(소스가 주는 만큼)."""
    return f"{p.title} {p.company} {p.body_excerpt} {p.emp_type} {p.category}".lower()


def classify_qualification(p: Posting, cfg: dict) -> str:
    """자격요건 라벨: 수습CPA / 자격무관.

    KICPA 수습보드(kicpa_susup)는 무조건 수습CPA(합격자 대상 보드). 그 외엔 모집대상 종합 텍스트에
    수습/공인회계사/CPA 등 키워드가 있고 제외어가 없으면 수습CPA, 아니면 자격무관(보수적 기본).
    """
    d = cfg["dashboard"]
    if p.source == "kicpa_susup":
        return "수습CPA"
    text = _detail_text(p)
    if any(k.lower() in text for k in d.get("qual_exclude_keywords", [])):
        return "자격무관"
    if any(k.lower() in text for k in d.get("qual_susup_keywords", [])):
        return "수습CPA"
    return "자격무관"


def classify_emp_kind(p: Posting, cfg: dict) -> str:
    """채용구분 라벨: 인턴 / 계약직 / 파트타임 / 정규직 (우선순위 매칭, 미매칭 기본=정규직)."""
    d = cfg["dashboard"]
    text = _detail_text(p)
    for label, kws in d.get("empkind_keywords", {}).items():
        if any(k.lower() in text for k in kws):
            return label
    return "정규직"

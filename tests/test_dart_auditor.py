# -*- coding: utf-8 -*-
"""감사인 표기 정규화 — DART 원문은 회사가 직접 쓴 자유 텍스트라 같은 법인이 여러 표기로 갈린다."""
from src.adapters.dart import _norm_auditor


def test_실측_변형_3종이_한_표기로_모인다():
    # 188곳 실측에서 나온 실제 값들
    assert _norm_auditor("삼일회계법인 (PwC)") == "삼일회계법인"
    assert _norm_auditor("한영 회계법인") == "한영회계법인"
    assert _norm_auditor("안진") == "안진회계법인"


def test_이미_정규형이면_그대로():
    for v in ("삼일회계법인", "삼정회계법인", "한울회계법인", "삼덕회계법인"):
        assert _norm_auditor(v) == v


def test_접두형_상호는_붙이지_않는다():
    # '회계법인 리안'은 상호 자체가 접두형 — 공백을 지우면 다른 이름이 된다
    assert _norm_auditor("회계법인 리안") == "회계법인 리안"


def test_빈값_처리():
    assert _norm_auditor("") == ""
    assert _norm_auditor(None) == ""
    assert _norm_auditor("  -  ") in ("", "-")

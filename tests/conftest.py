"""공용 픽스처 — 실제 config 규칙으로 테스트(규칙이 곧 사양)."""
from __future__ import annotations

import pytest

from src.config import load_config
from src.record import Posting


@pytest.fixture(scope="session")
def cfg() -> dict:
    return load_config()


def make_posting(**kw) -> Posting:
    """필수 필드 기본값을 채운 Posting 헬퍼."""
    base = {"source": "kicpa_susup", "source_label": "구인(수습CPA)", "title": ""}
    base.update(kw)
    return Posting(**base)

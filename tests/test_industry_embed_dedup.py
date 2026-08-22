"""산업 스트림 의미 군집(embeds.refine) — 병합 규칙과 스트림 분리 불변식.

로컬엔 VOYAGE_API_KEY가 없으므로 **클라이언트를 주입**해 결정론적으로 검증한다
(refine의 `client` 인자가 원래 테스트 주입용으로 열려 있다).
"""
from __future__ import annotations

import pytest

from src import embeds
from src.export import _title_sig


class FakeVoyage:
    """텍스트 → 미리 정한 벡터를 돌려주는 가짜 임베딩 클라이언트."""

    def __init__(self, vecs: dict):
        self.vecs = vecs
        self.embedded: list[str] = []

    def embed(self, texts, model=None, input_type=None):
        self.embedded.extend(texts)
        res = type("R", (), {})()
        res.embeddings = [self.vecs[t] for t in texts]
        return res


A = "삼성전자 반도체 영업이익 사상 최대"
B = "삼성전자 반도체 실적 역대 최고"        # A와 같은 사건, 다른 표현 → 병합 대상
C = "현대차 완성차 판매 실적 개선"           # 무관한 기사

VECS = {
    A: [1.0, 0.0, 0.0],
    B: [0.99, 0.14, 0.0],   # A와 코사인 ≈ 0.99
    C: [0.0, 0.0, 1.0],     # 직교
}


def item(title, url, category="반도체·전자"):
    return {"title": title, "url": url, "category": category,
            "published": "2026-08-22", "published_at": "2026-08-22T09:00:00",
            "source_label": "연합뉴스"}


@pytest.fixture
def icfg(cfg, tmp_path):
    """산업 임베딩 설정 — 캐시는 tmp로(실제 industry_vectors.json을 건드리지 않게)."""
    import copy
    c = copy.deepcopy(cfg)
    c["dashboard"]["industry_embed_cache_path"] = str(tmp_path / "ind_vec.json")
    return c


class TestIndustryRefine:
    def test_merges_same_event_different_wording(self, icfg):
        items = [item(A, "u1"), item(B, "u2"), item(C, "u3")]
        out = embeds.refine(items, _title_sig, icfg, client=FakeVoyage(VECS), prefix="industry")
        assert len(out) == 2                       # A·B가 한 장으로
        assert out[0]["url"] == "u1"               # 최신(앞선 인덱스)이 대표
        assert [d["url"] for d in out[0]["dupes"]] == ["u2"]

    def test_never_merges_across_industries(self, icfg):
        """산업을 가로지르는 병합은 없어야 한다 — refine은 같은 category 쌍만 후보로 삼는다."""
        items = [item(A, "u1", "반도체·전자"), item(B, "u2", "자동차·모빌리티")]
        out = embeds.refine(items, _title_sig, icfg, client=FakeVoyage(VECS), prefix="industry")
        assert len(out) == 2
        assert all("dupes" not in i for i in out)

    def test_no_key_is_noop(self, icfg, monkeypatch):
        """키가 없으면 어휘 군집 결과를 그대로 돌려준다(오프라인 폴백 — 견고성 원칙)."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        items = [item(A, "u1"), item(B, "u2")]
        out = embeds.refine(items, _title_sig, icfg, prefix="industry")
        assert len(out) == 2

    def test_min_tokens_gate_avoids_needless_calls(self, icfg):
        """공통 핵심토큰이 부족하면 임베딩 호출조차 하지 않는다(비용 게이트)."""
        fake = FakeVoyage(VECS)
        items = [item(A, "u1"), item(C, "u3")]     # 공통 토큰 없음
        out = embeds.refine(items, _title_sig, icfg, client=fake, prefix="industry")
        assert len(out) == 2
        assert fake.embedded == []                  # API 미호출


class TestStreamIsolation:
    def test_cache_paths_are_separate(self, cfg):
        """캐시를 공유하면 _save_cache가 '현재 목록 url'만 남기고 잘라 서로의 벡터를 축출한다.

        그러면 뉴스와 산업이 매 실행 상대의 벡터를 지워 재임베딩이 무한 반복된다.
        """
        d = cfg["dashboard"]
        assert d["industry_embed_cache_path"] != d["news_embed_cache_path"]

    def test_prefix_defaults_to_news(self, cfg, tmp_path):
        """prefix 기본값이 news라 기존 호출부(build_news)는 동작이 바뀌지 않는다."""
        import copy
        c = copy.deepcopy(cfg)
        c["dashboard"]["news_embed_cache_path"] = str(tmp_path / "news_vec.json")
        c["dashboard"]["news_embed_candidate_min_tokens"] = 2
        items = [item(A, "u1", "감사"), item(B, "u2", "감사")]
        out = embeds.refine(items, _title_sig, c, client=FakeVoyage(VECS))
        assert len(out) == 1

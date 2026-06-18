"""뉴스 의미 군집(임베딩) — 어휘 군집이 못 묶는 '같은 사건·다른 표현'을 보조 병합.

설계 원칙(코어 LLM-free의 게이트된 예외):
  - **생성 LLM 미사용**(결정론적 벡터 유사도). VOYAGE_API_KEY 있을 때만 작동, 없으면 **no-op → 어휘 군집만으로
    100% 오프라인 동작**(견고성·무키 보장 유지).
  - **'걸릴 때만 가동'**: 1단계 어휘 군집(`export._dedup_near`)으로 안 묶였지만 어휘로는 애매한 **의심 쌍**
    (같은 카테고리 + 공통 핵심토큰 ≥ N)이 있을 때만 임베딩을 호출한다. 의심 쌍이 없으면 API 호출조차 안 함.
  - **URL→벡터 캐시**(`news_vectors.json`): 이미 본 기사는 재임베딩하지 않음 → 매 수집 비용·시간 최소.
  - 모든 외부호출 try/except — 임베딩이 깨져도 어휘 군집 결과를 그대로 반환(전체 실패 금지).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _client():
    """VOYAGE_API_KEY + SDK 있을 때만 클라이언트. 없으면 None(오프라인=어휘 군집만)."""
    if not os.environ.get("VOYAGE_API_KEY"):
        return None
    try:
        import voyageai
        return voyageai.Client()
    except Exception:  # noqa: BLE001 — SDK 미설치 등
        return None


def _load_cache(path: str) -> dict:
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(path: str, cache: dict, keep_urls: set) -> None:
    # 현재 목록 url만 보관(무한증가 방지). 재등장 기사는 재임베딩(저렴)하면 되므로 단순 정리로 충분.
    cache = {u: v for u, v in cache.items() if u in keep_urls}
    try:
        Path(path).write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _vectors(client, model: str, url_to_text: dict, keep_urls: set, cache_path: str) -> dict:
    """필요한 url들의 벡터 확보 — 캐시 우선, 없는 것만 배치 임베딩. 실패 시 가능한 것만 반환."""
    cache = _load_cache(cache_path)
    need = [(u, t) for u, t in url_to_text.items() if u not in cache]
    if need:
        try:
            res = client.embed([t for _, t in need], model=model, input_type="document")
            for (u, _), vec in zip(need, res.embeddings):
                cache[u] = vec
        except Exception:  # noqa: BLE001 — 호출 실패해도 기존 캐시분으로 진행
            pass
    _save_cache(cache_path, cache, keep_urls)
    return {u: cache[u] for u in url_to_text if u in cache}


def _cosine(a, b) -> float:
    s = da = db = 0.0
    for x, y in zip(a, b):
        s += x * y
        da += x * x
        db += y * y
    return s / ((da ** 0.5) * (db ** 0.5)) if da and db else 0.0


def refine(items: list[dict], sig_fn, cfg: dict, client=None) -> list[dict]:
    """어휘 1차 군집된 대표 리스트를 받아, 의심 쌍을 임베딩 코사인으로 추가 병합한다.

    items는 최신순(앞이 최신) 전제 — 병합 시 가장 앞(최신) 대표를 유지하고 나머지를 dupes로 흡수.
    `client`는 테스트 주입용(없으면 환경 키로 생성). `sig_fn(title)->set` 은 export._title_sig.
    """
    d = cfg["dashboard"]
    if not d.get("news_embed_enabled", True) or len(items) < 2:
        return items
    client = client or _client()
    if client is None:
        return items  # 키 없음 → 어휘 군집만(폴백)

    th = d.get("news_embed_threshold", 0.82)
    min_tok = d.get("news_embed_candidate_min_tokens", 1)
    model = d.get("news_embed_model", "voyage-3.5-lite")
    cache_path = d.get("news_embed_cache_path", "news_vectors.json")

    n = len(items)
    sigs = [sig_fn(it.get("title", "")) for it in items]
    cats = [it.get("category") for it in items]

    # '걸릴 때만': 어휘로 안 묶인 의심 쌍 = 같은 카테고리 + 공통 핵심토큰 ≥ min_tok
    pairs, involved = [], set()
    for i in range(n):
        if not sigs[i]:
            continue
        for j in range(i + 1, n):
            if cats[i] != cats[j] or not sigs[j]:
                continue
            if len(sigs[i] & sigs[j]) >= min_tok:
                pairs.append((i, j))
                involved.add(i)
                involved.add(j)
    if not pairs:
        return items  # 의심 쌍 없음 → 임베딩 호출 안 함

    keep_urls = {it.get("url") for it in items}
    vecs = _vectors(client, model,
                    {items[k]["url"]: items[k].get("title", "") for k in involved},
                    keep_urls, cache_path)

    # union-find로 코사인≥th 쌍을 묶음
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in pairs:
        ui, uj = items[i].get("url"), items[j].get("url")
        if ui in vecs and uj in vecs and _cosine(vecs[ui], vecs[uj]) >= th:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)  # 더 앞(최신) 인덱스를 대표로

    # 각 그룹의 최소 인덱스(=최신)를 대표로, 나머지는 dupes로 흡수
    rep_of = {}
    for i in range(n):
        r = find(i)
        rep_of.setdefault(r, i)  # i 오름차순이라 첫 등장이 최소 인덱스
    out = []
    for i in range(n):
        r = find(i)
        if rep_of[r] == i:
            out.append(items[i])
        else:
            rep = items[rep_of[r]]
            dupes = rep.setdefault("dupes", [])
            dupes.append({k: items[i].get(k) for k in ("title", "url", "source_label", "published")})
            dupes.extend(items[i].get("dupes", []))  # 흡수되는 대표가 갖고 있던 중복도 승계
    return out

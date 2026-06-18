"""뉴스 임베딩 임계값 튜닝 진단 — `news_embed_relevance_floor`·`news_embed_category_margin` 잡기.

실행(키는 환경변수로만, 채팅/코드에 넣지 말 것):
    VOYAGE_API_KEY=... python -m src.embed_tune          # 기본: docs/data/news.json 제목 사용

읽기 전용(데이터·config 변경 없음). 카테고리 4개 프로토타입과 각 기사 제목의 코사인 분포를 출력해
  - 관련성 floor: 오프도메인(낮은 max_sim) 하단을 보고 결정
  - 카테고리 margin: best!=현재인 '재배정 후보'의 (best-현재) 분포를 보고 결정
을 사람이 눈으로 판단할 수 있게 한다. 마지막에 잠정 추천값을 제시.
"""

from __future__ import annotations

import os

from src import embeds
from src.config import load_config


def _pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    i = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def main() -> None:
    if not os.environ.get("VOYAGE_API_KEY"):
        print("VOYAGE_API_KEY 환경변수가 없습니다. 키와 함께 실행하세요.")
        return
    import json
    from pathlib import Path

    cfg = load_config()
    d = cfg["dashboard"]
    model = d.get("news_embed_model", "voyage-3.5-lite")

    client = embeds._client()
    if client is None:
        print("voyageai 클라이언트 생성 실패(패키지/키 확인).")
        return

    data = json.loads(Path("docs/data/news.json").read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not items:
        print("docs/data/news.json에 기사가 없습니다. 먼저 수집(run-all) 후 실행하세요.")
        return

    protos = embeds._prototypes(client, model, d.get("news_queries", {}))
    if not protos:
        print("프로토타입 임베딩 실패.")
        return
    cats = list(protos.keys())

    url_to_text = {it["url"]: it.get("title", "") for it in items if it.get("url")}
    vecs = embeds._vectors(client, model, url_to_text, set(url_to_text),
                           d.get("news_embed_cache_path", "news_vectors.json"))

    rows = []  # (max_sim, current, best, margin, title)
    for it in items:
        v = vecs.get(it.get("url"))
        if v is None:
            continue
        sims = {c: embeds._cosine(v, protos[c]) for c in cats}
        cur = it.get("category")
        best = max(sims, key=sims.get)
        margin = (sims[best] - sims.get(cur, 0.0)) if cur in sims else 0.0
        rows.append((max(sims.values()), cur, best, margin, it.get("title", "")[:46]))

    n = len(rows)
    print(f"\n=== 표본 {n}건 (model={model}) ===\n")

    # 관련성: max_sim 분포 + 하위 15건(오프도메인 후보)
    ms = sorted(r[0] for r in rows)
    print("[관련성] max_sim 분위수:",
          " ".join(f"p{p}={_pct(ms,p):.3f}" for p in (2, 5, 10, 25, 50)), f"min={ms[0]:.3f}")
    print("  ↓ max_sim 낮은 순 15건(이 중 진짜 무관기사 위쪽으로 floor 설정):")
    for s, cur, best, mg, t in sorted(rows)[:15]:
        print(f"    {s:.3f}  [{cur}] {t}")
    for f in (0.25, 0.30, 0.35, 0.40):
        print(f"  · floor={f}: 드롭 {sum(1 for r in rows if r[0] < f)}건")

    # 카테고리: 재배정 후보(best!=현재) margin 분포 + 샘플
    cand = sorted([r for r in rows if r[1] != r[2]], key=lambda r: -r[3])
    print(f"\n[카테고리] 재배정 후보(best≠현재) {len(cand)}건. (best-현재) 큰 순:")
    for s, cur, best, mg, t in cand[:18]:
        print(f"    Δ={mg:.3f}  {cur}→{best}  {t}")
    for m in (0.05, 0.08, 0.10, 0.15):
        print(f"  · margin={m}: 재배정 {sum(1 for r in cand if r[3] > m)}건")

    # 잠정 추천
    rec_floor = round(max(0.20, _pct(ms, 5) - 0.02), 2)
    print(f"\n>>> 잠정 추천: relevance_floor≈{rec_floor} (p5 약간 아래), "
          f"category_margin≈0.10~0.15(위 샘플서 확신 flip만 남는 값)")
    print(">>> 위 '낮은 max_sim 15건'과 '재배정 후보 샘플'을 보고 최종값을 회신해 주세요(또는 그대로 붙여넣기).")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""아카이브 일회성 정리 — 제목 중복 제거 + 군집 id(gid) 소급 부여.

**왜 필요한가**

'전체 기간' 화면에 같은 기사가 여러 장 뜨는 원인이 둘이었다.

1. **같은 제목·다른 링크** — 구글뉴스 RSS는 같은 기사를 시점에 따라 다른 base64 링크로
   내보낸다. 아카이브 upsert가 URL만 키로 삼아 그때마다 새 레코드가 됐다.
   실측: 업계 2,527건 중 481건(19%), 산업 3,492건 중 64건(1.8%).
2. **평면화된 군집** — `archive._expand`가 라이브의 `대표 + dupes`를 독립 레코드로 편다
   (배열을 그대로 담으면 스냅샷마다 누적돼 11MB까지 부푼 실측 사고 때문). 그 결과
   라이브에서 카드 1장이던 사건이 아카이브에선 5장으로 흩어졌다.

1은 레코드를 지워 해결하고, 2는 **지우지 않고** 같은 사건에 같은 `gid`를 붙여 프론트가
다시 접을 수 있게 한다(정보 보존 + 화면 정돈).

앞으로 들어오는 데이터는 `archive.merge_items`의 제목 가드와 `_expand`의 gid 스탬프가
담당하므로, 이 스크립트는 **과거분에 한 번만** 돌리면 된다.

사용:
    python -m scripts.archive_dedup --dry-run     # 무엇이 어떻게 바뀌는지만 출력
    python -m scripts.archive_dedup               # 실제 정리 + index 재작성
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src import archive
from src.config import load_config
from src.export import _same_issue, _title_sig

# gid를 붙일 스트림. 인사이트는 간행물 제목이라 '같은 사건' 개념이 없어 제외한다.
_CLUSTER = ("news", "industry")


def _params(cfg: dict, stream: str) -> tuple[float, float, int]:
    d = cfg["dashboard"]
    pre = "industry" if stream == "industry" else "news"
    return (d.get(f"{pre}_neardup_jaccard", 0.6),
            d.get(f"{pre}_neardup_overlap", 0.67),
            d.get(f"{pre}_neardup_min_tokens", 4))


def _drop_title_dupes(items: list[dict]) -> tuple[list[dict], int]:
    """같은 제목은 한 레코드로. 먼저 아카이브된 쪽을 남기고 빈 필드만 보강한다."""
    keep: dict[str, dict] = {}
    order: list[str] = []
    for it in items:
        t = archive.norm_title(it.get("title", ""))
        if not t:
            t = "\x00" + (it.get("url") or "")      # 제목 없는 레코드는 URL로 개별 취급
        if t in keep:
            old, new = keep[t], it
            if (new.get("first_archived") or "9") < (old.get("first_archived") or "9"):
                old, new = new, old                  # 더 이른 최초수집일을 대표로
            keep[t] = archive._merge_one(old, new)
        else:
            keep[t] = it
            order.append(t)
    return [keep[t] for t in order], len(items) - len(keep)


def _assign_gid(items: list[dict], th: float, ov: float, min_tok: int) -> int:
    """같은 사건에 같은 gid. 라이브 `_dedup_near`와 동일한 판정(`_same_issue`)을 쓴다.

    입력은 최신순이므로 **먼저 나온 쪽(최신)이 대표**가 되어 라이브 화면과 대표 선택이 일치한다.
    카테고리가 다르면 비교하지 않는다(가로지르는 오병합 방지 — 산업 스트림의 선점 잠식과 같은 이유).
    """
    reps: list[tuple[frozenset, str, str]] = []      # (제목집합, 카테고리, gid)
    merged = 0
    for it in items:
        sig = _title_sig(it.get("title", ""))
        cat = it.get("category")
        gid = ""
        if sig:
            for rsig, rcat, rgid in reps:
                if rcat == cat and _same_issue(sig, rsig, th, ov, min_tok):
                    gid = rgid
                    break
        if gid:
            merged += 1
        else:
            gid = archive.norm_url(it.get("url", ""))
            if sig:
                reps.append((sig, cat, gid))
        it["gid"] = gid
    return merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    report: dict = {}

    for stream in archive._STREAMS:
        d = archive.ARCHIVE_DIR / stream
        if not d.exists():
            continue
        st: dict = {}
        for path in sorted(d.glob("*.json")):
            items = archive._read_shard(path)
            if not items:
                continue
            before = len(items)
            items, dropped = _drop_title_dupes(items)
            clustered = 0
            if stream in _CLUSTER:
                clustered = _assign_gid(items, *_params(cfg, stream))
            st[path.stem] = {"before": before, "after": len(items),
                             "제목중복_제거": dropped, "군집으로_접힘": clustered,
                             "카드수": len(items) - clustered}
            if not args.dry_run:
                archive._write_shard(path, path.stem, items)
        if st:
            report[stream] = st

    if not args.dry_run:
        archive.rebuild_index(since=cfg["dashboard"].get("archive_since", ""))

    report["_mode"] = "dry-run" if args.dry_run else "applied"
    Path("_arch_dedup_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("report → _arch_dedup_report.json")


if __name__ == "__main__":
    main()

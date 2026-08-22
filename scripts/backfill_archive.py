# -*- coding: utf-8 -*-
"""아카이브 소급 구축 — git 스냅샷 복원 + Google News RSS 기간 소급(1회성, 멱등).

배경: `docs/data/news.json`은 매 수집마다 전량 덮어쓰기라 보존창(21일)이 지난 기사가 사라진다.
반대로 **git 이력에는 30분 간격 스냅샷이 2,900장 넘게 남아 있어** 그 구간은 손실 없이 복원된다.
리포지토리 생성(2026-06-16) 이전 구간은 스냅샷이 없으므로 RSS의 `after:`/`before:` 연산자로 소급 수집한다.

    python -m scripts.backfill_archive git   --stream news [--dry-run]
    python -m scripts.backfill_archive rss   --stream industry --from 2026-05-01 --to 2026-08-23
    python -m scripts.backfill_archive index

고볼륨 구간에서 한 창이 RSS 100건 상한에 닿으면(창 결과가 계속 100 근처면) `--window`를 줄여
재실행하면 된다 — URL 기준 upsert라 몇 번을 돌려도 결과는 같다.

⚠️ 실행 전 `git fetch origin` (로컬 클론이 뒤처져 있으면 최근 스냅샷이 통째로 빠진다).
⚠️ `git checkout` / `git reset --hard` 금지 — 워킹트리의 docs/data/*.json이 덮어써진다.
   이 스크립트는 읽기 전용 git 명령(rev-list / log / cat-file)만 쓴다.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import subprocess
import time
from pathlib import Path

from src import archive
from src.adapters.base import FetchResult
from src.adapters.news_rss import build_industry_adapters, build_news_adapters
from src.config import load_config
from src.export import build_industry, build_news

_SNAPSHOT = {"news": "docs/data/news.json",
             "industry": "docs/data/industry.json",
             "insights": "docs/data/insights.json"}

# ─────────────────────────── 갈래 ① git 스냅샷 복원 ───────────────────────────

def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def _commits(path: str, ref: str) -> list[tuple[str, str]]:
    """[(sha, 커밋 ISO 시각)] — 오래된 순. 최초 등장 시각을 first_archived로 쓰기 위해 시각도 받는다."""
    out = _run(["git", "log", "--reverse", "--format=%H%x09%aI", ref, "--", path])
    rows = []
    for line in out.splitlines():
        if "\t" in line:
            sha, iso = line.split("\t", 1)
            rows.append((sha.strip(), iso.strip()))
    return rows


def _blobs(shas: list[str], path: str) -> list[bytes]:
    """`git cat-file --batch`로 blob 일괄 추출.

    커밋마다 `git show`를 돌리면 프로세스를 2,900번 띄워 ~3분이 걸린다. batch는 한 번으로 10~20초.
    ⚠️ **바이너리 모드 필수** — Windows에서 텍스트 모드로 열면 \\r\\n 변환 때문에
       `<oid> blob <size>` 프로토콜의 바이트 오프셋이 어긋난다.
    ⚠️ `--buffer` + `communicate()` 필수 — 같은 스레드에서 write/read를 번갈아 하면
       64KB 파이프 버퍼에서 데드락이 난다.
    """
    proc = subprocess.Popen(["git", "cat-file", "--batch", "--buffer"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    payload = b"".join(f"{sha}:{path}\n".encode() for sha in shas)
    out, _ = proc.communicate(payload)

    blobs: list[bytes] = []
    pos = 0
    while pos < len(out):
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].decode("utf-8", "replace")
        pos = nl + 1
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":      # 'missing' 등 — 그 커밋엔 파일이 없었음
            blobs.append(b"")
            continue
        size = int(parts[2])
        blobs.append(out[pos:pos + size])
        pos += size + 1                               # blob 뒤 개행 1바이트
    return blobs


def restore_from_git(stream: str, ref: str, dry_run: bool, since: str) -> dict:
    path = _SNAPSHOT[stream]
    rows = _commits(path, ref)
    if not rows:
        raise SystemExit(f"{path} 커밋 이력이 없습니다. `git fetch origin` 후 다시 시도하세요.")
    print(f"  스냅샷 {len(rows)}개 ({rows[0][1][:10]} ~ {rows[-1][1][:10]}) 추출 중…")
    blobs = _blobs([sha for sha, _ in rows], path)

    by_url: dict[str, dict] = {}
    parsed = 0
    for (_, iso), blob in zip(rows, blobs):
        if not blob:
            continue
        try:
            items = json.loads(blob.decode("utf-8")).get("items") or []
        except Exception:  # noqa: BLE001 — 손상 스냅샷 1장이 전체 복원을 막지 않게
            continue
        parsed += 1
        day = iso[:10]
        for it in items:
            url = archive.norm_url(it.get("url", ""))
            if not url:
                continue
            # 스키마 진화 보정(필드 추가뿐이라 하위호환): published_at은 2026-06-19 커밋부터 존재
            if not it.get("published_at") and it.get("published"):
                it["published_at"] = it["published"] + "T00:00:00"
            if url in by_url:
                by_url[url] = archive._merge_one(by_url[url], archive.slim(it, day))
            else:
                by_url[url] = archive.slim(it, day)     # first_archived = 최초 등장 커밋 날짜

    items = list(by_url.values())
    stats = {"snapshots": len(rows), "parsed": parsed, "unique": len(items)}
    if dry_run:
        months: dict[str, int] = {}
        today = _dt.date.today().isoformat()
        for it in items:
            if since and (it.get("published") or today) < since:
                continue
            m = archive.month_key(it, today)
            months[m] = months.get(m, 0) + 1
        stats["months"] = dict(sorted(months.items()))
    else:
        stats["added"] = archive.bulk_merge(stream, items, since=since)
    return stats


# ─────────────────────────── 갈래 ② RSS 기간 소급 ───────────────────────────

def _windows(start: str, end: str, days: int) -> list[tuple[str, str]]:
    """[start, end)를 days 단위 반열림 구간으로 — 경계 중복·누락 없음."""
    d0 = _dt.date.fromisoformat(start)
    d1 = _dt.date.fromisoformat(end)
    out = []
    while d0 < d1:
        nxt = min(d0 + _dt.timedelta(days=days), d1)
        out.append((d0.isoformat(), nxt.isoformat()))
        d0 = nxt
    return out


def _backfill_cfg(cfg: dict) -> dict:
    """백필용 런타임 사본 — 원본 config는 절대 건드리지 않는다.

    · 보존기간 해제: 안 하면 과거 기사가 21·30일 컷오프에 **전멸**한다(백필의 핵심 함정).
    · 임베딩 비활성: 수개월치를 임베딩하면 비용이 크고 news_vectors.json 캐시가 과거로 오염된다.
    · 일자상한(max_per_day_per_cat)은 **유지** — 도배 방지 기준이 라이브 화면과 같아야 한다.
    """
    c = copy.deepcopy(cfg)
    d = c["dashboard"]
    d["news_recent_days"] = 99999
    d["news_recent_days_by_category"] = {}
    d["industry_recent_days"] = 99999
    d["news_embed_enabled"] = False
    d["news_embed_relevance_enabled"] = False
    d["news_embed_category_enabled"] = False
    return c


def backfill_rss(stream: str, start: str, end: str, window: int,
                 sleep: float, dry_run: bool, since: str) -> dict:
    cfg = load_config()
    bcfg = _backfill_cfg(cfg)
    build = build_news if stream == "news" else build_industry
    make = build_news_adapters if stream == "news" else build_industry_adapters

    total_added: dict[str, int] = {}
    total_items = 0
    wins = _windows(start, end, window)
    print(f"  {stream}: {start} ~ {end}, {window}일 창 {len(wins)}개")
    for bgn, fin in wins:
        results: list[FetchResult] = []
        for ad in make(bcfg, (bgn, fin)):
            try:
                results.append(FetchResult(ad.source, ad.label, ad.fetch(), ok=True))
            except Exception as e:  # noqa: BLE001 — 창 하나 실패가 전체를 막지 않게
                results.append(FetchResult(ad.source, ad.label, [], ok=False, error=str(e)))
            time.sleep(sleep)       # 순차 + 지연: 백필은 시간 여유가 있고 throttle 회피가 최우선
        payload = build(bcfg, results=results)
        items = payload.get("items") or []
        total_items += len(items)
        print(f"    {bgn}~{fin}: {len(items)}건")
        if not dry_run:
            for m, n in archive.merge_items(stream, items, since=since).items():
                total_added[m] = total_added.get(m, 0) + n   # 창 단위 flush → 중단돼도 이어감
    return {"windows": len(wins), "collected": total_items, "added": dict(sorted(total_added.items()))}


# ─────────────────────────────────── CLI ───────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="아카이브 소급 구축")
    sp = ap.add_subparsers(dest="cmd", required=True)

    g = sp.add_parser("git", help="git 스냅샷에서 복원")
    g.add_argument("--stream", choices=list(_SNAPSHOT), default="news")
    g.add_argument("--ref", default="origin/main")
    g.add_argument("--dry-run", action="store_true")

    r = sp.add_parser("rss", help="RSS after:/before: 기간 소급")
    r.add_argument("--stream", choices=["news", "industry"], default="industry")
    r.add_argument("--from", dest="start", required=True)
    r.add_argument("--to", dest="end", required=True)
    r.add_argument("--window", type=int, default=7)
    r.add_argument("--sleep", type=float, default=1.2)
    r.add_argument("--dry-run", action="store_true")

    sp.add_parser("index", help="archive/index.json 재작성")

    a = ap.parse_args()
    since = load_config()["dashboard"].get("archive_since", "")

    if a.cmd == "git":
        stats = restore_from_git(a.stream, a.ref, a.dry_run, since)
    elif a.cmd == "rss":
        stats = backfill_rss(a.stream, a.start, a.end, a.window, a.sleep, a.dry_run, since)
    else:
        stats = archive.rebuild_index(since=since)

    if a.cmd != "index":
        archive.rebuild_index(since=since)
    out = Path("_backfill_stats.json")
    out.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {out} (콘솔 한글은 깨질 수 있으니 이 파일로 확인)")


if __name__ == "__main__":
    main()

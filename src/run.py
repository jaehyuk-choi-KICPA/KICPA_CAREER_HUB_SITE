"""오케스트레이션 — 스크랩 → 필터 → 상태갱신 → feed.json 발행.

모드:
  (기본) 1회 실시간:   python -m src.run
  다이제스트 포함:      python -m src.run --digest
  24시간 데몬+LAN서빙:  python -m src.run --loop
폰(메신저봇R)은 http://<랩탑IP>:<port>/feed.json 을 폴링한다.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import functools
import http.server
import json
import socket
import socketserver
import threading
import time
from pathlib import Path

from src.adapters.base import safe_fetch
from src.config import load_config
from src.filters import filter_postings
from src.formatter import build_digest, format_item
from src.sources import build_adapters
from src.state import State
from src.util import is_open, today_iso


def _scrape(cfg: dict, state: State):
    adapters = build_adapters(cfg, state)
    all_postings = []
    report = []
    for ad in adapters:
        res = safe_fetch(ad)
        report.append((res.label, res.ok, res.count, res.error))
        all_postings.extend(res.postings)
    kept = filter_postings(all_postings, cfg)
    new = state.update(kept)
    return all_postings, kept, new, report


def _write_feed(cfg: dict, *, new_items=None, digest="__keep__") -> None:
    path = Path(cfg["runtime"]["feed_path"])
    feed: dict = {}
    if path.exists():
        try:
            feed = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            feed = {}
    feed["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    if new_items is not None:
        feed["new_items"] = new_items
    if digest != "__keep__":
        feed["digest"] = digest
    feed.setdefault("new_items", [])
    feed.setdefault("digest", None)
    path.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")


def _deliver_items(cfg: dict, items: list[dict]) -> set[str]:
    """개별(실시간) 공고 게시. **실제 전송 성공한 uid 집합**을 반환(실패분은 미발송 처리→다음 주기 재시도).

    feed 방식(폰)이면 게시는 폰이 하므로 전부 '발송됨'으로 간주(uid 반환).
    """
    if not items:
        return set()
    if cfg["runtime"].get("delivery") != "kakao_pc":
        return {it["uid"] for it in items}  # 폰이 feed.json 폴링해 게시

    room = cfg["runtime"].get("kakao_room") or ""
    if not room:
        print("[deliver] kakao_room 미설정 → 게시 생략(다음 주기 재시도)")
        return set()

    from src.kakao_pc import send_message

    delivered: set[str] = set()
    for it in items:
        try:
            send_message(room, it["text"])
            delivered.add(it["uid"])
            time.sleep(1.5)  # 도배 방지 간격
        except Exception as e:  # noqa: BLE001 — 실패분은 notified 안 함→재시도
            print(f"[deliver] 전송 실패(재시도 예정): {type(e).__name__}: {e}")
    print(f"[deliver] 카톡 PC 게시: {len(delivered)}/{len(items)}건 → {room}")
    return delivered


def _deliver_digest(cfg: dict, chunks: list[str]) -> None:
    """다이제스트 게시(best-effort). 매일 재발송되므로 uid 추적은 불필요."""
    if not chunks or cfg["runtime"].get("delivery") != "kakao_pc":
        return
    room = cfg["runtime"].get("kakao_room") or ""
    if not room:
        return
    from src.kakao_pc import send_messages

    sent = send_messages(room, chunks)
    print(f"[deliver] 다이제스트 게시: {sent}/{len(chunks)}개 → {room}")


def _print_report(mode: str, report, kept, new) -> None:
    print(f"\n=== {mode} 실행 리포트 ({_dt.datetime.now():%Y-%m-%d %H:%M:%S}) ===")
    for label, ok, count, err in report:
        status = f"{count}건" if ok else f"❌ 실패: {err}"
        print(f"  - {label}: {status}")
    print(f"  필터 통과: {len(kept)}건 / 신규: {len(new)}건")


def do_realtime(cfg: dict, state: State):
    _all, kept, new, report = _scrape(cfg, state)
    # 마감 지난 공고는 신규라도 알림하지 않는다(콜드스타트에 만료 공고 폭주 방지)
    new_open = [p for p in new if is_open(p.deadline)]
    new_expired = [p for p in new if not is_open(p.deadline)]
    new_items = [{"uid": p.uid, "text": format_item(p.to_dict(), cfg)} for p in new_open]

    _write_feed(cfg, new_items=new_items)
    delivered = _deliver_items(cfg, new_items)

    # 실제 발송 성공분만 '오늘 게시'로 기록(일일 다이제스트 대상) → 실패분은 다음 주기 재시도
    state.mark_notified(list(delivered), posted_date=today_iso())
    # 만료분은 게시 없이 억제만(다이제스트에 안 잡힘)
    state.mark_notified([p.uid for p in new_expired])
    state.prune_expired()
    state.save()
    _print_report("실시간", report, kept, new_open)
    return new_items


def do_seed(cfg: dict, state: State) -> None:
    """첫 배포용: 현재 공고를 조용히 baseline으로 등록(게시 없음)."""
    _all, kept, new, report = _scrape(cfg, state)
    state.mark_notified([p.uid for p in new])
    state.prune_expired()
    state.save()
    _write_feed(cfg, new_items=[], digest=None)
    _print_report("시드(무게시)", report, kept, [])
    print(f"  baseline 등록: {len(new)}건 → 이후 실행부터 '신규'만 게시")


def do_digest(cfg: dict, state: State):
    do_realtime(cfg, state)  # 최신 목록 반영 + 신규 실시간 발행
    todays = state.posted_today()
    if not todays:
        _write_feed(cfg, digest=None)
        print("  다이제스트: 오늘 올린 공고 없음 → 게시 생략")
        return []
    chunks = build_digest(todays, cfg)
    _write_feed(cfg, digest={"date": today_iso(), "text": chunks})
    _deliver_digest(cfg, chunks)
    print(f"  다이제스트: 오늘 올린 {len(todays)}건 → {len(chunks)}개 메시지")
    return chunks


def _start_server(cfg: dict) -> None:
    host = cfg["runtime"]["serve_host"]
    port = int(cfg["runtime"]["serve_port"])
    directory = str(Path(cfg["runtime"]["feed_path"]).resolve().parent)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)

    class _Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    httpd = _Srv((host, port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"[serve] http://{host}:{port}/{Path(cfg['runtime']['feed_path']).name} (LAN 폴링용)")


def _online(timeout: float = 3.0) -> bool:
    """인터넷 연결 확인(가벼운 TCP 연결). 스크랩이 아닌 연결성만 점검."""
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def do_loop(cfg: dict, state: State) -> None:
    poll = int(cfg["runtime"]["poll_minutes"]) * 60
    digest_hour = int(cfg["runtime"]["digest_hour"])
    if cfg["runtime"].get("delivery") == "feed":
        _start_server(cfg)  # 폰 방식일 때만 LAN 서빙(노트북 단독이면 불필요)

    check_every = 60  # 연결성·일정 점검 간격(초)
    last_scrape = 0.0  # monotonic. 0 = 시작 직후 즉시 1회
    last_digest_date = None
    was_online = False
    print(
        f"[loop] 폴링 {poll // 60}분 · 다이제스트 매일 {digest_hour}시 · "
        f"연결 끊김→복구 시 즉시 1회. Ctrl+C로 종료."
    )
    while True:
        online = _online()
        now = _dt.datetime.now()
        mono = time.monotonic()
        try:
            if not online:
                if was_online:
                    print("[loop] 인터넷 끊김 — 복구되면 즉시 1회 검색 예정")
            else:
                reconnected = not was_online  # 끊겼다가(또는 시작 후 처음) 연결됨
                if last_digest_date != now.date() and now.hour >= digest_hour:
                    do_digest(cfg, state)  # 하루 1회(첫 온라인 순간 ≥지정시각)
                    last_digest_date = now.date()
                    last_scrape = mono
                elif last_scrape == 0.0 or reconnected or (mono - last_scrape) >= poll:
                    if reconnected and last_scrape != 0.0:
                        print("[loop] 연결 복구 — 즉시 검색")
                    do_realtime(cfg, state)
                    last_scrape = mono
        except Exception as e:  # noqa: BLE001 — 데몬은 절대 죽지 않는다
            print(f"[loop] 이번 주기 오류(계속 진행): {type(e).__name__}: {e}")
        was_online = online
        time.sleep(check_every)


def main() -> None:
    ap = argparse.ArgumentParser(description="CPA 채용공고 → 카카오 오픈채팅 피드 생성")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--digest", action="store_true", help="실시간 + 일일 다이제스트 1회")
    ap.add_argument("--loop", action="store_true", help="24시간 데몬(폴링+다이제스트+LAN 서빙)")
    ap.add_argument("--seed", action="store_true", help="첫 배포용: 현재 공고를 조용히 baseline 등록")
    args = ap.parse_args()

    cfg = load_config(args.config)
    state = State(cfg["runtime"]["state_path"])

    if args.seed:
        do_seed(cfg, state)
    elif args.loop:
        do_loop(cfg, state)
    elif args.digest:
        do_digest(cfg, state)
    else:
        do_realtime(cfg, state)


if __name__ == "__main__":
    main()

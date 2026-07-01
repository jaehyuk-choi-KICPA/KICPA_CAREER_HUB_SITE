"""웹 푸시 알림 발송 — 새 채용공고를 구독자에게 푸시(LLM-free).

3층 모니터·수집 파이프라인과 독립된 발송 단계. **state.json만 입력으로 읽어** export(무거운
수집)의 성공/실패와 무관하게 동작한다. 멱등(idempotent): 매 실행마다 `notified=False`이고 마감 전인
공고를 전부 다시 발송 시도 → 한 run이 드롭돼도 공고는 notified=False로 남아 다음 성공 run이 발송
(유실 아님 = 지연, at-least-eventually).

흐름:
  1. state.json에서 notified=False & 진행중(is_open) 공고 선별. 마감지난 미발송분은 게시 없이 억제.
  2. 구독 목록을 Cloudflare Worker `GET /list`(Bearer)로 조회.
  3. 공고 × 구독으로 pywebpush 발송(VAPID 서명). 개별 try/except(한 구독 실패가 전체 안 막음).
  4. 발송 성공분만 mark_notified(실패분은 다음 run 재시도). 410/404 구독은 Worker에서 정리.
  5. notify_status.json 기록(관측성 — freshness가 '조용한 발송 실패'를 감지).

모드:
  python -m src.notifier          # 발송(기본)
  python -m src.notifier --seed   # 현재 공고를 조용히 baseline 억제(활성화 직전 1회 — 콜드스타트 폭주 방지)
  python -m src.notifier --dry-run  # 발송 없이 대상만 출력

보안: VAPID 개인키·구독 read 토큰은 환경변수에서만(코드/커밋 금지).
견고성: 모든 외부 호출 try/except — 발송 실패가 워크플로 전체를 죽이지 않는다(base.safe_fetch 철학).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import urllib.request
from pathlib import Path

from src.classify import classify_emp_kind, classify_firm, classify_qualification
from src.config import load_config
from src.record import Posting
from src.state import State
from src.util import dday, is_open, today_iso


def _is_susup(entry: dict, cfg: dict) -> bool:
    """state 엔트리가 수습CPA 대상 공고인지 — scope='susup' 구독자 필터용."""
    try:
        p = Posting(
            source=entry.get("source", ""), source_label=entry.get("source_label", ""),
            title=entry.get("title", ""), company=entry.get("company", ""),
            body_excerpt=entry.get("body_excerpt", ""), emp_type=entry.get("emp_type", ""),
            category=entry.get("category", ""), url=entry.get("url", ""),
        )
        return classify_qualification(p, cfg) == "수습CPA"
    except Exception:  # noqa: BLE001 — 판정 실패는 보수적으로 전체 구독자에게만(susup 제외)
        return False


def _is_big4_intern(entry: dict, cfg: dict) -> bool:
    """state 엔트리가 빅4(삼일·삼정·안진·한영) 인턴 공고인지 — scope='big4intern' 구독자 필터용."""
    try:
        p = Posting(
            source=entry.get("source", ""), source_label=entry.get("source_label", ""),
            title=entry.get("title", ""), company=entry.get("company", ""),
            body_excerpt=entry.get("body_excerpt", ""), emp_type=entry.get("emp_type", ""),
            category=entry.get("category", ""), url=entry.get("url", ""),
        )
        return classify_firm(p, cfg) in ("삼일", "삼정", "안진", "한영") and classify_emp_kind(p, cfg) == "인턴"
    except Exception:  # noqa: BLE001 — 판정 실패는 보수적으로 big4intern 구독자 제외
        return False


# ----------------------------------------------------------------------------- 구독 저장소(Worker) I/O

def _fetch_subscriptions(worker_url: str, token: str) -> list[dict]:
    """Worker GET /list(Bearer)로 전체 구독 조회. 실패 시 빈 리스트(→ 아무도 notified 안 됨 → 다음 run 재시도)."""
    if not worker_url or not token:
        return []
    try:
        req = urllib.request.Request(
            worker_url.rstrip("/") + "/list",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "hbmons-notifier"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            data = json.loads(r.read().decode("utf-8"))
        subs = data.get("subscriptions") if isinstance(data, dict) else data
        return [s for s in (subs or []) if isinstance(s, dict) and s.get("endpoint")]
    except Exception as e:  # noqa: BLE001
        print(f"[notify] 구독 목록 조회 실패(이번 발송 보류·다음 run 재시도): {type(e).__name__}: {e}")
        return []


def _prune_subscriptions(worker_url: str, token: str, endpoints: set[str]) -> int:
    """만료(410/404) 구독을 Worker POST /unsubscribe로 정리. 정리 건수 반환(best-effort)."""
    if not worker_url or not endpoints:
        return 0
    done = 0
    for ep in endpoints:
        try:
            body = json.dumps({"endpoint": ep}).encode("utf-8")
            req = urllib.request.Request(
                worker_url.rstrip("/") + "/unsubscribe", data=body, method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}",
                         "User-Agent": "hbmons-notifier"},
            )
            with urllib.request.urlopen(req, timeout=15):  # noqa: S310
                done += 1
        except Exception:  # noqa: BLE001 — 정리 실패는 치명적 아님(다음 run 재시도)
            pass
    return done


# ----------------------------------------------------------------------------- 푸시 본문

def _dday_label(deadline: str) -> str:
    d = dday(deadline)
    if d is None:
        return "상시채용"
    if d < 0:
        return "마감"
    if d == 0:
        return "오늘 마감"
    return f"D-{d}"


def _format_push(entry: dict, cfg: dict) -> dict:
    """state 엔트리 → 푸시 payload {title, body, url, tag}."""
    nf = cfg["notifications"]
    fields = {
        "title": entry.get("title", "") or "새 채용공고",
        "label": entry.get("source_label", "") or "채용",
        "company": entry.get("company", "") or "",
        "deadline": entry.get("deadline", "") or "상시",
        "dday": dday(entry.get("deadline", "")) if entry.get("deadline") else "",
        "dday_label": _dday_label(entry.get("deadline", "")),
        "url": entry.get("url", "") or "https://hbmons.com/",
    }
    try:
        title = nf["title_format"].format(**fields)
        body = nf["body_format"].format(**fields)
    except Exception:  # noqa: BLE001 — 포맷 키 누락 등은 안전 폴백
        title = fields["title"]
        body = f'{fields["label"]} · {fields["dday_label"]}'
    return {"title": title[:120], "body": body[:200], "url": fields["url"], "tag": entry.get("uid", "") or title}


# ----------------------------------------------------------------------------- 발송

def _send_one(subscription: dict, payload: dict, cfg: dict, vapid_priv: str):
    """단일 구독에 1건 발송. 반환: ('ok'|'gone'|'fail', endpoint)."""
    from pywebpush import WebPushException, webpush

    nf = cfg["notifications"]
    ep = subscription.get("endpoint", "")
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid_priv,
            vapid_claims={"sub": nf.get("vapid_subject", "mailto:admin@hbmons.com")},
            ttl=int(nf.get("ttl_seconds", 86400)),
        )
        return "ok", ep
    except WebPushException as e:  # noqa: PERF203
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (404, 410):
            return "gone", ep
        print(f"[notify] 발송 실패(code={code}): {str(e)[:120]}")
        return "fail", ep
    except Exception as e:  # noqa: BLE001
        print(f"[notify] 발송 예외: {type(e).__name__}: {str(e)[:120]}")
        return "fail", ep


def _select_targets(state: State, cfg: dict) -> tuple[list[dict], list[str]]:
    """발송 대상(진행중 미발송)과 억제 대상(마감지난 미발송) 분리."""
    only_open = cfg["notifications"].get("only_new_open", True)
    targets, expired = [], []
    for uid, e in state.entries.items():
        if e.get("notified"):
            continue
        if is_open(e.get("deadline", "")):
            ent = dict(e)
            ent["uid"] = uid
            targets.append(ent)
        elif only_open:
            expired.append(uid)
    # 오래된 것부터(first_seen 오름차순) — max_per_run 캡 시 먼저 발견된 것 우선
    targets.sort(key=lambda x: x.get("first_seen", ""))
    return targets, expired


def run_notify(cfg: dict, *, dry_run: bool = False) -> dict:
    import os

    nf = cfg["notifications"]
    state = State(cfg["runtime"]["state_path"])
    targets, expired = _select_targets(state, cfg)

    # 마감지난 미발송분은 게시 없이 억제(콜드스타트 만료공고 폭주 방지 — run.py do_realtime와 동일)
    if expired:
        state.mark_notified(expired)

    cap = int(nf.get("max_per_run", 25))
    capped = targets[:cap]

    status = {"ran_at": _dt.datetime.now().isoformat(timespec="seconds"),
              "candidates": len(targets), "sending": len(capped),
              "expired_suppressed": len(expired)}

    if dry_run:
        for t in capped:
            print(f"  - [{t.get('source_label')}] {t.get('title')} (마감 {t.get('deadline')})")
        status["dry_run"] = True
        print(f"[notify] dry-run: 발송대상 {len(capped)}/{len(targets)}건, 억제 {len(expired)}건")
        return status

    if not capped:
        state.save()
        status["delivered"] = 0
        status["subscribers"] = None
        _write_status(cfg, status)
        print("[notify] 발송할 새 공고 없음")
        return status

    vapid_priv = os.environ.get("VAPID_PRIVATE_KEY", "")
    token = os.environ.get("SUBS_READ_TOKEN", "")
    worker_url = nf.get("worker_url", "")
    if not vapid_priv:
        print("[notify] VAPID_PRIVATE_KEY 없음 → 발송 불가(state 보존, 다음 run 재시도)")
        status["error"] = "no_vapid_key"
        _write_status(cfg, status)
        return status

    subs = _fetch_subscriptions(worker_url, token)
    status["subscribers"] = len(subs)

    delivered: list[str] = []
    gone: set[str] = set()
    for t in capped:
        payload = _format_push(t, cfg)
        is_susup = _is_susup(t, cfg)            # scope 필터: 수습CPA 전용 구독자는 비-수습 공고 제외
        is_big4intern = _is_big4_intern(t, cfg)  # scope 필터: 빅4 인턴 전용 구독자는 비-(빅4·인턴) 공고 제외
        sent_ok = 0
        transient = 0
        relevant = 0
        for sub in subs:
            scope = sub.get("scope", "all")
            if scope == "susup" and not is_susup:
                continue                         # 이 공고는 이 구독자 범위 밖 — 발송 안 함
            if scope == "big4intern" and not is_big4intern:
                continue                         # 빅4 인턴 구독자 범위 밖 — 발송 안 함
            relevant += 1
            res, ep = _send_one(sub, payload, cfg, vapid_priv)
            if res == "ok":
                sent_ok += 1
            elif res == "gone":
                gone.add(ep)
            else:
                transient += 1
        # 전달 판정: 보낼 대상 없음(구독 0·범위 밖)·1건 이상 성공·전부 만료(유효 수신자 없음) → 전달로 간주(무한재시도 방지).
        # 순수 일시오류(transient>0, 성공 0)만 미전달 → 다음 run 재시도.
        if not subs or relevant == 0 or sent_ok > 0 or transient == 0:
            delivered.append(t["uid"])

    state.mark_notified(delivered, posted_date=today_iso())
    state.save()

    pruned = _prune_subscriptions(worker_url, token, gone)
    status.update({"delivered": len(delivered), "gone_pruned": pruned})
    _write_status(cfg, status)
    print(f"[notify] 발송 {len(delivered)}/{len(capped)}건 · 구독 {len(subs)}명 · 만료정리 {pruned}건")
    return status


def run_seed(cfg: dict) -> int:
    """현재 notified=False 공고를 조용히 모두 억제(발송 없음). 활성화 직전 1회 — 콜드스타트 폭주 방지."""
    state = State(cfg["runtime"]["state_path"])
    uids = [uid for uid, e in state.entries.items() if not e.get("notified")]
    state.mark_notified(uids)
    state.save()
    print(f"[notify] seed: 현재 공고 {len(uids)}건을 baseline 억제(이후 '신규'만 발송)")
    return len(uids)


def _write_status(cfg: dict, status: dict) -> None:
    try:
        path = Path(cfg["notifications"].get("status_path", "docs/data/notify_status.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="웹 푸시 채용 알림 발송")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--seed", action="store_true", help="현재 공고를 조용히 baseline 억제(활성화 직전 1회)")
    ap.add_argument("--dry-run", action="store_true", help="발송 없이 대상만 출력")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not cfg["notifications"].get("enabled") and not (args.seed or args.dry_run):
        # 비활성이어도 status 하트비트는 남긴다 → freshness가 notify_status.json을 STALE로 오판하지 않음
        _write_status(cfg, {"ran_at": _dt.datetime.now().isoformat(timespec="seconds"),
                            "enabled": False})
        print("[notify] notifications.enabled=false → 발송 비활성(seed/dry-run은 가능)")
        return

    if args.seed:
        run_seed(cfg)
    else:
        run_notify(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

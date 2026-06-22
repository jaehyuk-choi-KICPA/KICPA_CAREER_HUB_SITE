"""수동 시험 푸시 발송 — GitHub Actions `push-test.yml`(workflow_dispatch) 전용.

VAPID 개인키는 GitHub Secret(`VAPID_PRIVATE_KEY`)에만 존재해 **로컬에선 발송 불가**.
이 스크립트를 Actions에서 돌려 현재 구독자에게 '시험 알림' 1건을 보낸다.
state(공고 발송 이력)를 건드리지 않으므로 몇 번을 돌려도 안전(멱등).

notifier 내부(`_fetch_subscriptions`/`_send_one`)를 그대로 재사용 — 실제 발송 경로와 동일.
환경변수: `VAPID_PRIVATE_KEY`(필수)·`SUBS_READ_TOKEN`(구독 조회)·`PUSH_BODY`(선택, 본문)
·`PUSH_URL`(선택, 알림이 가리킬 URL — 없으면 jobs.json 첫 공고로 '뒤로가기=홈' 동선까지 테스트).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config  # noqa: E402
from src import notifier  # noqa: E402


def _sample_url() -> str:
    """테스트 알림이 가리킬 공고 URL — env `PUSH_URL` 우선, 없으면 jobs.json 첫 공고, 없으면 홈.
    실제 외부 공고 URL이면 sw.js가 홈(?goto) 경유로 열어 '뒤로 가기=회법몬 홈' 동선까지 테스트된다."""
    u = os.environ.get("PUSH_URL", "").strip()
    if u:
        return u
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = json.loads(Path(root, "docs/data/jobs.json").read_text(encoding="utf-8"))
        for p in data.get("postings") or []:
            if p.get("url"):
                return p["url"]
    except Exception:  # noqa: BLE001
        pass
    return "https://hbmons.com/"


def main() -> int:
    cfg = load_config()
    nf = cfg["notifications"]
    priv = os.environ.get("VAPID_PRIVATE_KEY", "")
    token = os.environ.get("SUBS_READ_TOKEN", "")
    if not priv:
        print("VAPID_PRIVATE_KEY 없음 → 발송 불가(GitHub Secret 확인)")
        return 1

    url = _sample_url()
    body = os.environ.get("PUSH_BODY", "").strip() or \
        "눌러서 공고로 이동 → 공고에서 '뒤로 가기' 하면 회법몬 홈이 떠야 정상! 🏠"
    payload = {
        "title": "회법몬 테스트 알림 🔔",
        "body": body,
        "url": url,
        "tag": "hbmons-test",
    }
    print(f"테스트 공고 URL: {url}")

    subs = notifier._fetch_subscriptions(nf.get("worker_url", ""), token)
    print(f"구독자 {len(subs)}명에게 시험 발송")
    ok = gone = fail = 0
    for s in subs:
        st, ep = notifier._send_one(s, payload, cfg, priv)
        host = ep.split("/")[2] if "://" in ep else ep[:30]
        print(f"  -> {st}  ({host})")
        ok += st == "ok"
        gone += st == "gone"
        fail += st == "fail"
    print(f"결과: ok={ok} gone={gone} fail={fail} (총 {len(subs)})")
    # 발송 0건인데 구독자가 있으면 실패(키 불일치 등) → 워크플로 빨강으로 신호
    return 0 if (ok > 0 or len(subs) == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())

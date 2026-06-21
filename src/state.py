"""공고 상태 저장소 — 중복제거 + 다이제스트용 '현재 게시중' 현황.

state.json: uid -> {source,label,title,company,deadline,posted_date,url,category,
                    first_seen, notified}
- 신규(실시간용): 이번에 처음 본 uid → 반환해서 실시간 알림, 이후 notified=True.
- 게시중(다이제스트용): 마감일 미도래 항목.
- 마감 지난 항목은 정리해 저장소를 가볍게 유지.
조서 프로젝트 cache.py 의 '키 기반 JSON 영속' 발상을 차용.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from src.record import Posting
from src.util import is_open


class State:
    def __init__(self, path: str = "state.json"):
        self.path = Path(path)
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — 손상 시 새로 시작
                self.entries = {}

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def deadlines_by_native_id(self) -> dict[str, str]:
        """KICPA 등 상세 보강 캐시용: native_id -> deadline(있는 것만)."""
        return {
            e["native_id"]: e["deadline"]
            for e in self.entries.values()
            if e.get("native_id") and e.get("deadline")
        }

    def bodies_by_native_id(self) -> dict[str, str]:
        """KICPA 상세 본문 캐시용: native_id -> body_excerpt(있는 것만). 한 번 긁은 본문 재사용."""
        return {
            e["native_id"]: e["body_excerpt"]
            for e in self.entries.values()
            if e.get("native_id") and e.get("body_excerpt")
        }

    def update(self, postings: list[Posting]) -> list[Posting]:
        """스크랩 결과를 반영하고 **이번에 새로 발견된** 공고 리스트를 반환.

        매 호출 시 본 공고의 last_seen(마지막 목격 시각)을 갱신한다 → carry_forward의 grace 판정 기준.
        """
        now = _dt.datetime.now().isoformat(timespec="seconds")
        today = _dt.date.today().isoformat()
        new: list[Posting] = []
        for p in postings:
            e = self.entries.get(p.uid)
            if e is None:
                self.entries[p.uid] = {
                    **p.to_dict(),
                    "first_seen": now,
                    "last_seen": today,
                    "notified": False,
                }
                new.append(p)
            else:
                # 가변 필드 갱신(마감일·근무지·고용형태가 뒤늦게 채워지는 경우 등) + 목격 시각 갱신
                for k in ("title", "company", "deadline", "posted_date", "category",
                          "location", "emp_type", "source_label", "url", "body_excerpt"):
                    if getattr(p, k):   # 빈 값은 덮어쓰지 않음(캐시된 body를 carried 빈값이 지우지 않게)
                        e[k] = getattr(p, k)
                e["last_seen"] = today
        return new

    def carry_forward(self, present_uids: set[str], grace_days: int,
                      today: str | None = None) -> list[Posting]:
        """이번 스크랩에 빠졌지만 **아직 마감 전이고 최근(grace_days 이내) 목격된** 공고를 복원.

        KICPA가 살아있는 공고를 목록에서 일시적으로 내렸다 올리며 깜빡이는 문제 대응
        (상세페이지는 살아있음). last_seen이 grace_days를 넘으면 더는 유지하지 않아 좀비 공고를 막는다.
        """
        today = today or _dt.date.today().isoformat()
        cutoff = (_dt.date.today() - _dt.timedelta(days=grace_days)).isoformat()
        fields = set(Posting.__dataclass_fields__)
        out: list[Posting] = []
        for uid, e in self.entries.items():
            if uid in present_uids:
                continue
            if not is_open(e.get("deadline", ""), today=today):
                continue
            if (e.get("last_seen") or "") < cutoff:   # 너무 오래 안 보이면 복원 중단
                continue
            out.append(Posting(**{k: e.get(k, "") for k in fields}))
        return out

    def mark_notified(self, uids: list[str], posted_date: str | None = None) -> None:
        """notified 처리. posted_date를 주면 '그날 게시한 공고'로 기록(일일 다이제스트용).
        억제(만료 등 미게시)분은 posted_date 없이 호출 → 다이제스트에 안 잡힘."""
        for uid in uids:
            if uid in self.entries:
                self.entries[uid]["notified"] = True
                if posted_date:
                    self.entries[uid]["notified_date"] = posted_date

    def open_postings(self, today: str | None = None) -> list[dict]:
        """현재 게시중(마감 미도래) 항목."""
        return [e for e in self.entries.values() if is_open(e.get("deadline", ""), today=today)]

    def posted_today(self, today: str | None = None) -> list[dict]:
        """오늘 실제로 게시한 공고 — 일일 다이제스트용."""
        today = today or _dt.date.today().isoformat()
        return [e for e in self.entries.values() if e.get("notified_date") == today]

    def prune_expired(self, today: str | None = None) -> int:
        """마감 지난 항목 제거. 제거 건수 반환."""
        today = today or _dt.date.today().isoformat()
        dead = [
            uid
            for uid, e in self.entries.items()
            if e.get("deadline") and e["deadline"] < today
        ]
        for uid in dead:
            del self.entries[uid]
        return len(dead)

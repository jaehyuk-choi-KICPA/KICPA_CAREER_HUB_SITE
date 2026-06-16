"""게시 메시지 생성 — 개별(실시간) + 다이제스트(일일) 2종. 템플릿은 config에서.

dict(=Posting.to_dict() 또는 state 엔트리)를 입력으로 받아 소스 무관하게 동작.
"""

from __future__ import annotations

from src.util import today_iso

# 다이제스트에서 소스 노출 순서
_SOURCE_ORDER = ["kicpa_susup", "kicpa_cpa", "samil", "samjong", "anjin", "hanyoung"]


def _deadline_text(d: dict) -> str:
    return d.get("deadline") or "상시채용"


def format_item(d: dict, cfg: dict) -> str:
    """개별(실시간) 메시지."""
    f = cfg["formats"]
    body = f["item"].format(
        label=d.get("source_label", ""),
        title=d.get("title", ""),
        company=d.get("company") or "-",
        deadline=_deadline_text(d),
        url=d.get("url", ""),
        posted=d.get("posted_date", ""),
    )
    excerpt = d.get("body_excerpt") or ""
    if excerpt:
        body += f"\n{f['divider']}\n{excerpt}"
    return body


def _sort_key(d: dict):
    src = d.get("source", "")
    order = _SOURCE_ORDER.index(src) if src in _SOURCE_ORDER else len(_SOURCE_ORDER)
    return (order, d.get("deadline") or "9999-99-99")


def build_digest(open_entries: list[dict], cfg: dict, date: str | None = None) -> list[str]:
    """현재 게시중 공고 다이제스트. 길면 여러 메시지로 분할해 리스트로 반환."""
    f = cfg["formats"]
    date = date or today_iso()
    entries = sorted(open_entries, key=_sort_key)

    header = f["digest_header"].format(date=date, count=len(entries))
    divider = f["divider"]

    if not entries:
        return [f"{header}\n{divider}\n(오늘 올라온 공고가 없습니다)"]

    lines = [
        f["digest_line"].format(
            label=d.get("source_label", ""),
            title=d.get("title", ""),
            deadline=_deadline_text(d),
            url=d.get("url", ""),
        )
        for d in entries
    ]

    # 공고 사이 빈 줄로 가독성 ↑, 길이 제한에 맞춰 분할
    max_chars = int(f.get("digest_max_chars", 1800))
    chunks: list[str] = []
    cur: list[str] = []
    base_len = len(header) + len(divider) + 2

    def _flush(first: bool) -> None:
        head = header if first else f"{header} (계속)"
        chunks.append(f"{head}\n{divider}\n\n" + "\n\n".join(cur))

    cur_len = base_len
    first = True
    for line in lines:
        add = len(line) + 2  # 빈 줄 포함
        if cur and cur_len + add > max_chars:
            _flush(first)
            first = False
            cur = []
            cur_len = base_len
        cur.append(line)
        cur_len += add
    if cur:
        _flush(first)
    return chunks

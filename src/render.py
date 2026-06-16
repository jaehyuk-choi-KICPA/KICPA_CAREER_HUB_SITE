"""헤드리스 브라우저 렌더 헬퍼 — JS로 렌더되는 인사이트/간행물 페이지 수집용.

requests로 안 잡히는 SPA 페이지를 Chromium으로 렌더해 HTML을 반환한다.
Playwright 미설치/실패 시 None을 반환(어댑터는 빈 결과로 수렴 — 전체실패 금지).
"""

from __future__ import annotations


def render_html(url: str, *, wait_ms: int = 2500, timeout_ms: int = 30000) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 — 미설치 환경
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                )
            )
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:  # noqa: BLE001 — networkidle 타임아웃이어도 현재 DOM 사용
                pass
            page.wait_for_timeout(wait_ms)
            html = page.content()
            browser.close()
            return html
    except Exception:  # noqa: BLE001
        return None

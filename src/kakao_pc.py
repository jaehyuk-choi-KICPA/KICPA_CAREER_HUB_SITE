"""카카오톡 PC(윈도우 데스크톱 앱) 게시기 — 노트북 단독 운영용 (폰/메신저봇R 대체).

카카오는 오픈채팅 게시 공식 API가 없으므로, 노트북에서 카톡을 올리려면 **카톡 PC 앱을
GUI 자동화로 제어**하는 수밖에 없다. 여기서는 대상 오픈채팅방 창을 찾아 입력창에
메시지를 **클립보드로 붙여넣고(Enter로 전송)** 한다. 한글·여러 줄도 한 건으로 안전히 전송.

전제(반드시):
  1) 카카오톡 PC 설치·로그인.
  2) 대상 오픈채팅방을 **별도 창으로 열어둠**(채팅방 더블클릭 → 새 창). 창 제목 = 방 이름.
  3) 카톡 설정에서 "Enter로 전송" 활성화(기본값).

⚠️ 이 환경에서는 GUI를 띄울 수 없어 무인 검증 불가 → **사용자 노트북에서 직접 테스트**:
     python -m src.kakao_pc --list                 # 열린 창 제목 확인(방 이름 찾기)
     python -m src.kakao_pc "방이름" "테스트 메시지"   # 실제 1건 전송 테스트
  컨트롤 클래스/인덱스는 카톡 버전마다 다를 수 있어, 안 되면 _INPUT_CLASS/found_index 조정.
"""

from __future__ import annotations

import sys
import time

# 카톡 PC 입력창 컨트롤(버전에 따라 다를 수 있음)
_INPUT_CLASS = "RichEdit20W"


def list_windows() -> list[str]:
    """현재 열린 최상위 창 제목 목록(방 이름 확인용)."""
    from pywinauto import Desktop

    titles = []
    for w in Desktop(backend="win32").windows():
        try:
            t = w.window_text()
        except Exception:  # noqa: BLE001
            continue
        if t and t.strip():
            titles.append(t)
    return sorted(set(titles))


def _room_window(room: str):
    """방 제목으로 채팅 창을 찾는다. 같은 제목 창이 여럿이면(미리보기 등)
    보이고 면적이 가장 큰 진짜 채팅 창을 고른다."""
    from pywinauto import Desktop

    wins = [
        w
        for w in Desktop(backend="win32").windows(top_level_only=True)
        if room in (w.window_text() or "")
    ]
    if not wins:
        raise RuntimeError(f"방 창을 찾을 수 없음: {room}")

    def score(w):
        try:
            r = w.rectangle()
            vis = 1 if w.is_visible() else 0
            mini = 1 if w.is_minimized() else 0
            onscreen = 1 if (r.top >= 0 and r.left >= 0) else 0  # 화면 밖(음수좌표) 미리보기창 배제
            return (vis - mini, onscreen, r.width() * r.height())
        except Exception:  # noqa: BLE001
            return (0, 0, 0)

    return max(wins, key=score)


def send_message(room: str, text: str, *, delay: float = 0.5) -> None:
    """대상 방 창에 메시지 1건 전송.

    카톡은 입력칸을 표준 컨트롤로 노출하지 않으므로(win32/UIA 모두), 창을 앞으로 가져와
    **입력 영역(창 하단 중앙)을 좌표 클릭**해 포커스를 준 뒤 클립보드 붙여넣기+Enter 한다.
    여러 줄 메시지도 붙여넣기면 한 건으로 전송된다.
    """
    import pyperclip
    from pywinauto import mouse
    from pywinauto.keyboard import send_keys

    win = _room_window(room)
    win.set_focus()
    time.sleep(0.3)

    # 포커스 후 갱신된 창 위치 기준으로 입력 영역(하단 중앙) 클릭
    r = win.rectangle()
    click_x = (r.left + r.right) // 2
    click_y = r.bottom - 40  # 하단 입력창 근처
    mouse.click(coords=(click_x, click_y))
    time.sleep(0.2)

    pyperclip.copy(text)
    time.sleep(0.15)
    send_keys("^v")          # 붙여넣기(여러 줄도 한 메시지로 유지)
    time.sleep(delay)
    send_keys("{ENTER}")     # 전송
    time.sleep(delay)


def send_messages(room: str, texts: list[str], *, delay: float = 0.5, gap: float = 1.5) -> int:
    """여러 건 순차 전송. 성공 건수 반환. 한 건 실패해도 다음 건 진행(전체실패 금지)."""
    sent = 0
    for t in texts:
        if not t:
            continue
        try:
            send_message(room, t, delay=delay)
            sent += 1
            time.sleep(gap)  # 도배 방지 간격
        except Exception as e:  # noqa: BLE001
            print(f"[kakao_pc] 전송 실패(계속): {type(e).__name__}: {e}")
    return sent


def _main(argv: list[str]) -> None:
    if not argv or argv[0] == "--list":
        print("열린 창 제목:")
        for t in list_windows():
            print(" -", t)
        return
    if len(argv) < 2:
        print('사용법: python -m src.kakao_pc "방이름" "메시지"')
        return
    room, text = argv[0], argv[1]
    send_message(room, text)
    print(f"전송 시도 완료 → {room}")


if __name__ == "__main__":
    _main(sys.argv[1:])

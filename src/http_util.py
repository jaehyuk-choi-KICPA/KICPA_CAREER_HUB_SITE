"""공통 HTTP 유틸 — 어댑터들이 공유하는 예의 바른 세션/요청.

- 단일 세션 재사용(쿠키·연결 유지)
- User-Agent 지정, 재시도, 요청 간 짧은 대기(robots 예의)
- 인코딩 자동 보정(국내 사이트의 EUC-KR/CP949 대응)
"""

from __future__ import annotations

import time

import requests

# 연락처 표기는 예의(차단/문의 대비). 실제 운영 시 본인 연락처로 교체 가능.
USER_AGENT = "Mozilla/5.0 (compatible; CpaJobAlertBot/1.0)"

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _session = s
    return _session


def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = 20,
    encoding: str | None = None,
    retries: int = 2,
    pause: float = 1.0,
) -> requests.Response:
    """GET 요청 + 재시도 + 인코딩 보정. 성공 응답을 반환, 끝까지 실패하면 예외 전파.

    headers: 이 요청에만 적용할 헤더(세션 기본값에 덮어씀). 예: 봇 차단 우회용 브라우저 UA.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = session().get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            if encoding:
                r.encoding = encoding
            elif not r.encoding or r.encoding.lower() == "iso-8859-1":
                # requests가 헤더에서 못 잡으면 본문 기준 추정(국내 사이트 EUC-KR 대비)
                r.encoding = r.apparent_encoding or "utf-8"
            time.sleep(pause)  # 예의: 연속 요청 사이 간격
            return r
        except Exception as e:  # noqa: BLE001 — 마지막에 다시 던짐
            last_exc = e
            time.sleep(pause * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def post(
    url: str,
    *,
    data: dict | None = None,
    json: dict | None = None,
    headers: dict | None = None,
    timeout: int = 20,
    encoding: str | None = None,
    retries: int = 2,
    pause: float = 1.0,
) -> requests.Response:
    """POST 요청 + 재시도 + 인코딩 보정.

    data: 폼 인코딩 바디(ATS AJAX 목록). json: JSON 바디(REST API). headers: 요청별 헤더
    (예: recruiter.co.kr API의 `prefix` 헤더). data/json 중 하나만 쓴다.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if json is not None:
                r = session().post(url, json=json, headers=headers, timeout=timeout)
            else:
                r = session().post(url, data=data or {}, headers=headers, timeout=timeout)
            r.raise_for_status()
            if encoding:
                r.encoding = encoding
            elif not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            time.sleep(pause)
            return r
        except Exception as e:  # noqa: BLE001
            last_exc = e
            time.sleep(pause * (attempt + 1))
    assert last_exc is not None
    raise last_exc

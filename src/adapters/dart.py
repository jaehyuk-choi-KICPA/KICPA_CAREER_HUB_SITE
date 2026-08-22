"""DART 전자공시 Open API 어댑터 — 기업별 **감사 정보**(감사인·감사의견·핵심감사사항·감사보수).

왜 스크래핑이 아니라 Open API인가: 공식 API가 안정적·합법적이고 저작권도 안전하다
(**수치와 링크만** 저장하고 원문은 전재하지 않는다). 결정론적 공공 API라 코어 LLM-free 원칙과 충돌하지 않는다.

이 어댑터가 만드는 것은 "산업군 → 기업 → **그 회사의 감사 이슈**" 동선의 마지막 칸이다.
재무 수치는 일부러 담지 않는다 — 화면이 무거워지는 데 비해 DART 링크로 바로 보는 편이 낫고,
감사 지원자에게 실제로 값진 건 **핵심감사사항(KAM)**이기 때문이다. 그 회사 감사인이 무엇을 위험으로
봤는지가 그대로 적혀 있어, 산업 이해와 감사 관점을 잇는 가장 짧은 다리가 된다.

정찰 노하우(실측 — 사전 57곳 중 48곳 매칭, 그중 감사인·의견·보수 44곳 / KAM 42곳):
  - `api/accnutAdtorNmNdAdtOpinion.json` → `adtor`(감사인), `adt_opinion`(감사의견),
    `core_adt_matter`(**핵심감사사항**), `emphs_matter`(강조사항). 사업연도별 여러 행이 오므로
    `bsns_year`에 '당기'가 든 행을 고른다.
  - `api/adtServcCnclsSttus.json` → `adt_cntrct_dtls_mendng`(감사보수, 백만원),
    `adt_cntrct_dtls_time`(감사시간). 표준감사시간 논의의 실물 데이터다.
  - `corpCode.xml`은 비상장 포함 10만 건대라 동명이인이 흔하다 → **stock_code 있는 상장사를 우선**.
    정식 명칭이 통칭과 다른 곳이 많아(네이버→NAVER, KT→케이티, 한국전력→한국전력공사)
    config의 `dart` 필드로 보정한다.
  - 원문 뷰어는 `dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}` (키 불필요).
  - 한도는 일 20,000건. 기업 60곳 × 2콜 × 주 1회면 약 120콜이라 여유가 크다.

키 정책(VOYAGE_API_KEY와 동일한 게이트 패턴):
  - `DART_API_KEY` 환경변수(= GitHub Secret)에서만. 코드·저장소에 절대 넣지 않는다.
  - **키가 없으면 전체 no-op** → companies.json을 새로 쓰지 않고, 프론트는 DART 검색 링크만 노출한다.
"""

from __future__ import annotations

import datetime as _dt
import io
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile

from src.http_util import get

_API = "https://opendart.fss.or.kr/api"
_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
_EMPTY = ("", "-", "해당사항 없음", "해당사항없음", "없음")


def api_key() -> str:
    return (os.environ.get("DART_API_KEY") or "").strip()


def _json(path: str, **params) -> dict:
    params["crtfc_key"] = api_key()
    return get(f"{_API}/{path}", params=params, timeout=20).json()


def _clean(v: str) -> str:
    v = re.sub(r"\s+", " ", (v or "")).strip()
    return "" if v in _EMPTY else v


def _current(rows: list[dict]) -> dict:
    """사업연도 행들 중 '당기' 행. 표기가 제각각이라 못 찾으면 첫 행으로 폴백."""
    for r in rows:
        if "당기" in (r.get("bsns_year") or ""):
            return r
    return rows[0] if rows else {}


def split_kam(text: str) -> list[str]:
    """핵심감사사항 원문 → 항목 리스트.

    DART 원문은 매체가 아니라 회사가 쓴 자유 텍스트라 형식이 제각각이다(실측):
      "1. 건설중인자산의 감가상각개시시점 평가\\n2. 재화의 판매장려활동에 대한 매출차감의 정확성"
      "가. (별도재무제표) 기계장치의 감가상각개시시점에 대한 적정성 검토"
      "1. \\n영업권이 배분된 현금창출단위의 손상 검사"   ← 번호와 본문이 다른 줄
    번호만 있는 줄은 다음 줄과 합치고, 말머리 번호를 떼어 항목만 남긴다.
    """
    if not _clean(text):
        return []
    lines = [ln.strip() for ln in (text or "").replace("\r", "").split("\n")]
    lines = [ln for ln in lines if ln]

    merged: list[str] = []
    pending = False
    for ln in lines:
        if re.fullmatch(r"(?:[0-9]{1,2}|[가-힣])\s*[.)]", ln) or re.fullmatch(r"[①-⑳]", ln):
            pending = True          # 번호만 있는 줄 → 다음 줄과 합친다
            continue
        if pending and merged:
            merged[-1] = f"{merged[-1]} {ln}".strip() if merged[-1] == "" else ln
            pending = False
            if merged[-1]:
                continue
        merged.append(ln)
        pending = False

    out: list[str] = []
    for x in merged:
        x = re.sub(r"^\s*(?:[0-9]{1,2}|[가-힣])\s*[.)]\s*", "", x)
        x = re.sub(r"^\s*[①-⑳]\s*", "", x)
        x = re.sub(r"\s+", " ", x).strip()
        if len(x) >= 5 and x not in out:
            out.append(x)
    return out[:5]


def corp_code_map() -> dict[str, dict]:
    """회사명 → {corp_code, stock_code} (상장사 우선).

    corpCode.xml은 비상장 포함 10만 건대라 동명이인이 흔하다. **stock_code가 있는 상장사를 우선**
    채택해야 '삼성전자' 같은 이름이 엉뚱한 비상장 법인으로 잡히지 않는다.
    """
    r = get(f"{_API}/corpCode.xml", params={"crtfc_key": api_key()}, timeout=60)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        raw = z.read(z.namelist()[0])
    out: dict[str, dict] = {}
    for el in ET.fromstring(raw).iter("list"):
        name = (el.findtext("corp_name") or "").strip()
        if not name:
            continue
        rec = {"corp_code": (el.findtext("corp_code") or "").strip(),
               "stock_code": (el.findtext("stock_code") or "").strip()}
        prev = out.get(name)
        if prev is None or (not prev["stock_code"] and rec["stock_code"]):
            out[name] = rec
    return out


def _audit(corp_code: str, year: int) -> dict:
    """감사인·감사의견·핵심감사사항·감사보수. 최신 사업보고서가 아직 없으면 한 해 뒤로 재시도."""
    for y in (year, year - 1):
        try:
            op = _json("accnutAdtorNmNdAdtOpinion.json", corp_code=corp_code,
                       bsns_year=str(y), reprt_code="11011")
        except Exception:  # noqa: BLE001
            return {}
        rows = (op.get("list") or []) if op.get("status") == "000" else []
        if not rows:
            time.sleep(0.2)
            continue
        cur = _current(rows)
        out = {
            "fy": y,
            "stlm_dt": _clean(cur.get("stlm_dt")),
            "auditor": _clean(cur.get("adtor")),
            "opinion": _clean(cur.get("adt_opinion")),
            "kam": split_kam(cur.get("core_adt_matter")),
            "emphasis": _clean(cur.get("emphs_matter")),
            "report_url": _VIEWER.format(cur.get("rcept_no") or "") if cur.get("rcept_no") else "",
        }
        time.sleep(0.2)
        try:
            ad = _json("adtServcCnclsSttus.json", corp_code=corp_code,
                       bsns_year=str(y), reprt_code="11011")
            arows = (ad.get("list") or []) if ad.get("status") == "000" else []
            a = _current(arows)
            out["fee"] = _clean(a.get("adt_cntrct_dtls_mendng"))      # 백만원
            out["hours"] = _clean(a.get("adt_cntrct_dtls_time"))
        except Exception:  # noqa: BLE001 — 보수는 부가 정보라 실패해도 감사인은 살린다
            pass
        return out
    return {}


def build_companies(cfg: dict) -> dict | None:
    """기업 사전의 회사들에 대해 감사 정보를 모은다.

    키가 없으면 None을 돌려 호출부가 파일을 덮어쓰지 않게 한다(무키 = 기능 비활성, 사이트는 정상).
    한 회사가 실패해도 나머지는 살린다(전체실패 금지).
    """
    if not api_key():
        print("  기업정보: DART_API_KEY 없음 → 건너뜀(프론트는 검색 링크만 노출)")
        return None

    d = cfg["dashboard"]
    sheet = d.get("industry_companies") or {}
    try:
        names = corp_code_map()
    except Exception as e:  # noqa: BLE001
        print(f"  기업정보: corpCode 내려받기 실패({type(e).__name__}) → 건너뜀")
        return None

    year = _dt.date.today().year - 1
    out: dict = {}
    miss: list[str] = []
    for canon, meta in sheet.items():
        rec = names.get((meta or {}).get("dart") or canon)
        if not rec:
            miss.append(canon)
            continue
        try:
            info = _audit(rec["corp_code"], year)
        except Exception as e:  # noqa: BLE001 — 한 회사 실패가 전체를 막지 않게
            print(f"    {canon}: {type(e).__name__}")
            continue
        if info.get("auditor"):
            out[canon] = {"corp_code": rec["corp_code"], "stock_code": rec["stock_code"], **info}

    if miss:
        print(f"  기업정보: DART 미매칭 {len(miss)}곳 — {', '.join(miss[:8])}")
    kam = sum(1 for v in out.values() if v.get("kam"))
    print(f"  기업정보: {len(out)}곳 (핵심감사사항 {kam}곳)")
    return {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"), "companies": out}

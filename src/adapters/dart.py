"""DART 전자공시 Open API 어댑터 — 기업별 감사인 + 3개년 주요계정 + 최근 공시.

왜 스크래핑이 아니라 Open API인가: 공식 API가 안정적·합법적이고 저작권도 안전하다
(**수치와 링크만** 저장하고 원문은 전재하지 않는다). 결정론적 공공 API라 코어 LLM-free 원칙과도 충돌하지 않는다.

이 어댑터가 만드는 것은 "산업군 → 기업 → **재무제표**" 동선의 마지막 칸이다.
특히 `flr_nm`(공시 제출인명)으로 **그 회사의 감사인**을 알아낼 수 있는 게 핵심이다 —
감사보고서는 감사인이 제출하므로 제출인이 곧 회계법인이다.

키 정책(VOYAGE_API_KEY와 동일한 게이트 패턴):
  - `DART_API_KEY` 환경변수(= GitHub Secret)에서만 읽는다. 코드·저장소에 절대 넣지 않는다.
  - **키가 없으면 전체 no-op** → companies.json을 만들지 않고, 프론트는 DART 검색 링크만 노출한다
    (사이트는 정상 동작). 무키 오프라인 보장 유지.

정찰 노하우(실측):
  - `api/list.json` 응답 필드에 `flr_nm`(제출인)·`rcept_no`(접수번호)·`report_nm`(보고서명)이 있다.
    공시유형 `pblntf_ty`는 A=정기공시, F=외부감사관련. 감사보고서는 F에 들어 있다.
  - `api/fnlttSinglAcnt.json`은 `reprt_code=11011`(사업보고서) **한 번 호출로 3개년**을 준다
    (thstrm=당기 / frmtrm=전기 / bfefrmtrm=전전기). 2015년 이후 제공.
  - 원문 뷰어는 `dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}` (키 불필요).
  - 한도는 일 20,000건. 기업 60곳 × 주 1회면 약 180콜이라 여유가 크다.
"""

from __future__ import annotations

import datetime as _dt
import io
import os
import time
import xml.etree.ElementTree as ET
import zipfile

from src.http_util import get

_API = "https://opendart.fss.or.kr/api"
_VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"

# 화면에 세울 주요계정(순서 = 표시 순서). DART 계정명 표기가 흔들려 별칭을 함께 둔다.
_ACCOUNTS = {
    "매출액": ("매출액", "수익(매출액)", "영업수익"),
    "영업이익": ("영업이익", "영업이익(손실)"),
    "당기순이익": ("당기순이익", "당기순이익(손실)"),
    "자산총계": ("자산총계",),
    "부채총계": ("부채총계",),
    "자본총계": ("자본총계",),
}


def api_key() -> str:
    return (os.environ.get("DART_API_KEY") or "").strip()


def _json(path: str, **params) -> dict:
    params["crtfc_key"] = api_key()
    r = get(f"{_API}/{path}", params=params, timeout=20)
    return r.json()


def _num(s: str):
    """DART 금액 문자열 → int. 빈 값·'-'는 None(0과 구분해야 '자료 없음'을 표시할 수 있다)."""
    s = (s or "").replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


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


def _filings(corp_code: str, years: int) -> tuple[str, list[dict]]:
    """(감사인, 최근 공시 목록). 정기공시(A) + 외부감사관련(F)을 각각 조회한다.

    한 번에 다 받으면 100건 상한에 밀려 감사보고서가 빠질 수 있어 유형을 나눠 부른다.
    """
    end = _dt.date.today()
    bgn = end - _dt.timedelta(days=365 * years)
    rows: list[dict] = []
    for ty in ("A", "F"):
        try:
            d = _json("list.json", corp_code=corp_code, pblntf_ty=ty,
                      bgn_de=bgn.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d"),
                      page_count=100, sort="date", sort_mth="desc")
        except Exception:  # noqa: BLE001 — 한 유형이 실패해도 나머지는 살린다
            continue
        if d.get("status") == "000":
            rows.extend(d.get("list") or [])
        time.sleep(0.2)

    auditor = ""
    for it in rows:                      # 감사보고서 제출인 = 그 회사의 감사인
        if "감사보고서" in (it.get("report_nm") or "") and (it.get("flr_nm") or "").strip():
            auditor = it["flr_nm"].strip()
            break

    rows.sort(key=lambda i: i.get("rcept_dt") or "", reverse=True)
    filings = [{"name": (i.get("report_nm") or "").strip(),
                "date": i.get("rcept_dt") or "",
                "filer": (i.get("flr_nm") or "").strip(),
                "url": _VIEWER.format(i.get("rcept_no") or "")}
               for i in rows[:8]]
    return auditor, filings


def _financials(corp_code: str, year: int) -> tuple[int, dict]:
    """(사업연도, {계정: {thstrm, frmtrm, bfefrmtrm}}). 사업보고서 1회 호출로 3개년.

    연결(CFS)을 우선하되 없으면 개별(OFS). 최신 사업보고서가 아직 안 나온 시기를 감안해 한 해 뒤로도 시도한다.
    """
    for y in (year, year - 1):
        try:
            d = _json("fnlttSinglAcnt.json", corp_code=corp_code, bsns_year=str(y), reprt_code="11011")
        except Exception:  # noqa: BLE001
            return 0, {}
        if d.get("status") != "000":
            time.sleep(0.2)
            continue
        rows = d.get("list") or []
        has_cfs = any(r.get("fs_div") == "CFS" for r in rows)
        want = "CFS" if has_cfs else "OFS"
        out: dict = {}
        for label, aliases in _ACCOUNTS.items():
            for r in rows:
                if r.get("fs_div") == want and (r.get("account_nm") or "").strip() in aliases:
                    out[label] = {"thstrm": _num(r.get("thstrm_amount")),
                                  "frmtrm": _num(r.get("frmtrm_amount")),
                                  "bfefrmtrm": _num(r.get("bfefrmtrm_amount"))}
                    break
        if out:
            return y, out
    return 0, {}


def build_companies(cfg: dict) -> dict | None:
    """기업 사전(config)의 회사들에 대해 감사인·3개년 주요계정·최근 공시를 모은다.

    키가 없으면 None을 돌려 호출부가 파일을 만들지 않게 한다(무키 = 기능 비활성, 사이트는 정상).
    한 회사가 실패해도 나머지는 살린다(전체실패 금지).
    """
    if not api_key():
        print("  기업정보: DART_API_KEY 없음 → 건너뜀(프론트는 검색 링크만 노출)")
        return None

    d = cfg["dashboard"]
    sheet = d.get("industry_companies") or {}
    years = d.get("dart_filing_years", 2)
    try:
        names = corp_code_map()
    except Exception as e:  # noqa: BLE001
        print(f"  기업정보: corpCode 내려받기 실패({type(e).__name__}) → 건너뜀")
        return None

    this_year = _dt.date.today().year
    out: dict = {}
    miss: list[str] = []
    for canon, meta in sheet.items():
        query = (meta or {}).get("dart") or canon
        rec = names.get(query)
        if not rec:
            miss.append(canon)
            continue
        try:
            auditor, filings = _filings(rec["corp_code"], years)
            fy, fin = _financials(rec["corp_code"], this_year - 1)
        except Exception as e:  # noqa: BLE001 — 한 회사 실패가 전체를 막지 않게
            print(f"    {canon}: {type(e).__name__}")
            continue
        out[canon] = {"corp_code": rec["corp_code"], "stock_code": rec["stock_code"],
                      "auditor": auditor, "fy": fy, "financials": fin, "filings": filings}
        time.sleep(0.2)

    if miss:
        print(f"  기업정보: DART 미매칭 {len(miss)}곳 — {', '.join(miss[:8])}")
    print(f"  기업정보: {len(out)}곳 (감사인 확인 {sum(1 for v in out.values() if v['auditor'])}곳)")
    return {"generated_at": _dt.datetime.now().isoformat(timespec="seconds"), "companies": out}

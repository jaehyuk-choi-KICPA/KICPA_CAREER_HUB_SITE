"""EY한영 채용 어댑터 (eycareers-kr.recruiter.co.kr — recruiter.co.kr SaaS ATS, Next.js).

목록은 정적 HTML이 아니라 **JSON API**로 로드된다(클라이언트 렌더링).
JS 번들 분석으로 찾은 실제 호출:

  POST https://api-recruiter.recruiter.co.kr/position/v1/jobflex
    headers: prefix = <사이트 호스트명>  (window.location.hostname)
    body(JSON): {"pageableRq": {page, size, sort}, "filter": {... openStatusList:["OPEN"] ...}}

응답 list[] 항목 필드:
  positionSn        : ATS 고유 공고 ID (native_id, 상세 URL에도 사용)
  title             : 공고 제목(깔끔한 한글)
  startDateTime     : 접수 시작(게시일)
  endDateTime       : 접수 마감(마감일) — 'T' 앞 날짜를 yyyy-mm-dd로
  careerType        : NEW(신입)/CAREER(경력)/NEW_CAREER(신입·경력)/INTERNSHIP(인턴)/
                      FIELD_DIFFERENCE(분야별 상이)/NONE
  openStatus        : OPEN(게시중) — 필터에 openStatusList:["OPEN"]로 게시중만 요청
  recruitmentType   : GENERAL/PERMANENT(상시)

상세 URL: https://eycareers-kr.recruiter.co.kr/career/jobs/{positionSn}

구분 필터: careerType == "CAREER"(순수 경력)만 소스 단계에서 제외(삼정 receive_div=="E"와 동일 발상).
NEW_CAREER(신입·경력 병기)·NEW·INTERNSHIP·FIELD_DIFFERENCE는 남기고, 중앙 filters.py가 보조망.

견고성: API 미응답/스키마 변형 시 예외 대신 빈 리스트로 수렴(safe_fetch가 한 번 더 감쌈).
JSON 바디·커스텀 헤더(prefix)는 http_util.post(json=, headers=)로 보낸다(재시도·예의딜레이 공유).
"""

from __future__ import annotations

from src.adapters.base import Adapter
from src.http_util import post
from src.record import Posting
from src.util import to_iso_date

_HOST = "eycareers-kr.recruiter.co.kr"
_API = "https://api-recruiter.recruiter.co.kr/position/v1/jobflex"
_DETAIL = f"https://{_HOST}/career/jobs/"

# careerType 코드 → 한글 구분 라벨(Posting.category, 필터 보조망용)
_CAREER_LABEL = {
    "NEW": "신입",
    "CAREER": "경력",
    "NEW_CAREER": "신입/경력",
    "INTERNSHIP": "인턴",
    "FIELD_DIFFERENCE": "분야별 상이",
    "ANY": "전체",
    "NONE": "",
}
# 소스 단계에서 제외할 순수 경력 코드(인턴·신입만 남김)
_EXCLUDE_CAREER = {"CAREER"}


class HanyoungAdapter(Adapter):
    source = "hanyoung"
    label = "EY한영"

    def __init__(self, page_size: int = 100, max_pages: int = 5):
        self.page_size = page_size
        self.max_pages = max_pages

    def _fetch_page(self, page: int) -> dict:
        """단일 페이지 JSON을 가져온다. 실패하면 예외 전파(상위에서 흡수)."""
        headers = {
            "prefix": _HOST,
            "Content-Type": "application/json",
            "Origin": f"https://{_HOST}",
            "Referer": f"https://{_HOST}/",
        }
        body = {
            "pageableRq": {
                "page": page,  # recruiter.co.kr 페이지는 1부터 시작(0이면 400)
                "size": self.page_size,
                "sort": ["CREATED_DATE_TIME,DESC"],
            },
            "filter": {
                "keyword": "",
                "tagSnList": [],
                "jobGroupSnList": [],
                "careerTypeList": [],
                "regionSnList": [],
                "submissionStatusList": [],
                "openStatusList": ["OPEN"],  # 게시중 공고만
                "resumeLanguageTypeList": [],
            },
        }
        r = post(_API, json=body, headers=headers, encoding="utf-8")
        return r.json()

    def fetch(self) -> list[Posting]:
        out: list[Posting] = []
        for page in range(1, self.max_pages + 1):
            try:
                data = self._fetch_page(page)
            except Exception:  # noqa: BLE001 — 페이지 실패는 비치명적(모은 만큼 반환)
                break
            items = data.get("list") or []
            for it in items:
                p = self._to_posting(it)
                if p is not None:
                    out.append(p)
            pg = data.get("pagination") or {}
            total_pages = pg.get("totalPages") or 1
            if not items or page >= total_pages:
                break
        return out

    def _to_posting(self, it: dict) -> Posting | None:
        """API 항목 1건 → Posting. 경력 공고는 None(소스 단계 제외)."""
        career = (it.get("careerType") or "").strip()
        if career in _EXCLUDE_CAREER:
            return None

        sn = it.get("positionSn")
        if sn is None:
            return None
        sn = str(sn)

        title = it.get("title") or ""
        # endDateTime/startDateTime: "2026-06-03T23:59:59" → 마감일/게시일
        deadline = to_iso_date(it.get("endDateTime") or "")
        posted = to_iso_date(it.get("startDateTime") or "")

        return Posting(
            source=self.source,
            source_label=self.label,
            title=title,
            company="EY한영",
            deadline=deadline,
            posted_date=posted,
            url=f"{_DETAIL}{sn}",
            category=_CAREER_LABEL.get(career, career),
            native_id=sn,
        )

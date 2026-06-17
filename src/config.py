"""config.yaml 로더 — 기본값 병합."""

from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULTS: dict = {
    "runtime": {
        "max_pages": 8,   # KICPA 목록 수집 깊이 상한(빈 페이지서 자동중단). CPA보드 45건=5p 누락 방지
        "poll_minutes": 180,
        "digest_hour": 9,
        "state_path": "state.json",
        "delivery": "kakao_pc",   # kakao_pc(노트북 단독) | feed(폰 메신저봇R)
        "kakao_room": "",
        "feed_path": "feed.json",
        "serve_host": "0.0.0.0",
        "serve_port": 8777,
    },
    "filters": {
        "exclude_keywords": ["경력", "시니어", "senior", "매니저", "manager", "파트너", "partner"],
        "exclude_exceptions": ["경력무관", "신입", "인턴", "수습", "trainee", "entry"],
        # 강한 제외(제목에 있으면 본문 예외 무시) — 제목이 명백히 경력 대상인 공고
        "hard_exclude_keywords": ["경력직", "시니어", "senior", "수석", "팀장", "년 이상", "년이상"],
        "include_keywords": [],
    },
    "formats": {
        "divider": "━━━━━━━━━━━",
        "item": "[{label}] {title}\n🏢 {company}   📅 마감일: {deadline}\n▶ 공고 전문: {url}",
        "digest_header": "📋 {date} 오늘 올라온 채용 공고 ({count}건)",
        "digest_line": "[{label}] {title}  📅 {deadline}  ▶ {url}",
        "digest_max_chars": 1800,
    },
    # 대시보드 분류 키워드 (하드코딩 금지 — 여기서만 관리)
    "dashboard": {
        # 채용 법인축: source 키 → 법인 라벨. KICPA 보드는 로컬(회사명에 Big4명 있으면 보정)
        "firm_by_source": {
            "kicpa_susup": "로컬",
            "kicpa_cpa": "로컬",
            "samjong": "삼정",
            "anjin": "안진",
            "hanyoung": "한영",
            "samil": "삼일",
        },
        # 회사명에 이 키워드가 있으면 해당 법인으로 보정(로컬 공고 안의 Big4)
        "firm_keywords": {
            "삼일": ["삼일", "pwc", "pricewaterhouse"],
            "삼정": ["삼정", "kpmg"],
            "안진": ["안진", "deloitte", "딜로이트"],
            "한영": ["한영", "ey", "ernst"],
        },
        # KICPA 보드 공고 중 회사명/제목에 이 키워드가 있으면 '로컬'(회계·세무 법인), 없으면 '기타'(일반기업·공공 등)
        "local_keywords": ["회계법인", "세무법인", "회계사무소", "세무회계", "감사반",
                           "accounting", "tax firm"],
        # 채용 직무축: 제목+회사 키워드 → 분야 (위에서부터 우선 매칭, 미매칭은 audit_default 처리)
        "field_keywords": {
            "딜": ["deal", "m&a", "m＆a", "인수", "합병", "valuation", "가치평가", "실사",
                   "npl", "fas", "ib", "ipo", "transaction", "deal adv", "재무자문",
                   "fdd", "due diligence", "기업금융", "구조조정"],
            "택스": ["tax", "세무", "세제", "조세", "이전가격", "법인세", "상속", "증여",
                     "vat", "부가세", "양도세", "관세", "택스"],
            "감사": ["감사", "audit", "assurance", "회계감사", "외부감사", "외감", "내부회계",
                     "결산", "재무제표", "공시", "회계감리", "ifrs"],
        },
        # 직무 미매칭 시 '감사' 디폴트로 둘 법인(로컬 회계법인 수습/스태프 직무는 대체로 감사).
        # Big4·기타는 자문/디지털/일반직이 많아 디폴트 적용 안 함(기타 유지) — 오분류 방지.
        "audit_default_firms": ["로컬"],
        # 뉴스/이슈 카테고리(단순화): 키워드 → 카테고리 (미매칭=기타)
        "news_keywords": {
            "딜": ["m&a", "m＆a", "인수", "합병", "ipo", "상장", "deal", "사모", "pe", "vc", "투자유치"],
            "세무": ["세무", "세금", "조세", "국세청", "세제", "과세", "법인세", "부가세", "양도세"],
            "회계": ["회계", "감사", "공시", "재무제표", "회계기준", "ifrs", "k-ifrs", "분식", "내부회계"],
        },
        # 빅펌 인사이트 관련도 정렬 키워드(제목에 많을수록 상단) — 수습/회계사 학습에 유용한 것 우선
        "insight_relevance_keywords": [
            "감사", "회계", "세무", "세금", "조세", "내부회계", "ifrs", "공시", "재무제표",
            "밸류업", "value-up", "esg", "지속가능", "결산", "감가상각", "이연법인세", "연결재무",
            "리스", "수익인식", "배당", "상장", "ipo", "m&a", "인수", "가치평가", "실사",
            "리스크", "내부통제", "지배구조", "거버넌스", "신탁세무", "tax",
        ],
        "soon_days": 7,          # 마감 임박 기준(일)
        "new_days": 7,           # '신규' 채용 기준(게시 N일 이내)
        "news_recent_days": 10,  # 기사 기본 보존 기간(N일 지난 기사 제외)
        # 카테고리별 보존기간 override — 저빈도·고관련(채용/시험·딜)은 더 오래 노출(감사·세무는 기본값)
        "news_recent_days_by_category": {
            "채용·시험": 45,
            "딜·M&A": 21,
        },
        "news_per_category": 20, # 카테고리별 뉴스 최대 건수
        # 기사 4분류(좁은→넓은 순 = dedup 선점 순서). 채용·시험에 업계동향 흡수, 감사에 제도·규제 흡수.
        "news_queries": {
            "채용·시험": ("수습 공인회계사 OR 공인회계사 시험 OR 한국공인회계사회 OR CPA 합격 OR 회계사 채용 OR "
                          "회계법인 채용 OR 빅4 회계 OR 공인회계사 업계 OR 감사보수 OR 회계사 연봉 OR 회계법인 실적"),
            "딜·M&A": ("인수합병 OR M&A OR IPO OR 기업가치평가 OR 구조조정 OR 사모펀드 회계법인 OR "
                       "실사 회계법인 OR 재무자문 회계법인"),
            "세무": "세법개정 OR 조세정책 OR 세무조사 OR 법인세 OR 상속증여세 OR 국제조세",
            "감사": ("회계기준 OR 감사기준 OR K-IFRS OR 내부회계관리제도 OR 회계감독 OR 금융감독원 회계 OR "
                     "감사의견 OR 외부감사 OR 회계감리"),
        },
        # 제목에 이 단어가 있으면 노이즈로 제외(시상·행사·동정 등)
        "news_exclude": ["시상", "수상", "기획전", "캠페인", "부고", "위촉", "임명식", "골프", "기부", "동정"],
        # 관련성 게이트: 제목에 아래 도메인어가 하나도 없으면 제외(넓은 OR 쿼리의 엉뚱한 매칭 차단)
        "news_require_any": [
            "회계", "회계사", "공인회계사", "cpa", "회계법인", "감사", "감사인", "회계감리",
            "세무", "세금", "세법", "조세", "국세", "법인세", "상속세", "증여세", "양도세",
            "부가세", "과세", "관세", "ifrs", "공시", "내부회계", "재무제표",
            "m&a", "m＆a", "인수합병", "ipo", "기업가치", "실사", "사모", "구조조정",
            "딜로이트", "삼일", "삼정", "안진", "한영", "kpmg", "pwc", " ey ", "빅4", "빅four",
            "금감원", "금융감독원", "한공회", "세정", "수습", "기장",
        ],
    },
    # 신선도(누락) 모니터 — 스케줄 드롭으로 데이터가 낡았는지 감지. 카나리아(HTML 양식)와는 별개.
    "freshness": {
        "site_url": "https://hbmons.com",     # 시각 증거 스크린샷 대상(라이브 사이트)
        "data_dir": "docs/data",
        "stale_multiplier": 2,                 # STALE = 나이 > 기대간격×배수 + grace
        "grace_minutes": 20,                   # GitHub 스케줄 지연 흡수 여유
        "report_path": "freshness_report.md",
        "screenshot_path": "freshness_shot.png",
        # 데이터 파일 → (라벨, 기대 갱신 간격(분)). 워크플로 cron과 일치시킬 것.
        "streams": {
            "jobs.json": {"label": "채용공고", "expected_minutes": 30},
            "news.json": {"label": "기사", "expected_minutes": 120},
            "insights.json": {"label": "빅펌 인사이트", "expected_minutes": 720},
        },
    },
    # 라이브 종단(e2e) 검증 — 배포된 화면이 의도대로 보이는지(canary·freshness가 못 보는 '사용자 화면').
    "sitecheck": {
        "site_url": "https://hbmons.com",
        "updated_max_minutes": 360,   # 헤더 '최근 업데이트'가 이보다 오래면 이상(스케줄 드롭은 freshness가 별도 감지)
        "report_path": "sitecheck_report.md",
        "screenshot_path": "sitecheck_shot.png",
        "use_llm": True,              # 키 없으면 자동 비활성=결정론 검사만
        "llm_model": "claude-opus-4-8",
    },
    # 자기검증 카나리아 (하루 1회) — 소스 양식 변경/공고 누락 감지. 코드 수정은 사람 게이트.
    "canary": {
        "drop_ratio": 0.6,       # 어제 대비 이 비율 이상 급감하면 드리프트(예: 0.6 = 60%↓)
        "min_baseline": 3,       # 어제 건수가 이 미만이면 급감 판정 보류(노이즈 방지)
        "state_path": "canary_state.json",
        "report_path": "canary_report.md",
        "use_llm": True,         # 키 없으면 자동 비활성(구조 체크만)
        "llm_model": "claude-opus-4-8",
        "missing_ratio": 1.5,    # LLM이 본 공고수가 스크래퍼의 이 배↑면 누락 의심
        # 소스 키 → 시각 점검할 '목록 페이지' URL (about 탭의 원문 출처와 동일)
        "source_urls": {
            "kicpa_susup": "https://www.kicpa.or.kr/home/jobOffrSrchNewGnrl/list.face",
            "kicpa_cpa": "https://www.kicpa.or.kr/home/jobOffrSrchGnrl/list.face",
            "samjong": "https://career.kr.kpmg.com/hr/rec/recruit/jobopen/controller/candidate/JobOpen310WebController/init.hr",
            "anjin": "https://join.deloitte.co.kr/WiseRecruit2/User/RecruitList.aspx",
            "hanyoung": "https://eycareers-kr.recruiter.co.kr/career/home",
            "samil": "https://www.pwc.com/kr/ko/career/experienced.html",
        },
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    user = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _merge(_DEFAULTS, user or {})

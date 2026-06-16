"""config.yaml 로더 — 기본값 병합."""

from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULTS: dict = {
    "runtime": {
        "max_pages": 2,
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
        # 채용 직무축: 제목+회사 키워드 → 분야 (위에서부터 우선 매칭, 미매칭=기타)
        "field_keywords": {
            "딜": ["deal", "m&a", "m＆a", "인수", "valuation", "가치평가", "실사",
                   "npl", "fas", "ib", "ipo", "transaction", "deal adv", "재무자문"],
            "감사": ["감사", "audit", "assurance", "회계감사", "외부감사"],
            "택스": ["tax", "세무", "세제", "조세", "이전가격"],
        },
        # 뉴스/이슈 카테고리(단순화): 키워드 → 카테고리 (미매칭=기타)
        "news_keywords": {
            "딜": ["m&a", "m＆a", "인수", "합병", "ipo", "상장", "deal", "사모", "pe", "vc", "투자유치"],
            "세무": ["세무", "세금", "조세", "국세청", "세제", "과세", "법인세", "부가세", "양도세"],
            "회계": ["회계", "감사", "공시", "재무제표", "회계기준", "ifrs", "k-ifrs", "분식", "내부회계"],
        },
        "soon_days": 7,          # 마감 임박 기준(일)
        "new_days": 7,           # '신규' 채용 기준(게시 N일 이내)
        "news_recent_days": 7,   # 기사 보존 기간(N일 지난 기사 제외)
        "news_per_category": 20, # 카테고리별 뉴스 최대 건수
        # 기사=면접·업계지식 중심. 카테고리별 Google News RSS 쿼리(노이즈는 news_exclude로 제거)
        "news_queries": {
            "제도·규제": "회계기준 OR 감사기준 OR K-IFRS OR 내부회계관리제도 OR 회계감독 OR 금융감독원 회계",
            "세무": "세법개정 OR 조세정책 OR 세무조사 OR 법인세 OR 상속증여세 OR 국제조세",
            "딜·M&A": "인수합병 OR M&A OR IPO 회계법인 OR 기업가치평가 OR 구조조정 회계법인",
            "회계업계": "회계법인 OR 빅4 회계 OR 공인회계사 업계 OR 삼일 삼정 안진 한영 회계",
        },
        # 제목에 이 단어가 있으면 노이즈로 제외(시상·행사·동정 등)
        "news_exclude": ["시상", "수상", "기획전", "캠페인", "부고", "위촉", "임명식", "골프", "기부", "동정"],
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

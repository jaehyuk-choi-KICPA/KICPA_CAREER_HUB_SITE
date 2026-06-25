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
        "exclude_exceptions": ["경력무관", "무관", "신입", "인턴", "수습", "trainee", "entry"],
        # 예외어 바로 뒤에 이 부정어가 붙으면 예외로 안 침 — '신입불가'·'신입 제외'의 '신입'이
        # 경력 전용 공고를 오구제하는 부분일치 버그 방지(서율회계법인 '경력 3년이상(신입불가)' 실측).
        "exception_negators": ["불가", "제외", "불가능", "안됨", "안 됨", "아님", "없음", "x"],
        # 강한 제외(제목에 있으면 본문 예외 무시) — 제목이 명백히 경력 대상인 공고
        "hard_exclude_keywords": ["경력직", "시니어", "senior", "수석", "팀장", "년 이상", "년이상",
                                  "년차", "년 차", "경력사원"],   # 'N년차'·경력사원 = 경력 전용(신입 병기 시 제목 예외로 구제)
        "include_keywords": [],
        # 제목에 이 구절이 있으면 역할 노이즈로 제외(면제 소스보다 우선) — 수습CPA·회계사 타깃과 무관한
        # 사무보조(세무 기장직원). '기장'만 보면 '기장 업무 포함' 수습공고도 오제거되므로 **채용 패턴으로 한정**.
        "title_exclude_keywords": ["기장직원", "기장 직원", "기장 및", "기장담당", "기장 담당"],
        # 경력 필터 면제 소스 — 보드 자체가 타깃을 확정해 올라온 건 그대로 수용(제목이 '경력직'이어도
        # 모집대상에 신입/경력 병기인 경우 등). 수습CPA 보드(kicpa_susup)가 대표 케이스.
        "bypass_sources": ["kicpa_susup"],
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
        # === 자격요건축(수습CPA/자격무관) — 직무분류 대체. 제목+회사+상세(body_excerpt)+고용형태+구분 텍스트로 판정 ===
        # KICPA 수습보드(kicpa_susup)는 무조건 수습CPA. 그 외엔 아래 키워드가 있으면 수습CPA, 없으면 자격무관(보수적).
        "qual_susup_keywords": ["수습", "공인회계사", "cpa", "회계사", "신입회계사", "회계사 시험", "회계사 합격"],
        # 위 키워드가 있어도 이 단어가 있으면 자격무관으로(경력 전용 등). filter_postings가 경력만 공고는 이미 제외.
        "qual_exclude_keywords": ["경력무관", "자격무관"],
        # === 채용구분축(인턴/계약직/파트타임/정규직) — 우선순위 매칭, 미매칭 기본=정규직 ===
        "empkind_keywords": {
            "인턴": ["인턴", "intern", "체험형"],
            "계약직": ["계약직", "기간제", "contract"],
            # 'part time'(공백)·'parttime'(붙임)도 잡되, 바 '파트'/'part'는 금지(오탐: '수습 파트'(부서)·'Parthenon')
            "파트타임": ["파트타임", "시간제", "part-time", "part time", "parttime", "아르바이트"],
            "정규직": ["정규직", "정규"],
        },
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
        # '방금 올라온 공고'(is_new) — 발견 24h 이내 + **게시일이 N일 이내**여야 인정.
        # 게시일이 오래된 공고를 뒤늦게 처음 수집해도(KICPA 깜빡임·페이지 변동) '방금'으로 오표시되는 것 방지.
        "new_posted_max_age_days": 2,
        "jobs_grace_days": 2,    # 공고가 목록서 일시 누락돼도 마감 전이면 N일간 유지(KICPA 깜빡임 대응)
        "news_recent_days": 21,  # 기사 기본 보존 기간(N일 지난 기사 제외) — 수량 확보 위해 확대
        # 카테고리별 보존기간 override — 저빈도·고관련(채용/시험·딜)은 더 오래 노출(감사·세무는 기본값)
        "news_recent_days_by_category": {
            "채용·시험": 75,
            "딜·M&A": 30,   # 60→30: 딜 누적 비중 완화(고볼륨이라 길게 둘 필요 없음)
        },
        "news_per_category": 75, # 카테고리별 RSS 수집 상한. 구글뉴스는 관련도순이라 최신 기사가 뒤쪽에도 흩어짐
                                 # → 50에서 자르면 신선기사를 통째 유실(실측: 세무·감사 거의 2배 회복). 75로 상향.
        "news_neardup_jaccard": 0.6,  # 제목 단어집합 Jaccard 이 값↑이면 같은 이슈로 군집화(최신 대표, 나머지는 dupes)
        "news_neardup_overlap": 0.67,   # 보조: 포함도(겹침/작은쪽) 이 값↑ + 공통토큰 하한 충족 시 같은 사건(다른 표현)으로 군집
        "news_neardup_min_tokens": 4,   # 보조 군집의 공통 핵심토큰 최소 개수(오병합 방지 하한)
        # 의미 군집(임베딩) — 어휘로 못 묶는 같은 사건(다른 표현)을 보조 병합. VOYAGE_API_KEY 있을 때만 작동(없으면 어휘만=폴백).
        "news_embed_enabled": True,
        "news_embed_model": "voyage-3.5-lite",   # 경량·다국어·저비용
        "news_embed_threshold": 0.83,            # 코사인 이 값↑이면 같은 사건으로 병합. 0.88=과소병합(동일사건 흩어짐),
                                                 # 0.85=중간, 0.83=더 적극 병합(발전공기업 통합 동일사건을 1카드로 — 사용자 선호). 0.82 이하는 과병합 위험.
        "news_embed_candidate_min_tokens": 1,    # '걸릴 때만': 같은 카테고리+공통토큰 이 수↑인 의심 쌍만 임베딩 호출
        "news_embed_cache_path": "news_vectors.json",  # URL→벡터 캐시(새 기사만 임베딩 → 비용·시간 최소)
        # 관련성 게이트(#1)·카테고리 보정(#2) — 카테고리 프로토타입 코사인. 키워드 1차, 임베딩 보수적 보조.
        # ⚠️ 실데이터 튜닝(embed_tune, 41건): 제목 코사인이 0.41~0.53로 좁고 노이즈/신호가 겹쳐(정상 세법기사<지방세 PR)
        #    관련성 드롭은 정상기사 오드롭 위험 → floor 낮춰 dormant. 카테고리 flip은 대부분 오답(법인세→딜) → 비활성.
        "news_embed_relevance_enabled": True,    # 단 floor 낮아 현 데이터 드롭 0(미래 ~0 garbage만 걸리는 안전망)
        "news_embed_category_enabled": False,    # 재배정 flip 대부분 오답이라 비활성(프로토타입 개선 시 재검토)
        "news_embed_relevance_floor": 0.25,      # max(4개 프로토타입 코사인) < 이 값 → 드롭. 실측 min 0.41이라 현재 드롭 0
        "news_embed_category_margin": 0.15,      # 재활성 시 기준(현 데이터 최대 마진 0.087 → 0 flip=안전)
        "news_max_per_day_per_cat": 8,  # 같은 (카테고리,발행일) 최대 N건 — 한 사건이 매체별로 도배하는 것 방지
        # 외국(미국 제외) 세무·감사·딜 이슈 차단 — 제목에 외국명이 있고 한국/미국/국제 마커가 하나도 없으면 제외.
        # (딜·M&A도 적용: 패러곤 뱅킹 그룹처럼 한국 무관 외국 매각 기사가 난잡하게 섞임. 글로벌·국제·미국 마커가
        #  있으면 keep 마커로 유지되므로 SK·삼성 등 한국기업 해외딜은 보존됨.)
        "news_foreign_filter_categories": ["세무", "감사", "딜·M&A"],
        "news_foreign_countries": [
            "베트남", "일본", "중국", "대만", "홍콩", "싱가포르", "인도네시아", "태국",
            "필리핀", "말레이시아", "인도", "독일", "프랑스", "영국", "호주", "캐나다",
            "브라질", "러시아", "스페인", "이탈리아", "네덜란드", "스위스", "멕시코",
            "사우디", "아랍에미리트", "uae", "튀르키예", "터키",
            "中,",   # 중국 약칭(쉼표 동반 시만 — '中企'·'中소' 등 국내 약어 오차단 방지). 예: '…中, 감사인 처벌'
        ],
        # 외국 매체(출처) 키워드 — source_label에 있으면 외국 기사로 간주(제목에 국가명 없어도 차단)
        "news_foreign_sources": [
            "vietnam", ".vn", "japan", "nikkei", "china", "xinhua", "thai", "indonesia",
            "jakarta", "manila", "bangkok", "straits", "taipei",
            "investing.com",   # 미국·외국 주총 proxy 기사 번역본 (감사인 비준·승인 노이즈)
            "씬짜오", "씬짜오베트남",   # 베트남 한국어 매체 — 베트남 현지 회계·감사(PwC 베트남 등) 기사 차단
            "데이터투자",   # 미국 SEC 공시(8-K 감사인 교체 등) 자동번역 애그리게이터 — 외국 소형주 노이즈
        ],
        # 위 외국명이 있어도 이 마커(한국·미국·국제공통)가 제목에 있으면 유지
        "news_keep_markers": [
            "한국", "국내", "우리나라", "한공회", "국세청", "금감원", "금융위", "증선위",
            "기재부", "기획재정부", "국제", "글로벌", "oecd", "ifrs", "g7", "g20",
            "다국적", "미국", "글로벌최저한세", "디지털세",
        ],
        # 제목에 이 키워드가 있으면 카테고리를 '채용·시험'으로 강제 보정
        # (RSS '감사' 쿼리가 가져온 기사라도 채용·수습 관련이면 재분류)
        "news_hire_title_keywords": [
            "미지정 회계사", "수습 공인회계사", "공인회계사 수습", "회계사 수습처",
            "실무수습기관", "수습처 못", "수습처 막", "공인회계사 합격", "cpa 합격",
            "회계사 채용", "회계법인 채용", "수습기관 확대",
            "한공회장", "선발 과도", "선발 인원", "선발 축소", "선발 규모",
            "합격자 수", "회계사 선발", "선발인원",
        ],
        # 출처(매체) 제외 — 정치색 강한 매체 등(source_label 부분일치)
        "news_exclude_sources": ["뉴스타파", "대한민국 정책브리핑", "Naver Blog"],   # 정치색·보도자료·블로그 출처 제외
        # 기사 4분류(좁은→넓은 순 = dedup 선점 순서). 채용·시험에 업계동향 흡수, 감사에 제도·규제 흡수.
        "news_queries": {
            "채용·시험": ("수습 공인회계사 OR 공인회계사 시험 OR 한국공인회계사회 OR CPA 합격 OR 회계사 채용 OR "
                          "회계법인 채용 OR 빅4 회계 OR 공인회계사 업계 OR 회계사 연봉 OR 회계법인 실적 OR "
                          "실무수습기관 OR 미지정 회계사 OR 회계사 수습처"),
            "딜·M&A": ("인수합병 OR M&A OR IPO OR 기업공개 OR 기업가치평가 OR "
                       "사모펀드 OR 바이아웃 OR 재무실사 OR 재무자문 OR 리그테이블 OR 경영권 OR 매각 OR "
                       "회계실사 OR 밸류에이션 OR 상장폐지 OR 지분인수 OR 구주매각"),
            "세무": ("세법개정 OR 조세정책 OR 세무조사 OR 법인세 OR 상속증여세 OR 국제조세 OR "
                     "이전가격 OR 조세불복 OR 세무조정 OR 부가가치세 OR 양도소득세"),
            # 감사는 구글 RSS 100건 상한 + 관련도순 정렬 때문에 단일 쿼리로는 오늘 기사가 뒤로 밀림.
            # 2개 풀로 분리 → 각각 최대 100건, 합산 후 URL 기준 dedup.
            "감사": [
                # 풀 A: 기준·제도·의견
                ("회계기준 OR 감사기준 OR K-IFRS OR 내부회계관리제도 OR 회계감독 OR "
                 "금융감독원 회계 OR 감사의견 OR 외부감사 OR 회계감리"),
                # 풀 B: 보수·부정·감사인·제재
                ("감사보수 OR 분식회계 OR 지정감사 OR 표준감사시간 OR 외감법 OR 외감 OR "
                 "감사인 OR 증선위 OR 회계처리"),
            ],
        },
        # 제목에 이 단어가 있으면 노이즈로 제외(시상·행사·동정 등)
        "news_exclude": ["시상", "수상", "기획전", "캠페인", "부고", "위촉", "임명식", "골프", "기부", "동정",
                         "코인", "암호화폐", "(보도설명)", "(해명)",
                         "관사",   # 코인·보도자료성·공관(관사) 행정 노이즈 제외(예: '대구시장 관사 매각 검토')
                         "악성코드", "APT", "랜섬", "피싱", "해킹",   # '세무조사' 미끼 보안기사(실버폭스 등) 제외
                         "입찰공고",   # 재개발조합 감정평가법인 선정 등 입찰공고(법인세 오매칭) 제외
                         "농지 매각", "농기계"],   # 딜 쿼리 '매각' 오매칭 농정·지자체 노이즈 제외
        # 지자체 행정 홍보 제외 — ○○시/군 + 행정 액션(세미나·컨설팅·유예 등)이 함께면 제외. 국가기관 언급 시 유지.
        "news_local_gov_action": ["세미나", "컨설팅", "유예", "우대", "이자보전", "역량 강화", "역량강화", "선정"],
        "news_local_gov_keep": ["국세청", "기재부", "기획재정부", "금감원", "금융감독원", "증선위", "한공회",
                                "한국공인회계사회", "국세"],
        # 법인 개업·개소 홍보(PR/동정) 제외 — '법인어 + 개업/오픈류'가 함께일 때만 컷(단독어는 정상기사 오차단 위험).
        # 예: "○○세무사, 세무법인 엑스퍼트 역삼점 오픈"(지점 개소 PR) → 제거. '사업자 개업신고' 등은 법인어 없어 보존.
        "news_firm_pr_entities": ["세무법인", "회계법인", "세무사사무소", "세무사 사무소", "세무회계사무소"],
        "news_firm_pr_actions": ["오픈", "개소", "개업", "현판", "분사무소", "출간", "발간"],
        # 관련성 게이트: 제목에 아래 도메인어가 하나도 없으면 제외(넓은 OR 쿼리의 엉뚱한 매칭 차단)
        "news_require_any": [
            "회계", "회계사", "공인회계사", "cpa", "회계법인", "감사", "감사인", "회계감리",
            "세무", "세금", "세법", "조세", "국세", "법인세", "상속세", "증여세", "양도세",
            "부가세", "과세", "관세", "ifrs", "공시", "내부회계", "재무제표",
            "m&a", "m＆a", "인수합병", "ipo", "기업가치", "재무실사", "사모",
            "매각", "바이아웃", "증선위", "밸류에이션", "상장폐지", "지분인수", "실사",
            "이전가격", "부가가치세", "양도소득세",
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
            # "notify_status.json": {"label": "푸시 발송", "expected_minutes": 30},  # notifier 미운영 중
        },
    },
    # 라이브 종단(e2e) 검증 — 배포된 화면이 의도대로 보이는지(canary·freshness가 못 보는 '사용자 화면').
    "sitecheck": {
        "site_url": "https://hbmons.com",
        "updated_max_minutes": 360,   # 헤더 '최근 서치'가 이보다 오래면 이상(스케줄 드롭은 freshness가 별도 감지)
        "report_path": "sitecheck_report.md",
        "screenshot_path": "sitecheck_shot.png",
        "result_path": "sitecheck_result.json",   # 루프 분기용(status·class·failed)
        "use_llm": True,              # 키 없으면 자동 비활성=결정론 검사만
        "llm_model": "claude-opus-4-8",
        # 타당성(plausibility): '오늘 신규'가 총건수의 이 비율↑이고 총 ≥ min이면 비현실적(예: 48/48=전량 신규)
        "implausible_today_ratio": 0.8,
        "min_total_for_ratio": 8,
        "max_attempts": 3,            # 셀프힐링 재실행 상한
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
        "check_filter_leakage": True,   # 채용 목록에 경력 전용 공고 누출 결정론 점검(jobs.json)
        # 소스 키 → 시각 점검할 '목록 페이지' URL (about 탭의 원문 출처와 동일)
        "source_urls": {
            "kicpa_susup": "https://www.kicpa.or.kr/home/jobOffrSrchNewGnrl/list.face",
            "kicpa_cpa": "https://www.kicpa.or.kr/home/jobOffrSrchGnrl/list.face",
            "samjong": "https://career.kr.kpmg.com/hr/rec/recruit/jobopen/controller/candidate/JobOpen310WebController/init.hr",
            "anjin": "https://join.deloitte.co.kr/WiseRecruit2/User/RecruitList.aspx",
            "hanyoung": "https://eycareers-kr.recruiter.co.kr/career/jobs",
            "samil": "https://www.pwc.com/kr/ko/career/experienced.html",
        },
    },
    # 웹 푸시 채용 알림 — 새 공고를 구독자에게 발송(src/notifier.py). 코어 LLM-free.
    # enabled=false면 발송 비활성(seed/dry-run은 가능). 검증 후 true로 전환.
    "notifications": {
        "enabled": True,
        "worker_url": "https://hbmons-push.trackingsite.workers.dev",   # 구독 저장 Worker(push.hbmons.com 연결 시 교체)
        "vapid_public": "BP7FISRizBQtx8OHcwaspl-KTupAl_R82zTL7o0PqzhqrGj6-bxqY3X-92rNYhVXySuntQaO6fxIOVtDFHYA1Yg",  # applicationServerKey(app.js와 동일값)
        "vapid_subject": "mailto:michael005009@gmail.com",  # VAPID claims sub
        "only_new_open": True,     # 진행중(마감 전) 신규만 발송, 만료 미발송분은 게시 없이 억제
        "ttl_seconds": 86400,      # 푸시 TTL(미수신 기기 보관 시간)
        "max_per_run": 25,         # 한 run에서 발송할 공고 상한(콜드스타트 폭주 방지)
        "title_format": "{title}",
        "body_format": "{label} · 마감 {deadline} ({dday_label})",
        "status_path": "docs/data/notify_status.json",  # 발송 관측성(freshness가 조용한 실패 감지)
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

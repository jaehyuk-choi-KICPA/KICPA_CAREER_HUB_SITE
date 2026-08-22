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
        # aicpa(미국회계사): 제목이 명시적으로 AICPA 타깃이면 사이트 대상 아님 → 목록에서 제외
        # (서현 IT감사 AICPA 실측, 사용자 결정). 병기 제목("KICPA/AICPA …")도 드롭되는 트레이드오프 수용.
        "title_exclude_keywords": ["기장직원", "기장 직원", "기장 및", "기장담당", "기장 담당",
                                   "aicpa", "미국회계사", "미국공인회계사"],
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
        # 매칭 전에 판정 텍스트에서 지우는 중립화 토큰 — "AICPA"의 'cpa'가 수습CPA로 오인되는 부분문자열 오탐 차단.
        # exclude가 아닌 strip인 이유: "KICPA/AICPA 병기" 공고는 남은 kicpa·수습 등 키워드로 수습CPA를 유지해야 해서.
        "qual_strip_tokens": ["aicpa", "미국공인회계사", "미국회계사", "us cpa"],
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
        "news_foreign_filter_categories": ["세무", "감사"],
        "news_foreign_countries": [
            "베트남", "일본", "중국", "대만", "홍콩", "싱가포르", "인도네시아", "태국",
            "필리핀", "말레이시아", "인도", "독일", "프랑스", "영국", "호주", "캐나다",
            "브라질", "러시아", "스페인", "이탈리아", "네덜란드", "스위스", "멕시코",
            "사우디", "아랍에미리트", "uae", "튀르키예", "터키",
            "中,",   # 중국 약칭(쉼표 동반 시만 — '中企'·'中소' 등 국내 약어 오차단 방지). 예: '…中, 감사인 처벌'
            "中 ",   # 중국 약칭(공백 동반) — '[中 하드테크 IPO 빅뱅]' 등. 붙여쓰는 '中企'·'中소'는 여전히 오차단 없음
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
            "한공회장", "한공회", "선발 과도", "선발 인원", "선발 축소", "선발 규모",
            "합격자 수", "회계사 선발", "선발인원",
        ],
        # 출처(매체) 제외 — 정치색 강한 매체 등(source_label 부분일치)
        # 정치색·보도자료·블로그·지역지 출처 제외(부분일치). 지역지는 세무에 지역 교육·행정·인사 노이즈가 많아 일괄 차단.
        "news_exclude_sources": [
            "뉴스타파", "대한민국 정책브리핑", "Naver Blog",
            # 지역 일간지
            "도민일보", "부산일보", "국제신문", "울산신문", "경상일보", "경남신문", "매일신문", "영남일보", "대구신문",
            "강원일보", "충북일보", "충청일보", "충청투데이", "중부매일", "대전일보", "중도일보", "금강일보",
            "전북일보", "전남일보", "광주일보", "무등일보", "광남일보",
            "경기일보", "중부일보", "경인일보", "인천일보", "기호일보", "제주일보", "한라일보", "제민일보",
            "시사일보", "자치안성신문", "농민신문",
            "Hypebeast",   # 패션·라이프스타일 매체 — 외국 스포츠구단 지분 매각(LA Lakers) 등 무관 딜 기사
        ],
        # 기사 3분류(좁은→넓은 순 = dedup 선점 순서). 채용·시험에 업계동향 흡수, 감사에 제도·규제 흡수.
        # 딜·M&A는 2026-08-22 폐지 — 부동산·해외 소형딜 노이즈가 심하고 수습 CPA에게 실효가 낮았다
        # (아카이브 기준 기사의 66%를 차지하며 다른 카테고리를 시각적으로 묻어버렸다).
        "news_queries": {
            "채용·시험": ("수습 공인회계사 OR 공인회계사 시험 OR 한국공인회계사회 OR CPA 합격 OR 회계사 채용 OR "
                          "회계법인 채용 OR 빅4 회계 OR 공인회계사 업계 OR 회계사 연봉 OR 회계법인 실적 OR "
                          "실무수습기관 OR 미지정 회계사 OR 미지정 OR 회계사 수습처"),
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
                         "승진", "영전",   # 인사 동정(예: '국세청 ○○과장 부이사관 승진') — 시시콜콜 인사기사 제외
                         "실무교육", "보수교육", "세무설명회", "[프로필]",   # 지역 상의·세무사회 교육·설명회·인사 프로필 노이즈
                         "코인", "암호화폐", "(보도설명)", "(해명)",
                         "관사",   # 코인·보도자료성·공관(관사) 행정 노이즈 제외(예: '대구시장 관사 매각 검토')
                         "악성코드", "APT", "랜섬", "피싱", "해킹",   # '세무조사' 미끼 보안기사(실버폭스 등) 제외
                         "입찰공고",   # 재개발조합 감정평가법인 선정 등 입찰공고(법인세 오매칭) 제외
                         "농지 매각", "농기계",   # 딜 쿼리 '매각' 오매칭 농정·지자체 노이즈 제외
                         # 정치 이슈 연루 기사 제외 — 정당·정치인 공방/국회 이벤트 프레임(정책 내용보다 정치가 주인 기사).
                         # ⚠️ '국회'·'의원' 단독은 금지: '미지정 회계사, 국회도 문 연다'(채용)·'병의원 부가가치세'(세무) 오차단 실측.
                         # ' 의원'(공백 동반)은 인명 뒤 호칭만 매칭 — '병의원'은 안전.
                         "정무위", "국정감사", "국감", "청문회", "인사청문", "특검", "탄핵",
                         "대선", "총선", "지방선거", "여야", "야당", "여당", "민주당", "국민의힘",
                         "국민의 힘", "공약", "개각", " 의원", "대통령",
                         # (2차 보강) 정치인이 '분식회계'를 비유로 쓴 정당 공방이 감사 쿼리에 걸림(송영길·정청래 실측).
                         # 한자 약칭 與/野는 공백 동반("與ㅤ8·17 전당대회")·병기("與野")만 — '참여' 등 한글은 무관.
                         "전당대회", "합동연설회", "[현장영상]",   # 정당 행사·방송 정치클립 마커
                         "與 ", "野 ", "與野",                      # 한자 정당 약칭
                         "시의회", "군의회", "구의회", "도의회"],   # 지방의회(지자체 시설 매각 행정기사 — 고창군의회 실측)
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
            # 딜 도메인어(m&a·ipo·매각·사모·밸류에이션 등)는 2026-08-22 제거 —
            # 카테고리를 폐지해도 이 게이트에 남아 있으면 딜 기사가 감사·세무 쿼리를 타고 들어온다.
            # 실측: 이 13개를 빼자 라이브 61건 중 딜 기사 15건이 정확히 전부 탈락하고 감사·세무는 무손실.
            "증선위",
            "이전가격", "부가가치세", "양도소득세",
            "딜로이트", "삼일", "삼정", "안진", "한영", "kpmg", "pwc", " ey ", "빅4", "빅four",
            "금감원", "금융감독원", "한공회", "세정", "수습", "기장",
        ],
        # ======================= 산업별 기사(회계·재무 렌즈) =======================
        # 기존 news_* 파이프라인과 **완전 분리된 별도 스트림**(docs/data/industry.json).
        # 목적: "관심산업군 -> 기업 -> DART 재무제표" 학습 동선. 일반 기술·정책 트렌드가 아니라
        #       **숫자로 드러나는 사건**(실적·수주·증설·증자·M&A·손상·구조조정)만 남긴다.
        # ⚠️ 절대 news_queries / news_require_any / news_exclude 에 섞지 말 것:
        #    ① embeds._prototypes가 news_queries 값 전체를 프로토타입 임베딩 → 기존 감사·세무 판정 오염
        #    ② _dedup_near가 카테고리를 무시하므로 dict 순서상 선점 잠식
        #    ③ news_exclude의 정치어가 에너지·건설 산업정책 기사를 대량 오차단
        #    ④ news_require_any(회계 도메인어)는 산업 기사를 100% 드롭
        "industry_enabled": True,
        "industry_per_category": 60,        # 쿼리(풀)당 RSS 수집 상한
        # '최근' 화면 보존기간. 그 이전은 아카이브가 담당.
        # 14 -> 30: 진단 결과 최대 손실원이 관련성 게이트가 아니라 **이 컷오프**였다(자동차 120건 중 60건,
        # 통신 79건이 여기서 탈락). 구글뉴스 RSS는 관련도순이라 넓은 앵커 쿼리일수록 과거 기사가 섞여 온다.
        "industry_recent_days": 30,
        "industry_max_per_day_per_cat": 4,  # (산업, 발행일)별 상한 — 한 사건이 도배하는 것 방지
        "industry_min_interval_minutes": 180,  # run-all은 30분 주기지만 산업은 3시간에 1회만 수집
                                               # (어댑터 22개 -> 구글뉴스 throttle·리포 churn 방어)
        "industry_fetch_workers": 4,        # 산업 전용 병렬도(뉴스 8보다 낮춤 — throttle 회피)
        # 산업 탭은 **국내 기업 기사만** 본다. 뉴스 쪽 필터(news_foreign_*)는 '미국·글로벌'을 keep 마커로
        # 살려두지만 산업엔 그 예외를 두지 않는다 — 엔비디아·YMTC·트럼프미디어 실적은 우리 목적과 무관하다.
        # 판정: 제목에 외국 마커가 있고, (사전 기업 태그도 없고 국내 마커도 없으면) 제외.
        # 덕분에 "삼성전자, 美 공장 증설"은 남고 "美 제조업 설비투자 5200조"는 빠진다.
        "industry_foreign_filter": True,
        "industry_foreign_markers": [
            # 한글 국가·지역명
            "미국", "중국", "일본", "대만", "홍콩", "싱가포르", "베트남", "인도네시아", "태국",
            "필리핀", "말레이시아", "인도", "독일", "프랑스", "영국", "호주", "캐나다", "브라질",
            "러시아", "스페인", "이탈리아", "네덜란드", "스위스", "멕시코", "사우디",
            "아랍에미리트", "uae", "튀르키예", "터키", "유럽",
            # 한자·약칭 — 공백/쉼표 동반형만(붙여쓰는 '中企'·'美친' 등 오차단 방지). 기존 뉴스 필터와 같은 관례.
            "美 ", "美,", "中 ", "中,", "日 ", "日,", "獨 ", "佛 ", "英 ", "露 ", "러, ", "EU ",
            # 국내 기사에 자주 등장하는 외국 기업·기관
            "엔비디아", "인텔", "tsmc", "애플", "마이크론", "ymtc", "화웨이", "샤오미", "테슬라",
            "byd", "도요타", "혼다", "폭스바겐", "포드", "gm ", "스텔란티스",
            "아마존", "구글", "마이크로소프트", "메타", "오픈ai", "앤트로픽", "스페이스x",
            "보잉", "에어버스", "화이자", "머크", "노보노디스크", "트럼프", "연준",
        ],
        # 위 마커가 있어도 국내 신호가 있으면 유지(사전 기업 태그가 붙은 기사는 자동으로 유지된다)
        "industry_domestic_markers": ["한국", "국내", "우리나라", "대한민국", "코스피", "코스닥", "국산"],
        # 산업 목록 = 프론트 칩 순서 = dedup 선점 순서. 값이 리스트면 풀(pool)로 취급(build_news_adapters와 동일).
        #  - 풀 A = 업종 앵커 OR 리스트(단일 토큰/복합명사만 -> 구글 파싱 모호성 0)
        #  - 풀 B = "업종어 + 재무이벤트" 2어절(OR 미포함) — 실적 기사 밀도 확보용
        # ⚠️ `A B OR C D`(AND쌍의 OR)는 구글 파싱이 보장되지 않으므로 금지.
        "industry_queries": {
            "반도체·전자": [
                "반도체 OR 파운드리 OR HBM OR D램 OR 낸드 OR 디스플레이 OR OLED OR 소부장",
                "반도체 실적",
            ],
            "자동차·모빌리티": [   # 이차전지는 완성차 밸류체인으로 보고 여기 귀속
                "완성차 OR 자동차부품 OR 전기차 OR 이차전지 OR 배터리 OR 자율주행 OR 타이어",
                "완성차 실적",
                "배터리 수주",
            ],
            "조선·방산·기계": [
                "조선업 OR 조선사 OR 해운 OR 방산 OR 항공우주 OR 건설기계 OR 공작기계 OR 플랜트",
                "조선 수주",
            ],
            "건설·부동산": [
                "건설사 OR 시공사 OR 재건축 OR 주택사업 OR 리츠 OR 부동산PF OR 프로젝트파이낸싱 OR 도급",
                "건설사 실적",
            ],
            "에너지·화학": [
                "정유 OR 석유화학 OR 화학업계 OR LNG OR 발전사 OR 원전 OR 재생에너지 OR 태양광 OR 수소",
                "석유화학 실적",
            ],
            "철강·소재": [
                "철강 OR 제철 OR 비철금속 OR 알루미늄 OR 시멘트 OR 제지업계 OR 유리업계",
                "철강 실적",
            ],
            "제약·바이오": [
                "제약사 OR 바이오 OR 신약 OR 임상 OR CDMO OR 위탁생산 OR 의료기기 OR 헬스케어",
                "제약 실적",
            ],
            "유통·소비재": [
                "유통업계 OR 백화점 OR 대형마트 OR 이커머스 OR 편의점 OR 식품업계 OR 화장품 OR 면세점",
                "유통업계 실적",
                "식품업계 실적",
            ],
            "금융·보험": [
                "금융지주 OR 시중은행 OR 증권사 OR 보험사 OR 카드사 OR 캐피탈 OR 저축은행 OR 자산운용",
                "보험사 회계",   # IFRS17·계리적가정 — 회계 렌즈로 가치가 가장 높은 축
                "금융지주 실적",
            ],
            "IT·플랫폼·게임": [
                "플랫폼 기업 OR 게임사 OR 인터넷 기업 OR 클라우드 OR SI업계 OR 소프트웨어 기업",
                "게임사 실적",
            ],
            "통신·미디어·엔터": [
                "통신사 OR 이동통신 OR 방송사 OR 미디어 기업 OR 엔터테인먼트 OR 콘텐츠 기업 OR OTT",
                "통신사 실적",
                "엔터테인먼트 실적",
            ],
        },
        # 관련성 게이트(핵심) — 제목에 '숫자로 드러나는 사건' 도메인어가 하나도 없으면 제외.
        # 넓은 앵커 쿼리(풀 A)가 끌어온 제품·기술·정책 기사를 여기서 전량 떨군다.
        "industry_require_any": [
            # 손익·실적
            "실적", "영업이익", "영업손실", "순이익", "당기순", "적자", "흑자", "매출", "매출액",
            "어닝", "컨센서스", "가이던스", "잠정실적", "수익성", "영업마진", "원가",
            # 자본·자금조달
            "유상증자", "무상증자", "증자", "회사채", "전환사채", "신주인수권", "자사주", "배당",
            # ⚠️ 단독 "공모"는 금지 — '사진 공모전'·'스타트업 공모'가 통과한다(실측). 반드시 복합어로.
            "차입", "자금조달", "공모주", "공모가", "공모청약", "청약", "상장", "ipo", "기업공개",
            "상장폐지", "액면분할",
            "주주환원", "밸류업",
            # 딜·구조조정
            "인수", "합병", "m&a", "m＆a", "매각", "지분", "출자", "물적분할", "인적분할", "분할합병",
            "구조조정", "본입찰", "우선협상", "실사", "밸류에이션", "기업가치", "경영권",
            "희망퇴직", "감원", "사업재편", "철수",
            # 투자·수주
            "수주", "공급계약", "장기계약", "설비투자", "증설", "capex", "공장 건설", "공장 신설",
            "생산능력", "가동률",
            # 회계·공시·재무리스크
            "공시", "재무제표", "감사보고서", "감사의견", "내부회계", "손상", "손상차손", "충당금",
            "대손", "부채비율", "자본잠식", "워크아웃", "회생절차", "법정관리", "신용등급",
            "재무구조", "현금흐름", "차입금", "유동성", "지배구조", "주주총회", "이사회",
        ],
        # 노이즈 제외(제목 부분일치). ⚠️ news_exclude 재사용 금지 — 정치어가 산업정책 기사를 오차단한다.
        # 산업 스트림 최대 노이즈원 = **증권가 시황·특징주**(재무어를 다 포함해 게이트를 그냥 통과함).
        "industry_exclude": [
            # 시황·주가 (최우선 차단)
            "특징주", "상한가", "하한가", "급등", "급락", "강세", "약세", "테마주", "관련주",
            "목표주가", "목표가", "투자의견", "매수 추천", "비중확대", "장중", "개장", "마감시황",
            "코스피 마감", "코스닥 마감", "증시 마감", "주간 증시", "리딩방", "수익률 인증",
            "주가 전망", "52주 신고가", "공매도 잔고", "황제주", "주식 리딩",
            # 띄어쓰기 없는 변형까지 — '[주간증시전망]'이 '주간 증시'를 피해 통과한 실측 사례
            "증시전망", "주간증시", "증시 전망", "서학개미", "동학개미",
            # 행사·동정·PR
            "시상", "수상", "기획전", "캠페인", "부고", "위촉", "임명식", "골프", "기부", "동정",
            "승진", "영전", "[프로필]", "채용설명회", "간담회 개최", "협약 체결", "MOU 체결",
            "봉사활동", "사회공헌",
            # 잡음
            "코인", "암호화폐", "(보도설명)", "(해명)", "랜섬", "피싱", "해킹", "악성코드",
            "공모전", "사진 공모", "아이디어 공모",   # '공모'류 행사(자금조달 아님)
        ],
        # 출처 제외 — ⚠️ news_exclude_sources 재사용 금지: 지역지는 산업(지역 공장·조선·석화)에
        # 유효 기사가 많다. 증권정보 애그리게이터·블로그성만 차단.
        "industry_exclude_sources": ["Naver Blog", "Hypebeast", "인포스탁데일리"],
        # 의미 군집(임베딩) — 어휘로 못 묶는 '같은 사건·다른 표현'을 보조 병합.
        # embeds.refine만 쓴다(제목 벡터 코사인). **enrich는 쓰지 않는다** — enrich의 프로토타입은
        # news_queries를 임베딩하므로 산업에 적용하면 카테고리 체계가 어긋난다.
        # ⚠️ 캐시 파일은 반드시 뉴스와 분리 — _save_cache가 '현재 목록 url'만 남기고 자르기 때문에
        #    한 파일을 공유하면 매 실행 서로의 벡터를 축출해 재임베딩이 무한 반복된다.
        "industry_embed_enabled": True,
        "industry_embed_threshold": 0.83,
        "industry_embed_candidate_min_tokens": 2,   # 산업은 업종어가 흔해 공통토큰 1이면 의심쌍이 폭증 → 2
        # 이 캐시는 **커밋하지 않는다**(.gitignore). 벡터 파일은 수 MB라 3시간마다 커밋하면 리포가 부푼다.
        # 캐시가 없으면 매 실행 재임베딩하지만 제목 200여 건이라 비용이 사실상 0(voyage-3.5-lite).
        "industry_embed_cache_path": "industry_vectors.json",
        # 근접중복 파라미터(뉴스와 값은 같지만 독립 튜닝 여지를 위해 별도 키)
        "industry_neardup_jaccard": 0.6,
        "industry_neardup_overlap": 0.67,
        "industry_neardup_min_tokens": 4,
        # ===== 기업 사전 (산업 <-> 기업 <-> 별칭) =====
        # 표준명이 키. industries=소속 산업(복수 가능), aliases=제목에 나올 수 있는 표기(표준명은 자동 포함),
        # dart=DART 검색어(생략 시 표준명), strict=True면 짧거나 동음이의라 경계 검사 강제.
        "industry_companies": {
            "삼성전자":     {"industries": ["반도체·전자"], "aliases": []},
            "SK하이닉스":   {"industries": ["반도체·전자"], "aliases": ["하이닉스"]},
            "LG디스플레이": {"industries": ["반도체·전자"], "aliases": ["LGD"]},
            "LG이노텍":     {"industries": ["반도체·전자"], "aliases": []},
            "삼성전기":     {"industries": ["반도체·전자"], "aliases": []},
            "한미반도체":   {"industries": ["반도체·전자"], "aliases": []},
            "현대차":       {"industries": ["자동차·모빌리티"], "aliases": ["현대자동차"], "dart": "현대자동차"},
            "기아":         {"industries": ["자동차·모빌리티"], "aliases": ["기아차"], "strict": True},
            "현대모비스":   {"industries": ["자동차·모빌리티"], "aliases": []},
            "LG에너지솔루션": {"industries": ["자동차·모빌리티"], "aliases": ["LG엔솔"]},
            "삼성SDI":      {"industries": ["자동차·모빌리티"], "aliases": []},
            "SK온":         {"industries": ["자동차·모빌리티"], "aliases": [], "strict": True},
            "HD현대중공업": {"industries": ["조선·방산·기계"], "aliases": ["현대중공업"]},
            "한화오션":     {"industries": ["조선·방산·기계"], "aliases": []},
            "삼성중공업":   {"industries": ["조선·방산·기계"], "aliases": []},
            "한화에어로스페이스": {"industries": ["조선·방산·기계"], "aliases": ["한화에어로"]},
            "HMM":          {"industries": ["조선·방산·기계"], "aliases": [], "strict": True},
            "삼성물산":     {"industries": ["건설·부동산"], "aliases": []},
            "현대건설":     {"industries": ["건설·부동산"], "aliases": []},
            "GS건설":       {"industries": ["건설·부동산"], "aliases": []},
            "대우건설":     {"industries": ["건설·부동산"], "aliases": []},
            "DL이앤씨":     {"industries": ["건설·부동산"], "aliases": []},
            "SK이노베이션": {"industries": ["에너지·화학"], "aliases": ["SK이노"]},
            "GS칼텍스":     {"industries": ["에너지·화학"], "aliases": []},
            "에쓰오일":     {"industries": ["에너지·화학"], "aliases": ["S-Oil", "에스오일"], "dart": "S-Oil"},
            "LG화학":       {"industries": ["에너지·화학"], "aliases": []},
            "롯데케미칼":   {"industries": ["에너지·화학"], "aliases": []},
            "한국전력":     {"industries": ["에너지·화학"], "aliases": ["한전"], "dart": "한국전력공사"},
            "포스코홀딩스": {"industries": ["철강·소재"], "aliases": ["포스코"], "dart": "POSCO홀딩스"},
            "현대제철":     {"industries": ["철강·소재"], "aliases": []},
            "고려아연":     {"industries": ["철강·소재"], "aliases": []},
            "삼성바이오로직스": {"industries": ["제약·바이오"], "aliases": ["삼성바이오"]},
            "셀트리온":     {"industries": ["제약·바이오"], "aliases": []},
            "유한양행":     {"industries": ["제약·바이오"], "aliases": []},
            "한미약품":     {"industries": ["제약·바이오"], "aliases": []},
            "SK바이오팜":   {"industries": ["제약·바이오"], "aliases": [], "dart": "에스케이바이오팜"},
            "이마트":       {"industries": ["유통·소비재"], "aliases": []},
            "롯데쇼핑":     {"industries": ["유통·소비재"], "aliases": []},
            "쿠팡":         {"industries": ["유통·소비재", "IT·플랫폼·게임"], "aliases": []},
            "CJ제일제당":   {"industries": ["유통·소비재"], "aliases": []},
            "아모레퍼시픽": {"industries": ["유통·소비재"], "aliases": ["아모레"]},
            "KB금융":       {"industries": ["금융·보험"], "aliases": ["KB금융지주", "국민은행"]},
            "신한지주":     {"industries": ["금융·보험"], "aliases": ["신한금융", "신한은행"]},
            "하나금융지주": {"industries": ["금융·보험"], "aliases": ["하나금융", "하나은행"]},
            "우리금융지주": {"industries": ["금융·보험"], "aliases": ["우리금융", "우리은행"]},
            "삼성생명":     {"industries": ["금융·보험"], "aliases": []},
            "삼성화재":     {"industries": ["금융·보험"], "aliases": [], "dart": "삼성화재해상보험"},
            "네이버":       {"industries": ["IT·플랫폼·게임"], "aliases": ["NAVER"], "dart": "NAVER"},
            "카카오":       {"industries": ["IT·플랫폼·게임"], "aliases": [], "strict": True},
            "크래프톤":     {"industries": ["IT·플랫폼·게임"], "aliases": []},
            "엔씨소프트":   {"industries": ["IT·플랫폼·게임"], "aliases": ["엔씨"]},
            "넷마블":       {"industries": ["IT·플랫폼·게임"], "aliases": []},
            "SK텔레콤":     {"industries": ["통신·미디어·엔터"], "aliases": ["SKT"]},
            "KT":           {"industries": ["통신·미디어·엔터"], "aliases": [], "strict": True, "dart": "케이티"},
            "LG유플러스":   {"industries": ["통신·미디어·엔터"], "aliases": ["LGU+"]},
            "하이브":       {"industries": ["통신·미디어·엔터"], "aliases": [], "strict": True},
            "CJ ENM":       {"industries": ["통신·미디어·엔터"], "aliases": ["CJENM"]},
        },
        # 태깅 금지 별칭 — 일반명사와 충돌해 오탐이 잦은 것(사전 실수 안전망)
        "industry_company_stopwords": ["대상", "삼표", "동원", "대성", "미래", "한샘"],
        "industry_company_max_tags": 3,   # 기사 1건당 기업 태그 상한
        # DART 전자공시 검색 링크 템플릿 — industry.json에 실어 프론트가 그대로 사용(API 키 불필요)
        "industry_dart_search_url": "https://dart.fss.or.kr/dsab007/main.do?textCrpNm={q}",
        # DART 전자공시 Open API — 기업별 감사인·3개년 주요계정·최근 공시(docs/data/companies.json).
        # ⚠️ DART_API_KEY는 GitHub Secret에서만. **키 없으면 기능 전체 비활성**(파일 미생성,
        #    프론트는 DART 검색 링크만 노출 → 사이트는 정상). VOYAGE_API_KEY와 같은 게이트 패턴.
        "dart_enabled": True,
        "dart_filing_years": 2,                 # 최근 공시 조회 기간(년)
        "companies_min_interval_minutes": 10080,  # 재무·감사인은 분기 단위로만 바뀜 → 주 1회
        # 아카이브 하한 — 이 날짜 이전 발행 기사는 아카이브에 넣지 않는다.
        # (git 스냅샷에 첫 수집이 끌어온 4월 기사가 3건 섞여 있어 월 칩이 지저분해짐)
        "archive_since": "2026-05-01",
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
            # 산업은 industry_min_interval_minutes(180) 게이트로 3시간에 1회만 수집 → 기대간격도 그에 맞춤
            "industry.json": {"label": "산업 기사", "expected_minutes": 240},
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
        "llm_model": "claude-haiku-4-5",   # 최저가 비전 모델($1/$5 MTok) — 스냅샷 정상여부 판독엔 충분(토큰비 절감)
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
        "llm_model": "claude-haiku-4-5",   # 최저가 비전 모델($1/$5 MTok) — 목록 페이지 공고수 세기엔 충분(토큰비 절감)
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

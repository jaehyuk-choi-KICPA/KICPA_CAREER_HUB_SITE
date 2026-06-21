# 회법몬 수집(스크랩) 엔진 개선 일지

채용공고·기사·인사이트를 모아오는 **수집 엔진의 보완 기록**입니다. 좌상단 공식 빌드 번호와 **무관**하게,
"무엇이 문제였고, 어디에 어떤 코드를 얹어 해결했는지"의 흐름을 남깁니다.

## 수집 파이프라인 개요 (모든 변경은 이 골격 위에서 일어남)

```
소스별 어댑터(src/adapters/*)  →  sources.fetch_all (도메인 간 병렬, 각 호출을 safe_fetch로 감쌈)
   →  분류 classify.py (법인 / 직무)  →  필터 filters.py (경력 제외 등)
   →  export.py 가 생성·정리(중복제거 · 보존기간 · 일자별 상한 · 신규/금일 판정)
   →  docs/data/{jobs,news,insights}.json  →  GitHub Pages 서빙
```

- **견고성 원칙:** 한 소스가 깨져도 나머지는 살아남는다(전체 실패 금지 — `safe_fetch`).
- **규칙 기반:** 분류·필터·큐레이션은 전부 키워드 규칙(`config.py`의 `dashboard`). 코어는 LLM 미사용.
- **확장 방법:** 새 소스 = 어댑터 1개 추가 + 한 줄 등록 / 새 규칙 = `config.py`에 키 추가.

> 작성 규칙: 최신이 맨 위. 각 항목 = **증상/계기 → 무엇을 → 어디에 얹었나(코드 플로우) → 효과/검증**.

---

## 2026-06-22 — KICPA 모집대상/자격요건 본문 수집(body_excerpt) → 제목 너머 필터·분류

- **증상/계기:** KICPA 공고는 `body_excerpt`가 비어 **사실상 제목(+회사명)만으로** 필터링됨. 그래서 "제목은 평범한데 모집대상은 경력 전용", 반대로 "제목은 경력인데 자격요건은 신입/경력무관" 케이스를 못 가림(사용자 지적). KICPA 목록·`th`표엔 모집대상이 없고 **상세 본문 `div.txt_infor`**(모집부문·담당업무·자격요건)에만 있음.
- **무엇을 / 어디에:** KICPA 어댑터가 마감일 위해 **이미 상세페이지를 방문**하므로(`_enrich_deadline`), 같은 soup에서 `div.txt_infor`(폴백 `td.txt_left.last`) 텍스트를 긁어 `body_excerpt`에 담음(≤1000자, 추가 요청 0). 본문도 **native_id 캐시**로 1회만 수집·재사용 — `state.bodies_by_native_id()` + `build_kicpa_adapters(.., body_cache)` + 어댑터 게이트를 "마감일·본문 중 하나라도 없으면 보강"으로 확장. **`State.update` 갱신 필드에 `body_excerpt` 추가**(기존 엔트리도 채워지고 carried·캐시 일관 — 빈 값은 덮지 않음).
- **효과/검증:** 어댑터 fetch 10/10 body 채움(800~1000자), state 14/20 영속(캐시 작동→다음 run 재요청 안 함). 필터·`classify_qualification`이 모집대상까지 보고 판정(수습CPA 정밀화). 전체 **68 테스트 통과**. (jobs.json 출력엔 body 미포함 — 프론트 미표시·내부 처리 전용.)

---

## 2026-06-21 (6) — 경력공고 누출 3중 차단(신입불가 오구제 + N년차 + grace 부활)

- **증상/계기:** 일반 CPA 보드(`kicpa_cpa`)의 **'세무기장 경력 3년이상 모집(신입불가)'**(서율회계법인)가 NEW로 노출. (사용자는 스크랩 범위가 넓어진 것으로 오인했으나 `kicpa_cpa`는 init부터 수집한 KICPA 2보드 중 하나 — **범위 변경 없음**. 사용자 결정: 일반 보드 유지 + 필터 강화.) 세 갈래로 샜음:
- **무엇을 / 어디에:**
  1. **'신입불가' 부분일치 오구제** — 제목 '3년이상'(hard)인데 '신입불가'의 '신입'이 예외어로 잡혀 통과. `config.filters.exception_negators`(불가·제외·아님 등) 신설 + `filters._exception_present()`가 예외어 바로 뒤 부정어면 예외 무효. `passes`의 제목·본문 예외검사 2곳 교체.
  2. **N년차 미탐지** — hard_exclude에 `년차`·`년 차`·`경력사원` 추가('경력 3년차' 등이 '년 이상'에 안 걸리던 갭).
  3. **grace 부활(핵심)** — 필터로 빠진 공고가 `state`에 남아 `carry_forward`(grace)로 되살아남. `export.py`에서 `carried = filter_postings(state.carry_forward(...), cfg)` — 복원분도 현재 필터를 통과해야만 유지(목록 일시 누락=복원 / 필터 제외=복원 금지). **이게 없으면 1·2를 고쳐도 서율이 계속 부활했음.**
- **효과/검증:** 단위검증(서율·N년차·경력사원→제외, 진짜 신입병기·수습보드 bypass→유지). 회귀테스트 2종 추가, 전체 **68 통과**. 재수집 최종: 서율/신입불가 **잔존 0**(kicpa_cpa 8).

---

## 2026-06-21 (5) — 수습CPA 보드(kicpa_susup) 경력 필터 면제

- **증상/계기:** KICPA 수습CPA 보드 공고 중 **제목은 '경력직'인데 모집대상엔 신입/경력 병기**인 건이 `filters.passes`의 hard-exclude 가드(제목에 경력 키워드+제목에 예외어 없음→제외)에 걸려 누락. 보드 자체가 수습CPA 타깃을 확정하므로 떨구면 안 됨.
- **무엇을 / 어디에:** `config.filters`에 **`bypass_sources`**(경력 필터 면제 소스 목록) 신설 = `["kicpa_susup"]`. `filters.passes` 맨 앞에서 `p.source in bypass_sources`면 무조건 통과(하드코딩 없이 config 키로). 카나리아 `_check_filter_leakage`도 같은 면제를 적용(면제 소스는 '경력 누출'로 오탐하지 않게 skip).
- **효과/검증:** 단위검증 — `kicpa_susup`+경력직 제목→통과, 타 소스(samil)+경력직 제목→여전히 제외. 재수집 시 kicpa_susup 18건 정상. 보드에 그런 공고가 올라오면 이제 그대로 수용.

---

## 2026-06-21 (4) — 구글뉴스 '빈 피드' 재시도(카테고리 통째 0건 방지)

- **증상/계기:** 라이브에서 **세무 기사 0건**. 직전 15:01 수집엔 세무 17건이었는데 15:31 수집에서 0. 구글뉴스 세무 쿼리 RSS를 직접 호출하니 **item 0개**(같은 쿼리가 잠시 뒤 재호출 시 100건). 즉 구글이 특정 쿼리에 **간헐적으로 200+빈 피드**를 반환 → 뉴스는 매 수집이 새 스냅샷이라 그 회차 해당 카테고리가 통째로 0건이 됨(소스 5/5 '성공'으로 표시돼 조용한 실패).
- **무엇을 / 어디에:** `adapters/news_rss.py GoogleNewsAdapter.fetch`에 **빈 피드 재시도** — `item` 파싱 결과가 0개면 1.5초 쉬고 최대 3회 재시도. 도메인 쿼리(세무·감사·딜·채용)는 사실상 항상 결과가 있으므로 0건=일시 throttle로 간주(정상 0건 쿼리는 우리 도메인에 없음 → 오버헤드 무해).
- **효과/검증:** 재수집 시 세무 0→32건 복구(총 170: 감사68·딜48·세무32·채용22). 재시도가 빈응답 회차를 흡수해 카테고리 누락 사고를 막음.
- **남은(선택):** 더 강한 견고성으로 '직전 수집의 신선 기사 carry-forward'(jobs grace와 동형)도 가능 — 재시도가 실패하는 장기 throttle까지 방어. 현재는 재시도로 충분 판단.

---

## 2026-06-21 (3) — 뉴스 파이프라인에서 '구조조정' 키워드 제거(딜 노이즈)

- **증상/계기:** 딜·M&A 수집어 `구조조정`이 회계·딜과 무관한 기사를 대량 유입(게임사 CEO의 엑스박스/게임패스 비판, 공기업 경영평가, 면세점·유통 구조조정, 법인 해산, 방송사 회생 등). 사용자가 라이브에서 직접 확인하고 "무관 기사 과다"로 제거 요청. (사용자가 처음엔 `field_keywords.딜`(채용 직무분류·레거시)에서 뺐으나 뉴스 경로와 무관 → 원복.)
- **무엇을 / 어디에:**
  1. `config.dashboard.news_queries.딜·M&A`에서 `구조조정 OR` 토큰 제거 — 구글뉴스 RSS가 애초에 해당 기사를 안 가져오게(수집 단계 차단).
  2. `config.dashboard.news_require_any`(관련성 게이트)에서 `구조조정` 제거 — 다른 경로로 들어와도 제목에 도메인어가 없으면 탈락(2차 방어). **단 `사모`·`매각`·`인수합병` 등 다른 도메인어가 함께 있는 정상 기사는 그대로 통과**(게이트는 OR).
  3. 이미 라이브 `docs/data/news.json`에 적재된 `구조조정` 단독 기사 5건은 새 게이트 로직을 그대로 적용한 1회성 스크립트로 즉시 제거(다른 도메인어 보유 기사는 보존). `field_keywords.딜`은 원래대로 `구조조정` 복원(직무분류 부작용 제거).
- **효과/검증:** news.json 84→79건(5건 제거: 문스튜디오·발전5사경평·클럽디청담해산·면세점·JTBC회생). 제거목록 ensure_ascii=False JSON으로 육안 검증, news.json `json.load` 유효성 OK. 다음 수집부터 `구조조정` 단독 기사는 미유입.

---

## 2026-06-21 (2) — 채용알림 웹푸시 가동 + 통합 모니터 cron(5h)

- **무엇을 / 어디에:**
  1. **채용알림 발송 가동** — `run-all.yml`에 `python -m src.notifier` 스텝 + 시크릿 env(`VAPID_PRIVATE_KEY`·`SUBS_READ_TOKEN`) + `notify_status.json` 커밋. `notifier.py`에 **scope 필터**(`_is_susup` → `classify_qualification`): 수습CPA 전용 구독자는 수습CPA 공고만 발송. `worker/subscriptions.js`가 구독 record에 `scope` 저장. config `notifications.enabled=true`, VAPID 키쌍 재발급(공개키→config·app.js, 개인키→GitHub Secret). Cloudflare Worker 배포(wrangler). `requirements.txt`에 pywebpush.
  2. **통합 모니터** — `monitor.yml`(cron `0 */5 * * *`)이 canary(소스 급감)+sitecheck(신선도 셀프힐링)를 묶어 5시간 점검. 신선도 미갱신만 자동 재수집, 그 외 `monitor`/`needs-human` 이슈. freshness(1h)·sitecheck(3h)는 안정화까지 병행.
- **검증/효과:** VAPID 서명 OK · Worker /subscribe scope 저장·/list Bearer·미인증 401 확인 · seed 43건 억제(콜드스타트 방지) · notifier 클린 실행 · 라이브(hbmons.com)에 새 VAPID 공개키·sw.js·manifest 배포 확인.
- **남은:** monitor 첫 cron 실행(=supervised 검증) 후 안정 시 freshness/sitecheck cron 폐기. 브라우저 구독→수신 실테스트. [[insight-notifier-inactive]] 갱신(이제 가동).

---

## 2026-06-21 — 자격요건·채용구분 분류 신설(직무 대체) + is_new 24h + 기사 게이트·균형정렬

- **증상/계기:** 채용 직무분류(딜/감사/택스/기타)가 수습공인회계사 타깃엔 덜 결정적. 기사 화면이 딜로 도배(코인·블로그·해외 IPO·지자체 행정 노이즈 + dedup 비대칭).
- **무엇을 / 어디에:**
  1. **자격요건·채용구분 분류** — `classify.py`에 `classify_qualification`(수습CPA/자격무관)·`classify_emp_kind`(인턴/정규직/계약직/파트타임). 판정 입력 = 제목+회사+`body_excerpt`+`emp_type`+`category` 종합(`_detail_text`). KICPA 수습보드(`kicpa_susup`)=무조건 수습CPA, 그 외 `qual_susup_keywords` 매칭·`qual_exclude_keywords` 미해당이면 수습CPA. config에 `qual_susup_keywords`·`qual_exclude_keywords`·`empkind_keywords` 추가. `export.py build_jobs`가 `qualification`·`emp_kind` + `counts.by_*` 출력(`field`는 레거시 병행).
  2. **NEW=게시 24h** — `export.py`가 발견시각(`first_seen`) 24h 이내를 `is_new`로(게시일은 날짜뿐이라 24h 정밀도엔 발견시각 사용). 프론트 '방금 올라온 공고' 패널도 `is_new` 기준으로 통일.
  3. **기사 게이트(노이즈 차단)** — config `news_exclude`(코인·암호화폐·(보도설명)·(해명))·`news_exclude_sources`(대한민국 정책브리핑·Naver Blog)·신규 `news_local_gov_action`/`news_local_gov_keep`. `export.py build_news` 루프에 **지자체 행정 게이트**(○○시/군 + 세미나·유예 등, 국가기관 언급 시 유지) 1블록.
  4. **딜 편중 완화** — 딜 보존 60→30일(`news_recent_days_by_category`). 프론트 `app.js spreadCategories`(같은 카테고리 3연속 방지) — dedup 압축 비대칭(감사/세무는 같은 사건 다매체→1건, 딜은 개별 건→다수)으로 '전체' 상단이 딜로 도배되는 것 완화.
- **효과/검증:** `export` 재수집 OK(채용 68·기사 159). 게이트 누락 0(코인·보도·블로그·지자체 제거 확인). 기사 분포 감사62·세무34·딜45로 딜 독점 해소. 자격요건 수습CPA18/자격무관50, 채용구분 인턴29/정규34/계약4/파트1.
- **남은 튜닝(시각 반복검토 필요):** 딜 쿼리 추가 축소(일반 IPO/매각·해외 노이즈), `when:` 최신창 연산자, 영풍 같은 대형 단일사건 dedup 임계. Big4 모집대상 상세수집(`body_excerpt`)으로 수습CPA 판정 정밀화.

---

## 2026-06-19 — 감사 쿼리 2풀 분리 + 딜 쿼리 단순화 + 정렬 tiebreaker + Investing.com 차단

- **증상/계기:** 06-19 감사 기사 1건(당일분 거의 없음). 딜 건수도 18건으로 낮음. 기사 카드 같은 날 내 순서가 뒤죽박죽.
- **진단:**
  1. Google News RSS는 **관련도순 100건 상한** → 키워드가 많은 단일 쿼리는 오늘 기사가 100번 밖으로 밀려 유실.
  2. 딜 쿼리가 긴 복합 구문("Big4 회계·세무·자문 OR M&A 자문")이라 구글이 구문 전체를 찾아 오히려 건수가 줄고, `require_any` 게이트가 단일 키워드 없이 떨어짐.
  3. 같은 날 기사 간 시각 정보 없음(`published` = 날짜만) → 정렬이 타이일 때 불안정.
  4. `감사인` 키워드가 `Investing.com 한국어` 미국 기업 주주총회 번역 기사를 끌어옴(제목에 국가명 없어 외국필터 우회).
- **무엇을 / 어디에:**
  1. **감사 쿼리 2풀 분리** (`config.yaml` `news_queries.감사` = `list[str]`):
     - 풀A(기준·제도): `회계기준 OR 감사기준 OR K-IFRS OR 내부회계관리제도 OR 회계감독 OR 금융감독원 회계 OR 감사의견 OR 외부감사 OR 회계감리`
     - 풀B(이슈·처분): `감사보수 OR 분식회계 OR 지정감사 OR 표준감사시간 OR 외감법 OR 외감 OR 감사인 OR 증선위 OR 회계처리`
     - `build_news_adapters()`(`news_rss.py`)가 `str | list[str]` 지원 → 2번째+ 풀은 source명 `gnews_감사_2`로 접미사. URL 기반 dedup이 풀 간 중복 자동 제거.
     - 부수정리: `감사보수`를 채용·시험 쿼리에서 제거(dedup 선점 때문에 감사 카테고리가 박탈되던 버그).
  2. **딜 쿼리 단순화** — 복합 구문을 단어 단위로: `인수합병 OR M&A OR IPO OR 기업공개 OR 기업가치평가 OR 구조조정 OR 사모펀드 OR 바이아웃 OR 실사 OR 재무자문 OR 리그테이블 OR 경영권 OR 매각`
     - `require_any`에 `매각`, `바이아웃`, `증선위` 추가(새 딜/감사 단어 게이트 통과용).
  3. **published_at 필드 추가** (`news.py` NewsItem 데이터클래스): RFC822 pubDate에서 UTC 정규화된 `yyyy-mm-ddTHH:MM:SS`를 `published_at`으로 보존(기존 `published`는 날짜만). `export.build_news` 정렬 키를 `published_at`으로 교체.
  4. **Investing.com 차단** — `news_foreign_sources`에 `"investing.com"` 추가(세무·감사 카테고리에서 source_label 부분일치로 차단).
- **효과/검증:** 감사 06-19 기사 1건→3건, 전체 감사 30건→38건. 딜 18건→26건. 정렬 tiebreaker로 같은 날 최신 기사가 위로.

---

## 2026-06-18 — 기사 수집량 회복(딜 0건 사고) + 임베딩 과병합 교정

- **증상:** 라이브 기사 수가 비정상적으로 적고(총 30~41), **딜·M&A가 0건**까지 떨어지는 일 발생. 사용자가
  "오늘 기사 수가 너무 작다 / 딜이 다 날아갔다" 지적.
- **진단(단계별 funnel 계측):** 두 가지 병목이 겹침.
  1. **RSS 카테고리당 상한이 너무 낮음(`news_per_category`=50).** 구글뉴스 RSS는 **관련도순**이라 최신 기사가
     피드 뒤쪽(50~100위)에도 흩어져 있는데 50에서 잘라 **뒤쪽 신선기사를 통째 유실**. 실측: 같은 쿼리를
     100건까지 받으면 recency 통과분이 **세무 40→85·감사 39→72**로 거의 2배. → **75로 상향**.
  2. **임베딩 의미군집 임계(`news_embed_threshold`)가 너무 낮음(0.82).** 짧은 한국어 제목에서 임베딩이
     비변별적인데 후보쌍(같은 카테고리+공통토큰≥1)이 느슨하고 union-find가 전이연결돼 **별개 사건이 하나로
     과병합**(예: 한공회장 '선발 과도' 발언 ↔ 금융위 '수습처 확대' 발표가 한 카드로). 표시 대표 수가 40까지 붕괴.
     → 먼저 0.88로 올렸더니 이번엔 **과소병합**(발전공기업 통합 동일사건이 4카드로 흩어짐) → 0.85(중간)를 거쳐
     **0.83**으로 정착(실측: 발전통합 동일사건이 1카드(+7)로 완전 병합·금감원 덤핑 18매체 깔끔·선발↔수습처는 여전히 분리).
  3. **딜 공급 자체가 얇음.** 딜 회계기사는 제목에 회계법인이 안 들어가는 일반 M&A가 많아 `require_any` 게이트를
     못 넘고, recency(35일)까지 겹쳐 RSS draw가 나쁘면 0까지 떨어짐. → 딜 보존기간 **35→60일**(저빈도·고관련 원칙).
- **무엇을/어디에:** `config.py` `dashboard` — `news_per_category` 50→75, `news_embed_threshold` 0.82→**0.83**,
  `news_recent_days_by_category['딜·M&A']` 35→60. (임베딩은 끄지 않고 임계만 조정 — 동일사건 군집은 유지.)
- **효과/검증:** 키 ON 재빌드 시 딜 0건 사고 해소, 동일사건(발전공기업 통합 1카드·금감원 덤핑 등) 적극 병합되고
  별개사건(선발 과도↔수습처 확대)은 분리. **임계 튜닝 교훈: 0.82↓=과병합 / 0.88=과소병합 / 0.83=동일사건 적극병합(선호).**
  ⚠️ 카테고리별 표시 건수는 구글뉴스 RSS draw에 따라 매 수집 출렁임(예: 수습처 기사가 안 들어오면 채용 카드가 1건까지) — 임계 탓 아님.

---

## 2026-06-18 — (v1.09) 인사이트 '금일' 폐기·단순화 + 채용 first_seen 노출 + build_news 핫픽스

- **build_news 핫픽스(긴급):** `build_news`가 일자상한 적용 블록·print·`return`을 잃어 **None 반환** → `_write_guarded`에서
  AttributeError로 전체/뉴스 export('Scrape all' 단계) 크래시(run-all·scrape-news 연속 실패). 일자상한 루프 + return 복원.
- **인사이트 단순화:** `build_insights`에서 관련성 정렬·`_mark_insight_new`·`today_count`·is_new 정렬 전부 제거. 함수
  `_mark_insight_new`·`_other_month_only`·`_EN_MONTHS`/월 regex 삭제, `insights_seen.json` 폐기(git rm). 페이로드 =
  `{generated_at, items}`만, **법인별 스크랩 순서(≈사이트 최신순) 그대로**. 프론트가 source_label로 4박스 그룹핑 →
  박스별 랜덤 추천 + 펼치기(최신순). 어댑터 라벨 `딜로이트안진`→`Deloitte안진`(영문 prefix 통일).
- **채용 first_seen 노출:** `build_jobs` item에 `first_seen`(state.entries의 발견시각) 추가 → 프론트 '새로 올라온 공고'가
  게시일(날짜뿐) 대신 **발견시각 최신순**으로 정렬(같은 날 타이로 방금 올라온 공고가 밀리던 문제 해결).
- **모니터/워크플로 정리:** canary `_check_insight_order` 제거(is_new 없음), sitecheck '인사이트 금일수 타당성' 체크 제거,
  scrape-insights·run-all·sitecheck의 git add에서 `insights_seen.json` 제거.
- **검증:** 무키 news export 정상 반환(이슈 86), insights payload에 today_count/is_new 없음·4법인×12·insights_seen 미생성,
  헤드리스로 4박스·랜덤·펼치기·새공고 first_seen 정렬(삼정 인턴 최상단) 확인. py_compile 전부 OK.

## 2026-06-18 — 임베딩 관련성 게이트(#1) + 카테고리 보정(#2) (enrich, 키 있을 때만)

- **증상/계기:** 넓은 OR 쿼리가 키워드 게이트(`news_require_any`)는 통과하지만 의미상 무관한 기사를 통과시키고,
  카테고리가 '어느 쿼리가 가져왔나'로만 정해져 오분류가 남음.
- **무엇을:** 카테고리 4개 프로토타입 벡터와 기사 제목의 코사인으로 ① 오프도메인 드롭 ② 카테고리 보수적 재배정.
  키워드 규칙은 1차 유지, 임베딩은 보조(과드롭·churn 방지 하한).
- **어디에 얹었나(플로우):** `embeds._prototypes`(news_queries 값 4건 임베딩, input_type='query', 매회·캐시 안 함) +
  `embeds.enrich(items, _title_sig, cfg)`. `export.build_news`에서 **정렬 직후·`_dedup_near` 직전(5.5단계)** 호출 —
  dict 단계라 dedup 우선순위 불변, 재배정이 refine 동일카테고리 군집·일자상한 버킷에 반영. 제목 벡터는
  `news_vectors.json` 공유(refine 재사용 → 중복 임베딩 없음). **재배정 카테고리에 recency 재적용 안 함**(over-drop 방지·의도).
  config: `news_embed_relevance_enabled`·`news_embed_category_enabled`·`news_embed_relevance_floor`(0.30)·
  `news_embed_category_margin`(0.08). 키 없으면 enrich no-op → 키워드/쿼리 분류 그대로(폴백).
- **효과/검증:** fake client 단위 — 오프도메인 드롭·오분류 재배정·온도메인/마진미달 불변, 무키 폴백 확인.
- **실데이터 튜닝(`src/embed_tune.py`, 41건, voyage-3.5-lite):** max_sim 분포가 **0.41~0.53로 좁고 노이즈/신호가
  겹침**(정상 '세법개정안' 0.439 < 저가치 '지방세 감사패' 0.444) → 어떤 floor도 정상기사 오드롭. 카테고리 재배정
  후보는 마진 0.002~0.087로 작고 **상위 flip이 대부분 오답**(1위 '법인세 손금 불가'를 세무→딜로). 결론:
  voyage-lite로 짧은 한국어 제목+키워드 게이트 통과분(도메인 균질)은 **비변별적**. → **관련성 floor 0.25(dormant
  안전망)·카테고리 enabled=False**로 확정. 노이즈(지방세 PR)는 키워드 `news_exclude`, 채용 오분류는
  `news_hire_title_keywords`가 더 적합한 레버. 임베딩 **군집(refine/dedup)은 별개로 유효**.

## 2026-06-18 — 의미 군집(임베딩) 2단계 — 어휘로 못 묶는 같은 사건 보조 병합(Voyage, 게이트)

- **증상/계기:** 어휘(Jaccard·포함도) 군집은 '발전공기업 통합' 5건처럼 같은 사건을 매체마다 다른 표현으로 쓴
  헤드라인을 못 묶음(어휘 겹침이 낮음). 의미 군집엔 임베딩이 정석.
- **무엇을:** 1단계 어휘 군집 뒤 **2단계 임베딩 보조 병합**을 추가. 단 **'걸릴 때만'** — 어휘로 안 묶였지만
  같은 카테고리+공통 핵심토큰 ≥N인 **의심 쌍이 있을 때만** Voyage 임베딩을 호출하고, 코사인 ≥ 임계면 병합.
- **어디에 얹었나(플로우):** `src/embeds.py` 신설(`refine`) — VOYAGE_API_KEY 있을 때만 작동(없으면 no-op
  =어휘 군집만, 오프라인·무키 보장 유지). `export.build_news`가 `_dedup_near`(어휘) 직후 `embeds.refine(items, _title_sig, cfg)`
  호출. URL→벡터는 `news_vectors.json`에 캐시(새 기사만 임베딩 → 비용·시간 최소, run-all·scrape-news가 커밋).
  config(`dashboard`): `news_embed_enabled`·`news_embed_model`(voyage-3.5-lite)·`news_embed_threshold`(0.82)·
  `news_embed_candidate_min_tokens`(1)·`news_embed_cache_path`. requirements에 `voyageai`, 워크플로에 `VOYAGE_API_KEY` secret.
- **효과/검증:** fake client 단위검증 — 발전공기업 2건 병합(대표+dupe), 무관·타카테고리는 미병합. 키/패키지 없는
  로컬은 어휘만으로 동일 결과(폴백 무결성). 모든 외부호출 try/except(임베딩 깨져도 어휘 결과 반환).
  ⚠️ **비용:** 제목 짧고+캐시+의심쌍 한정이라 월 센트 단위(대개 free tier). 진짜 트레이드오프는 비용이 아니라
  '코어 생성 경로에 외부 의존성 추가' — 키 없으면 자동 폴백으로 흡수.

## 2026-06-18 — 중복 기사 '버리기→묶기'(군집화) + 같은 사건 보조 매칭

- **증상/계기:** 딜·M&A 등에서 같은 사건을 매체별로 다른 표현으로 쓴 헤드라인이 여러 건 노출(도배). 기존
  `_dedup_near`는 Jaccard≥0.6 근접중복을 **버려서** 정보가 사라졌고, 표현이 다르면 아예 안 묶였음
  (예: '발전공기업 통합 권고' 5건이 5개로 남음).
- **무엇을:** (a) 중복을 버리지 않고 **대표(최신) 1건 + 나머지를 `dupes`로 첨부**해 군집화(프론트가 카드에서
  '동일 주제 기사 N개'로 펼침). (b) 같은 사건·다른 표현을 더 잡도록 **보조 매칭** 추가 — 포함도(겹침/작은쪽)
  ≥`news_neardup_overlap`(0.67) **이면서** 공통 핵심토큰 ≥`news_neardup_min_tokens`(4)면 같은 이슈.
- **어디에 얹었나(플로우):** `export._dedup_near`를 군집화로 재작성(대표=최신, dupes 누적), 매칭 판정을
  `_same_issue(a,b, jaccard, overlap, min_tok)`로 분리. config에 `news_neardup_overlap`·`news_neardup_min_tokens`
  추가(`dashboard`). dupes는 `to_dict` 결과 dict에 동적 추가(title·url·source_label·published). 일자상한
  (`news_max_per_day_per_cat`)은 대표 기준으로만 카운트 → 중복은 금일 수에도 안 잡힘.
- **효과/검증:** 실측 — 묶음 8→16건, 흡수 13→22건. **전 클러스터 수동 점검: 오병합(서로 다른 주제 합침) 0건**
  (보수적 하한 덕에 같은 사건이 여러 묶음으로 '덜 묶이는' 안전한 방향). 프론트 펼침 UI 헤드리스 캡처 확인.
  ⚠️ 완전한 의미 군집은 임베딩 필요(코어 LLM-free 유지) — 어휘 기반은 같은 사건 일부만 묶음(과병합보다 안전 우선).

## 2026-06-18 — 인사이트 '금일' 오인 수정: first_seen 보존(재등장 흡수)

- **증상/계기:** 명백히 오늘 발간이 아닌(예: 5월호) 인사이트가 '금일'로 표시됨. 추적해 보니 법인별 상한
  (~12건) 경계에서 새 글이 올라오면 오래된 글이 목록에서 잠시 밀려나는데, `_mark_insight_new`가 **현재
  목록에 없는 url을 state에서 즉시 삭제**(`{u:d ... if u in cur}`) → 소스 재정렬로 그 글이 다시 상위로
  올라오면 `first_seen=오늘`로 재기록돼 **오래된 글이 신규로 오인**(jobs '깜빡임'과 동일 패턴).
- **무엇을:** first_seen 기록을 목록에서 빠져도 **보존**(재등장 시 원래 날짜 유지 → 신규 오인 방지).
- **어디에 얹었나(플로우):** `export._mark_insight_new` 말미의 prune을 교체 — 현재 목록은 항상 보존하고,
  무한증가는 `MAX_SEEN`(600) 초과 시 '현재 목록에 없으면서 first_seen 오래된 것'부터만 정리.
  `insights_seen.json`은 scrape-insights·run-all·sitecheck 워크플로가 커밋(CI 간 영속).
- **효과/검증:** 드롭→재등장 시나리오 독립 시뮬레이션 — 재등장 항목 is_new=False, 원래 first_seen 보존 확인.
- **추가 안전장치(월 파싱):** first_seen 보존만으로는 과거 newsletter가 *오늘 처음 잡히는* 순간엔 여전히 '금일'로
  뜸(실측: 삼일 Monthly Newsletter 2026.02~.05 4건이 금일로 오인). → `_other_month_only(title, cur_ym)`로
  제목의 발행월(`2026.05`/`2026년 5월호`/`May 2026`)을 파싱, **이번 달이 아니면 is_new=False**.
  `_mark_insight_new`의 is_new 판정에 `and not _other_month_only(...)` 결합. 본문이 제목에 붙어 우발적 과거
  날짜가 섞이는 경우 대비 **이번 달이 한 번이라도 언급되면 유지**(오탐 최소화). 월 표기 없으면 판단 보류(기존 로직).
- **효과/검증:** 실제 insights.json에 적용 — 오인됐던 4건 즉시 제외(today_count 4→0). 제목 9종 케이스 단위검증 통과.
  ⚠️ '금일'은 *오늘 최초 발견* 의미(발행일 데이터 없음). 월 미표기 간행물은 여전히 최초발견일 기준.

## 2026-06-18 — 카나리아 의도-인지화 + 인사이트 신규 상단 + 신입·경력 이중타깃 보존

- **증상/계기:** 카나리아 지적이 전부 틀림. 원인은 카나리아 시각점검이 라이브 소스 페이지의 *모든* 공고를
  세어 스크래퍼 카운트와 비교 → 우리가 의도적으로 경력 공고를 거르는 걸 몰라 상시 거짓 '누락 의심'. 또
  ① 신입·경력 동시모집 공고가 제목의 '경력직/년 이상' 한 단어 때문에 통째로 탈락(이중타깃 유실),
  ② 빅펌 인사이트가 관련성 정렬에 묻혀 그날 신규가 중간에 위치(직관성 저하).
- **무엇을:** (a) 카나리아 LLM 프롬프트에 **큐레이션 의도**를 주입해 '신입/수습 관점'으로 판정,
  (b) hard-exclude가 제목에 신입/수습/경력무관/무관/인턴이 병기되면 살리도록, (c) 인사이트 신규를 그날 상단 부상,
  (d) 카나리아에 출력물 의도 점검 가드 2종 추가.
- **어디에 얹었나(플로우):**
  - `canary._project_context(cfg)` 신설 — `filters`의 제외/예외 키워드를 디제스트해 의도 문자열 생성 →
    `_vision_check`(visible_postings→**entry_visible**, 신입 지원가능 공고만 카운트)·`_suggest_fix`에 주입,
    `run`에서 1회 계산해 전달(코어 LLM-free 유지, 점검용 컨텍스트일 뿐).
  - `filters.passes`(28-30) hard-exclude 가드를 `... and not any(exc in title for exc in exceptions)`로 —
    제목 한정 예외 검사(본문만의 신입은 순수 경력 제목을 못 구제). `exclude_exceptions`에 `"무관"` 추가(config.py+config.yaml).
  - `export.build_insights`에서 `_mark_insight_new` **이후** `items.sort(key=lambda it: 0 if it.get('is_new') else 1)`
    (stable — 그룹 내 관련성 순서 보존). 프론트는 JSON 순서대로 렌더하므로 JS 변경 불필요.
  - `canary._check_insight_order`(insights.json: 비신규 뒤 신규 위반 감지) +
    `canary._check_filter_leakage`(jobs.json: 제목에 hard 키워드 있고 예외 없는 순수 경력 누출 감지) →
    `run`이 소스 루프 후 append, 기존 리포트·drift·Draft PR 경로에 자동 합류. 토글 `canary.check_filter_leakage`.
- **효과/검증:** `filters.passes` 6케이스 ALL PASS(이중타깃 유지·순수 경력 제외 확인). 결정론 가드 2종을 실제
  `docs/data/*.json`로 실행 — 인사이트 48건 정렬 위반 0, jobs 63건 누출 0(정상). 전 파일 `py_compile` OK.
  ※ 카나리아 워크플로는 **cron 제거·수동 전용**(workflow_dispatch)으로 전환 — 하루 1회 직접 실행.

## 2026-06-18 — 공고 '깜빡임' 방지: 지속성(grace) 레이어

- **증상/계기:** 기술보증기금 공고가 화면에서 사라졌다 나타났다 반복. 추적해 보니 KICPA가 *살아있는* 공고를
  목록 페이지에서 잠깐씩 내렸다 다시 올림(상세페이지는 정상 200). 스크랩이 '내려간 순간'을 만나면 그 공고가 통째로 빠짐.
- **무엇을:** 이번 수집에 안 잡혔더라도 '마감 전 + 최근에 봤던' 공고는 잠시(기본 2일) 유지하도록.
- **어디에 얹었나(플로우):** `state.update`가 공고마다 마지막 목격일(`last_seen`)을 기록 →
  `state.carry_forward`(신규 메서드)가 이번에 빠진 공고 중 *마감 전·2일 이내 본 것*을 되살림 →
  `export.build_jobs`가 신규 수집분 + 복원분을 합쳐 출력, `state.prune_expired`로 마감분은 제거.
  유지 기간은 `config.dashboard.jobs_grace_days`로 조절.
- **효과/검증:** 기술보증기금 공고 복원 확인(진행중·D-day 정상). 2일 넘게 안 보이면 자동 탈락 → '좀비 공고' 방지.

## 2026-06-18 — 기사 분류 보정 + 외국 기사 차단 강화

- **증상/계기:** "최운열 한공회장 …선발 과도" 기사가 '감사'로 잘못 분류됨. 또 베트남 세무 기사가 노출됨
  (제목이 한국어로 번역돼 국가명이 안 보이고 출처만 `Vietnam.vn`).
- **무엇을:** 채용·시험 성격 기사를 제대로 분류하고, 외국 국내 세무·감사 기사는 *출처 기준*으로도 차단.
- **어디에 얹었나:** `news_hire_title_keywords`에 '한공회장·선발 과도·선발 인원' 등 추가
  (제목 기반 재분류 pre-pass, `export.build_news`의 dedup 이전 단계) /
  외국 매체 차단에 `news_foreign_sources`(출처 라벨) 추가 — 제목에 국가명이 없어도 출처가 외국 매체면 컷.
- **효과/검증:** 한공회장 기사 '채용·시험'으로 이동, 베트남 기사 제거 확인.

## 2026-06-17 — 제목 기반 재분류 · 외국 노이즈 게이트 · 통합 자동화

- **증상/계기:** 채용·수습 기사가 '감사' 쿼리에만 잡혀 '감사'로 굳어짐 / 외국 국내 세무·감사 기사가 섞임 /
  GitHub 무료 cron이 자주 드롭돼 예약 수집이 거의 안 뜸.
- **무엇을:** 제목 기반 채용·시험 재분류, 외국(미국 제외) 세무·감사 차단 게이트, 30분 주기 안정 수집 체계.
- **어디에 얹었나:** `export.build_news`의 dedup 전 단계에 제목 키워드 재분류 추가 /
  `news_foreign_*`(대상 카테고리·국가명·keep 마커) 게이트 /
  외부 핑거(cron-job.org)가 `repository_dispatch`로 `run-all.yml`을 30분마다 호출 → 채용+기사+인사이트 일괄 수집.
- **효과/검증:** 분류 정확도↑, 외국 노이즈↓, 예약 실행 드롭 우회.

## 이전 — 수집 품질 기반 다지기

- 기사 OR 쿼리 설계, 보존기간(`news_recent_days` + 카테고리별 override),
  중복제거(제목 정규화 + 근접중복 Jaccard + (카테고리,발행일) 일자 상한)로 **수량과 관련성**을 함께 끌어올림.
- 세부 튜닝 레버와 시행착오는 `CLAUDE.md`의 '축적 시사점'과 `memory/` 인덱스를 참조.

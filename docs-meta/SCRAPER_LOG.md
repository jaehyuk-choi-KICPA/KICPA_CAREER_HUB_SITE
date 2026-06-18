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

# 회계법인 취업 허브 (KICPA_CAREER_HUB_SITE) — 프로젝트 컨텍스트

빅4·로컬 회계법인의 **수습공인회계사(기합 포함)·회계법인 입사 준비자**를 위한 **정적 웹 대시보드**.
채용공고 + 회계·세무·딜 업계 뉴스 + Big4 인사이트를 자동 수집 → GitHub Actions가 `docs/data/*.json`을
커밋 → GitHub Pages(`docs/`)가 서빙. 타깃: 포트폴리오(삼일 PwC Digital).

> 계획 원본: `C:\Users\micha\.claude\plans\snazzy-wondering-hickey.md`.
> 연혁: 원래 "채용알림봇"(카톡 오픈채팅 자동게시)→ GUI 게시 불안정으로 보류 → 스크래퍼 자산을 살려 웹으로 피벗.

## 콘텐츠 3스트림 (채용이 메인)
1. **채용공고** — KICPA 2보드 + 삼정·안진·한영·삼일(6어댑터). 분류: 법인(삼일/삼정/안진/한영/로컬/기타) ×
   직무(딜/감사/택스/기타) × 상태(진행중/마감) × NEW(게시 N일). 카드에 고용형태·근무지·D-day.
   (로컬=KICPA 보드의 회계·세무 법인 / 기타=그 외 일반기업·공공 등. `config.dashboard.local_keywords`로 구분.)
2. **기사** — Google News RSS(`news_rss.py`), 4분류(채용·시험/감사/세무/딜·M&A). 제목+출처+링크만, 노이즈 제외, 기본 21일 보존(카테고리별 차등).
3. **빅펌 인사이트** — 삼일·삼정·안진·한영 간행물(`insights.py`). 사이트가 JS(SPA)라 **Playwright 헤드리스**(`render.py`)로 렌더 후 링크 추출.

## 설계 원칙 (변경 시 준수)
- **어댑터 패턴**: 소스마다 다른 HTML/JSON/RSS를 `src/adapters/*`가 **공통 레코드**로 수렴. 채용=`record.Posting`,
  뉴스/인사이트=`news.NewsItem`. **새 소스 = 어댑터 1개** + `sources.py`/`export.py` 한 줄.
- **규칙 기반(LLM·MCP 미사용)**: 분류·필터·큐레이션 전부 키워드 규칙(`config.py`의 `dashboard`). 하드코딩 금지.
  - **유일한 예외**: 아래 "자기검증 카나리아"의 **하루 1회 시각 점검**에서만 Claude API 사용. **코어 데이터 파이프라인
    (수집·분류·필터·생성)은 LLM-free 유지** — 카나리아는 프로덕션 데이터를 절대 쓰지 않는 별도(out-of-band) 감시일 뿐.
- **견고성=전체실패 금지**: 모든 어댑터 호출 `base.safe_fetch`로 감쌈(한 소스 깨져도 나머지 출력).
- **자기검증 카나리아 (`src/canary.py`, 하루 1회)** — 스크래퍼의 숙명적 약점(소스가 HTML을 바꾸면 조용히 0건·누락)을
  매일 감시. **감지·진단·알림은 자동, 코드 수정은 사람 게이트**(LLM은 *제안*만, 회계사가 확정 — 자율 에이전트 금지·
  Human-in-the-loop 원칙). 계층:
  1. **구조 체크(무료·LLM 없음)**: 소스별 수집 건수를 `canary_state.json`에 저장 → 어제 대비 **0건/급감**(임계 `drop_ratio`)
     또는 `safe_fetch` 실패 감지.
  2. **시각 체크(하루 1회 LLM, 키 있을 때만)**: `render.render_screenshot`로 소스 목록 페이지 스냅샷 → Claude vision에
     "보이는 공고 수 / 정상 목록 페이지인가" 질의 → 스크래퍼 카운트와 대조(누락·양식 변경 감지).
  3. **출력 = 진단 + 제안 Draft PR**: 드리프트 발견 시 `canary_report.md`(어디가 어떻게 깨졌는지 + LLM 수정 *제안*)를
     담은 **Draft PR**을 자동 생성. **당신이 Claude Code로 검토·보완·머지**(절대 자동 머지·자동 프로덕션 커밋 안 함).
  - **보안**: API 키는 코드/exe **내장 금지**, GitHub Actions **secret(`ANTHROPIC_API_KEY`)**에서만. **키 없으면 LLM
    비활성=구조 체크만**(100% 오프라인). 전송 대상은 **공개 채용 페이지 스냅샷뿐**(사적 데이터 없음).
  - ⚠️ **첫 도입 시 supervised 검증 필수**: LLM 시각 프롬프트/응답을 `workflow_dispatch` 수동 실행으로 한 번
    눈으로 확인한 뒤 cron 자동화에 의존할 것(실제 양식 샘플로 프롬프트 검증 — 조서 프로젝트 동일 교훈).
- **병렬 정책**: 채용·뉴스는 `sources.fetch_all`(ThreadPool, 도메인 간 자유), KICPA 상세는 도메인 내 ≤4.
  **인사이트는 순차**(Playwright sync 스레드 비안전).
- **저작권 안전**: 뉴스·인사이트는 제목·링크만(본문 전재 금지).
- **저작권/개인정보**: 공개 채용공고·공식 간행물만. UGC(면접후기) 미포함(명예훼손·인증·스팸 리스크).

## 개발 시 주의 (실측 노하우)
- **Windows 콘솔 한글 깨짐**: 터미널 출력으로 판단 금지. 결과를 `ensure_ascii=False` JSON으로 써서 Read로 검증.
- **프론트 시각 검증**: 로컬 서버(`docs/`) + **헤드리스 렌더 스크린샷**(Edge `--screenshot` 또는 Playwright)로 직접 확인.
  Edge 헤드리스는 async fetch 대기 위해 `--virtual-time-budget` 필요. 비기본 탭은 Playwright로 click 후 캡처.
- `lxml` 미설치 → BeautifulSoup `html.parser`.
- 각 사이트 정찰 노하우는 어댑터 docstring에 기록.

## 수집 품질 개선 루프 (반복 수행 시 준수)
수집의 본질 가치 = **누락 없이(coverage)·관련성 있게(relevance) 가져와 잘 업데이트**하는 것. 분류보다 우선.
개선은 다음 루프로 진행하고, **루프마다 산출 시사점을 메모리(`memory/`)와 본 CLAUDE.md에 누적**한다.
1. **시각 검증(매 루프 필수)**: 로컬 서버 + 헤드리스 스크린샷으로 홈페이지를 **LLM이 직접 눈으로 확인**한다.
   스크랩은 링크·셀렉터·양식이 깨지면 텍스트 카운트만으론 안 보이고 **화면으로 봐야 교정이 빠르다**
   (빈 카드·깨진 링크·중복·이상 정렬을 시각으로 포착). 깨진 소스는 해당 소스 목록 페이지도 스냅샷 대조.
2. **진단**: 소스별 수집수 vs 실제 페이지(시각), 링크 HTTP 유효성, 카테고리/직무 관련성, 중복·신선도.
3. **수정**: 규칙·셀렉터·쿼리·보존기간 등을 config/어댑터에서 조정(LLM-free 코어 유지).
4. **재검증·채점** 후 **핵심 시사점을 메모리에 1건씩 적립**(다음 루프가 참조).
> 채점 이력·시사점은 `memory/MEMORY.md` 인덱스 참조. 누적된 교훈을 무시하지 말고 매 루프 먼저 읽을 것.

### 축적 시사점 (개선 루프 누적 — 메모리와 동기화)
- **안진 인사이트 URL**: 실제 글은 `/our-thinking/`이 아니라 `/kr/ko/.../(perspectives|research|analysis)/<글>.html`
  leaf(산업·서비스 하위). `/our-thinking/`는 섹션 랜딩일 뿐 → 옛 패턴이 2건만 잡음(현재 4사 각 12).
- **KICPA CPA보드는 45건=5페이지**(수습보드 17=2p). `max_pages` 상한이 낮으면 조용히 누락 → 8로 상향
  (어댑터가 빈 페이지서 자동중단). **카나리아 카운트가 10의 배수에 딱 걸리면 페이지 상한 의심.**
- **채용 직무 미매칭**: 로컬 회계법인 공고는 `audit_default_firms`로 **'감사' 디폴트**(수습≈감사). Big4·기타는 기타 유지.
  경력 누출은 제목 기반 `hard_exclude_keywords`로 차단하되, **제목에 신입/수습/경력무관/무관/인턴이 병기되면 유지**
  (신입·경력 동시모집 이중타깃 보존 — hard-exclude는 제목 한정 예외 검사. `filters.passes`). 순수 경력 제목만 제외.
- **기사 4분류**(채용·시험←회계업계 / 감사←제도·규제 / 딜·M&A / 세무). 저빈도·고관련 카테고리는
  `news_recent_days_by_category`로 보존기간 길게(채용 45·딜 21). 넓은 OR 쿼리 노이즈는 `news_require_any`
  도메인어 게이트로, 매체만 다른 동일 헤드라인은 **제목 정규화 dedup**으로 제거. config 순서=dedup 선점 순서.
  같은 사건 매체별 도배는 어휘 Jaccard로는 못 묶음(의미 군집은 임베딩 필요) → `news_neardup_jaccard`(거의동일만)
  + **`news_max_per_day_per_cat`**((카테고리,발행일) 상한)으로 도배 차단(05-31 수습이슈 20→8).
- **링크 점검**: 스트림별 샘플 HTTP. 단 뉴스는 `news.google.com/rss/...` redirect라 200=Google 도달일 뿐(실기사 아님).
- **기사 수량 레버**(58→116 실측, 종합 7.9→8.9): 안전=`news_per_category`(20→50)→풀린 뒤엔 **`news_recent_days`(→21)**가
  주 레버(세무·감사 건수가 limit 미만이면 recency가 한계). **위험=쿼리 확장**(앞순위 넓히면 dedup 선점으로 뒷순위 잠식,
  딜 일반어는 require_any 게이트가 컷→0). 채용·딜은 공급 한계라 품질>수량. 정치색 매체는 `news_exclude_sources`(예: 뉴스타파).
- **시각검증 노하우**: SPA 글 경로는 render_html 후 anchor href의 **경로 prefix 빈도**를 세어 진짜 글 패턴을 찾는다.
- **기사 카테고리 오분류**: RSS 분류는 "어느 쿼리가 가져왔나"로 결정 → 채용·수습 기사가 "감사" 쿼리에만 잡히면
  `감사`로 고정됨. 해결: `news_hire_title_keywords`(config)로 제목 기반 **사후 보정 pre-pass**(export.py `build_news`)
  — 채용·수습 키워드가 제목에 있으면 카테고리를 `채용·시험`으로 강제 재분류(dedup 전 처리). 한공회장 발언·선발인원
  이슈도 여기 포함(예: "한공회장","선발 과도","선발 인원").
- **KICPA 목록 깜빡임(공고 유실)**: 살아있는 공고를 KICPA가 **목록 페이지에서 일시적으로 내렸다 올림**(상세페이지는
  status 200 유지) → 스크랩이 그 순간을 놓쳐 카드가 깜빡 사라짐(실측: 기술보증기금 공고 18:32 있다 19:02 사라짐).
  해결: **지속성(grace) 레이어** — `state.update`가 공고별 `last_seen` 기록, `state.carry_forward`가 이번 스크랩에
  빠졌어도 **마감 전 + last_seen이 `jobs_grace_days`(2일) 이내**면 복원(export.py `build_jobs`). grace 넘으면 자동 탈락
  (좀비 방지), `prune_expired`로 마감분 정리. state.json은 run-all.yml이 커밋(CI 간 영속). **목록 카운트가 1~2건씩
  깜빡이면 소스 목록 변동이지 스크랩 버그 아님 → grace로 흡수.**
- **외국 세무·감사 노이즈**: 넓은 OR 쿼리가 베트남·일본 등 **외국 국내 제도** 기사를 끌어옴(한국 독자 무관).
  해결: `news_foreign_filter_categories`(세무·감사만) + `news_foreign_countries`(미국 제외 외국명) +
  `news_foreign_sources`(외국 매체 source_label — 제목에 국가명 없어도 출처가 Vietnam.vn 등이면 차단) +
  `news_keep_markers`(한국·미국·국제공통=국제/글로벌/OECD/IFRS/국세청 등). 제목 국가명 **또는** 외국매체이고
  keep 마커가 하나도 없으면 제외. **딜·M&A는 적용 안 함**(해외 인수 등 한국 관련성). 미국은 유지(keep 마커 포함).
  ⚠️ 외국 기사는 제목이 번역돼 국가명이 안 보일 수 있음 → **출처(source_label) 점검이 핵심**(예: Vietnam.vn).
- **카나리아는 큐레이션 의도-인지여야 한다**: 카나리아가 라이브 페이지의 *모든* 공고를 세어 스크래퍼(필터된)
  카운트와 비교하면 **우리가 의도적으로 경력을 거르는 걸 몰라 상시 거짓 '누락 의심'**이 뜬다. 해결: `canary._project_context(cfg)`
  가 `filters`의 제외/예외 키워드를 디제스트한 **의도 문자열**을 `_vision_check`(공고 전부→**신입 지원가능분만** 카운트)·
  `_suggest_fix`에 주입 → '신입/수습 관점'으로 판정. 출력물 의도 점검 가드도 카나리아에 둠:
  `_check_insight_order`(신규 인사이트가 상단 아님)·`_check_filter_leakage`(경력 전용 공고 누출). 결정론·LLM 불필요.
  카나리아 워크플로는 **수동 전용**(cron 없음 — 하루 1회 직접 실행).
- **인사이트는 그날 신규를 상단으로**: 관련성 정렬에 신규가 묻혀 직관성이 떨어짐 → `export.build_insights`가
  `_mark_insight_new` 이후 `is_new` 우선 **stable sort**로 그날 신규를 최상단 부상(그룹 내 관련성 순서 보존).
  프론트는 JSON 순서대로 렌더 + `is_new`→`today-dot` 표시(JS 무변경).
- **인사이트 '금일' 오인 = first_seen 보존으로 해결**: 인사이트는 발행일이 없어 `is_new`=*오늘 최초 발견*으로
  판정(`_mark_insight_new`, `insights_seen.json`). 법인별 상한(~12) 경계에서 새 글이 오면 오래된 글이 목록에서
  잠시 밀려나는데, 이때 state에서 **삭제하면 재등장 시 신규로 오인**(jobs 깜빡임과 동일). → 현재 목록에 없어도
  first_seen **보존**(MAX_SEEN 상한 초과 시 부재·오래된 것만 정리). **'금일 인사이트'가 오래된 글로 보이면
  상한 경계 churn 의심 → 보존 로직 점검.**

## 구조
```
src/
  adapters/  kicpa·samjong·anjin·hanyoung·samil(채용) + news_rss(기사) + insights(빅펌) + base
  sources.py(조립+병렬) export.py(생성 진입점 --part) classify.py(법인/직무) render.py(헤드리스)
  canary.py(자기검증 카나리아 — 양식변경/누락 감지, 드리프트 시 Draft PR)
  freshness.py(신선도 모니터 — 데이터가 낡았는지=스케줄 드롭 감지, STALE 시 Draft PR)
  sitecheck.py(라이브 종단 e2e — 배포된 화면이 의도대로 보이는지, 실패 시 GitHub 이슈)
  config.py filters.py state.py util.py http_util.py record.py news.py
  run.py·kakao_pc.py·messenger_bot.js  ← 카톡봇(보류, 유지)
docs/  index.html app.js style.css  CNAME  +  data/{jobs,news,insights}.json + data/status.json(점검시각)   (GitHub Pages 루트, hbmons.com)
.github/workflows/  scrape.yml(채용30분) scrape-news.yml(2h) scrape-insights.yml(일2회) canary.yml(양식감시 — **수동 전용**, cron 없음·하루1회 직접 실행) freshness.yml(신선도 매시간) sitecheck.yml(종단점검 3h) run-all.yml(외부핑거 통합실행)
```
> **GitHub cron은 무료·public에서 자주 드롭됨**(실측: 예약 실행이 거의 안 뜸). 안정적 주기 실행은 **외부 핑거
> (cron-job.org, 30분 간격)**가 `repository_dispatch{event_type:run-all}`로 `run-all.yml`을 호출 →
> 채용+기사+인사이트 일괄. cron 워크플로들은 보조로 유지.
> **외부 핑거 설정 요약**: cron-job.org → POST `https://api.github.com/repos/jaehyuk-choi-KICPA/KICPA_CAREER_HUB_SITE/dispatches`
> Headers: `Accept: application/vnd.github+json` · `Authorization: Bearer <PAT(Contents+Actions R/W)>` ·
> `X-GitHub-Api-Version: 2022-11-28` · `Content-Type: application/json` / Body: `{"event_type":"run-all"}`

### 자동화 신뢰성 = 3층 모니터링 (변경 시 함께 고려)
1. **실행됐나** → `freshness.py`(데이터 나이로 스케줄 드롭 감지). 2. **누락 없이 수집됐나** → `canary.py`(소스 양식/건수).
3. **사용자가 실제로 제대로 보나** → `sitecheck.py`(라이브 URL을 브라우저로 열어 헤더 시각·탭별 카드수 vs 데이터·콘솔에러 + **타당성** + 선택적 LLM 비전).
- **타당성(plausibility)**: 렌더 검사는 *의미 오류*를 못 잡는다(예: '금일 인사이트 48/48'=전량 신규는 화면엔 멀쩡한 숫자). sitecheck가 `오늘신규/총`이 `implausible_today_ratio`↑면 이상 처리(파생 지표는 반드시 별도 타당성 검사).
- **셀프힐링(sitecheck.yml)**: 실패를 `recoverable`(신선도·일시 → **스크랩 재실행→재점검 무인 반복**, max_attempts 상한)과 `code`(타당성·렌더·콘솔 → **재실행 안 함**)로 분류. 코드 버그는 `--explain`(LLM 진단·수정 *제안*)을 담아 **GitHub 이슈**로 올림(라벨 sitecheck,needs-human, 복구 시 auto-close). **코드 자동수정·자동머지 절대 금지 — 적용은 사람이 Claude Code로.**
- **점검 시각**: 헤더 "최근 업데이트"는 `docs/data/status.json`의 `last_run`(export `main`이 매 실행 기록 — 0건이라 데이터가 안 바뀌어도 전진). 폴백은 jobs `generated_at`. **pagebuild와 무관**.
- LLM은 카나리아·sitecheck의 **out-of-band 점검·제안**에만(키 없으면 결정론만). 자동 수정·자동 머지 금지(Human-in-the-loop).
config.yaml  requirements.txt
```

## 실행 / 배포
```
python -m src.export [--part jobs|news|insights]   # docs/data/*.json
cd docs && python -m http.server 8000              # 로컬 확인
```
배포: GitHub Pages(Branch main /docs). 검색 주기는 워크플로 `cron:` 수정으로 변경.

## 기록 규칙 (빌드 / 수집툴) — 빌드업 시 필수, 트랙 분리
기록 문서는 **`docs-meta/`** 에 통합 관리(루트엔 CLAUDE.md·README만 유지 — 자동로드·GitHub 렌더 보존).
> **세션 시작 시 보조 참고자료**: `docs-meta/`의 **PATCHNOTES.md**(빌드/변경 이력)·**SCRAPER_LOG.md**(수집 엔진 보완 흐름)·
> **사용설명서.md**(운영·배포·설정)를 관련 작업 전 우선 확인할 것. (전량 통독 불필요 — 작업 맥락에 맞는 문서만 펼쳐 참고.)
사용자가 변경 흐름을 추적·블로그화할 수 있도록 **두 트랙**으로 나눠 기록한다. 자동수집(`auto:`) 커밋은 제외.
- **빌드 트랙 → `docs-meta/PATCHNOTES.md`**: **UI 개선·새 기능**이 있을 때만(= 공식 표시버전이 올라갈 때) 최상단에 새 버전 엔트리.
  분류 **🎨 UI 개선 / ✨ 새로운 기능** 항상 표기(없으면 '변경 없음'), 각 항목 [무엇]+[배경]. **블로그 복붙용 한국어 톤**.
- **수집툴 트랙 → `docs-meta/SCRAPER_LOG.md`**: 어댑터·config·분류·필터·수집 플로우 변경은 **빌드와 무관하게** 날짜 엔트리로.
  형식 = **증상/계기 → 무엇을 → 어디에 얹었나(코드 플로우) → 효과/검증**. 상단의 '수집 파이프라인 개요' 골격 위에 건다.
- 트랙 혼동 금지: 스크랩 변경을 PATCHNOTES에 넣지 않는다(수집툴은 버전과 독립).
- **교차 반영(작성 시 필수)**: PATCHNOTES/SCRAPER_LOG를 갱신할 때 **CLAUDE.md와 `docs-meta/사용설명서.md`**의 관련 서술도
  적절히 수정·추가(수정사항 없으면 생략). **README는 영향 판단 후에만** 수정. [[patchnotes-discipline]]

## 협업 규칙
- **너의 페르소나**: 너는 **뛰어난 실력의 10년차 웹개발자(프론트·백엔드 모두 능통)**. UX·정보위계·성능·접근성을
  스스로 따지고, 단순 지시 수행을 넘어 더 나은 구조·간결한 UI를 능동적으로 제안한다(제안과 실행을 구분해 보고).
- **서브에이전트 모델**: 기본 Sonnet(정찰 포함), 복잡 구현·디버깅만 Opus.

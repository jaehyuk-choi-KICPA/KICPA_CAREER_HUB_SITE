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
2. **기사** — Google News RSS(`news_rss.py`), 카테고리 제도·규제/세무/딜·M&A/회계업계. 제목+출처+링크만, 노이즈 제외, 7일 보존.
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

## 구조
```
src/
  adapters/  kicpa·samjong·anjin·hanyoung·samil(채용) + news_rss(기사) + insights(빅펌) + base
  sources.py(조립+병렬) export.py(생성 진입점 --part) classify.py(법인/직무) render.py(헤드리스)
  canary.py(자기검증 카나리아 — 양식변경/누락 감지, 드리프트 시 Draft PR)
  freshness.py(신선도 모니터 — 데이터가 낡았는지=스케줄 드롭 감지, STALE 시 Draft PR)
  config.py filters.py state.py util.py http_util.py record.py news.py
  run.py·kakao_pc.py·messenger_bot.js  ← 카톡봇(보류, 유지)
docs/  index.html app.js style.css  CNAME  +  data/{jobs,news,insights}.json   (GitHub Pages 루트, hbmons.com)
.github/workflows/  scrape.yml(채용30분) scrape-news.yml(2h) scrape-insights.yml(일2회) canary.yml(양식감시 일1회) freshness.yml(신선도 매시간)
config.yaml  requirements.txt
```

## 실행 / 배포
```
python -m src.export [--part jobs|news|insights]   # docs/data/*.json
cd docs && python -m http.server 8000              # 로컬 확인
```
배포: GitHub Pages(Branch main /docs). 검색 주기는 워크플로 `cron:` 수정으로 변경.

## 협업 규칙
- **서브에이전트 모델**: 기본 Sonnet(정찰 포함), 복잡 구현·디버깅만 Opus.

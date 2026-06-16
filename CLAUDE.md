# 회계법인 취업 허브 (KICPA_CAREER_HUB_SITE) — 프로젝트 컨텍스트

빅4·로컬 회계법인의 **수습공인회계사(기합 포함)·회계법인 입사 준비자**를 위한 **정적 웹 대시보드**.
채용공고 + 회계·세무·딜 업계 뉴스 + Big4 인사이트를 자동 수집 → GitHub Actions가 `docs/data/*.json`을
커밋 → GitHub Pages(`docs/`)가 서빙. 타깃: 포트폴리오(삼일 PwC Digital).

> 계획 원본: `C:\Users\micha\.claude\plans\snazzy-wondering-hickey.md`.
> 연혁: 원래 "채용알림봇"(카톡 오픈채팅 자동게시)→ GUI 게시 불안정으로 보류 → 스크래퍼 자산을 살려 웹으로 피벗.

## 콘텐츠 3스트림 (채용이 메인)
1. **채용공고** — KICPA 2보드 + 삼정·안진·한영·삼일(6어댑터). 분류: 법인(삼일/삼정/안진/한영/로컬) ×
   직무(딜/감사/택스/기타) × 상태(진행중/마감) × NEW(게시 N일). 카드에 고용형태·근무지·D-day.
2. **기사** — Google News RSS(`news_rss.py`), 카테고리 제도·규제/세무/딜·M&A/회계업계. 제목+출처+링크만, 노이즈 제외, 7일 보존.
3. **빅펌 인사이트** — 삼일·삼정·안진·한영 간행물(`insights.py`). 사이트가 JS(SPA)라 **Playwright 헤드리스**(`render.py`)로 렌더 후 링크 추출.

## 설계 원칙 (변경 시 준수)
- **어댑터 패턴**: 소스마다 다른 HTML/JSON/RSS를 `src/adapters/*`가 **공통 레코드**로 수렴. 채용=`record.Posting`,
  뉴스/인사이트=`news.NewsItem`. **새 소스 = 어댑터 1개** + `sources.py`/`export.py` 한 줄.
- **규칙 기반(LLM·MCP 미사용)**: 분류·필터·큐레이션 전부 키워드 규칙(`config.py`의 `dashboard`). 하드코딩 금지.
- **견고성=전체실패 금지**: 모든 어댑터 호출 `base.safe_fetch`로 감쌈(한 소스 깨져도 나머지 출력).
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

## 구조
```
src/
  adapters/  kicpa·samjong·anjin·hanyoung·samil(채용) + news_rss(기사) + insights(빅펌) + base
  sources.py(조립+병렬) export.py(생성 진입점 --part) classify.py(법인/직무) render.py(헤드리스)
  config.py filters.py state.py util.py http_util.py record.py news.py
  run.py·kakao_pc.py·messenger_bot.js  ← 카톡봇(보류, 유지)
docs/  index.html app.js style.css  +  data/{jobs,news,insights}.json   (GitHub Pages 루트)
.github/workflows/  scrape.yml(채용1h) scrape-news.yml(6h) scrape-insights.yml(일1회)
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

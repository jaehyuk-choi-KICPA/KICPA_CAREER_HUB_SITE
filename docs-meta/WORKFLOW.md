# 회법몬(hbmons.com) 전체 워크플로우

> **연동 규칙**: 아래 파일이 변경되면 이 문서도 함께 수정한다.
> `.github/workflows/*.yml` · `src/export.py` · `src/sources.py` · `src/adapters/*` · `src/config.py`

---

## 1. 전체 흐름 (조감도)

```mermaid
flowchart TD
    subgraph TRIGGER["⏰ 트리거"]
        EXT["cron-job.org<br/>30분 간격<br/>repository_dispatch"]
        GH_CRON["GitHub Cron<br/>freshness 1h / sitecheck 3h"]
        MANUAL["수동 실행<br/>canary / scrape 개별"]
    end

    subgraph COLLECT["🔄 수집 (GitHub Actions)"]
        RUN_ALL["run-all.yml<br/>(주 수집 경로)"]
        SCRAPE["scrape.yml<br/>(채용 단독, 수동)"]
        SCRAPE_N["scrape-news.yml<br/>(기사 단독, 수동)"]
        SCRAPE_I["scrape-insights.yml<br/>(인사이트 단독, 수동)"]
    end

    subgraph PIPELINE["🐍 파이썬 파이프라인 (src/)"]
        EXPORT["export.py --part jobs|news|insights"]
        SOURCES["sources.fetch_all()<br/>ThreadPool, 도메인 간 병렬"]
        ADAPTERS_J["채용 어댑터 ×6<br/>kicpa(2) · samil · samjong · anjin · hanyoung"]
        ADAPTERS_N["뉴스 어댑터<br/>GoogleNewsAdapter × 5풀<br/>채용·시험 / 감사A·감사B / 딜 / 세무"]
        ADAPTERS_I["인사이트 어댑터 ×4<br/>Playwright 헤드리스 순차<br/>삼일 · 삼정 · 안진 · 한영"]
        STATE["state.py<br/>first_seen · last_seen · grace"]
        CLASSIFY["classify.py<br/>법인 / 직무 분류"]
        FILTER["filters.py<br/>경력 제외 · 예외 보존"]
        DEDUP["export._dedup_near()<br/>제목 Jaccard 근접중복 군집화"]
        EMBEDS["embeds.py (선택)<br/>Voyage 임베딩<br/>관련성 게이트 · 의미군집"]
    end

    subgraph OUTPUT["📦 출력"]
        DATA["docs/data/<br/>jobs.json · news.json<br/>insights.json · status.json"]
        STATE_J["state.json<br/>(Actions가 커밋, CI 간 영속)"]
    end

    subgraph SERVE["🌐 서빙 (GitHub Pages)"]
        PAGES["GitHub Pages<br/>docs/ → hbmons.com"]
        BROWSER["브라우저<br/>index.html + app.js + style.css"]
    end

    subgraph MONITOR["🔍 모니터링"]
        FRESH["freshness.yml (1h)<br/>freshness.py<br/>status.json 나이 체크"]
        SITE["sitecheck.yml (3h)<br/>sitecheck.py<br/>라이브 URL 헤드리스 종단점검"]
        CANARY["canary.yml (수동)<br/>canary.py<br/>소스 구조·건수 + LLM 시각"]
        DRAFT_PR["Draft PR<br/>(freshness · canary)"]
        GH_ISSUE["GitHub Issue<br/>(sitecheck)"]
    end

    EXT -->|"repository_dispatch{run-all}"| RUN_ALL
    GH_CRON --> FRESH & SITE
    MANUAL --> SCRAPE & SCRAPE_N & SCRAPE_I & CANARY

    RUN_ALL --> EXPORT
    SCRAPE & SCRAPE_N & SCRAPE_I --> EXPORT

    EXPORT -->|"--part jobs"| SOURCES --> ADAPTERS_J
    EXPORT -->|"--part news"| ADAPTERS_N
    EXPORT -->|"--part insights"| ADAPTERS_I

    ADAPTERS_J --> CLASSIFY --> FILTER --> STATE --> DATA
    ADAPTERS_N --> DEDUP --> EMBEDS --> DATA
    ADAPTERS_I --> DATA
    STATE --> STATE_J

    DATA -->|"git commit"| PAGES --> BROWSER

    FRESH -->|"데이터 낡음"| DRAFT_PR
    SITE -->|"렌더·타당성 이상"| GH_ISSUE
    SITE -->|"신선도 실패"| RUN_ALL
    CANARY -->|"건수·양식 드리프트"| DRAFT_PR
```

---

## 2. 채용공고 파이프라인 상세

```mermaid
flowchart LR
    subgraph SRC["소스 (6 어댑터)"]
        K1["KICPA CPA보드<br/>최대 8p × 9건"]
        K2["KICPA 수습보드<br/>최대 8p × 9건"]
        S["삼일PwC"]
        SJ["삼정KPMG"]
        A["안진Deloitte"]
        H["한영EY"]
    end

    subgraph PROC["처리"]
        C["classify.py<br/>firm · field<br/>(local→감사 디폴트)"]
        F["filters.py<br/>경력 제외<br/>신입/수습 예외 보존"]
        ST["state.py<br/>first_seen 기록<br/>grace(2일) 유실 복원"]
        SORT["마감 임박순 정렬<br/>진행중 > 마감"]
    end

    OUT["docs/data/jobs.json<br/>+ state.json 커밋"]

    SRC --> C --> F --> ST --> SORT --> OUT
```

**핵심 필드**: `firm` · `field` · `status(open/closed)` · `dday` · `posted_date` · `first_seen` · `is_new`

---

## 3. 뉴스 파이프라인 상세

```mermaid
flowchart LR
    subgraph RSS["Google News RSS (5풀)"]
        N1["채용·시험 쿼리<br/>75건"]
        N2["감사 풀A (기준·제도)<br/>75건"]
        N3["감사 풀B (보수·처분)<br/>75건"]
        N4["딜·M&A 쿼리<br/>75건"]
        N5["세무 쿼리<br/>75건"]
    end

    subgraph FILTER2["필터"]
        RD["recency 필터<br/>카테고리별 보존기간<br/>채용45·딜60·세무21·감사21일"]
        FF["외국 기사 필터<br/>세무·감사만 적용<br/>news_foreign_sources/countries"]
        RA["require_any 게이트<br/>도메인어 없으면 제외"]
        HT["hire_title 보정<br/>채용 키워드 제목→채용·시험 재분류"]
    end

    subgraph DEDUP2["중복 처리"]
        URL["URL dedup (동일 기사)"]
        NEAR["_dedup_near()<br/>Jaccard 근접중복 군집화<br/>대표 1건 + dupes 첨부"]
        EMB["embeds.refine() (선택)<br/>의미 유사 군집 보조"]
    end

    CAP["news_max_per_day_per_cat<br/>카테고리×일자 상한"]
    SORT2["published_at 내림차순 정렬<br/>시각 tiebreaker"]
    OUT2["docs/data/news.json"]

    RSS --> URL --> RD --> FF --> RA --> HT --> SORT2 --> NEAR --> EMB --> CAP --> OUT2
```

**풀 분리 이유**: Google RSS는 관련도순 100건 상한 → 단일 감사 쿼리는 오늘 기사가 100위 밖으로 밀림 → 2풀로 각 100건 확보.

---

## 4. 인사이트 파이프라인 상세

```mermaid
flowchart LR
    subgraph PW["Playwright 헤드리스 (순차)"]
        P1["삼일PwC"]
        P2["삼정KPMG"]
        P3["Deloitte안진<br/>/kr/ko/.../(perspectives|research|analysis)"]
        P4["EY한영"]
    end

    OUT3["docs/data/insights.json<br/>{generated_at, items[]}"]
    UI["프론트 4박스 그룹핑<br/>박스별 랜덤 추천 1편<br/>+ 펼치기(스크랩 순서)"]

    P1 & P2 & P3 & P4 -->|"URL dedup · 법인당 cap"| OUT3 --> UI
```

**순차 이유**: Playwright sync API는 스레드 비안전.

---

## 5. 모니터링 3층

| 층 | 파일 | 주기 | 감지 대상 | 출력 |
|---|---|---|---|---|
| 실행됐나 | `freshness.py` | 1h | `status.json` 나이 > 임계 (외부핑거 죽음) | Draft PR |
| 수집됐나 | `canary.py` | 수동 | 소스별 건수 급감·0건·양식 변경 | Draft PR + LLM 진단 |
| 제대로 보이나 | `sitecheck.py` | 3h | 라이브 URL 렌더·카드수·콘솔 에러·타당성 | GitHub Issue |

**셀프힐링**: sitecheck가 `recoverable` 판정 시 scrape 재실행 → 재점검 (최대 attempts 상한).  
**Human-in-the-loop**: LLM은 진단·제안만, 코드 수정·머지는 사람이 Claude Code로.

---

## 6. 파일 맵

```
회법몬/
├── CLAUDE.md                    ← 프로젝트 컨텍스트 (Claude Code 자동 로드)
├── config.yaml                  ← 운영 설정 (runtime · filters · formats)
├── src/
│   ├── config.py                ← dashboard 전체 규칙 (쿼리·필터·분류)
│   ├── export.py                ← 수집 진입점 (--part jobs|news|insights)
│   ├── sources.py               ← ThreadPool 병렬 fetch 조율
│   ├── state.py                 ← 채용공고 상태 영속 (first_seen · grace)
│   ├── classify.py              ← 법인/직무 분류 규칙
│   ├── filters.py               ← 경력 제외 필터
│   ├── news.py                  ← NewsItem 데이터클래스
│   ├── record.py                ← Posting 데이터클래스
│   ├── embeds.py                ← Voyage 임베딩 (키 있을 때만)
│   ├── render.py                ← Playwright 헤드리스 유틸
│   ├── canary.py                ← 수집 구조 감시
│   ├── freshness.py             ← 실행 신선도 감시
│   ├── sitecheck.py             ← 라이브 종단 점검
│   ├── http_util.py             ← safe HTTP (재시도·인코딩)
│   ├── util.py                  ← 공통 유틸
│   └── adapters/
│       ├── base.py              ← Adapter ABC + safe_fetch
│       ├── kicpa.py             ← KICPA CPA/수습 보드
│       ├── samil.py             ← 삼일PwC
│       ├── samjong.py           ← 삼정KPMG
│       ├── anjin.py             ← 안진Deloitte
│       ├── hanyoung.py          ← 한영EY
│       ├── news_rss.py          ← Google News RSS (5풀)
│       └── insights.py          ← Big4 간행물 (Playwright)
├── docs/                        ← GitHub Pages 루트 (hbmons.com)
│   ├── index.html               ← SPA 껍데기
│   ├── app.js                   ← 전체 프론트 로직
│   ├── style.css                ← 스타일
│   └── data/
│       ├── jobs.json            ← 채용공고 (Actions가 갱신)
│       ├── news.json            ← 기사 (Actions가 갱신)
│       ├── insights.json        ← 인사이트 (Actions가 갱신)
│       └── status.json          ← 마지막 수집 시각
├── .github/workflows/
│   ├── run-all.yml              ← 주 수집 (외부핑거 → repository_dispatch)
│   ├── freshness.yml            ← 신선도 감시 (1h cron)
│   ├── sitecheck.yml            ← 종단 점검 (3h cron)
│   ├── canary.yml               ← 양식 감시 (수동)
│   ├── scrape.yml               ← 채용 단독 (수동)
│   ├── scrape-news.yml          ← 기사 단독 (수동)
│   └── scrape-insights.yml      ← 인사이트 단독 (수동)
├── docs-meta/                   ← 개발 문서 (GitHub Pages 미서빙)
│   ├── WORKFLOW.md              ← ★ 이 파일 (워크플로우 시각화)
│   ├── PATCHNOTES.md            ← UI/기능 빌드 이력
│   ├── SCRAPER_LOG.md           ← 수집툴 변경 이력
│   └── 사용설명서.md             ← 운영·배포 가이드
├── state.json                   ← 채용공고 상태 (Actions 커밋으로 CI 간 영속)
├── canary_state.json            ← 소스별 건수 이력 (canary 기준선)
└── tests/                       ← pytest 단위 테스트
```

---

## 7. 외부 핑거 설정 요약

| 항목 | 값 |
|---|---|
| 서비스 | cron-job.org |
| 주기 | 30분 |
| Method | POST |
| URL | `https://api.github.com/repos/jaehyuk-choi-KICPA/KICPA_CAREER_HUB_SITE/dispatches` |
| Headers | `Authorization: Bearer <PAT>` · `Accept: application/vnd.github+json` · `X-GitHub-Api-Version: 2022-11-28` |
| Body | `{"event_type":"run-all"}` |
| PAT 권한 | Contents R/W · Actions R/W |

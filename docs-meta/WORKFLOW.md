# 회법몬(hbmons.com) 전체 워크플로우

> **연동 규칙**: 아래 파일이 변경되면 이 문서도 함께 수정한다.
> `.github/workflows/*.yml` · `src/export.py` · `src/sources.py` · `src/adapters/*` · `src/config.py`

---

## 1. 전체 흐름 (조감도)

```mermaid
flowchart TD
    subgraph TRIGGER["⏰ 트리거"]
        EXT["cron-job.org<br/>30분 간격<br/>repository_dispatch"]
        GH_CRON["GitHub Cron<br/>monitor 5h(통합) · freshness 1h · sitecheck 3h"]
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
        MON["monitor.yml (5h · 통합)<br/>canary+sitecheck<br/>신선도만 자동 재수집"]
        DRAFT_PR["Draft PR<br/>(freshness · canary)"]
        GH_ISSUE["GitHub Issue<br/>(monitor · sitecheck)"]
    end

    EXT -->|"repository_dispatch{run-all}"| RUN_ALL
    GH_CRON --> MON & FRESH & SITE
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
    MON -->|"신선도 미갱신"| RUN_ALL
    MON -->|"렌더·코드 이상"| GH_ISSUE
```

> **추가 흐름**: `run-all`은 수집 후 **푸시 발송**(`src/notifier.py` → 구독자)도 수행한다(§5.5 채용알림). 모니터링은 **통합 `monitor.yml`(5h)**이 canary+sitecheck를 묶어 점검하며 신선도 미갱신만 자동 재수집한다(§5).

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
        C["classify.py<br/>firm · 자격요건(수습CPA/자격무관)<br/>· 채용구분(인턴/정규/계약/파트)<br/>모집대상 텍스트 키워드 판정"]
        F["filters.py<br/>경력 제외<br/>신입/수습 예외 보존"]
        ST["state.py<br/>first_seen 기록<br/>grace(2일) 유실 복원"]
        SORT["마감 임박순 정렬<br/>진행중 > 마감"]
    end

    OUT["docs/data/jobs.json<br/>+ state.json 커밋"]

    SRC --> C --> F --> ST --> SORT --> OUT
```

**핵심 필드**: `firm` · `qualification`(수습CPA/자격무관) · `emp_kind`(인턴/정규직/계약직/파트타임) · `status(open/closed)` · `dday` · `posted_date` · `first_seen` · `is_new`(발견 24h)
*(구 `field`(직무)는 폐기 — export에서 레거시 병행만)*

**KICPA 상세 보강(`kicpa.py._enrich_deadline`)**: KICPA 목록엔 마감일·모집대상이 없어 상세페이지를 1회 방문해 **마감일·근무지·고용형태 + 모집대상/자격요건 본문(`div.txt_infor`→`body_excerpt`)**을 채운다. 덕분에 `filters.passes`·`classify_qualification`이 **제목 너머 모집대상까지** 보고 판정(경력/신입 오분류 방지). 마감일·본문 모두 `native_id` 캐시(`state` 영속)로 **1회만 수집·재사용**. *(bypass: `kicpa_susup` 보드는 경력 필터 면제 — 보드 자체가 수습CPA 타깃.)*

**수동 공고 주입(`export._load_manual_postings`)**: ATS 미수집(삼일PwC 개별페이지형) 공고는 **`docs/data/manual_jobs.json`**에 수기 등록 → `build_jobs`가 크롤 결과 뒤에 합친다. native_id 고정이라 uid 안정 → filter·classify·state(first_seen/notified)·dedup·jobs.json·**notifier(푸시)** 모두 동일 경로(=NEW 패널 + 알림 1회). 시즌 종료 시 항목 삭제. (빅4 특집 박스는 `big4_recruit.json` 별도 관리 — 두 파일 병행.)
  - **`manual` 플래그**: 주입한 수동 공고는 `state.carry_forward`(KICPA 깜빡임 복원) **대상 제외** → manual_jobs.json에서 빼면 **즉시 드롭**(깜빡임 보호는 크롤 공고 전용).
  - **`title_appends`**(url_contains·append): 특정 **크롤 공고** 제목에 표시용 접미사(별도 카드 분리 없이). 예: 삼정 감사(901)=파트타임 겸함 → "(파트 포함)" 표기. items 빌드 후·정렬 전 적용.
  - **`prune_uids`**: 분리했다 통합한 잔재 등 **state 좀비 uid 일회성 삭제**(carry_forward 복원 방지).

**크로스소스 중복 제거(`export._dedup_cross_source`)**: 같은 공고가 **한공회 재게시 + 빅4 자체 ATS** 양쪽에 뜨면(예: `[딜로이트 안진회계법인] 2026 신입회계사 정기채용`=kicpa_susup vs `2026 신입회계사 정기채용`=anjin) **(법인, 정규화제목) 동일**으로 보고 1건만 남긴다. 정규화=앞 '[회사명]' 접두 제거+공백·구두점 제거. **빅4 자체 ATS(직접 지원 링크)를 우선 보존**, 한공회 재게시 제거. `build_jobs` hydrate 직후 적용.

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
        RD["recency 필터<br/>카테고리별 보존기간<br/>채용75·딜30·세무21·감사21일"]
        FF["외국 기사 필터<br/>세무·감사만 적용<br/>news_foreign_sources/countries"]
        RA["require_any 게이트<br/>도메인어 없으면 제외"]
        GT["노이즈 게이트<br/>보도자료·지자체 행정·코인·Naver Blog"]
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

    RSS --> URL --> RD --> FF --> RA --> GT --> HT --> SORT2 --> NEAR --> EMB --> CAP --> OUT2
```

**풀 분리 이유**: Google RSS는 관련도순 100건 상한 → 단일 감사 쿼리는 오늘 기사가 100위 밖으로 밀림 → 2풀로 각 100건 확보.
**딜 편중 보정**: 딜 보존 60→30일 축소 + 프론트 `spreadCategories`(전체 탭, 같은 카테고리 3연속 방지)로 dedup 압축 비대칭(감사/세무는 1건으로 묶이고 딜은 개별 건이라 다수)에 따른 딜 도배 완화.

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

## 5. 모니터링 (통합 monitor.yml 5h + 레거시 3층 병행)

**통합**: `monitor.yml`(5h cron `0 */5 * * *`)이 canary(소스 급감 구조점검) + sitecheck(라이브 종단·신선도 셀프힐링)를
**한 잡**으로 묶어 점검한다. **신선도 미갱신(recoverable)일 때만 자동 재수집**, 그 외(렌더·타당성·코드)는 `monitor`/`needs-human`
라벨 GitHub 이슈로 에스컬레이션. 안정 확인 전까지 아래 레거시 3층도 병행하며, 이후 freshness·sitecheck의 cron을 폐기(수동 전용)해 중복 제거 예정.

| 층 | 파일 | 주기 | 감지 대상 | 출력 |
|---|---|---|---|---|
| **통합** | **`monitor.yml`** (canary+sitecheck) | **5h** | 소스 급감 + 라이브 종단·신선도 | 이슈 / 신선도시 자동 재수집 |
| 실행됐나 | `freshness.py` | 1h | `status.json` 나이 > 임계 (외부핑거 죽음) | Draft PR |
| 수집됐나 | `canary.py` | 수동 | 소스별 건수 급감·0건·양식 변경 | Draft PR + LLM 진단 |
| 제대로 보이나 | `sitecheck.py` | 3h | 라이브 URL 렌더·카드수·콘솔 에러·타당성 | GitHub Issue |

**셀프힐링**: monitor/sitecheck가 `recoverable`(신선도 미갱신) 판정 시 scrape 재실행 → 재점검 (최대 attempts 상한).  
**Human-in-the-loop**: LLM은 진단·제안만, 코드 수정·머지는 사람이 Claude Code로.

---

## 5.5 채용알림 (웹 푸시) 파이프라인

```mermaid
flowchart LR
    BTN["프론트 '🔔 채용알림'<br/>scope: 전체 / 수습CPA"] -->|"PushManager.subscribe(VAPID 공개키)"| SW["sw.js 등록"]
    SW -->|"POST /subscribe {endpoint,keys,scope}"| WK["Cloudflare Worker<br/>hbmons-push.*.workers.dev<br/>KV에 scope 포함 저장"]
    RUN["run-all.yml → src/notifier.py"] -->|"GET /list (Bearer)"| WK
    RUN -->|"state.json 신규(notified=False) × scope 매칭"| PUSH["pywebpush(VAPID 서명)<br/>→ 구독자 브라우저"]
```

- **발송 순서(중요)**: run-all은 **수집 → 데이터 커밋·푸시 → Pages 라이브 확인 → 알람 발송 → 발송상태 커밋** 순. 알림 클릭은 `sw.js`상 **무조건 hbmons.com 홈으로** 가므로, 알람보다 데이터가 먼저 라이브여야 구독자가 새 공고를 본다. `Wait for Pages` 스텝이 방금 푸시한 `jobs.json`의 `generated_at`이 라이브에 반영될 때까지 폴링(최대 ~5분)한 뒤 알람을 쏜다. (과거: 알람 먼저 → 데이터 나중 커밋 → 알람 직후 들어온 사람은 빈 홈을 보는 창이 있었음.)
- **scope**: `수습CPA 전용` 구독자는 `classify_qualification`이 수습CPA인 공고만, `전체`는 인턴·일반 포함 전부 수신.
- **콜드스타트 억제**: 활성화 직전 `python -m src.notifier --seed`로 기존 공고를 baseline(notified=True) 처리 → 가입 직후 폭주 없음.
- **보안**: VAPID 개인키(`VAPID_PRIVATE_KEY`)·구독 read 토큰(`SUBS_READ_TOKEN`)은 **GitHub Secret에서만**. Worker `READ_TOKEN`은 `wrangler secret`. 코드/커밋엔 **공개키만**.
- **구성요소**: `docs/sw.js`(수신) · `docs/app.js subscribePush()`(구독) · `worker/subscriptions.js`(KV 저장) · `src/notifier.py`(발송) · `config.notifications`(enabled·worker_url·vapid_public). 견고성: 발송 실패가 run을 막지 않음(`|| true`), 미발송분은 notified=False로 남아 다음 run 재시도.
- **시험 발송(수동)**: `push-test.yml`(workflow_dispatch) → `scripts/push_test.py`가 구독자 전원에게 '시험 알림' 1건 발송. **state 미변경(멱등)**. VAPID 개인키가 GitHub Secret에만 있어 로컬 발송이 불가하므로, 푸시 동작 점검은 Actions에서 이 워크플로를 돌려 확인한다(입력 `body`·`url` 커스텀; `url` 비우면 `jobs.json` 첫 공고로 보내 **알림→공고→뒤로가기=홈** 동선까지 실기기 점검 가능).
- **알림 클릭 동선**: `sw.js notificationclick`은 **무조건 회법몬 홈(`hbmons.com`)을 연다/포커스**한다(외부 공고로 보내지 않음). 새 공고는 홈 '방금 올라온 공고'에 노출되므로 거기서 본다. *(과거 외부 공고로 직접 보내 '뒤로가기=홈'을 시도했으나 — `?goto` 홈경유·히스토리 조작·iOS bfcache 등 — 브라우저·기기별 동작 차이로 빈 화면·버튼 비활성·엉뚱페이지 오류가 잦아 폐기. '회법몬만 연다'가 전 플랫폼에서 안정적. payload의 공고 url은 알림 본문 표시용으로만 유지.)*

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
│   ├── classify.py              ← 법인/자격요건(수습CPA·자격무관)/채용구분(인턴·정규·계약·파트) 분류
│   ├── filters.py               ← 경력 제외 필터
│   ├── notifier.py              ← 웹 푸시 채용알림 발송(pywebpush·VAPID·scope)
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
│   ├── app.js                   ← 전체 프론트 로직 (필터 2축·카드·푸시 구독)
│   ├── style.css                ← 스타일
│   ├── sw.js                    ← 푸시 서비스워커 (수신, 캐시 없음)
│   ├── manifest.json            ← PWA 매니페스트 (아이콘·테마색)
│   ├── icon.svg / icon-192·512.png / favicon.ico / apple-touch-icon.png  ← 로고/아이콘
│   └── data/
│       ├── jobs.json            ← 채용공고 (qualification·emp_kind 포함)
│       ├── news.json            ← 기사 (Actions가 갱신)
│       ├── insights.json        ← 인사이트 (Actions가 갱신)
│       ├── status.json          ← 마지막 수집 시각
│       └── notify_status.json   ← 푸시 발송 관측성
├── .github/workflows/
│   ├── run-all.yml              ← 주 수집 (외부핑거 → repository_dispatch) + 푸시 발송(notifier)
│   ├── push-test.yml            ← 수동 시험 푸시 (scripts/push_test.py · state 미변경)
│   ├── monitor.yml              ← 통합 점검 (5h cron · canary+sitecheck 셀프힐링)
│   ├── freshness.yml            ← 신선도 감시 (1h cron · monitor 안정화 후 폐기 예정)
│   ├── sitecheck.yml            ← 종단 점검 (3h cron · monitor 안정화 후 폐기 예정)
│   ├── canary.yml               ← 양식 감시 (수동)
│   ├── scrape.yml               ← 채용 단독 (수동) <-외부 핑거로 가동
│   ├── scrape-news.yml          ← 기사 단독 (수동) <-외부 핑거로 가동
│   └── scrape-insights.yml      ← 인사이트 단독 (수동) <-외부 핑거로 가동
├── worker/                      ← Cloudflare Worker (푸시 구독 저장소, 정적 사이트의 미니 백엔드)
│   ├── subscriptions.js         ← /subscribe·/list·/unsubscribe (KV, scope 저장)
│   └── wrangler.toml            ← 배포 설정 (KV 바인딩·ALLOWED_ORIGIN)
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

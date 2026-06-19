# 회법몬 (KICPA Career Hub)

[![site](https://img.shields.io/badge/live-hbmons.com-1b4f9c)](https://hbmons.com)
[![tests](https://github.com/jaehyuk-choi-KICPA/KICPA_CAREER_HUB_SITE/actions/workflows/tests.yml/badge.svg)](https://github.com/jaehyuk-choi-KICPA/KICPA_CAREER_HUB_SITE/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.11-blue)
![license](https://img.shields.io/badge/data-titles%20%26%20links%20only-lightgrey)

> 빅4·로컬 회계법인의 **수습공인회계사·회계법인 입사 준비자**를 위해, 흩어진 **채용공고 + 회계·세무·딜 업계 뉴스 + Big4 인사이트**를
> 자동으로 모아 한 화면에 보여주는 **서버리스 정적 웹 대시보드**. → **라이브: [hbmons.com](https://hbmons.com)**

수습 CPA 준비자는 한국공인회계사회·삼일·삼정·안진·한영 등 **6개+ 사이트를 매번 따로** 확인해야 한다.
회법몬은 이 소스들을 **자동 수집 → 법인 × 직무 × 진행상태로 분류·필터 → 한 화면**으로 정리하고, 업계 뉴스·빅펌 간행물까지 묶는다.
**서버·노트북 상시구동 불필요** — 외부 스케줄러가 GitHub Actions를 트리거해 수집·커밋하고, GitHub Pages가 서빙한다.

## 미리보기

| 채용공고 (법인×직무×상태 필터 + 새 공고 패널) | 기사 (4분류 + 동일주제 군집) |
|:---:|:---:|
| [![채용공고](assets/shot-jobs.png)](https://hbmons.com) | [![기사](assets/shot-news.png)](https://hbmons.com/?#news) |

---

## 핵심 설계 결정 — *왜* 이렇게 만들었나

> 회계 도메인 데이터를 다루므로 **재현성·검증가능성·환각 차단**을 최우선으로 두고 설계했다.

| 결정 | 이유 |
|---|---|
| **어댑터 패턴** (소스→공통 레코드 `Posting`) | 사이트마다 다른 HTML/RSS/JSON을 한 스키마로 수렴. 이후 단계(필터·분류·중복제거)는 한 형태만 다룸. **새 소스 = 어댑터 1개.** |
| **규칙 기반 코어 (LLM-free)** | 분류·필터·큐레이션은 전부 키워드 규칙(`config.yaml`). **결정론·재현성·비용 0·오프라인 동작**, 그리고 데이터 파이프라인에서 **LLM 환각을 원천 배제**. |
| **LLM은 '판단'에만, 그것도 게이트** | 뉴스 의미 군집은 *어휘로 애매한 의심 쌍에 한해* 임베딩 호출(키 있을 때만, 없으면 어휘 폴백=오프라인 유지). 시각 점검도 프로덕션 데이터를 안 쓰는 out-of-band. |
| **Human-in-the-loop** | 소스가 깨지면 **감지·진단은 자동, 코드 수정은 사람.** LLM은 *제안*만 하고 Draft PR로 올림 — 자동 머지·자동 프로덕션 커밋 없음. |
| **견고성 = 전체 실패 금지** | 모든 어댑터 호출을 `safe_fetch`로 격리 → **한 소스가 깨져도 나머지는 정상 출력.** |

## 신뢰성 엔지니어링 — 운영하며 쌓은 것

개인 토이가 아니라 **실제로 24/7 돌아가는** 자동화라, 스크래퍼의 숙명적 약점(소스가 조용히 바뀌거나 스케줄이 드롭되면 *말없이* 낡은 데이터)을 **3층으로 감시**한다.

- **`freshness`** — 데이터 나이로 *스케줄이 돌았나* 감지(STALE 시 Draft PR).
- **`canary`** — 소스별 수집 건수·양식 급변 감지(0건/급감/양식변경). 선택적 LLM 시각 점검.
- **`sitecheck`** — 배포된 **라이브 화면**을 브라우저로 열어 *사용자가 실제로 제대로 보나* 종단 점검 + 파생지표 **타당성** 검사 + 셀프힐링.

> **실제 인시던트 대응 예:** `run-all` 한 실행이 동시성 그룹(`data-commit`) 잠금을 쥔 채 **행에 걸려 수집이 수 시간 정지** → 원인 규명 후 `timeout-minutes`를 추가해 *행 걸린 run이 그룹을 장기 점유하지 못하게* 재발 차단. (모니터링이 없었다면 조용히 낡았을 사고.)
>
> **소스 깜빡임 대응:** KICPA가 살아있는 공고를 목록에서 잠깐 내렸다 올리는 현상 → `state`의 **grace 레이어**(`last_seen`/`carry_forward`)로 흡수해 카드가 깜빡 사라지지 않게.

## 콘텐츠 3스트림

1. **채용공고 (메인)** — KICPA(수습CPA·CPA) + 삼정·안진·한영·삼일. **법인 ×직무(딜/감사/택스/기타) ×진행상태** 필터 + NEW·마감 D-day + "새로 올라온 공고" 패널.
2. **기사** — Google News RSS 4분류(채용·시험/감사/세무/딜·M&A). 제목·출처·링크만, 노이즈 제외, 중복은 군집화.
3. **빅펌 인사이트** — 삼일·삼정·안진·한영 간행물 링크(SPA라 헤드리스 렌더). 저작권 안전(제목·링크만).

## 아키텍처

```
외부 스케줄러(cron-job.org) ──repository_dispatch──► GitHub Actions(run-all)
                                                          │
            6 어댑터(병렬)  ─safe_fetch→ 공통 레코드 ─► 필터 ─► 규칙 분류 ─► (게이트)임베딩 군집
                                                          │
                                          docs/data/*.json 커밋 ─► GitHub Pages(docs/) ─► 바닐라 SPA
                                                          │
                       모니터링 3층: freshness · canary · sitecheck (이상 시 Draft PR / GitHub Issue)
```

## 기술 스택

**Python** (스크래퍼·규칙 엔진·상태기계) · **바닐라 JS/CSS** (프론트, 빌드도구 없음, 다크모드·반응형) ·
**GitHub Actions** (CI/CD·스케줄·셀프힐링) · **Playwright** (SPA 헤드리스 렌더) · **GitHub Pages** (서빙) ·
선택적 **Anthropic / Voyage API** (out-of-band 시각점검·의미군집, 키 없으면 자동 비활성).

## 테스트

순수 로직(필터·분류·상태기계·날짜 파싱)에 대한 **pytest 단위 테스트**. 규칙이 곧 사양이므로 실제 `config`로 검증한다.

```bash
pip install pytest PyYAML
python -m pytest tests/ -v
```

## 로컬 실행

```bash
pip install -r requirements.txt
python -m playwright install chromium      # 인사이트(SPA 렌더)용 1회
python -m src.export                       # docs/data/{jobs,news,insights}.json 생성
#   부분만:  python -m src.export --part jobs|news|insights
cd docs && python -m http.server 8000      # http://localhost:8000
```

## 배포 (GitHub Pages)

1. `main`에 push → **Settings → Pages → Deploy from branch: `main` / `/docs`**.
2. 자동 갱신은 **외부 핑거(cron-job.org 등)가 `repository_dispatch{event_type:run-all}`로 `run-all.yml`을 30분마다 호출**.
   - GitHub 무료·public cron은 드롭이 잦아, **정기 수집은 외부 핑거가 전담**(개별 `scrape*.yml`은 수동 보조).
   - 모니터링(`freshness` 매시간 · `sitecheck` 3시간)은 GitHub cron 유지.
3. (선택) LLM 점검: **Settings → Secrets → Actions**에 `ANTHROPIC_API_KEY` 추가. 없으면 결정론 검사만(오프라인).

## 문서 (`docs-meta/`)

- [사용설명서](docs-meta/사용설명서.md) — 운영·배포·설정·문제해결
- [패치노트](docs-meta/PATCHNOTES.md) — 빌드별 UI 개선·새 기능
- [수집 엔진 개선 일지](docs-meta/SCRAPER_LOG.md) — 스크랩 툴 보완 흐름

## 원칙 (저작권·개인정보)

공개된 채용공고·공식 간행물의 **제목과 링크만** 수집한다(본문 전재·UGC·개인정보 없음). 비영리.

---

<sub>※ 초기엔 카카오톡 오픈채팅 자동 게시(`run.py`·`kakao_pc.py`)로 시작했으나 GUI 자동화 불안정으로 웹 대시보드로 피벗. 레거시 코드는 보존.</sub>

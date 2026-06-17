# 회계법인 취업 허브 (KICPA_CAREER_HUB_SITE)

빅4·로컬 회계법인의 **수습공인회계사(기합 포함)·회계법인 입사 준비자**를 위한 정적 웹 대시보드.
**채용공고 검색 + 회계·세무·딜 업계 뉴스 + Big4 인사이트 링크**를 자동 수집해 GitHub Pages로 서빙한다.
서버·노트북 불필요(GitHub Actions가 주기 수집·커밋).

## 콘텐츠 3스트림
1. **채용공고(메인)** — KICPA(수습CPA·CPA) + 삼정·안진·한영·삼일. **법인 × 직무(딜/감사/택스/기타) ×
   진행상태** 좌측 필터 레일 검색 + 신규(NEW)·마감 D-day + 우측 "금일 올라온 공고" 패널.
2. **기사** — Google News RSS로 제도·규제/세무/딜·M&A/회계업계 (면접·업계지식 중심, 노이즈 제외, 1주일 보존).
3. **빅펌 인사이트** — 삼일·삼정·안진·한영 간행물 링크(헤드리스 렌더). 제목·링크만(저작권 안전).

## 구조
```
GitHub Actions(cron) → python -m src.export → docs/data/*.json 커밋 → GitHub Pages(docs/) 서빙
```
- 소스마다 사이트가 달라 **어댑터 패턴**(소스→공통 레코드)으로 흡수. 채용·뉴스는 병렬, 인사이트는 순차(헤드리스).
- 프론트: 바닐라 HTML/CSS/JS(빌드 도구 없음), 다크모드, 모바일 반응형.

## 로컬 실행
```bash
pip install -r requirements.txt
python -m playwright install chromium     # 인사이트(JS 렌더)용 1회
python -m src.export                      # docs/data/{jobs,news,insights}.json 생성
#   부분만:  python -m src.export --part jobs|news|insights
cd docs && python -m http.server 8000     # http://localhost:8000
```

## 배포 (GitHub Pages)
1. GitHub에 push (아래 "git" 참조).
2. 저장소 **Settings → Pages → Source: Deploy from a branch, Branch: `main` / `/docs`**.
3. 워크플로가 자동 갱신:
   - `.github/workflows/scrape.yml` — 채용 **30분** (cron 보조)
   - `.github/workflows/scrape-news.yml` — 기사 **2시간** (cron 보조)
   - `.github/workflows/scrape-insights.yml` — 인사이트 **하루 2회**(09·21시 KST, Chromium 설치, cron 보조)
   - `.github/workflows/run-all.yml` — 채용+기사+인사이트 **일괄 수집** (외부 핑거 트리거 전용)
   - `.github/workflows/canary.yml` — 자기검증(소스 양식/공고 누락) **매일 1회**(아래 참조)
   - `.github/workflows/freshness.yml` — 신선도 모니터(스케줄 드롭으로 데이터가 낡았는지) **매시간**, STALE 시 Draft PR
   - **안정적 주기 실행**: GitHub cron은 무료·public에서 드롭이 잦음 → **cron-job.org 등 외부 핑거**가
     `repository_dispatch{event_type:run-all}`로 `run-all.yml`을 30분마다 호출(개별 cron은 보조).
   - **검색 주기 변경**: `run-all.yml`의 외부 핑거 interval 또는 개별 워크플로 `cron:` 수정.
   - 수동 즉시 실행: 저장소 Actions 탭 → 해당 워크플로 → Run workflow.

## 자기검증 카나리아 (소스 양식 변경/공고 누락 감지)
스크래퍼는 소스가 HTML을 바꾸면 조용히 0건/누락이 난다. `src/canary.py`가 **하루 1회** 이를 감시한다.
- **구조 체크(무료)**: 어제 대비 0건/급감/수집실패 (`canary_state.json` 기준).
- **시각 체크(LLM, 키 있을 때만)**: 목록 페이지 스냅샷을 Claude vision로 보고 화면 공고수·양식 정상여부를
  스크래퍼 카운트와 대조.
- **드리프트 시**: `canary_report.md`(진단 + LLM 수정 *제안*)를 담은 **Draft PR 자동 생성**.
  **자동 머지·자동 프로덕션 커밋은 하지 않는다** — Claude Code로 검토·보완 후 사람이 머지(Human-in-the-loop).
- **LLM 켜기**: 저장소 **Settings → Secrets and variables → Actions → New repository secret**에
  `ANTHROPIC_API_KEY` 추가. 없으면 **구조 체크만**(100% 오프라인). 전송 대상은 공개 채용 페이지 스냅샷뿐.
- ⚠️ **첫 도입**: Actions 탭에서 `canary`를 **수동 실행(Run workflow)**해 LLM 응답을 한 번 눈으로 검증한 뒤
  cron 자동화에 의존할 것.

## 피드백
사이트 푸터의 "만족도 조사 · 피드백" 버튼 → Google Form.

---
## (보류) 카카오톡 자동 게시 — 레거시
초기엔 카톡 오픈채팅 자동 게시(`run.py`·`kakao_pc.py`·`messenger_bot.js`)였으나 GUI 자동화 불안정으로 보류.
코드는 보존. 현재 제품은 위 웹 대시보드.

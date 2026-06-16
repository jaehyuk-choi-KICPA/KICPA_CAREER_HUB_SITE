# 회계법인 취업 허브 (KICPA_CAREER_HERB_SITE)

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
   - `.github/workflows/scrape.yml` — 채용 **3시간**
   - `.github/workflows/scrape-news.yml` — 기사 **9시간**
   - `.github/workflows/scrape-insights.yml` — 인사이트 **매일 1회**(Chromium 설치)
   - **검색 주기 변경**: 각 파일의 `cron:` 한 줄만 수정 후 push(코드 변경 불필요).
   - 수동 즉시 실행: 저장소 Actions 탭 → 해당 워크플로 → Run workflow.

## 피드백
사이트 푸터의 "만족도 조사 · 피드백" 버튼 → Google Form.

---
## (보류) 카카오톡 자동 게시 — 레거시
초기엔 카톡 오픈채팅 자동 게시(`run.py`·`kakao_pc.py`·`messenger_bot.js`)였으나 GUI 자동화 불안정으로 보류.
코드는 보존. 현재 제품은 위 웹 대시보드.

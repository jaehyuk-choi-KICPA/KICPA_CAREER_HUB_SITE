"use strict";

const FIRM_ORDER = ["삼일", "삼정", "안진", "한영", "로컬", "기타"];
const FIRM_COLOR = { 삼일:"#d9692a", 삼정:"#1a6fb5", 안진:"#2e8b57", 한영:"#b59312", 로컬:"#6b7684", 기타:"#8a94a6" };
const FIELD_ORDER = ["감사", "택스", "딜", "기타"];        // 채용 직무 필터 순서(기사와 일관: 감사·택스·딜)
const NEWS_CAT_ORDER = ["채용·시험", "감사", "세무", "딜·M&A"];  // 기사 카테고리 필터 순서(감사·세무(택스)·딜 일관)

function el(tag, props = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const c of [].concat(kids)) if (c) n.appendChild(c);
  return n;
}
const $ = (id) => document.getElementById(id);
async function loadJSON(p) {
  // 캐시버스트: Pages CDN이 옛 JSON을 서빙하지 않도록 매 로드 고유 쿼리 부여(브라우저 no-store와 별개)
  const u = p + (p.includes("?") ? "&" : "?") + "v=" + Date.now();
  try { const r = await fetch(u, {cache:"no-store"}); return r.ok ? await r.json() : null; } catch { return null; }
}

// ---- 기사 신규 표시(브라우저별 기억) — 카드 점(항목별)과 탭 점(독립) ----
function _seenGet(k){ try { return JSON.parse(localStorage.getItem(k) || "[]"); } catch { return []; } }
function _seenSet(k, arr){ try { localStorage.setItem(k, JSON.stringify(arr)); } catch (e) {} }
let NEWS_TODAY_URLS = [];                 // 현재 '오늘 발행' 기사 url(데이터 로드 시 채움)
function isSeenNews(url){ return _seenGet("seen_news").includes(url); }
function markSeenNews(url){ const s = _seenGet("seen_news"); if (!s.includes(url)) { s.push(url); _seenSet("seen_news", s); } }
function updateNewsTabDot(){             // 탭 점 = 안 본 신규(_today)가 하나라도 남았나
  const seen = _seenGet("tabseen_news");
  const dot = document.querySelector('.tab-btn[data-tab="news"] .tab-new');
  if (dot) dot.hidden = !NEWS_TODAY_URLS.some((u) => !seen.includes(u));
}
function clearNewsTabDot(){ _seenSet("tabseen_news", NEWS_TODAY_URLS.slice()); updateNewsTabDot(); }
// 카드 점은 항목별 제거, 탭 점은 아무 신규 클릭/펼치기 시 함께 해제(독립 — 다른 카드 점은 유지)
function dismissNews(url, dotEl){ markSeenNews(url); if (dotEl && dotEl.remove) dotEl.remove(); clearNewsTabDot(); }

// ---- 테마(다크모드) ----
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  const btn = $("theme-toggle"); if (btn) btn.textContent = t === "dark" ? "☀️" : "🌙";
}
(function initTheme() {
  let t = localStorage.getItem("theme");
  if (!t) t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  applyTheme(t);
})();

// ---- 스켈레톤 ----
function skel(n) {
  return Array.from({ length:n }, () => el("div", { class:"skeleton" }, [
    el("div", { class:"skel-line w40" }), el("div", { class:"skel-line w90" }),
    el("div", { class:"skel-line w70" }), el("div", { class:"skel-line w55" }),
  ]));
}

const NEWS_CAT_COLOR = { "채용·시험":"#1b4f9c", "감사":"#7a4fb0", "세무":"#8a5a1b", "딜·M&A":"#0f9d77", "인사이트":"#c2410c" };

// ---- 탭 전환 ----
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("on", b === btn));
      const t = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + t));
      if (t === "news") clearNewsTabDot();   // 기사 탭 방문 = 탭 점 해제(카드 점은 유지 — 독립)
      window.scrollTo({ top: 0 });
    });
  });
  // 로고(회법몬) 클릭 → 채용공고 탭 최상단 + 데이터 새로고침
  const logo = document.querySelector(".brand h1");
  if (logo) logo.addEventListener("click", async () => {
    document.querySelector('.tab-btn[data-tab="jobs"]')?.click();
    const upd = $("updated");
    const prev = upd.textContent;
    upd.textContent = "새로고침 중…";
    const [jobs, status] = await Promise.all([
      loadJSON("data/jobs.json"), loadJSON("data/status.json"),
    ]);
    const stamp = (status && status.last_run) || (jobs && jobs.generated_at) || "";
    upd.textContent = stamp ? "최근 업데이트: " + stamp.replace("T", " ") : prev;
    if (jobs) initJobs(jobs);
  });
}

// ===================== 채용 =====================
const JS = { firm:new Set(), field:new Set(), status:"open", onlyNew:false, kw:"", sort:"deadline" };
let JOBS = [];

function ddayInfo(it) {
  if (it.status === "closed") return { t:"마감", c:"closed" };
  const d = it.dday;
  if (d === null || d === undefined) return { t:"상시", c:"" };
  if (d === 0) return { t:"오늘마감", c:"soon" };
  if (d < 0) return { t:"마감", c:"closed" };
  return { t:"D-" + d, c: d <= 3 ? "soon" : d <= 7 ? "warn" : "" };
}

// D-day 배지 엘리먼트. 당일마감(dday=0)은 '오늘'+'마감' 두 토큰으로 — 모바일에서만 2줄로 쌓아 칸 무너짐 방지.
function ddayBadge(it) {
  const dd = ddayInfo(it);
  const span = el("span", { class:"dday " + dd.c });
  if (it.status !== "closed" && it.dday === 0) {
    span.classList.add("today2");
    span.append(el("span", { text:"오늘" }), el("span", { text:"마감" }));
  } else {
    span.textContent = dd.t;
  }
  return span;
}

// 카드 제목에서 선행 [회사명](아래 .company와 중복)을 제거해 가독성↑. 매칭 안 되면 원제목 유지.
function displayJobTitle(it) {
  let t = (it.title || "").trim();
  const co = (it.company || "").trim();
  if (!co) return t;
  const coN = co.replace(/\s+/g, "");
  const m = t.match(/^\[([^\]]*)\]\s*/);
  if (m) {                                  // 선행 [회사명] 또는 [회사명 …]
    const inner = m[1].replace(/\s+/g, "");
    if (inner === coN || inner.includes(coN) || coN.includes(inner)) t = t.slice(m[0].length);
  } else if (t.replace(/\s+/g, "").startsWith(coN)) {   // 대괄호 없이 평문 선행
    t = t.slice(co.length).replace(/^[\s\-–·:|]+/, "");
  }
  return t.trim() || it.title;
}

function jobCard(it) {
  const dd = ddayInfo(it);
  // 좌측=법인·직무 / 우측=상태표시(NEW·D-day) 통일 배치
  const left = el("div", { class:"top-left" }, [
    el("span", { class:"badge", style:`background:${FIRM_COLOR[it.firm]||"#6b7684"}`, text:it.firm }),
    el("span", { class:"tag", text:it.field }),
  ]);
  const right = el("div", { class:"top-right" }, [
    ddayBadge(it),   // D-day = 우측상단 (당일마감은 모바일에서 2줄)
  ]);
  const top = el("div", { class:"card-top" }, [left, right]);
  const title = el("h3", {}, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:displayJobTitle(it) })]);
  const company = el("div", { class:"company", text:it.company || "-" });
  const meta = el("div", { class:"card-meta" });
  const parts = [];
  if (it.emp_type) parts.push(el("span", { text:it.emp_type }));
  if (it.location) parts.push(el("span", { text:"📍" + it.location }));
  parts.push(el("span", { class:"meta-deadline", text:"📅 " + (it.deadline || "상시") }));  // 모바일에선 숨김(우측 D-day로 갈음)
  if (it.posted_date) parts.push(el("span", { text:"게시 " + it.posted_date }));
  parts.forEach((p, i) => { if (i) meta.appendChild(el("span", { class:"sep", text:"·" })); meta.appendChild(p); });
  // NEW 배지는 제거(정보량 절감) — 신규는 카드 좌측 초록 테두리(.is-new)로 표시
  return el("article", { class:"card" + (it.status==="closed"?" closed":"") + (it.is_new?" is-new":"") },
    [top, title, company, meta]);
}

// 진행상태 분류: 진행중(open=마감일 있는 진행) / 마감(closed) / 상설(open이지만 마감일 없는 상시채용)
function matchStatus(it, status) {
  const standing = it.dday === null || it.dday === undefined;
  if (status === "open") return it.status === "open" && !standing;
  if (status === "closed") return it.status === "closed";
  if (status === "standing") return it.status === "open" && standing;
  return true;
}

function renderJobs() {
  const kw = JS.kw.trim().toLowerCase();
  let list = JOBS.filter((it) => {
    if (JS.firm.size && !JS.firm.has(it.firm)) return false;
    if (JS.field.size && !JS.field.has(it.field)) return false;
    if (!matchStatus(it, JS.status)) return false;
    if (JS.onlyNew && !it.is_new) return false;
    if (kw && !((it.title + " " + (it.company||"")).toLowerCase().includes(kw))) return false;
    return true;
  });
  const openFirst = (a,b) => (a.status==="open"?0:1) - (b.status==="open"?0:1);
  list.sort((a, b) => {
    if (JS.sort === "posted") return (b.posted_date||"").localeCompare(a.posted_date||"");
    // deadline (default): 진행중 먼저 → 마감 임박순
    return openFirst(a,b) || ((a.dday??1e6)-(b.dday??1e6));
  });
  $("jobs-list").replaceChildren(...list.map(jobCard));
  $("jobs-empty").hidden = list.length > 0;
  $("jobs-summary").textContent = list.length + "건";   // 결과 건수 즉시 피드백
  renderActiveFilters();
}

// 결과 영역 상단에 선택된 필터를 제거가능 칩으로 노출(레일을 다시 열지 않고 해제)
function syncChips(sel) { document.querySelectorAll(sel + " .filter-chip").forEach((c) => c._sync && c._sync()); }
function clearFirm(v)  { JS.firm.delete(v); renderFirmChips(); renderJobs(); }
function clearField(v) { JS.field.delete(v); syncChips("#f-field"); renderJobs(); }
function clearStatus() { JS.status = "open"; renderFirmChips(); syncChips("#f-status"); renderJobs(); }
function clearKw()     { JS.kw = ""; $("kw").value = ""; renderJobs(); }
const STATUS_LABEL = { closed:"마감", standing:"상설" };
function renderActiveFilters() {
  const box = $("active-filters"); if (!box) return;
  const chips = [];
  const add = (label, onX) => {
    const x = el("button", { type:"button", class:"x", text:"✕" });
    x.addEventListener("click", onX);
    chips.push(el("span", { class:"afilter" }, [el("span", { text:label }), x]));
  };
  JS.firm.forEach((f) => add(f, () => clearFirm(f)));
  JS.field.forEach((f) => add(f, () => clearField(f)));
  if (STATUS_LABEL[JS.status]) add(STATUS_LABEL[JS.status], clearStatus);   // 기본(진행중)은 칩 미표시
  if (JS.kw.trim()) add('"' + JS.kw.trim() + '"', clearKw);
  box.replaceChildren(...chips);
}

function todayItem(it, isOld) {
  const dd = ddayInfo(it);
  const row1 = el("div", { class:"row1" }, [
    el("span", { class:"dot", style:`background:${FIRM_COLOR[it.firm]||"#6b7684"}` }),
    el("span", { class:"firm", text:it.firm }),
    el("span", { class:"dday " + dd.c, text:dd.t }),
  ]);
  const t = el("div", { class:"t" }, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]);
  // 가장 최근 날짜가 아닌(=어제) 공고는 흐리게(.is-old). 정렬 기준은 패널 제목 '(최신순)'으로 안내.
  return el("div", { class:"today-item" + (isOld?" is-old":"") }, [row1, t]);
}
function renderToday(genStamp) {
  // 최근 2일(어제·오늘) 게시 공고 — 자정 지나면 창이 하루씩 이동(18일이면 17·18, 19일이면 18·19).
  // 기준일은 데이터 생성일(genStamp). UTC로 날짜 계산해 로컬 타임존에 따른 off-by-one 방지.
  const today = (genStamp || "").slice(0, 10);
  const dt = new Date(today + "T00:00:00Z");
  dt.setUTCDate(dt.getUTCDate() - 1);
  const since = dt.toISOString().slice(0, 10);   // 어제
  const items = JOBS.filter((it) => it.status !== "closed" && it.posted_date && it.posted_date >= since)
    .sort((a, b) => (b.posted_date || "").localeCompare(a.posted_date || ""));   // 최신 게시일이 위로
  $("today-count").textContent = String(items.length);
  $("today-empty").hidden = items.length > 0;
  // 정렬은 최신순(제목 '(최신순)'으로 안내). 가장 최근 게시일과 다른(=어제) 공고는 흐리게.
  const maxDate = items.length ? items[0].posted_date : "";
  $("today-list").replaceChildren(...items.slice(0, 12).map((it) =>
    todayItem(it, it.posted_date !== maxDate)));
}

function countBy(key) { const m={}; for (const it of JOBS) m[it[key]]=(m[it[key]]||0)+1; return m; }

// 법인별 카운트 = 현재 선택된 진행상태(진행중/마감/상설)에 해당하는 건만 집계
function firmCountsByStatus() {
  const m = {}; FIRM_ORDER.forEach((f)=>m[f]=0);
  for (const it of JOBS) if (matchStatus(it, JS.status) && m[it.firm] !== undefined) m[it.firm]++;
  return m;
}
// 법인 칩을 현재 상태 기준 카운트로 (재)렌더 — 상태 변경 시 호출
function renderFirmChips() {
  buildOpts("f-firm", FIRM_ORDER, "checkbox", (v)=>JS.firm.has(v),
    (v)=>{ JS.firm.has(v)?JS.firm.delete(v):JS.firm.add(v); renderJobs(); }, firmCountsByStatus());
}

// 필터를 사이트 톤과 통일된 칩 버튼으로 렌더(복수선택=checkbox형, 단일선택=radio형 모두 지원).
// 선택 상태는 .on 클래스로 직접 관리(getOn으로 동기화) — 체크박스 제거로 이질감 해소.
function buildOpts(rowId, values, type, getOn, onToggle, counts) {
  const chips = values.map((v) => {
    const label = Array.isArray(v) ? v[0] : v, val = Array.isArray(v) ? v[1] : v;
    const cnt = counts ? el("span", { class:"cnt", text: "(" + (counts[label] || 0) + ")" }) : null;
    const chip = el("button", { type:"button", class:"filter-chip" }, [el("span", { text:label }), cnt]);
    const sync = () => chip.classList.toggle("on", getOn(val));
    sync();
    chip._sync = sync;
    chip.addEventListener("click", () => { onToggle(val); chips.forEach((c) => c._sync()); });
    return chip;
  });
  $(rowId).replaceChildren(...chips);
}

let _controlsBound = false;   // reset이 initJobs를 재호출해도 컨트롤 리스너 중복 바인딩 방지

function initJobs(data) {
  JOBS = data.postings || [];

  renderFirmChips();   // 법인 칩 = 선택 상태 기준 동적 카운트
  buildOpts("f-field", FIELD_ORDER, "checkbox", (v)=>JS.field.has(v),
    (v)=>{ JS.field.has(v)?JS.field.delete(v):JS.field.add(v); renderJobs(); });   // 직무는 카운트 미표시
  buildOpts("f-status", [["진행중","open"],["마감","closed"],["상설","standing"]], "radio",
    (v)=>JS.status===v, (v)=>{ JS.status=v; renderFirmChips(); renderJobs(); });   // 상태 바뀌면 법인 카운트 갱신

  if (!_controlsBound) { bindControls(data); _controlsBound = true; }
  renderJobs();
  renderToday(data.generated_at);
}

function bindControls(data) {
  $("kw").addEventListener("input", (e)=>{ JS.kw=e.target.value; renderJobs(); });
  $("sort").addEventListener("change", (e)=>{ JS.sort=e.target.value; renderJobs(); });
  const setRail = (open) => {
    $("rail").classList.toggle("open", open);
    const t = $("rail-toggle");
    t.setAttribute("aria-expanded", open ? "true" : "false");
    t.textContent = open ? "필터 닫기 ▴" : "필터 ▾";
  };
  $("rail-toggle").addEventListener("click", () => {
    const open = !$("rail").classList.contains("open");
    setRail(open);
    if (open) $("rail").scrollIntoView({ behavior:"smooth", block:"start" });
  });
  $("rail-close").addEventListener("click", () => {
    setRail(false);
    $("rail-toggle").scrollIntoView({ behavior:"smooth", block:"start" });
  });
}

// ===================== 기사/인사이트 =====================
function newsCard(it) {
  const catColor = NEWS_CAT_COLOR[it.category];
  const left = el("div", { class:"top-left" }, [
    it.category ? el("span", { class:"tag cat", style:`background:${catColor||"#667085"}`, text: it.category }) : null,
    el("span", { class:"tag", text: it.source_label || it.source || "" }),
  ]);
  const isNew = !!it._today && !isSeenNews(it.url);   // 신규 && 아직 안 본 것만 점 표시
  const dot = isNew ? el("span", { class:"today-dot", title:"오늘 올라옴" }) : null;
  const right = el("div", { class:"top-right" }, [dot]);
  const top = el("div", { class:"card-top" }, [left, right]);
  const titleA = el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title });
  const kids = [top, el("h3", {}, [titleA])];
  if (it.summary) kids.push(el("div", { class:"company", text:it.summary }));
  if (it.published) kids.push(el("div", { class:"card-meta" }, [el("span", { text:it.published })]));
  // 같은 주제 중복 기사 묶음 — 네이티브 <details>로 우측 하단에 깔끔히 펼침(클릭 시 제목+링크 좌르르)
  let details = null;
  if (it.dupes && it.dupes.length) {
    const lis = it.dupes.map((d) => el("li", {}, [
      el("a", { href:d.url, target:"_blank", rel:"noopener", text:d.title || "(제목 없음)" }),
      d.source_label ? el("span", { class:"dupe-src", text:d.source_label }) : null,
    ]));
    details = el("details", { class:"dupes" }, [
      el("summary", { class:"dupes-toggle", text:`동일 주제 기사 ${it.dupes.length}개` }),
      el("ul", { class:"dupes-list" }, lis),
    ]);
    kids.push(details);
  }
  // 해제: 제목 클릭 또는 '동일 주제' 펼치기만으로도 그 카드 점 + 탭 점 제거(브라우저별 기억)
  if (isNew) {
    titleA.addEventListener("click", () => dismissNews(it.url, dot));
    if (details) details.addEventListener("toggle", () => { if (details.open) dismissNews(it.url, dot); });
  }
  return el("article", { class:"card" }, kids);
}

// 인사이트 카드: 공통 '인사이트' 태그 제거, 발행 법인을 법인색 태그로 표시
const INSIGHT_FIRM = { "삼일PwC":"삼일", "삼정KPMG":"삼정", "딜로이트안진":"안진", "EY한영":"한영" };
function insightCard(it) {
  const firm = INSIGHT_FIRM[it.source_label];
  const color = (firm && FIRM_COLOR[firm]) || "#667085";
  const left = el("div", { class:"top-left" }, [
    el("span", { class:"tag cat", style:`background:${color}`, text: it.source_label || it.source || "인사이트" }),
  ]);
  const right = el("div", { class:"top-right" }, [
    it._today ? el("span", { class:"today-dot", title:"오늘 올라옴" }) : null,
  ]);
  const top = el("div", { class:"card-top" }, [left, right]);
  const title = el("h3", {}, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]);
  const kids = [top, title];
  if (it.published) kids.push(el("div", { class:"card-meta" }, [el("span", { text:it.published })]));
  return el("article", { class:"card" }, kids);
}

function initSub(prefix, data, chipRowId, chipKey, fixed, cardFn) {
  const renderCard = cardFn || newsCard;
  const items = (data && data.items) || [];
  if (!items.length) { $(prefix+"-empty").hidden = false; return; }
  let selected = null;  // 단일선택: null=전체, 같은 칩 다시 누르면 해제
  const values = fixed || [...new Set(items.map((i)=>i[chipKey]).filter(Boolean))];
  const chips = [];
  const render = () => {
    const list = selected ? items.filter((i)=>i[chipKey]===selected) : items;
    $(prefix+"-list").replaceChildren(...list.map(renderCard));
    $(prefix+"-empty").hidden = list.length > 0;
    chips.forEach((c)=> c.classList.toggle("on", c.dataset.v === selected));
  };
  const row = $(chipRowId);
  values.forEach((v) => {
    const chip = el("span", { class:"chip", text:v });
    chip.dataset.v = v;
    chip.addEventListener("click", () => { selected = (selected === v) ? null : v; render(); });
    chips.push(chip);
  });
  row.replaceChildren(...chips);
  render();
}

// ===================== 부트 =====================
(async function () {
  initTabs();
  const tt = $("theme-toggle");
  if (tt) tt.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next); applyTheme(next);
  });
  // 로딩 스켈레톤
  $("jobs-list").replaceChildren(...skel(6));
  $("news-list").replaceChildren(...skel(4));
  $("insights-list").replaceChildren(...skel(4));

  const [jobs, news, insights, status] = await Promise.all([
    loadJSON("data/jobs.json"), loadJSON("data/news.json"), loadJSON("data/insights.json"),
    loadJSON("data/status.json"),
  ]);
  // 헤더 시각 = 점검 시각(last_run): 변화 없어도 자동화가 돌면 전진. 없으면 jobs 생성시각 폴백.
  const stamp = (status && status.last_run) || (jobs && jobs.generated_at) || "";
  $("updated").textContent = stamp ? "최근 업데이트: " + stamp.replace("T", " ") : "데이터 없음";

  // 당일 올라온 항목 표시(_today) — 기사=오늘 발행, 인사이트=오늘 최초발견(is_new)
  const newsToday = ((news && news.generated_at) || "").slice(0, 10);
  if (news && news.items) news.items.forEach((i) => { i._today = !!i.published && i.published === newsToday; });
  if (insights && insights.items) insights.items.forEach((i) => { i._today = !!i.is_new; });

  // 기사 신규 점: 현재 '오늘 발행' url 집합 → seen 정리(현재분만 보관) + 탭 점 초기화
  if (news && news.items) {
    NEWS_TODAY_URLS = news.items.filter((i) => i._today && i.url).map((i) => i.url);
    _seenSet("seen_news", _seenGet("seen_news").filter((u) => NEWS_TODAY_URLS.includes(u)));
    updateNewsTabDot();
  }

  // PC 전용 미니 박스: 금일 수 + 클릭 시 탭 이동
  const newsN = (news && news.items) ? news.items.filter((i) => i._today).length : 0;
  const insN = insights ? (insights.today_count != null ? insights.today_count
    : ((insights.items || []).filter((i) => i._today).length)) : 0;
  const setMini = (btnId, numId, n, tab) => {
    const b = $(btnId); if (!b) return;
    $(numId).textContent = String(n);
    b.addEventListener("click", () => document.querySelector(`.tab-btn[data-tab="${tab}"]`)?.click());
  };
  setMini("mini-news", "mini-news-n", newsN, "news");
  setMini("mini-insights", "mini-insights-n", insN, "insights");

  if (jobs) initJobs(jobs);
  else { $("jobs-empty").hidden = false; $("jobs-empty").textContent = "채용 데이터를 불러오지 못했습니다."; }
  initSub("news", news, "f-newscat", "category", NEWS_CAT_ORDER);
  initSub("insights", insights, "f-pub", "source_label", null, insightCard);
})();

"use strict";

const FIRM_ORDER = ["삼일", "삼정", "안진", "한영", "로컬", "기타"];
const FIRM_COLOR = { 삼일:"#d9692a", 삼정:"#1a6fb5", 안진:"#2e8b57", 한영:"#b59312", 로컬:"#6b7684", 기타:"#8a94a6" };
const FIELD_ORDER = ["딜", "감사", "택스", "기타"];

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

const NEWS_CAT_COLOR = { "제도·규제":"#1b4f9c", "세무":"#8a5a1b", "딜·M&A":"#0f9d77", "회계업계":"#7a4fb0", "인사이트":"#c2410c" };

// ---- 탭 전환 ----
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("on", b === btn));
      const t = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("on", s.id === "tab-" + t));
      window.scrollTo({ top: 0 });
    });
  });
  // 로고(회법몬) 클릭 → 채용공고 탭 최상단으로
  const logo = document.querySelector(".brand h1");
  if (logo) logo.addEventListener("click", () => {
    document.querySelector('.tab-btn[data-tab="jobs"]')?.click();
  });
}

// ===================== 채용 =====================
const JS = { firm:new Set(), field:new Set(), status:"open", onlyNew:false, onlySoon:false, kw:"", sort:"reco" };
let JOBS = [];

function ddayInfo(it) {
  if (it.status === "closed") return { t:"마감", c:"closed" };
  const d = it.dday;
  if (d === null || d === undefined) return { t:"상시", c:"" };
  if (d === 0) return { t:"오늘마감", c:"soon" };
  if (d < 0) return { t:"마감", c:"closed" };
  return { t:"D-" + d, c: d <= 3 ? "soon" : d <= 7 ? "warn" : "" };
}

function jobCard(it) {
  const top = el("div", { class:"card-top" }, [
    el("span", { class:"badge", style:`background:${FIRM_COLOR[it.firm]||"#6b7684"}`, text:it.firm }),
    it.is_new ? el("span", { class:"badge new", text:"NEW" }) : null,
    el("span", { class:"tag", text:it.field }),
  ]);
  const title = el("h3", {}, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]);
  const company = el("div", { class:"company", text:it.company || "-" });
  const dd = ddayInfo(it);
  const meta = el("div", { class:"card-meta" });
  const parts = [];
  if (it.emp_type) parts.push(el("span", { text:it.emp_type }));
  if (it.location) parts.push(el("span", { text:"📍" + it.location }));
  parts.push(el("span", { class:"dday " + dd.c, text:dd.t }));
  parts.push(el("span", { text:"📅 " + (it.deadline || "상시") }));
  if (it.posted_date) parts.push(el("span", { text:"게시 " + it.posted_date }));
  parts.forEach((p, i) => { if (i) meta.appendChild(el("span", { class:"sep", text:"·" })); meta.appendChild(p); });
  return el("article", { class:"card" + (it.status==="closed"?" closed":"") + (it.is_new?" is-new":"") },
    [top, title, company, meta]);
}

function renderJobs() {
  const kw = JS.kw.trim().toLowerCase();
  let list = JOBS.filter((it) => {
    if (JS.firm.size && !JS.firm.has(it.firm)) return false;
    if (JS.field.size && !JS.field.has(it.field)) return false;
    if (JS.status !== "all" && it.status !== JS.status) return false;
    if (JS.onlyNew && !it.is_new) return false;
    if (JS.onlySoon && !(it.status==="open" && it.dday!==null && it.dday>=0 && it.dday<=7)) return false;
    if (kw && !((it.title + " " + (it.company||"")).toLowerCase().includes(kw))) return false;
    return true;
  });
  const openFirst = (a,b) => (a.status==="open"?0:1) - (b.status==="open"?0:1);
  list.sort((a, b) => {
    if (JS.sort === "posted") return (b.posted_date||"").localeCompare(a.posted_date||"");
    if (JS.sort === "deadline") return openFirst(a,b) || ((a.dday??1e6)-(b.dday??1e6));
    // reco: 신규 먼저 → 진행중 → 임박순
    const an=a.is_new?0:1, bn=b.is_new?0:1;
    return (an-bn) || openFirst(a,b) || ((a.dday??1e6)-(b.dday??1e6));
  });
  $("jobs-list").replaceChildren(...list.map(jobCard));
  $("jobs-empty").hidden = list.length > 0;
}

function todayItem(it) {
  const dd = ddayInfo(it);
  const row1 = el("div", { class:"row1" }, [
    el("span", { class:"dot", style:`background:${FIRM_COLOR[it.firm]||"#6b7684"}` }),
    el("span", { class:"firm", text:it.firm }),
    el("span", { class:"dday " + dd.c, text:dd.t }),
  ]);
  const t = el("div", { class:"t" }, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]);
  return el("div", { class:"today-item" }, [row1, t]);
}
function renderToday(genStamp) {
  const today = (genStamp || "").slice(0, 10);
  const items = JOBS.filter((it) => it.status !== "closed" && it.posted_date && it.posted_date === today);
  $("today-count").textContent = String(items.length);
  $("today-empty").hidden = items.length > 0;
  $("today-list").replaceChildren(...items.slice(0, 12).map(todayItem));
}

function countBy(key) { const m={}; for (const it of JOBS) m[it[key]]=(m[it[key]]||0)+1; return m; }

// 필터를 사이트 톤과 통일된 칩 버튼으로 렌더(복수선택=checkbox형, 단일선택=radio형 모두 지원).
// 선택 상태는 .on 클래스로 직접 관리(getOn으로 동기화) — 체크박스 제거로 이질감 해소.
function buildOpts(rowId, values, type, getOn, onToggle, counts) {
  const chips = values.map((v) => {
    const label = Array.isArray(v) ? v[0] : v, val = Array.isArray(v) ? v[1] : v;
    const cnt = counts ? el("span", { class:"cnt", text: String(counts[label] || 0) }) : null;
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
  const c = data.counts || {};
  $("jobs-summary").textContent = `진행중 ${c.open||0} · 신규 ${c.new||0} · 마감 ${c.closed||0}`;
  const firmC = c.by_firm || countBy("firm"), fieldC = countBy("field");

  buildOpts("f-firm", FIRM_ORDER, "checkbox", (v)=>JS.firm.has(v),
    (v)=>{ JS.firm.has(v)?JS.firm.delete(v):JS.firm.add(v); renderJobs(); }, firmC);
  buildOpts("f-field", FIELD_ORDER, "checkbox", (v)=>JS.field.has(v),
    (v)=>{ JS.field.has(v)?JS.field.delete(v):JS.field.add(v); renderJobs(); }, fieldC);
  buildOpts("f-status", [["진행중","open"],["마감","closed"],["전체","all"]], "radio",
    (v)=>JS.status===v, (v)=>{ JS.status=v; renderJobs(); });

  if (!_controlsBound) { bindControls(data); _controlsBound = true; }
  renderJobs();
  renderToday(data.generated_at);
}

function bindControls(data) {
  $("kw").addEventListener("input", (e)=>{ JS.kw=e.target.value; renderJobs(); });
  $("sort").addEventListener("change", (e)=>{ JS.sort=e.target.value; renderJobs(); });
  const bindToggle = (id, key) => {
    const b = $(id);
    b.addEventListener("click", () => { JS[key] = !JS[key]; b.classList.toggle("on", JS[key]); renderJobs(); });
  };
  bindToggle("f-new", "onlyNew");
  bindToggle("f-soon", "onlySoon");
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
  $("reset").addEventListener("click", ()=>{
    JS.firm.clear(); JS.field.clear(); JS.status="open"; JS.onlyNew=false; JS.onlySoon=false; JS.kw=""; JS.sort="reco";
    $("kw").value=""; $("sort").value="reco";
    $("f-new").classList.remove("on"); $("f-soon").classList.remove("on");
    initJobs(data);   // 칩 재생성(상태 반영) — 컨트롤은 이미 바인딩되어 건너뜀
  });
}

// ===================== 기사/인사이트 =====================
function newsCard(it) {
  const catColor = NEWS_CAT_COLOR[it.category];
  const top = el("div", { class:"card-top" }, [
    it.category ? el("span", { class:"tag cat", style:`background:${catColor||"#667085"}`, text: it.category }) : null,
    el("span", { class:"tag", text: it.source_label || it.source || "" }),
  ]);
  const title = el("h3", {}, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]);
  const kids = [top, title];
  if (it.summary) kids.push(el("div", { class:"company", text:it.summary }));
  if (it.published) kids.push(el("div", { class:"card-meta" }, [el("span", { text:it.published })]));
  return el("article", { class:"card" }, kids);
}

function initSub(prefix, data, chipRowId, chipKey, fixed) {
  const items = (data && data.items) || [];
  if (!items.length) { $(prefix+"-empty").hidden = false; return; }
  let selected = null;  // 단일선택: null=전체, 같은 칩 다시 누르면 해제
  const values = fixed || [...new Set(items.map((i)=>i[chipKey]).filter(Boolean))];
  const chips = [];
  const render = () => {
    const list = selected ? items.filter((i)=>i[chipKey]===selected) : items;
    $(prefix+"-list").replaceChildren(...list.map(newsCard));
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

  const [jobs, news, insights] = await Promise.all([
    loadJSON("data/jobs.json"), loadJSON("data/news.json"), loadJSON("data/insights.json"),
  ]);
  const stamp = (jobs && jobs.generated_at) || "";
  $("updated").textContent = stamp ? "최근 업데이트: " + stamp.replace("T", " ") : "데이터 없음";

  if (jobs) initJobs(jobs);
  else { $("jobs-empty").hidden = false; $("jobs-empty").textContent = "채용 데이터를 불러오지 못했습니다."; }
  initSub("news", news, "f-newscat", "category", null);
  initSub("insights", insights, "f-pub", "source_label", null);
})();

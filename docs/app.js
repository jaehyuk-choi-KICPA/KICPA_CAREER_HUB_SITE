"use strict";

const FIRM_ORDER = ["삼일", "삼정", "안진", "한영", "로컬", "기타"];
const FIRM_COLOR = { 삼일:"#d9692a", 삼정:"#1a6fb5", 안진:"#2e8b57", 한영:"#b59312", 로컬:"#6b7684", 기타:"#8a94a6" };
const FIRM_FULL = { 삼일:"삼일PwC", 삼정:"삼정KPMG", 안진:"Deloitte안진", 한영:"EY한영", 로컬:"로컬", 기타:"기타" };  // 인사이트와 동일 풀네임
const FIRM_EN = { 삼일:"PwC", 삼정:"KPMG", 안진:"Deloitte", 한영:"EY", 로컬:"로컬", 기타:"기타" };  // 채용 카드용(모바일 공간 절약)
const QUAL_ORDER = ["수습CPA", "자격무관"];                 // 자격요건 필터(구 직무 대체)
const EMPKIND_ORDER = ["인턴", "정규직", "계약직", "파트타임"];   // 채용구분 필터
const NEWS_CAT_ORDER = ["채용·시험", "감사", "세무", "딜·M&A"];  // 기사 카테고리 필터 순서(감사·세무(택스)·딜 일관)

// 빅4 신입 공채 특집: 상태 표시(접수중/업로드 예정/마감/미정)
const BIG4_STATUS = { open:["접수중","open"], upcoming:["업로드 예정","upcoming"], closed:["마감","closed"], unknown:["일정 미정","unknown"] };

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
// '새로 올라온 공고' 방문 표시 — 사용자가 누른 공고만 흐리게(브라우저별 기억). 정렬은 최신순이라 날짜 흐림은 불필요.
function isVisitedJob(url){ return _seenGet("visited_jobs").includes(url); }
function markVisitedJob(url){ const s = _seenGet("visited_jobs"); if (!s.includes(url)) { s.push(url); _seenSet("visited_jobs", s); } }

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

// ---- 채용알림(웹 푸시) 구독 — scope: "all"(전체·인턴 포함) | "susup"(수습CPA 전용) ----
const VAPID_PUBLIC = "BP7FISRizBQtx8OHcwaspl-KTupAl_R82zTL7o0PqzhqrGj6-bxqY3X-92rNYhVXySuntQaO6fxIOVtDFHYA1Yg";  // config.notifications.vapid_public과 동일값
const WORKER_URL = "https://hbmons-push.trackingsite.workers.dev";   // 구독 저장 Worker
function urlB64ToUint8(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}
// ── 인앱 브라우저(카톡·네이버앱·인스타 등) 감지 — 서비스워커/푸시가 막혀 알림이 안 됨 ──
function inAppBrowserName() {
  const ua = navigator.userAgent || "";
  if (/KAKAOTALK/i.test(ua)) return "카카오톡";
  if (/KAKAOSTORY/i.test(ua)) return "카카오스토리";
  if (/NAVER\(inapp/i.test(ua)) return "네이버 앱";
  if (/DaumApps/i.test(ua)) return "다음 앱";
  if (/Instagram/i.test(ua)) return "인스타그램";
  if (/FBAN|FBAV|FB_IAB/i.test(ua)) return "페이스북";
  if (/\bLine\//i.test(ua)) return "라인";
  if (/\bBAND\b/i.test(ua)) return "밴드";
  return "";
}
function isInAppBrowser() { return inAppBrowserName() !== ""; }

// 진입 시 1회: 인앱 브라우저면 상단에 안내 배너(닫기 가능) — 푸시·일부 기능이 막히니 외부 브라우저로 열라 안내.
function showInAppNotice() {
  const name = inAppBrowserName();
  if (!name) return;
  const close = el("button", { "aria-label":"닫기", text:"✕",
    style:"flex:0 0 auto;border:0;background:transparent;color:inherit;font-size:15px;cursor:pointer;line-height:1;padding:0 2px;" });
  const bar = el("div", { role:"note",
    style:"background:#fff7ed;color:#7c2d12;border-bottom:1px solid #fdba74;padding:9px 14px;font-size:13px;line-height:1.5;display:flex;gap:10px;align-items:flex-start;justify-content:center;" }, [
    el("div", { style:"flex:1 1 auto;" }, [
      el("div", { text:`📱 ${name} 인앱 브라우저는 새 공고 ‘알림(푸시)’을 지원하지 않아요.` }),
      el("div", { style:"margin-top:3px;" }, [
        el("span", { text:"우측 상단 메뉴(⋮ 또는 공유) → ‘다른 브라우저로 열기’ → " }),
        el("strong", { text:"삼성인터넷·사파리·크롬·엣지" }),
        el("span", { text:"에서 열어주세요." }),
      ]),
    ]),
    close,
  ]);
  close.addEventListener("click", () => bar.remove());
  document.body.insertBefore(bar, document.body.firstChild);
}

async function subscribePush(scope, msgEl) {
  const say = (t) => { if (msgEl) msgEl.textContent = t; };
  if (isInAppBrowser()) {
    if (msgEl) msgEl.innerHTML = `📱 ${inAppBrowserName()} 인앱 브라우저에서는 알림을 켤 수 없어요. 우측 상단 메뉴(⋮ 또는 공유) → ‘다른 브라우저로 열기’ → <strong>삼성인터넷·사파리·크롬·엣지</strong>에서 연 뒤 다시 켜주세요.`;
    return;
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    // iOS는 일반 Safari 탭에서 PushManager가 없음 — '홈 화면에 추가'(PWA) 후에만 가능.
    const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent);
    const isStandalone = window.navigator.standalone === true
      || window.matchMedia("(display-mode: standalone)").matches;
    if (isIOS && !isStandalone) {
      say("📱 아이폰은 사파리 화면 맨 아래 가운데 ‘공유’ 버튼(네모에 위 화살표 ⬆️) → ‘홈 화면에 추가’ → 추가된 아이콘으로 열기. 그 다음 알림을 켤 수 있어요.");
    } else {
      say("이 브라우저는 푸시 알림을 지원하지 않아요.");
    }
    return;
  }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { say("알림 권한이 거부되었어요. 브라우저 설정에서 허용해 주세요."); return; }
    const reg = await navigator.serviceWorker.register("/sw.js");
    // 기존 구독이 현재 VAPID 공개키와 다르면(키 재발급 등) 폐기 후 재구독 — 안 그러면 stale 키에 묶여 수신 불가.
    const wantKey = urlB64ToUint8(VAPID_PUBLIC);
    let sub = await reg.pushManager.getSubscription();
    if (sub) {
      const have = sub.options && sub.options.applicationServerKey
        ? new Uint8Array(sub.options.applicationServerKey) : null;
      const sameKey = have && have.length === wantKey.length && have.every((b, i) => b === wantKey[i]);
      if (!sameKey) { try { await sub.unsubscribe(); } catch (_) { /* 브라우저측 해제 실패는 무시 */ } sub = null; }
    }
    if (!sub) {
      sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: wantKey });
    }
    const body = Object.assign({}, sub.toJSON(), { scope });
    const r = await fetch(WORKER_URL.replace(/\/$/, "") + "/subscribe", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (r.ok) { localStorage.setItem("push_scope", scope);
      say(scope === "susup" ? "✅ 수습CPA 전용 새 공고 알림을 신청했어요!" : "✅ 전체 새 공고 알림을 신청했어요!"); }
    else { say("신청 처리에 실패했어요. 잠시 후 다시 시도해 주세요."); }
  } catch (e) {
    say("알림 신청 중 문제가 발생했어요" + (e && e.message ? ": " + e.message : "."));
  }
}
async function unsubscribePush(msgEl) {
  const say = (t) => { if (msgEl) msgEl.textContent = t; };
  try {
    const reg = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : null;
    const sub = reg && (await reg.pushManager.getSubscription());
    if (sub) {
      try {
        await fetch(WORKER_URL.replace(/\/$/, "") + "/unsubscribe", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
      } catch (_) { /* 저장소 정리 실패는 비치명적 — 브라우저 구독은 해제 */ }
      await sub.unsubscribe();
    }
    localStorage.removeItem("push_scope");
    say("🔕 새 공고 알림을 껐어요.");
  } catch (e) {
    say("알림 끄기 중 문제가 발생했어요" + (e && e.message ? ": " + e.message : "."));
  }
}

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
  // 로고(회법몬) 클릭 → 강한 새로고침(앱 코드까지 최신화).
  // 데이터만 다시 받던 기존 방식은 모바일 홈화면(PWA)에서 새 버전이 안 떴음(index.html·CSS·JS가 HTTP 캐시에 묶임).
  // 캐시 비우고 캐시버스트 쿼리(?r=)로 문서를 통째로 재요청 → 최신 index.html이 최신 ?v= 토큰의 CSS/JS를 끌어옴.
  const logo = document.querySelector(".brand h1");
  if (logo) logo.addEventListener("click", async () => {
    const upd = $("updated"); if (upd) upd.textContent = "새로고침 중…";
    try {
      if (window.caches) {   // 안전망(현재 SW는 캐시 안 하지만, 옛 SW 잔여 캐시까지 정리)
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      }
      const reg = navigator.serviceWorker && (await navigator.serviceWorker.getRegistration());
      if (reg) reg.update();
    } catch (_) { /* 무시하고 어쨌든 리로드 */ }
    const u = new URL(location.href);
    u.searchParams.set("r", String(Date.now()));   // 문서 HTTP 캐시 우회
    location.replace(u.href);
  });
}

// ===================== 채용 =====================
const JS = { firm:new Set(), qual:new Set(), empkind:new Set(), status:"open", onlyNew:false, kw:"", sort:"deadline" };
let JOBS = [];
let DATA_GEN = "";   // jobs.generated_at(수집 시각) — 카드 'NEW 초록테두리' 신선도(3일) 기준점
// 초록테두리 = 처음 수집(first_seen)된 지 3일 이내. 패널 '방금 올라온 공고'(24h, is_new)와 분리.
function isFresh3(it) {
  if (!it.first_seen) return false;
  const g = Date.parse(DATA_GEN) || Date.now();
  const f = Date.parse(it.first_seen);
  return isFinite(f) && (g - f) <= 3 * 86400 * 1000;
}

function ddayInfo(it) {
  if (it.status === "closed") return { t:"마감", c:"closed" };
  const d = it.dday;
  if (d === null || d === undefined) return { t:"상시", c:"" };
  if (d === 0) return { t:"D-0", c:"soon d0" };   // 당일마감 = D-0(유일하게 박스)
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

// 카드 전체를 클릭하면 링크로 이동(+살짝 눌림 애니메이션). 단 내부 인터랙티브 요소(링크·펼치기·버튼)는 자체 동작 유지.
function makeCardClickable(article, url) {
  if (!url) return article;
  article.classList.add("clickable");
  article.addEventListener("click", (e) => {
    if (e.target.closest("a, details, summary, button")) return;
    window.open(url, "_blank", "noopener");
  });
  return article;
}

function jobCard(it) {
  const dd = ddayInfo(it);
  // 좌상단: 법인 약칭 + 채용구분 + 자격구분 (구 직무 태그 대체)
  const left = el("div", { class:"top-left" }, [
    el("span", { class:"firm-tag", style:`color:${FIRM_COLOR[it.firm]||"#6b7684"}`, text:FIRM_EN[it.firm]||it.firm }),
    it.emp_kind ? el("span", { class:"tag", text:it.emp_kind }) : null,
    it.qualification ? el("span", { class:"tag", text:it.qualification }) : null,
  ]);
  const top = el("div", { class:"card-top" }, [left]);
  const title = el("h3", {}, [el("a", { href:it.url, target:"_blank", rel:"noopener", text:displayJobTitle(it) })]);
  // 아래행: MM-DD | 기관명 | D-day — 무조건 한 줄(기관명만 말줄임). 제목 위에 기관명 있어 제목의 선행 [회사]는 displayJobTitle이 제거.
  const md = (it.posted_date || it.first_seen || "").slice(5, 10);   // 게시일 없으면 발견일로 폴백 → mm-dd
  const meta = el("div", { class:"card-meta" }, [
    md ? el("span", { class:"m-date", text:md }) : null,
    md ? el("span", { class:"sep", text:"|" }) : null,
    el("span", { class:"org", text:it.company || "-" }),
    el("span", { class:"sep", text:"|" }),
    el("span", { class:"dday " + dd.c, text:dd.t }),   // .card-meta 스코프에서 진한 빨강·가늘게
  ]);
  // NEW(수집 3일 이내) = 카드 좌측 초록 테두리(.is-new)
  return makeCardClickable(el("article", { class:"card" + (it.status==="closed"?" closed":"") + (isFresh3(it)?" is-new":"") },
    [top, title, meta]), it.url);
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
    if (JS.qual.size && !JS.qual.has(it.qualification)) return false;
    if (JS.empkind.size && !JS.empkind.has(it.emp_kind)) return false;
    if (!matchStatus(it, JS.status)) return false;
    if (JS.onlyNew && !it.is_new) return false;
    if (kw && !((it.title + " " + (it.company||"")).toLowerCase().includes(kw))) return false;
    return true;
  });
  const openFirst = (a,b) => (a.status==="open"?0:1) - (b.status==="open"?0:1);
  // 최근 게시순 정렬키: 게시일(일단위) 우선, 없으면 발견일(first_seen 날짜)로 폴백 → 게시일 비공개 공고도 묻히지 않음
  const postedKey = (it) => it.posted_date || (it.first_seen||"").slice(0,10) || "";
  list.sort((a, b) => {
    if (JS.sort === "posted") {
      // 1차: 게시일 최신순 → 2차: 같은 날이면 발견시각(first_seen) 최신순 tiebreaker(일단위 동률 해소)
      return postedKey(b).localeCompare(postedKey(a))
        || (b.first_seen||"").localeCompare(a.first_seen||"");
    }
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
function clearQual(v)    { JS.qual.delete(v); syncChips("#f-qual"); renderJobs(); }
function clearEmpkind(v) { JS.empkind.delete(v); syncChips("#f-empkind"); renderJobs(); }
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
  JS.qual.forEach((v) => add(v, () => clearQual(v)));
  JS.empkind.forEach((v) => add(v, () => clearEmpkind(v)));
  if (STATUS_LABEL[JS.status]) add(STATUS_LABEL[JS.status], clearStatus);   // 기본(진행중)은 칩 미표시
  if (JS.kw.trim()) add('"' + JS.kw.trim() + '"', clearKw);
  box.replaceChildren(...chips);
}

function todayItem(it) {
  const dd = ddayInfo(it);
  const row1 = el("div", { class:"row1" }, [
    el("span", { class:"dot", style:`background:${FIRM_COLOR[it.firm]||"#6b7684"}` }),
    el("span", { class:"firm", text:FIRM_FULL[it.firm]||it.firm }),   // 풀네임, 글자색은 기본(점만 색)
    el("span", { class:"dday " + dd.c, text:dd.t }),
  ]);
  const a = el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title });
  // 정렬은 최신순(패널 제목 안내) — 날짜 흐림 대신 '내가 누른' 공고만 흐리게(.is-old). 클릭 시 즉시 반영.
  const wrap = el("div", { class:"today-item" + (isVisitedJob(it.url) ? " is-old" : "") },
    [row1, el("div", { class:"t" }, [a])]);
  a.addEventListener("click", () => { markVisitedJob(it.url); wrap.classList.add("is-old"); });
  return wrap;
}
function renderToday(genStamp) {
  // 최근 24시간 이내 새로 올라온(처음 수집된) 공고 — 백엔드 is_new(발견시각 24h) 기준으로 통일.
  const items = JOBS.filter((it) => it.status !== "closed" && it.is_new);
  // '올라온 순' = 발견시각(first_seen) 최신순 — 방금 잡힌 공고가 위로.
  items.sort((a, b) => (b.first_seen || b.posted_date || "").localeCompare(a.first_seen || a.posted_date || ""));
  $("today-count").textContent = String(items.length);
  $("today-count").hidden = items.length === 0;   // 0이면 초록 배지 숨김(빈 상태에 '0' 강조 안 함)
  $("today-empty").hidden = items.length > 0;
  $("today-list").replaceChildren(...items.slice(0, 12).map(todayItem));
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
  DATA_GEN = data.generated_at || "";

  renderFirmChips();   // 법인 칩 = 선택 상태 기준 동적 카운트
  buildOpts("f-qual", QUAL_ORDER, "checkbox", (v)=>JS.qual.has(v),
    (v)=>{ JS.qual.has(v)?JS.qual.delete(v):JS.qual.add(v); renderJobs(); });       // 자격요건
  buildOpts("f-empkind", EMPKIND_ORDER, "checkbox", (v)=>JS.empkind.has(v),
    (v)=>{ JS.empkind.has(v)?JS.empkind.delete(v):JS.empkind.add(v); renderJobs(); });  // 채용구분
  buildOpts("f-status", [["진행중","open"],["마감","closed"],["상설","standing"]], "radio",
    (v)=>JS.status===v, (v)=>{ JS.status=v; renderFirmChips(); renderJobs(); });   // 상태 바뀌면 법인 카운트 갱신

  if (!_controlsBound) { bindControls(data); _controlsBound = true; }
  renderJobs();
  renderToday(data.generated_at);
}

function bindControls(data) {
  $("kw").addEventListener("input", (e)=>{ JS.kw=e.target.value; renderJobs(); });
  $("sort").addEventListener("change", (e)=>{ JS.sort=e.target.value; renderJobs(); });
  const aBtn = $("alert-add"), aNote = $("alert-note");   // 채용알림(웹 푸시) — 검색 박스에 녹임
  if (aBtn && aNote) {
    const reflect = () => {   // 패널 열 때 현재 구독 상태(scope) 반영
      const cur = localStorage.getItem("push_scope");
      aNote.querySelectorAll(".alert-opt").forEach((o) => o.classList.toggle("on", o.dataset.scope === cur));
      const m = $("alert-msg");
      if (m) m.textContent = cur ? (cur === "susup" ? "현재 ‘수습CPA 전용’ 알림 켜짐" : "현재 ‘전체’ 알림 켜짐") : "";
    };
    aBtn.addEventListener("click", () => {
      aNote.hidden = !aNote.hidden;
      aBtn.classList.toggle("on", !aNote.hidden);
      if (!aNote.hidden) reflect();
    });
    aNote.querySelectorAll(".alert-opt").forEach((opt) => {
      opt.addEventListener("click", () => {
        aNote.querySelectorAll(".alert-opt").forEach((o) => o.classList.toggle("on", o === opt));
        subscribePush(opt.dataset.scope, $("alert-msg"));
      });
    });
    const off = $("alert-off");
    if (off) off.addEventListener("click", async () => {
      await unsubscribePush($("alert-msg"));
      aNote.querySelectorAll(".alert-opt").forEach((o) => o.classList.remove("on"));
    });
  }
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
  return makeCardClickable(el("article", { class:"card" }, kids), it.url);
}

// 인사이트: 법인별 4박스(삼일·삼정·안진·한영). 박스마다 하루 단위 고정 추천 1편 + 펼치기(최신순) 전체 목록.
const INSIGHT_FIRM = { "삼일PwC":"삼일", "삼정KPMG":"삼정", "Deloitte안진":"안진", "EY한영":"한영" };
const INSIGHT_ORDER = ["삼일PwC", "삼정KPMG", "Deloitte안진", "EY한영"];

// 하루 단위 고정 추천 — 같은 날엔 같은 글, 자정(로컬) 지나면 갱신. seed에 법인 label을 섞어 박스마다 다르게.
function _dailyKey() {
  const d = new Date();
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}
function _dailyIndex(seed, n) {
  let h = 2166136261;                                   // FNV-1a 류 결정론 해시
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
  return Math.abs(h) % n;
}

function firmBox(label, list) {
  const color = FIRM_COLOR[INSIGHT_FIRM[label]] || "#667085";
  const head = el("div", { class:"firm-head" }, [
    el("span", { class:"firm-name", style:`color:${color}`, text:label }),
    el("span", { class:"firm-cap", text:"· 오늘의 추천" }),
  ]);
  // 전체 테두리를 법인색 연하게(모던) — 좌측 단색 테두리(채용 NEW)와 양식이 달라 혼동 없음
  const box = el("article", { class:"insight-firm", style:`border-color:${color}59` }, [head]);
  if (!list.length) {
    box.appendChild(el("div", { class:"firm-empty", text:"불러올 간행물이 아직 없어요." }));
    return box;
  }
  const pick = list[_dailyIndex(_dailyKey() + "|" + label, list.length)];   // 하루 단위 고정(자정 지나면 갱신·법인별 상이)
  box.appendChild(el("div", { class:"firm-pick" },
    [el("a", { href:pick.url, target:"_blank", rel:"noopener", text:pick.title })]));
  const lis = list.map((it) => el("li", {},
    [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]));
  box.appendChild(el("details", { class:"firm-more" }, [
    el("summary", { class:"firm-toggle", text:`펼치기 (최신순) · ${list.length}편` }),
    el("ul", { class:"firm-list" }, lis),
  ]));
  return box;
}

function renderInsights(insights) {
  const items = (insights && insights.items) || [];
  const grid = $("insights-grid");
  if (!grid) return;
  if (!items.length) { $("insights-empty").hidden = false; grid.replaceChildren(); return; }
  $("insights-empty").hidden = true;
  const byFirm = {};
  items.forEach((it) => { (byFirm[it.source_label] = byFirm[it.source_label] || []).push(it); });
  grid.replaceChildren(...INSIGHT_ORDER.map((label) => firmBox(label, byFirm[label] || [])));
}

// '전체' 보기 편중 완화: 최신순을 대체로 유지하되 같은 카테고리가 maxRun 넘게 연속되지 않게 살짝 섞음.
// (감사/세무는 dedup으로 적게 보이고 딜은 개별 건이라 많아 상단이 딜로 도배되는 현상 완화)
function spreadCategories(items, maxRun) {
  const out = [], pool = items.slice();
  let lastCat = null, run = 0;
  while (pool.length) {
    let idx = 0;
    if (run >= maxRun) { const alt = pool.findIndex((x) => x.category !== lastCat); if (alt !== -1) idx = alt; }
    const picked = pool.splice(idx, 1)[0];
    if (picked.category === lastCat) run++; else { lastCat = picked.category; run = 1; }
    out.push(picked);
  }
  return out;
}

function initSub(prefix, data, chipRowId, chipKey, fixed, cardFn, colors) {
  const renderCard = cardFn || newsCard;
  const items = (data && data.items) || [];
  if (!items.length) { $(prefix+"-empty").hidden = false; return; }
  let selected = null;  // 단일선택: null=전체
  const values = fixed || [...new Set(items.map((i)=>i[chipKey]).filter(Boolean))];
  const chips = [];
  const render = () => {
    const list = selected ? items.filter((i)=>i[chipKey]===selected)
                          : (chipKey === "category" ? spreadCategories(items, 2) : items);
    $(prefix+"-list").replaceChildren(...list.map(renderCard));
    $(prefix+"-empty").hidden = list.length > 0;
    chips.forEach((c)=> c.classList.toggle("on", c.dataset.v === (selected || "")));   // '전체'=빈 값
  };
  const mkChip = (label, val) => {
    const chip = el("button", { type:"button", class:"chip", text:label });
    chip.dataset.v = val;
    chip.addEventListener("click", () => { selected = val || null; render(); });
    return chip;
  };
  if (chipKey === "category") chips.push(mkChip("전체", ""));   // 세그먼트 첫 탭(잡코리아 스타일)
  values.forEach((v) => chips.push(mkChip(v, v)));
  $(chipRowId).replaceChildren(...chips);
  render();
}

// ===================== 글자수·맞춤법 도구 =====================
// 순수 클라이언트 유틸 — 입력 텍스트는 저장·전송하지 않는다(무수집 원칙).
function countBytes(s) {            // 한글 등 멀티바이트=2, ASCII=1 (사라민식 자소서 바이트)
  let n = 0;
  for (const ch of s) n += ch.charCodeAt(0) > 127 ? 2 : 1;
  return n;
}
function renderTools() {
  const text = $("tool-text").value;
  const noSpace = text.replace(/\s/g, "");
  $("st-chars").textContent = text.length.toLocaleString();
  $("st-chars-ns").textContent = noSpace.length.toLocaleString();
  $("st-bytes").textContent = countBytes(text).toLocaleString();
}
function initTools() {
  const ta = $("tool-text");
  if (!ta) return;
  ta.addEventListener("input", renderTools);
  renderTools();
}

// ===================== 빅4 신입 공채 특집 =====================
function big4Dday(end) {            // 'YYYY-MM-DD' → 잔여일(없으면 null)
  if (!end) return null;
  const t = Date.parse(end + "T23:59:59");
  if (!isFinite(t)) return null;
  return Math.ceil((t - Date.now()) / 86400000);
}
function big4DdayText(f, end) {     // 마감/D-day 텍스트(본문톤 빨간 글씨용)
  const dd = big4Dday(end);
  if (f.status === "closed") return "마감";
  if (dd === null) return "";
  return dd < 0 ? "마감" : "D-" + dd;
}
// 지원기간 한 줄: [트랙명] MM-DD ~ MM-DD ........ D-day(빨간 글씨)
function big4TrackLine(f, tr) {
  const md = (s) => (s || "").slice(5, 10);   // YYYY-MM-DD → MM-DD
  const range = tr.start ? `${md(tr.start)} ~ ${md(tr.end)}` : (tr.end ? `~ ${md(tr.end)} 마감` : "");
  const ddText = big4DdayText(f, tr.end);
  return el("div", { class:"big4-track" }, [
    tr.name ? el("span", { class:"big4-tname", text:tr.name }) : null,
    el("span", { class:"big4-trange", text:range }),
    ddText ? el("span", { class:"big4-dday", text:ddText }) : null,
  ]);
}
function big4Row(f) {
  const [statLabel, statClass] = BIG4_STATUS[f.status] || ["", ""];
  const tracks = f.tracks || [];
  const body = tracks.length
    ? tracks.map((tr) => big4TrackLine(f, tr))
    : [el("div", { class:"big4-track big4-tba", text:"일정 미정 · 추후 공개" })];
  const fc = FIRM_COLOR[f.firm] || "#6b7684";
  const row = el("article", { class:"big4-row" + (f.status === "closed" ? " is-closed" : ""),
    style:`--firm:${fc}` }, [
    el("div", { class:"big4-top" }, [
      el("span", { class:"big4-firm", text:f.label || FIRM_FULL[f.firm] || f.firm }),
      el("span", { class:"big4-badge " + statClass, text:statLabel }),
    ]),
    el("h4", { class:"big4-jtitle" }, [el("a", { href:f.url, target:"_blank", rel:"noopener", text:f.title })]),
    el("div", { class:"big4-tracks" }, body),
  ]);
  return makeCardClickable(row, f.url);
}
function renderBig4(data) {
  const firms = (data && data.firms) || [];
  const tabBtn = document.querySelector('.today-tab[data-view="big4"]');
  if (!firms.length) {                       // 데이터 없으면 특집 탭 비활성
    if (tabBtn) tabBtn.disabled = true;
    $("big4-empty").hidden = false;
    return;
  }
  if (data.title) $("big4-title-text").textContent = data.title;
  $("big4-empty").hidden = true;
  $("big4-list").replaceChildren(...firms.map(big4Row));
}
function initTodayTabs() {
  const tabs = document.querySelectorAll(".today-tab");
  tabs.forEach((btn) => btn.addEventListener("click", () => {
    if (btn.disabled) return;
    tabs.forEach((b) => { const on = b === btn; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    const v = btn.dataset.view;
    $("view-today").hidden = v !== "today";
    $("view-big4").hidden = v !== "big4";
  }));
}

// 기사/인사이트 통합 탭 내부 책갈피 토글(기사 ↔ 인사이트)
function initNewsTabs() {
  const tabs = document.querySelectorAll(".subtab");
  tabs.forEach((btn) => btn.addEventListener("click", () => {
    tabs.forEach((b) => { const on = b === btn; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    const v = btn.dataset.subview;
    $("subview-news").hidden = v !== "news";
    $("subview-insights").hidden = v !== "insights";
  }));
}

// ===================== 부트 =====================
(async function () {
  // 서비스워커 최신화: 방문할 때마다 sw.js 업데이트 체크 강제 → 새 sw.js(알림 동작 변경 등)가 빨리 반영.
  // (기존엔 구독 시에만 등록돼 옛 sw.js가 끈질기게 남았음. skipWaiting+claim과 함께 즉시 교체.)
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistration()
      .then(function (reg) { if (reg) reg.update(); })
      .catch(function () {});
  }
  showInAppNotice();   // 카톡 등 인앱 브라우저 진입 시 상단 안내 배너
  initTabs();
  const tt = $("theme-toggle");
  if (tt) tt.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    localStorage.setItem("theme", next); applyTheme(next);
  });
  // 로딩 스켈레톤
  $("jobs-list").replaceChildren(...skel(6));
  $("news-list").replaceChildren(...skel(4));
  $("insights-grid").replaceChildren(...skel(4));

  const [jobs, news, insights, status, big4] = await Promise.all([
    loadJSON("data/jobs.json"), loadJSON("data/news.json"), loadJSON("data/insights.json"),
    loadJSON("data/status.json"), loadJSON("data/big4_recruit.json"),
  ]);
  // 헤더 시각 = 점검 시각(last_run): 변화 없어도 자동화가 돌면 전진. 없으면 jobs 생성시각 폴백.
  const stamp = (status && status.last_run) || (jobs && jobs.generated_at) || "";
  $("updated").textContent = stamp ? "최근 서치: " + stamp.replace("T", " ") : "데이터 없음";

  // 당일 발행 기사 표시(_today) — 기사 신규 점/금일수에 사용. (인사이트는 v1.09에서 '금일' 개념 제거.)
  const newsToday = ((news && news.generated_at) || "").slice(0, 10);
  if (news && news.items) news.items.forEach((i) => { i._today = !!i.published && i.published === newsToday; });

  // 기사 신규 점: 현재 '오늘 발행' url 집합 → seen 정리(현재분만 보관) + 탭 점 초기화
  if (news && news.items) {
    NEWS_TODAY_URLS = news.items.filter((i) => i._today && i.url).map((i) => i.url);
    _seenSet("seen_news", _seenGet("seen_news").filter((u) => NEWS_TODAY_URLS.includes(u)));
    updateNewsTabDot();
  }

  // PC 전용 미니 박스: 금일 기사 수 + 클릭 시 기사 탭 이동
  const newsN = (news && news.items) ? news.items.filter((i) => i._today).length : 0;
  const miniNews = $("mini-news");
  if (miniNews) {
    $("mini-news-n").textContent = String(newsN);
    miniNews.addEventListener("click", () => document.querySelector('.tab-btn[data-tab="news"]')?.click());
  }

  if (jobs) initJobs(jobs);
  else { $("jobs-empty").hidden = false; $("jobs-empty").textContent = "채용 데이터를 불러오지 못했습니다."; }
  initSub("news", news, "f-newscat", "category", NEWS_CAT_ORDER);   // 색 없이 중립 밑줄 탭
  renderInsights(insights);
  initTools();          // 글자수·맞춤법 도구
  initTodayTabs();      // 책갈피 토글(방금 올라온 공고 ↔ 빅4 공채)
  initNewsTabs();       // 책갈피 토글(기사 ↔ 인사이트)
  renderBig4(big4);     // 빅4 신입 공채 특집(수동 큐레이션)
})();

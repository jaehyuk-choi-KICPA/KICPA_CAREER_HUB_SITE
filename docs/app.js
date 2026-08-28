"use strict";

const FIRM_ORDER = ["삼일", "삼정", "안진", "한영", "로컬", "기타"];
const FIRM_COLOR = { 삼일:"#d9692a", 삼정:"#1a6fb5", 안진:"#2e8b57", 한영:"#b59312", 로컬:"#6b7684", 기타:"#8a94a6" };
const FIRM_FULL = { 삼일:"삼일PwC", 삼정:"삼정KPMG", 안진:"Deloitte안진", 한영:"EY한영", 로컬:"로컬", 기타:"기타" };  // 인사이트와 동일 풀네임
const FIRM_EN = { 삼일:"PwC", 삼정:"KPMG", 안진:"Deloitte", 한영:"EY", 로컬:"로컬", 기타:"기타" };  // 채용 카드용(모바일 공간 절약)
const QUAL_ORDER = ["수습CPA", "자격무관"];                 // 자격요건 필터(구 직무 대체)
const EMPKIND_ORDER = ["인턴", "정규직", "계약직", "파트타임"];   // 채용구분 필터
// 카드 태그 표시 약칭(필터·데이터·분류는 풀네임 그대로) — 모바일 2열 카드 첫 줄 줄바꿈 방지
const EMPKIND_SHORT = { 정규직:"정규", 계약직:"계약", 파트타임:"파트", 인턴:"인턴" };
const NEWS_CAT_ORDER = ["채용·시험", "감사", "세무"];  // 기사 카테고리 필터 순서
// 딜·M&A는 2026-08-22 폐지 — 부동산·해외 소형딜 노이즈가 심하고 다른 카테고리를 시각적으로 묻어버렸다.

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

// 강한 새로고침: (옛 SW 잔여) 캐시 비우고 ?r= 캐시버스트로 문서를 통째로 재요청 → 코드(index.html·CSS·JS)까지 최신.
// 로고 클릭(수동)으로만 호출 — 자동 새로고침은 작성 중인 글(글자수 탭)이 날아갈 수 있어 두지 않는다.
async function hardReload() {
  const upd = $("updated"); if (upd) upd.textContent = "새로고침 중…";
  try {
    if (window.caches) { const ks = await caches.keys(); await Promise.all(ks.map((k) => caches.delete(k))); }
    const reg = navigator.serviceWorker && (await navigator.serviceWorker.getRegistration());
    if (reg) reg.update();
  } catch (_) { /* 무시하고 어쨌든 리로드 */ }
  const u = new URL(location.href);
  u.searchParams.set("r", String(Date.now()));
  location.replace(u.href);
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

// ---- 채용알림(웹 푸시) 구독 — scope: "all"(전체·인턴 포함) | "susup"(수습CPA 전용) | "big4intern"(빅4 인턴만) ----
const SCOPE_LABEL = { all: "전체", susup: "수습CPA 전용", big4intern: "빅4 인턴만" };
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
      say(`✅ ‘${SCOPE_LABEL[scope] || "전체"}’ 새 공고 알림을 신청했어요!`); }
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

const NEWS_CAT_COLOR = { "채용·시험":"#1b4f9c", "감사":"#7a4fb0", "세무":"#8a5a1b", "인사이트":"#c2410c" };

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
  // 로고(회법몬) 클릭 → 강한 새로고침(앱 코드까지 최신화). PWA 홈화면에서도 즉시 갱신.
  const logo = document.querySelector(".brand h1");
  if (logo) logo.addEventListener("click", () => hardReload());
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
function makeCardClickable(article, url, onOpen) {
  if (!url) return article;
  article.classList.add("clickable");
  article.addEventListener("click", (e) => {
    if (e.target.closest("a, details, summary, button")) return;
    if (onOpen) onOpen();          // 본문 클릭도 '읽음'으로 — 안 하면 읽은 기사에 점이 계속 남는다
    window.open(url, "_blank", "noopener");
  });
  return article;
}

function jobCard(it) {
  const dd = ddayInfo(it);
  // 좌상단: 법인 약칭 + 채용구분 + 자격구분 (구 직무 태그 대체)
  const left = el("div", { class:"top-left" }, [
    el("span", { class:"firm-tag", style:`color:${FIRM_COLOR[it.firm]||"#6b7684"}`, text:FIRM_EN[it.firm]||it.firm }),
    it.emp_kind ? el("span", { class:"tag", text:EMPKIND_SHORT[it.emp_kind]||it.emp_kind }) : null,
    it.qualification === "수습CPA" ? el("span", { class:"tag", text:"CPA" }) : null,   // 자격무관은 태그 생략(요건 없음=기본값), 수습CPA만 표시
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

function todayItem(it, showCompany) {
  const dd = ddayInfo(it);
  const row1 = el("div", { class:"row1" }, [
    el("span", { class:"dot", style:`background:${FIRM_COLOR[it.firm]||"#6b7684"}` }),
    // 풀네임, 글자색은 기본(점만 색). showCompany=회사명 우선(로컬 목록: 전부 '로컬'이라 법인명이 무의미)
    el("span", { class:"firm", text: showCompany ? (it.company || FIRM_FULL[it.firm] || it.firm) : (FIRM_FULL[it.firm] || it.firm) }),
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
      if (m) m.textContent = cur ? `현재 ‘${SCOPE_LABEL[cur] || "전체"}’ 알림 켜짐` : "";
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
  if (it.dupes && it.dupes.length >= 2) {   // 1건짜리 '묶음'은 노이즈 — 접을 이유가 없다
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
  return makeCardClickable(el("article", { class:"card" }, kids), it.url,
                           isNew ? () => dismissNews(it.url, dot) : null);
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
  box.appendChild(el("div", { class:"firm-pick" }, [
    el("a", { href:pick.url, target:"_blank", rel:"noopener", text:pick.title }),
    pick.summary ? el("div", { class:"firm-sum", text:pick.summary }) : null,
  ]));
  const lis = list.map((it) => el("li", {},
    [el("a", { href:it.url, target:"_blank", rel:"noopener", text:it.title })]));
  box.appendChild(el("details", { class:"firm-more" }, [
    el("summary", { class:"firm-toggle", text:`펼치기 · ${list.length}편` }),
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

// ── 업계(기사) 뷰 ────────────────────────────────────────────────────────
// 카테고리 칩과 기간 필터가 **한 상태를 공유**한다(NEWS.cat × NEWS.arch).
// 예전엔 '최근'은 initSub이, '전체 기간'은 별도 페이저가 각각 그렸는데, 후자가 칩 줄을 숨기고
// 아카이브 전량을 뿌려서 **감사를 보다 기간을 넓히면 필터가 풀리는** 문제가 있었다.
// 두 축은 직교해야 한다 — 카테고리는 '무엇을', 기간은 '어디까지'를 정할 뿐이다.
const NEWS = { data: null, arch: null, cat: null, pager: null };

function newsChips() {
  const row = $("f-newscat");
  if (!row) return;
  const mk = (label, val) => {
    const chip = el("button", { type:"button", text:label,
      class: "chip" + (val === (NEWS.cat || "") ? " on" : "") });   // '전체'=빈 값
    chip.addEventListener("click", () => { NEWS.cat = val || null; renderNews(); });
    return chip;
  };
  row.replaceChildren(mk("전체", ""), ...NEWS_CAT_ORDER.map((v) => mk(v, v)));
}

function renderNews() {
  const src = NEWS.arch || ((NEWS.data && NEWS.data.items) || []);
  const list = NEWS.cat
    ? src.filter((i) => i.category === NEWS.cat)
    : (NEWS.arch ? src : spreadCategories(src, 2));   // 섞기는 '최근·전체'에서만(아카이브는 시간순이 낫다)
  // '최근'은 수십 건이라 한 화면에 다 보이는 편이 낫고, 아카이브는 수천 건이라 페이저가 필요하다.
  NEWS.pager.set(list, NEWS.arch ? ARCH_PAGE : Infinity);
  newsChips();
}

function initNews(news) {
  NEWS.data = news;
  NEWS.pager = makePager("news-list", "news-empty", "news-more", newsCard);
  initRangeBar("range-news", "news",
    () => { NEWS.arch = null; renderNews(); },
    (items) => { NEWS.arch = items; renderNews(); });
  renderNews();
}

// ===================== 산업 스트림 · 누적 아카이브 =====================
// 산업 뷰는 업계 기사 뷰(renderNews)와 따로 둔다. 칩 개수·기업 축이라는 전제가 달라서,
// 한 함수로 합치면 잘 돌던 기사 화면이 회귀한다. 페이저(makePager)만 공유한다.

const ARCH = { index: null, shards: new Map() };   // 아카이브는 '전체 기간'을 누를 때만 받아온다
const ARCH_PAGE = 40;                              // 한 번에 그리는 카드 수(월 샤드는 최대 2,700건)

async function archIndex() {
  if (!ARCH.index) ARCH.index = (await loadJSON("data/archive/index.json")) || { streams:{} };
  return ARCH.index;
}
async function archShard(stream, month) {
  const key = stream + ":" + month;
  if (!ARCH.shards.has(key)) {
    const d = await loadJSON("data/archive/" + stream + "/" + month + ".json");
    ARCH.shards.set(key, (d && d.items) || []);
  }
  return ARCH.shards.get(key);
}

function mkChip2(label, count, on, onClick, cls) {
  const b = el("button", { type:"button", class:(cls || "chip2") + (on ? " on" : "") }, [
    document.createTextNode(label),
    count == null ? null : el("span", { class:"cnt", text:String(count) }),
  ]);
  b.addEventListener("click", onClick);
  return b;
}

// 목록 + '더보기' 페이저. 아카이브 월 샤드는 수천 건이라 한 번에 그리면 모바일이 멈춘다.
function makePager(listId, emptyId, moreId, cardFn) {
  const st = { items: [], shown: ARCH_PAGE, page: ARCH_PAGE };
  const draw = () => {
    const slice = st.items.slice(0, st.shown);
    // 2건 이하면 2열 그리드의 반쪽만 차서 '실패한 화면'처럼 보인다 → 1열 전폭으로
    $(listId).classList.toggle("cards-1", st.items.length <= 2);
    $(listId).replaceChildren(...slice.map(cardFn));
    $(emptyId).hidden = st.items.length > 0;
    const more = $(moreId);
    more.replaceChildren();
    if (st.items.length > slice.length) {
      const b = el("button", { type:"button", class:"arch-more",
        text:"더보기 (남은 " + (st.items.length - slice.length).toLocaleString() + "건)" });
      b.addEventListener("click", () => { st.shown += st.page; draw(); });
      more.appendChild(b);
    }
  };
  // page=Infinity면 '더보기' 없이 전량(수십 건짜리 '최근' 화면용)
  return { set(items, page) { st.page = page || ARCH_PAGE; st.items = items; st.shown = st.page; draw(); } };
}

// 아카이브 전 구간을 한 번에. 월 칩을 두면 상단 필터가 한 층 더 쌓이는데,
// 사용자가 '몇 월'을 고르고 싶은 경우는 드물고 '지난 것까지 다 보기'면 충분하다.
async function archAll(stream) {
  const idx = await archIndex();
  const months = ((idx.streams || {})[stream] || {}).months || [];
  const all = [];
  for (const m of months) all.push(...await archShard(stream, m.m));
  all.sort((a, b) => (b.published_at || b.published || "").localeCompare(a.published_at || a.published || ""));
  return all;
}

// 기간 필터: [최근][전체 기간] 둘뿐. 기본 '최근'은 이미 받아둔 JSON이라 네트워크 0.
function initRangeBar(barId, stream, onRecent, onAll) {
  const bar = $(barId);
  if (!bar) return;
  let mode = "recent";
  const draw = () => {
    const bR = el("button", { type:"button", class:"range-btn" + (mode === "recent" ? " on" : ""), text:"최근" });
    const bA = el("button", { type:"button", class:"range-btn" + (mode === "all" ? " on" : ""), text:"전체 기간" });
    bR.addEventListener("click", () => { if (mode === "recent") return; mode = "recent"; draw(); onRecent(); });
    bA.addEventListener("click", async () => {
      if (mode === "all") return;
      bA.textContent = "불러오는 중…";           // 전 구간은 수 MB라 체감이 있다
      const items = await archAll(stream);
      bA.textContent = "전체 기간";
      if (!items.length) return;                 // 아카이브가 아직 없으면 '최근' 유지
      mode = "all"; draw(); onAll(items);
    });
    bar.replaceChildren(bR, bA);
  };
  draw();
}

// ── 산업 뷰 ──────────────────────────────────────────────────────────────
const IND = { data:null, arch:null, cat:null, co:null, pager:null, comp:null };

// 감사인 배지 — 이 화면에서 가장 쓸모 있는 한 줄(누가 이 회사를 감사하는가). 자료 없으면 null.
function companyAuditor(name) {
  const c = IND.comp && IND.comp.companies && IND.comp.companies[name];
  return (c && c.auditor) ? el("span", { class:"comp-aud", text:c.auditor }) : null;
}
function companyOpinion(name) {
  const c = IND.comp && IND.comp.companies && IND.comp.companies[name];
  return (c && c.opinion) ? el("span", { class:"aud-op", text:c.opinion }) : null;
}

// 기업 요약 — **감사 정보**. 재무 수치는 일부러 담지 않는다(화면이 무거워지고, DART 링크로 보는 편이 낫다).
// 감사 지원자에게 실제로 값진 건 핵심감사사항이다 — 그 회사 감사인이 무엇을 위험으로 봤는지가 그대로 적혀 있다.
function companyBrief(name) {
  const c = IND.comp && IND.comp.companies && IND.comp.companies[name];
  if (!c) return [];
  const out = [];
  if (c.kam && c.kam.length) {
    out.push(el("div", { class:"kam" }, [
      el("div", { class:"kam-h", text:"핵심감사사항 · " + (c.fy || "") }),
      el("ul", { class:"kam-list" }, c.kam.map((k) => el("li", { text:k }))),
    ]));
  }
  if (c.emphasis) out.push(el("div", { class:"aud-emph", text:"강조사항 · " + c.emphasis }));
  const bits = [];
  if (c.hours) bits.push(el("span", { text:"감사시간 " + c.hours + "시간" }));
  if (c.report_url) bits.push(el("a", { class:"aud-link", href:c.report_url, target:"_blank",
                                        rel:"noopener", text:"사업보고서 원문" }));
  if (bits.length) out.push(el("div", { class:"aud-meta" }, bits));
  return out;
}

function industryCard(it) {
  const card = newsCard(it);   // 카드 골격은 기사와 동일(카테고리 색이 없어 중립 회색 태그로 나온다)
  const cos = it.companies || [];
  if (cos.length) {
    card.appendChild(el("div", { class:"co-row" }, cos.map((c) =>
      mkCoChip(c, () => { IND.co = c; renderIndustry(); window.scrollTo({ top:0 }); }))));
  }
  return card;
}
function mkCoChip(name, onClick) {
  const b = el("button", { type:"button", class:"co-chip", text:name });
  b.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
  return b;
}

function renderIndustry() {
  const base = IND.arch || ((IND.data && IND.data.items) || []);

  // 산업 칩 — 기사가 있는 산업만(빈 그룹 숨김). 순서는 industry.json의 categories를 따른다(프론트 하드코딩 회피).
  const counts = {};
  base.forEach((i) => { counts[i.category] = (counts[i.category] || 0) + 1; });
  const cats = (IND.data && IND.data.categories) || Object.keys(counts);
  if (IND.cat && !counts[IND.cat]) IND.cat = null;      // 이 월엔 없는 산업이면 선택 해제
  const catChips = [mkChip2("전체", base.length, !IND.cat,
    () => { IND.cat = null; IND.co = null; renderIndustry(); })];
  cats.forEach((c) => {
    if (counts[c]) catChips.push(mkChip2(c, counts[c], IND.cat === c,
      () => { IND.cat = (IND.cat === c ? null : c); IND.co = null; renderIndustry(); }));
  });
  $("f-indcat").replaceChildren(...catChips);

  const inCat = IND.cat ? base.filter((i) => i.category === IND.cat) : base;

  // 기업 칩 — 사전 전체가 아니라 **실제 기사가 있는 기업만**(renderLocalRecruit의 빈 그룹 숨김과 같은 원칙)
  const cc = {};
  inCat.forEach((i) => (i.companies || []).forEach((c) => { cc[c] = (cc[c] || 0) + 1; }));
  const names = Object.keys(cc).sort((a, b) => cc[b] - cc[a] || a.localeCompare(b, "ko"));
  if (IND.co && !cc[IND.co]) IND.co = null;
  // 기업 칩은 **접어서** 낸다(기본 닫힘). 산업 칩(둥근 알약) 바로 아래 같은 모양이 한 줄 더 깔리면
  // 두 축이 구분되지 않으므로, 기업은 카드 안 기업 태그와 같은 **사각 태그**로 통일했다.
  // 접혀 있어 소음이 없으니 산업을 고르기 전(전체 보기)에도 띄운다 — 기업부터 찾는 사람도 있다.
  // 칩이 1개뿐이면 '좁혀보기'가 무의미하다(빈 서랍). 라벨도 실제 의미에 맞춘다 —
  // 이 칩들은 '이 산업의 기업'이 아니라 '이 기사들에 등장한 기업'이다.
  const panel = $("co-panel"), row = $("f-indco");
  if (names.length >= 2 || IND.co) {
    panel.hidden = false;
    panel.querySelector(".co-n").textContent = " " + names.length;
    if (IND.co) panel.open = true;               // 기업이 선택된 상태면 접혀 있으면 안 된다
    row.replaceChildren(...names.map((n) => mkChip2(n, null, IND.co === n,
      () => { IND.co = (IND.co === n ? null : n); renderIndustry(); }, "chip-co")));
  } else { panel.hidden = true; row.replaceChildren(); }

  // 기업 헤더 — 산업 → 기업 → **DART 재무제표**로 넘어가는 칸
  const head = $("comp-head");
  if (IND.co) {
    const tpl = (IND.data && IND.data.dart_url) || "https://dart.fss.or.kr/dsab007/main.do?textCrpNm={q}";
    head.hidden = false;
    // ⚠️ replaceChildren는 el()과 달리 null을 걸러내지 않고 문자열 "null"로 바꿔 넣는다.
    // 감사 정보가 없는 기업에서 "nullnull"이 찍히던 원인 → 반드시 filter(Boolean).
    head.replaceChildren(...[
      el("span", { class:"comp-name", text:IND.co }),
      el("span", { class:"comp-n", text:"기사 " + cc[IND.co] + "건" }),
      companyAuditor(IND.co)
        || el("span", { class:"comp-aud comp-aud--none", text:"감사 정보 미수집" }),
      companyOpinion(IND.co),
      el("a", { class:"dart-btn", href:tpl.replace("{q}", encodeURIComponent(IND.co)),
                target:"_blank", rel:"noopener",
                text:companyAuditor(IND.co) ? "📄 DART 전자공시 →" : "📄 DART에서 감사보고서 찾기 →" }),
      ...companyBrief(IND.co),
    ].filter(Boolean));
  } else { head.hidden = true; head.replaceChildren(); }

  IND.pager.set(IND.co ? inCat.filter((i) => (i.companies || []).includes(IND.co)) : inCat);
  // 0건일 때 '없습니다'로 끝내면 막다른 길이다 — 아카이브로 넘어갈 길을 준다
  const empty = $("industry-empty");
  if (!empty.hidden && !IND.arch) {
    const go = el("button", { type:"button", class:"empty-cta", text:"전체 기간에서 찾아보기 →" });
    go.addEventListener("click", () => document.querySelectorAll("#range-industry .range-btn")[1]?.click());
    empty.replaceChildren(document.createTextNode("최근 기사가 없습니다. "), go);
  } else if (!empty.hidden) {
    empty.textContent = "이 기간에 해당하는 기사가 없습니다.";
  }
}

function initIndustry(data, companies) {
  IND.data = data;
  IND.comp = companies;
  IND.pager = makePager("industry-list", "industry-empty", "industry-more", industryCard);
  if (!data || !(data.items || []).length) {
    // 아직 수집 전(첫 배포 등)에도 화면이 깨지지 않게 — 책갈피는 살리고 안내만
    $("industry-list").replaceChildren();
    $("industry-empty").hidden = false;
    $("industry-empty").textContent = "산업 기사를 곧 모아 보여드릴게요.";
    return;
  }
  initRangeBar("range-industry", "industry",
    () => { IND.arch = null; renderIndustry(); },
    (items) => { IND.arch = items; renderIndustry(); });
  renderIndustry();
}

// ===================== 글자수·맞춤법 도구 =====================
// 순수 클라이언트 유틸 — 입력 텍스트는 저장·전송하지 않는다(무수집 원칙).
let byteWeight = 2;                 // 한글 등 멀티바이트 1자당 byte(2=사람인식 / 3=삼정·UTF-8). 회사별 자소서 기준 전환용.
function countBytes(s, w) {         // 멀티바이트(charCodeAt>127)=w, ASCII=1
  let n = 0;
  for (const ch of s) n += ch.charCodeAt(0) > 127 ? w : 1;
  return n;
}
function renderTools() {
  const text = $("tool-text").value;
  const noSpace = text.replace(/\s/g, "");
  $("st-chars").textContent = text.length.toLocaleString();
  $("st-chars-ns").textContent = noSpace.length.toLocaleString();
  $("st-bytes").textContent = countBytes(text, byteWeight).toLocaleString();
  const lbl = $("st-bytes-label");
  if (lbl) lbl.textContent = `한글 ${byteWeight} · 영문 1`;
}
function initTools() {
  const ta = $("tool-text");
  if (!ta) return;
  ta.addEventListener("input", renderTools);
  document.querySelectorAll(".byte-opt").forEach((opt) => {   // 2byte↔3byte 전환
    opt.addEventListener("click", () => {
      document.querySelectorAll(".byte-opt").forEach((o) => o.classList.toggle("on", o === opt));
      byteWeight = +opt.dataset.bytes || 2;
      renderTools();
    });
  });
  renderTools();
}

// ===================== 빅4 신입 공채 특집 =====================
function big4Dday(end) {            // 'YYYY-MM-DD' → 잔여일(없으면 null)
  // 본문 채용카드와 동일하게 '날짜 차이'로 계산(자정 기준) — 마감 당일 D-0, 다음날부터 마감.
  // (과거 end 23:59:59 − 현재시각 ceil 방식은 마감 당일에 D-1로 표시되는 오차가 있었음.)
  if (!end) return null;
  const t = Date.parse(end + "T00:00:00");
  if (!isFinite(t)) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return Math.round((t - today.getTime()) / 86400000);
}
function big4DdayText(f, end) {     // 마감/D-day 텍스트(본문톤 빨간 글씨용)
  const dd = big4Dday(end);
  if (f.status === "closed") return "마감";
  if (dd === null) return "";
  return dd < 0 ? "마감" : "D-" + dd;
}
// 트랙 마감 여부: end가 지났으면 마감(법인 status와 별개로 트랙 단위 판정)
function big4TrackClosed(f, tr) {
  if (f.status === "closed") return true;
  const dd = big4Dday(tr.end);
  return dd !== null && dd < 0;
}
// 지원기간 한 줄: [트랙명] MM-DD ~ MM-DD ........ D-day(빨간 글씨). 마감 트랙은 취소선+회색.
function big4TrackLine(f, tr) {
  const md = (s) => (s || "").slice(5, 10);   // YYYY-MM-DD → MM-DD
  const endTxt = tr.end_label || md(tr.end);  // 마감 시각 병기 등 표시용 오버라이드(D-day 계산은 end 그대로)
  const range = tr.start ? `${md(tr.start)} ~ ${endTxt}` : (tr.end ? `~ ${endTxt} 마감` : "");
  const ddText = big4DdayText(f, tr.end);
  const closed = big4TrackClosed(f, tr);
  const kids = [
    tr.name ? el("span", { class:"big4-tname", text:tr.name }) : null,
    el("span", { class:"big4-trange", text:range }),
    ddText ? el("span", { class:"big4-dday", text:ddText }) : null,
  ];
  const cls = "big4-track" + (closed ? " is-closed" : "");
  // 트랙별 공고 url 있으면 그 줄을 개별 링크로(감사/비감사 '나눠서' 진입). 없으면 박스 전체 링크 사용.
  return tr.url
    ? el("a", { class:cls + " big4-track-link", href:tr.url, target:"_blank", rel:"noopener" }, kids)
    : el("div", { class:cls }, kids);
}
function big4Row(f) {
  const tracks = f.tracks || [];
  // 모든 트랙이 마감이면 법인 status가 open이어도 마감 취급(배지 '마감' + 박스 회색) — 수동 갱신 지연 보호
  const allClosed = tracks.length > 0 && tracks.every((tr) => big4TrackClosed(f, tr));
  const status = (f.status === "open" && allClosed) ? "closed" : f.status;
  const [statLabel, statClass] = BIG4_STATUS[status] || ["", ""];
  const body = tracks.length
    ? tracks.map((tr) => big4TrackLine(f, tr))
    : [el("div", { class:"big4-track big4-tba", text:"일정 미정 · 추후 공개" })];
  const fc = FIRM_COLOR[f.firm] || "#6b7684";
  const row = el("article", { class:"big4-row" + (status !== "open" ? " is-dim" : ""),   // 진행중 아니면 회색(불 꺼진 느낌)
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
  if (!firms.length) {                       // 데이터 없으면 빅4 섹션만 숨김(탭 활성 여부는 부트에서 로컬과 합산 판단)
    $("sec-big4").hidden = true;
    return false;
  }
  // 섹션 제목은 정적 라벨("빅4 신입 회계사 공채") 고정 — JSON title(연도 포함)로 덮지 않음
  // 딱지 이원화: 접수중 법인 있으면 초록 '접수중', 전 법인 마감이면 회색 '접수 마감'(시즌 재개 시 자동 복귀)
  const anyOpen = firms.some((f) => f.status === "open");
  const badge = $("sec-big4-badge");
  badge.hidden = false;
  badge.textContent = anyOpen ? "접수중" : "접수 마감";
  badge.classList.toggle("closed", !anyOpen);
  $("big4-list").replaceChildren(...firms.map(big4Row));
  return true;
}

// ── 로컬 신규공채(2026 신규공채 탭 하단): jobs.json 자동 필터 — 로컬 × 수습CPA × 미마감
const LOCAL_CAP = 5;   // 기본 노출 수(초과분은 '펼치기'로)
const LOCAL_LISTS = { full: [], part: [] };   // 하위탭(풀/파트) 전환용 캐시
function localListBox(items) {
  if (!items.length) return [el("div", { class:"local-gempty", text:"지금 모집 중인 공고가 없어요." })];
  const out = [el("div", { class:"today-list" }, items.slice(0, LOCAL_CAP).map((it) => todayItem(it, true)))];
  if (items.length > LOCAL_CAP) {
    const more = el("details", { class:"local-more" }, [
      el("summary", { class:"local-more-toggle", text:"더보기" }),
      el("div", { class:"today-list" }, items.slice(LOCAL_CAP).map((it) => todayItem(it, true))),
    ]);
    const closer = el("div", { class:"local-more-close", text:"접기" });   // 펼친 목록 맨 아래에서 다시 접기
    closer.addEventListener("click", () => { more.open = false; });
    more.appendChild(closer);
    out.push(more);
  }
  return out;
}
function renderLocalGroup(which) {
  $("local-groups").replaceChildren(...localListBox(LOCAL_LISTS[which] || []));
}
function initLocalSubtabs() {
  const tabs = document.querySelectorAll(".local-subtab");
  tabs.forEach((btn) => btn.addEventListener("click", () => {
    tabs.forEach((b) => { const on = b === btn; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    renderLocalGroup(btn.dataset.group);
  }));
}
function renderLocalRecruit() {
  // 풀·파트 두 그룹만(인턴·계약직 로컬 공고는 메인 목록에서 접근 — 이 패널은 신규 수습공채 큐레이션)
  // 제목 '(마감)' 가드: 게시자가 제목만 고치고 마감일을 안 바꾸면 status가 open으로 남는 케이스
  // '회계사' 게이트: 수습 보드엔 총무·기장반 등 비회계사 공고도 올라옴(보드 특성상 수습CPA로 강제 분류)
  //  → 제목에 회계사/CPA가 있어야 통과. CPA는 AICPA·USCPA 부분문자열 오탐 방지(영문자 뒤 CPA 제외).
  const isCpaTitle = (t) => /회계사/.test(t) || /(^|[^A-Za-z])CPA/i.test(t);
  const pool = JOBS.filter((it) => it.firm === "로컬" && it.qualification === "수습CPA"
    && it.status !== "closed" && !/\(마감\)/.test(it.title || "") && isCpaTitle(it.title || ""));
  // 마감 임박순(상시=맨 뒤), 동순위는 게시일 최신순
  const dk = (it) => (it.dday === null || it.dday === undefined) ? 9999 : it.dday;
  pool.sort((a, b) => dk(a) - dk(b) || (b.posted_date || b.first_seen || "").localeCompare(a.posted_date || a.first_seen || ""));
  LOCAL_LISTS.full = pool.filter((it) => it.emp_kind === "정규직");
  LOCAL_LISTS.part = pool.filter((it) => it.emp_kind === "파트타임");
  $("local-n-full").textContent = LOCAL_LISTS.full.length ? String(LOCAL_LISTS.full.length) : "";
  $("local-n-part").textContent = LOCAL_LISTS.part.length ? String(LOCAL_LISTS.part.length) : "";
  renderLocalGroup(document.querySelector(".local-subtab.on")?.dataset.group || "full");
  const n = LOCAL_LISTS.full.length + LOCAL_LISTS.part.length;
  if (!n) $("sec-local").hidden = true;   // 둘 다 0건이면 섹션 자체 숨김(한쪽만 비면 하위탭 빈 문구)
  return n > 0;
}

function initTodayTabs() {
  const tabs = document.querySelectorAll(".today-tab");
  const views = document.querySelectorAll(".today-view");   // id 규약: view-<data-view>
  tabs.forEach((btn) => btn.addEventListener("click", () => {
    if (btn.disabled) return;
    tabs.forEach((b) => { const on = b === btn; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    views.forEach((v) => { v.hidden = v.id !== "view-" + btn.dataset.view; });
  }));
}

// 기사 탭 내부 책갈피 토글(업계 ↔ 산업 ↔ 리포트).
// 예전엔 두 서브뷰 id를 하드코딩해 세 번째를 추가하면 조용히 동작하지 않았다 →
// initTodayTabs와 같은 **id 규약(subview-<data-subview>) 순회**로 바꿔 확장에 열어 둔다.
// 셀렉터에 #tab-news 스코프를 붙인 이유: 다른 탭에 .subtab이 생겨도 서로 간섭하지 않게.
function initNewsTabs() {
  const tabs = document.querySelectorAll("#tab-news .subtab");
  const views = document.querySelectorAll("#tab-news .subview");
  const ranges = document.querySelectorAll("#tab-news .range-bar");
  tabs.forEach((btn) => btn.addEventListener("click", () => {
    tabs.forEach((b) => { const on = b === btn; b.classList.toggle("on", on); b.setAttribute("aria-selected", on ? "true" : "false"); });
    views.forEach((v) => { v.hidden = v.id !== "subview-" + btn.dataset.subview; });
    // 기간 필터는 책갈피 행에 함께 있으므로 보는 스트림 것만 남긴다(리포트는 아카이브 화면이 없어 둘 다 숨김)
    ranges.forEach((r) => { r.hidden = r.dataset.for !== btn.dataset.subview; });
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
  $("industry-list").replaceChildren(...skel(4));

  // 아카이브(archive/*)는 여기서 받지 않는다 — '전체 기간'을 누른 사람만 그 달치를 받아간다.
  const [jobs, news, insights, status, big4, industry, companies] = await Promise.all([
    loadJSON("data/jobs.json"), loadJSON("data/news.json"), loadJSON("data/insights.json"),
    loadJSON("data/status.json"), loadJSON("data/big4_recruit.json"), loadJSON("data/industry.json"),
    loadJSON("data/companies.json"),   // DART 키 없으면 파일이 없다 → null(기업 요약만 숨김)
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
  initNews(news);           // 업계 기사 — 카테고리 칩 × 기간 필터(최근 ↔ 전체 기간)
  initIndustry(industry, companies);   // 산업 뷰(산업 칩 → 기업 칩 → 감사인·재무 → DART)
  renderInsights(insights);
  initTools();          // 글자수·맞춤법 도구
  initTodayTabs();      // 책갈피 토글(방금 올라온 공고 ↔ 2026 신규공채)
  initNewsTabs();       // 책갈피 토글(기사 ↔ 인사이트)
  const hasBig4 = renderBig4(big4);                          // 빅4 공채(수동 큐레이션, 접이식 섹션)
  initLocalSubtabs();                                        // 풀 ↔ 파트 하위탭 토글
  const hasLocal = jobs ? renderLocalRecruit() : false;      // 로컬 신규공채(jobs.json 자동, initJobs 이후라 JOBS 준비됨)
  const recruitTab = document.querySelector('.today-tab[data-view="big4"]');
  if (recruitTab) recruitTab.disabled = !(hasBig4 || hasLocal);   // 둘 다 비면 탭 비활성
  if (!hasBig4 && !hasLocal) $("big4-empty").hidden = false;      // 뷰 전체 폴백 문구

  // NEW(24시간 내 새 공고)가 비어 있으면 신규공채를 기본 화면으로 — 빈 패널 대신 쓸모 있는 화면 먼저
  if (recruitTab && !recruitTab.disabled && !document.querySelector("#today-list .today-item")) recruitTab.click();

  const qs = new URLSearchParams(location.search);
  // 딥링크: ?view=big4 → 들어오자마자 '2026 신규공채' 화면으로(시즌 홍보용 단축 URL, id 하위호환 유지)
  if (qs.get("view") === "big4") {
    const b = document.querySelector('.today-tab[data-view="big4"]');
    if (b && !b.disabled) { b.click(); b.scrollIntoView({ block: "nearest" }); }
  }
  // 딥링크: ?sub=industry[&ind=반도체·전자][&co=삼성전자] → 기사 탭의 산업 책갈피로 바로
  const sub = qs.get("sub");
  if (sub === "industry" || sub === "insights" || sub === "news") {
    document.querySelector('.tab-btn[data-tab="news"]')?.click();
    document.querySelector('#tab-news .subtab[data-subview="' + sub + '"]')?.click();
    if (sub === "industry" && industry) {
      const ind = qs.get("ind"), co = qs.get("co");
      if (ind) IND.cat = ind;
      if (co) IND.co = co;
      if (ind || co) renderIndustry();
    }
  }
})();

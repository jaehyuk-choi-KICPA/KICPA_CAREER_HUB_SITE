/**
 * 회법몬 웹 푸시 구독 저장소 — Cloudflare Worker + KV.
 *
 * 정적 사이트(GitHub Pages)는 백엔드가 없어 푸시 구독(endpoint+keys)을 저장할 곳이 없다.
 * 이 Worker가 최소 백엔드: 구독 등록/해지(브라우저)·구독 목록 조회(GitHub Actions 전용)만 담당.
 * 발송 자체는 하지 않는다(발송은 src/notifier.py가 pywebpush로).
 *
 * 엔드포인트:
 *   POST /subscribe    — body=PushSubscription JSON → KV에 저장(멱등). 브라우저(CORS: 사이트 origin).
 *   POST /unsubscribe  — body={endpoint} → KV에서 삭제. 브라우저 또는 Actions(만료 정리).
 *   GET  /list         — Actions 전용. Authorization: Bearer <READ_TOKEN> → 전체 구독 반환.
 *
 * 보안: /list는 READ_TOKEN(시크릿) 필수. 쓰기는 Origin 체크(ALLOWED_ORIGIN) + 형식 검증.
 *   KV 키 = "sub:" + sha256(endpoint) — endpoint가 길고 URL-unsafe하므로 해시를 키로.
 *
 * 바인딩(wrangler.toml / secret):
 *   KV namespace: SUBS
 *   vars: ALLOWED_ORIGIN (예: https://hbmons.com)
 *   secret: READ_TOKEN (Actions의 SUBS_READ_TOKEN과 동일 값)
 */

async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function isAllowedOrigin(origin, env) {
  if (!origin) return true;   // 비브라우저(curl 등) — Origin 없음
  const list = (env.ALLOWED_ORIGIN || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (list.includes(origin)) return true;
  if (/^https?:\/\/localhost(:\d+)?$/.test(origin)) return true;     // 로컬 개발
  if (/^https?:\/\/127\.0\.0\.1(:\d+)?$/.test(origin)) return true;
  return false;
}

function corsHeaders(env, origin) {
  // 허용 출처면 그 출처를 echo(아니면 주 출처). credentials 미사용이라 echo로 충분.
  const primary = (env.ALLOWED_ORIGIN || "*").split(",")[0].trim();
  const allow = isAllowedOrigin(origin, env) && origin ? origin : primary;
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

function json(body, status, extra) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json", ...(extra || {}) },
  });
}

function validSubscription(s) {
  return (
    s && typeof s.endpoint === "string" && s.endpoint.startsWith("https://") &&
    s.endpoint.length < 1024 && s.keys && typeof s.keys.p256dh === "string" &&
    typeof s.keys.auth === "string"
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(env, origin);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    // ---- GET /list : Actions 전용(Bearer) ----
    if (url.pathname === "/list" && request.method === "GET") {
      const auth = request.headers.get("Authorization") || "";
      if (!env.READ_TOKEN || auth !== `Bearer ${env.READ_TOKEN}`) {
        return json({ error: "unauthorized" }, 401);
      }
      const out = [];
      let cursor;
      do {
        const page = await env.SUBS.list({ prefix: "sub:", cursor });
        for (const k of page.keys) {
          const v = await env.SUBS.get(k.name);
          if (v) {
            try { out.push(JSON.parse(v)); } catch (_) { /* skip */ }
          }
        }
        cursor = page.list_complete ? undefined : page.cursor;
      } while (cursor);
      return json({ count: out.length, subscriptions: out });
    }

    // ---- POST /subscribe ----
    if (url.pathname === "/subscribe" && request.method === "POST") {
      if (!isAllowedOrigin(origin, env)) {
        return json({ error: "forbidden origin" }, 403, cors);
      }
      let sub;
      try { sub = await request.json(); } catch (_) { return json({ error: "bad json" }, 400, cors); }
      if (!validSubscription(sub)) return json({ error: "invalid subscription" }, 400, cors);
      const key = "sub:" + (await sha256Hex(sub.endpoint));
      // 알림 범위: "susup"(수습CPA 전용) | "all"(전체·인턴 포함, 기본)
      const scope = sub.scope === "susup" ? "susup" : "all";
      const record = { endpoint: sub.endpoint, keys: sub.keys, scope, created: new Date().toISOString() };
      await env.SUBS.put(key, JSON.stringify(record));
      return json({ ok: true }, 201, cors);
    }

    // ---- POST /unsubscribe : 브라우저(자기 구독 해지) 또는 Actions(만료 정리) ----
    if (url.pathname === "/unsubscribe" && request.method === "POST") {
      let body;
      try { body = await request.json(); } catch (_) { return json({ error: "bad json" }, 400, cors); }
      if (!body || typeof body.endpoint !== "string") return json({ error: "no endpoint" }, 400, cors);
      const key = "sub:" + (await sha256Hex(body.endpoint));
      await env.SUBS.delete(key);
      return json({ ok: true }, 200, cors);
    }

    if (url.pathname === "/" || url.pathname === "/health") {
      return json({ service: "hbmons-push", ok: true });
    }
    return json({ error: "not found" }, 404, cors);
  },
};

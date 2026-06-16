// Cloudflare Worker — 정적 자산 서빙 + '금일 방문자수' 카운터(KV).
//
// 라우팅: 정적 파일은 Cloudflare가 먼저 서빙(assets), 매칭 안 되는 경로만 이 Worker가 처리.
//   /api/hit  → POST: 오늘(KST) 카운트 +1 / GET: 읽기만. 날짜 키라 매일 0부터 시작.
//   그 외      → 정적 자산으로 폴백(env.ASSETS).
//
// KV 바인딩(VISITS)이 없으면 count:null 반환 → 프론트가 카운터를 조용히 숨김(사이트 영향 0).
// 견고성: 모든 경로 try/catch — 카운터가 깨져도 페이지 서빙은 살린다.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/hit") return handleHit(request, env);
    return env.ASSETS.fetch(request);
  },
};

// 한국시간(KST=UTC+9) 기준 날짜 (서버는 UTC라 보정)
function kstDate() {
  return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}

async function handleHit(request, env) {
  const headers = { "content-type": "application/json", "cache-control": "no-store" };
  try {
    if (!env.VISITS) return new Response(JSON.stringify({ count: null }), { headers });
    const key = "v:" + kstDate();
    let count = parseInt((await env.VISITS.get(key)) || "0", 10);
    if (request.method === "POST") {
      count += 1;
      // 40일 후 자동 만료 → 저장소를 가볍게 유지(과거 일자 자동 정리)
      await env.VISITS.put(key, String(count), { expirationTtl: 60 * 60 * 24 * 40 });
    }
    return new Response(JSON.stringify({ count, date: kstDate() }), { headers });
  } catch (e) {
    return new Response(JSON.stringify({ count: null }), { headers });
  }
}

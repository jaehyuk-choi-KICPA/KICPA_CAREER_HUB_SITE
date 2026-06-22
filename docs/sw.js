/* 회법몬 서비스워커 — 푸시 알림 전용.
 *
 * ⚠️ fetch 가로채기·캐싱 절대 없음: 이 사이트는 데이터 신선도가 생명(채용/기사 JSON이 30분마다 갱신).
 *    SW가 fetch를 캐시하면 옛 JSON을 서빙해 화면이 굳는다 → push/notificationclick만 처리한다.
 */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (_) {
    data = { title: "회법몬", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "회법몬 — 새 채용공고";
  const options = {
    body: data.body || "",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    tag: data.tag || "hbmons-job",
    renotify: false,
    data: { url: data.url || "https://hbmons.com/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const raw = (event.notification.data && event.notification.data.url) || "https://hbmons.com/";
  const external = /^https?:\/\//i.test(raw) && raw.indexOf("hbmons.com") === -1;
  event.waitUntil(
    (async () => {
      // 외부 공고는 새 창(데스크톱=새 탭 / 모바일·iOS=오버레이)으로 연다 — 기존 회법몬 화면을 보존하고
      // (모바일은 닫으면 회법몬으로 복귀), iOS에서 메인뷰를 외부로 navigate하면 빈 화면 되던 문제도 방지.
      // (브라우저별로 신뢰성 없는 히스토리 조작 대신 '새 창'으로 단순·안정화.)
      if (external) {
        if (self.clients.openWindow) await self.clients.openWindow(raw);
        return;
      }
      // 내부 URL(회법몬 홈 등): 기존 탭 있으면 포커스·이동, 없으면 새로.
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of all) {
        if (client.url.includes("hbmons.com") && "focus" in client) {
          await client.focus();
          if ("navigate" in client) { try { await client.navigate(raw); } catch (_) { /* ignore */ } }
          return;
        }
      }
      if (self.clients.openWindow) await self.clients.openWindow(raw);
    })()
  );
});

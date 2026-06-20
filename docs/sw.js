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
  const target = (event.notification.data && event.notification.data.url) || "https://hbmons.com/";
  event.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of all) {
        if (client.url.includes("hbmons.com") && "focus" in client) {
          await client.focus();
          if ("navigate" in client) {
            try { await client.navigate(target); } catch (_) { /* ignore */ }
          }
          return;
        }
      }
      if (self.clients.openWindow) await self.clients.openWindow(target);
    })()
  );
});

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
  const isIOS = /iP(hone|ad|od)/.test(self.navigator && self.navigator.userAgent || "");
  const external = /^https?:\/\//i.test(raw) && raw.indexOf("hbmons.com") === -1;
  event.waitUntil(
    (async () => {
      // iOS(PWA): 메인뷰를 외부 공고로 navigate하면 닫을 때 '빈 화면'이 됨 → 외부 공고는 새 창(오버레이/사파리)로
      // 열어 PWA 홈은 그대로 둔다(닫으면 회법몬으로 복귀). ?goto 경유(히스토리 뒤로가기)는 iOS에 안 맞음.
      if (isIOS && external) {
        if (self.clients.openWindow) await self.clients.openWindow(raw);
        return;
      }
      // 데스크톱/안드: 공고를 홈(?goto) 경유로 열어 공고에서 '뒤로 가기' 시 회법몬 홈이 뜨게 한다.
      const target = external ? "https://hbmons.com/?goto=" + encodeURIComponent(raw) : raw;
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

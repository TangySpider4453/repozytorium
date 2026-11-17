// Service worker: tylko powiadomienia push (bez cache — dane zawsze świeże z Pi)
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data.json(); } catch (_) { d = { tytul: "Trener", tresc: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.tytul || "Trener", {
    body: d.tresc || "", icon: "/ikona-192.png", badge: "/ikona-192.png", data: { url: d.url || "/" } }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data.url || "/", self.location.origin).href;
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(l => {
    for (const c of l) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return clients.openWindow(url);
  }));
});

// Service worker: powiadomienia push + liczba na ikonie apki (bez cache: dane zawsze świeże z Pi)
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data.json(); } catch (_) { d = { tytul: "Dla Ciebie", tresc: e.data && e.data.text() }; }
  const n = d.plakietka || 1;
  e.waitUntil(Promise.all([
    self.registration.showNotification(d.tytul || "Dla Ciebie", {
      body: d.tresc || "", icon: "/static/ikona-192.png", badge: "/static/ikona-192.png", data: { url: d.url || "/#adwent" } }),
    self.navigator.setAppBadge ? self.navigator.setAppBadge(n).catch(() => {}) : null]));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data.url || "/#adwent", self.location.origin).href;
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(l => {
    for (const c of l) { if ("focus" in c) { c.navigate(url); return c.focus(); } }
    return clients.openWindow(url);
  }));
});

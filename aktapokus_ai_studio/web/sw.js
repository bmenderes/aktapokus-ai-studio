/* Aktapokus: yalnızca "uygulama olarak eklenebilir" olmak için. Önbellek YOK: belirteç ve özel veriler hiçbir yerde saklanmaz; her istek doğrudan ağa gider. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});

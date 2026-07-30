/* GSID service worker — offline shell + last-known intelligence.

   Strategy:
     app shell / static  → cache-first (fast launch, versioned)
     GET /api/*          → network-first, fall back to the last cached response
                           so a traveller with no signal still sees the most
                           recent brief, advisory and stories
     navigations         → network-first, fall back to the cached shell

   Bump CACHE_VERSION on every release, otherwise clients keep serving the old
   JS/CSS from cache after a deploy. */
const CACHE_VERSION = "gsid-v1";
const SHELL_CACHE = CACHE_VERSION + "-shell";
const DATA_CACHE = CACHE_VERSION + "-data";

const SHELL = [
  "/",
  "/static/css/styles.css",
  "/static/js/api.js",
  "/static/js/components.js",
  "/static/js/map.js",
  "/static/js/views.js",
  "/static/js/app.js",
  "/static/icons/icon-192.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      // addAll fails atomically if any single request 404s; tolerate that.
      .then((c) => Promise.allSettled(SHELL.map((u) => c.add(u))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => !k.startsWith(CACHE_VERSION)).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (e) => {
  if (e.data === "skipWaiting") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Never interfere with writes (refresh, quiz answers, preferences saves).
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // leave cross-origin alone

  // Data: fresh if possible, last-known if not.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(DATA_CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || offlineJson()))
    );
    return;
  }

  // Navigations: fall back to the cached app shell so deep links still open.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("/").then((hit) => hit || offlineJson()))
    );
    return;
  }

  // Code (JS/CSS/HTML) must never go stale behind a cache: serve from network
  // and fall back to cache only when offline. Relying on a human to bump
  // CACHE_VERSION every release is a footgun — a missed bump ships old code to
  // every installed client.
  if (/\.(?:js|css)$/.test(url.pathname)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(SHELL_CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Everything else (fonts, icons — effectively immutable): cache-first.
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res && res.ok && res.type === "basic") {
        const copy = res.clone();
        caches.open(SHELL_CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }))
  );
});

function offlineJson() {
  return new Response(
    JSON.stringify({ error: "offline", offline: true,
                     message: "You are offline — showing the last data this device loaded." }),
    { status: 503, headers: { "Content-Type": "application/json" } }
  );
}

/* Cache only app-owned files. This worker never falls through to an external
   emergency-time API: the PWA is useful only after its local install completes. */
const CACHE = "earthquakeprep-__BUNDLE_VERSION__";
const CORE = ["/", "/bundle/bundle.db", "/bundle/manifest.json", "/vendor/sql-wasm.wasm"];
// scripts/write-service-worker.mjs replaces this list in dist/ with all built
// client files. Production remains strictly cache-only at runtime.
const APP_SHELL = [];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll([...CORE, ...APP_SHELL]);
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", (event) => event.waitUntil((async () => {
  const keys = await caches.keys();
  await Promise.all(keys.filter((key) => key.startsWith("earthquakeprep-") && key !== CACHE).map((key) => caches.delete(key)));
  await self.clients.claim();
})()));
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const stored = await cache.match(url.pathname);
    if (!stored) return new Response("Offline asset not installed", { status: 503 });
    return stored;
  })());
});

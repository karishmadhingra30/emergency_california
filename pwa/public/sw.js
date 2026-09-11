/* Cache only app-owned files. This worker never falls through to an external
   emergency-time API: the PWA is useful only after its local install completes. */
const CACHE = "bay-ready-v1";
const CORE = ["/", "/bundle/bundle.db", "/bundle/manifest.json", "/vendor/sql-wasm.wasm"];
// scripts/write-service-worker.mjs replaces this list in dist/ with all built
// client files. Production remains strictly cache-only at runtime.
const APP_SHELL = [];
const MAP_PACK = "/bundle/bay-area.pmtiles";

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll([...CORE, ...APP_SHELL]);
    // Once a reviewed Bay Area pack is supplied, cache it as a local file.
    await cache.add(MAP_PACK).catch(() => undefined);
    await self.skipWaiting();
  })());
});
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const stored = await cache.match(url.pathname);
    if (!stored) return new Response("Offline asset not installed", { status: 503 });
    const range = event.request.headers.get("range");
    if (!range || url.pathname !== MAP_PACK) return stored;
    const bytes = await stored.arrayBuffer();
    const match = /bytes=(\d+)-(\d*)/.exec(range);
    if (!match) return stored;
    const start = Number(match[1]);
    const end = match[2] ? Number(match[2]) : bytes.byteLength - 1;
    return new Response(bytes.slice(start, end + 1), { status: 206, headers: { "Content-Range": `bytes ${start}-${end}/${bytes.byteLength}`, "Accept-Ranges": "bytes", "Content-Length": String(end - start + 1) } });
  })());
});

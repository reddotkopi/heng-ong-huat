// Heng Ong Huat offline cache. __VERSION__ changes with every build (new draw results),
// so an updated app replaces the old cache.
const CACHE = 'hoh-__VERSION__';
const FONTS = 'hoh-fonts-v1';
const SHELL = ['./', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png', './icons/apple-touch-icon.png', './icons/favicon-32.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith('hoh-') && k !== CACHE && k !== FONTS).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Pages: try the network first (fresh draw results), fall back to the cached copy after
// 4 seconds or when offline. latest.json (same-evening results): network first.
// Fonts: serve from cache, refresh in the background. Everything else from this site: cache first.
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const network = fetch(req).then((res) => { if (res.ok) cache.put('./', res.clone()); return res; });
      const timeout = new Promise((resolve) => setTimeout(resolve, 4000));
      try {
        const res = await Promise.race([network, timeout.then(() => cache.match('./'))]);
        return res || (await network);
      } catch {
        return (await cache.match('./')) || Response.error();
      }
    })());
    return;
  }
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    e.respondWith((async () => {
      const cache = await caches.open(FONTS);
      const hit = await cache.match(req);
      const refresh = fetch(req).then((res) => { if (res.ok || res.type === 'opaque') cache.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || refresh;
    })());
    return;
  }
  if (url.origin === self.location.origin && url.pathname.endsWith('/latest.json')) {
    e.respondWith(fetch(req).then((res) => { if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put('./latest.json', copy)); } return res; })
      .catch(() => caches.match('./latest.json').then((hit) => hit || Response.error())));
    return;
  }
  if (url.origin === self.location.origin) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});

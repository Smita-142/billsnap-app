const CACHE_NAME = 'bill-snap-shell-v3';
const APP_SHELL = [
  '/',
  '/offline.html',
  '/manifest.json',
  '/app-icon.svg',
  '/app-icon-192.png',
  '/app-icon-512.png',
  '/apple-touch-icon.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);
      const home = await fetch('/');
      if (!home.ok) throw new Error('Unable to precache the Bill Snap app shell');
      const markup = await home.clone().text();
      const assets = Array.from(markup.matchAll(/(?:src|href)="([^"]+)"/g), match => new URL(match[1], self.location.origin))
        .filter(asset => asset.origin === self.location.origin && asset.pathname.startsWith('/static/'))
        .map(asset => asset.href);
      await cache.put('/', home);
      await cache.addAll([...APP_SHELL.slice(1), ...assets]);
    })()
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put('/', copy));
          }
          return response;
        })
        .catch(async () => (await caches.match(request)) || (await caches.match('/')) || caches.match('/offline.html'))
    );
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          }
          return response;
        });
      })
    );
  }
});

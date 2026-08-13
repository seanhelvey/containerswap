// Service worker: keep the app usable on a bad connection.
//
// Static assets    -> cache first (they are versioned by CACHE name).
// Listing pages    -> network first, fall back to the copy we cached on last visit.
// Everything else  -> network, with an offline page as the last resort.

const CACHE = 'containerswap-v1';
const SHELL = [
  '/',
  '/offline',
  '/static/css/app.css',
  '/static/js/app.js',
  '/static/icons/icon.svg',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Never cache the inbox: it is private, per-user content.
  if (url.pathname.startsWith('/inbox')) return;

  const isAsset =
    url.pathname.startsWith('/static/') || url.pathname.startsWith('/uploads/');

  if (isAsset) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            const copy = response.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
            return response;
          })
      )
    );
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
        return response;
      })
      .catch(() =>
        caches.match(request).then((hit) => hit || caches.match('/offline'))
      )
  );
});

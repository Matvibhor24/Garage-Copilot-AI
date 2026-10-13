// App-shell service worker: the screens open instantly and survive patchy garage internet.
// Never caches the API, the voice socket or Firebase (Firestore has its own offline cache).
const CACHE = 'gc-shell-v1'
const SHELL = ['/', '/manifest.webmanifest', '/icon.svg', '/icon-192.png', '/mic-worklet.js']

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin) return
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) return

  // Pages: network first, fall back to the cached shell (all routes are the same SPA).
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request)
        .then((res) => { caches.open(CACHE).then((c) => c.put('/', res.clone())); return res })
        .catch(() => caches.match('/')),
    )
    return
  }
  // Hashed build assets never change: cache first.
  if (url.pathname.startsWith('/assets/') || SHELL.includes(url.pathname)) {
    e.respondWith(
      caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
        if (res.ok) caches.open(CACHE).then((c) => c.put(e.request, res.clone()))
        return res
      })),
    )
  }
})

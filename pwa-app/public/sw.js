// Simple SW for daily levels notifications + offline cache
const CACHE = 'levels-v1'
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(c => c.addAll(['/levels.json', '/'])))
  self.skipWaiting()
})
self.addEventListener('activate', event => { event.waitUntil(clients.claim()) })
self.addEventListener('fetch', event => {
  if (event.request.url.includes('/levels.json')) {
    event.respondWith(fetch(event.request).then(res => {
      const copy = res.clone()
      caches.open(CACHE).then(c => c.put(event.request, copy))
      return res
    }).catch(() => caches.match(event.request)))
  }
})
self.addEventListener('notificationclick', event => {
  event.notification.close()
  event.waitUntil(clients.matchAll({ type: 'window' }).then(cs => {
    const c = cs[0]
    return c ? c.focus() : clients.openWindow('/')
  }))
})
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'NEW_DAY') {
    self.registration.showNotification(`EURUSD levels for ${event.data.date}`, {
      body: `${event.data.n} levels ready. Tap to view.`,
      icon: '/icon-192.png',
      tag: `levels-${event.data.date}`,
    })
  }
})

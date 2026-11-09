/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

self.addEventListener('install', (e: ExtendableEvent) => {
  e.waitUntil(
    caches.open('levels-json').then((c) => c.add('/levels.json').catch(() => undefined))
  )
  self.skipWaiting()
})

self.addEventListener('activate', (e: ExtendableEvent) => {
  e.waitUntil(self.clients.claim())
})

// levels.json: network-first, fall back to cache
self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url)
  if (url.pathname === '/levels.json' && event.request.method === 'GET') {
    event.respondWith(
      fetch(event.request)
        .then(async (res) => {
          const copy = res.clone()
          const cache = await caches.open('levels-json')
          await cache.put(event.request, copy)
          return res
        })
        .catch(async () => {
          const cached = await caches.match(event.request)
          if (cached) return cached
          return new Response('offline', { status: 503 })
        })
    )
  }
})

self.addEventListener('notificationclick', (event: ExtendableEvent) => {
  const ne = event as unknown as { notification: Notification }
  ne.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((cs: readonly unknown[]) => {
      const c = cs[0] as WindowClient | undefined
      return c ? c.focus() : self.clients.openWindow('/')
    })
  )
})

self.addEventListener('message', (event: ExtendableMessageEvent) => {
  const d = (event.data as unknown) as { type?: string; date?: string; n?: number } | undefined
  if (d && d.type === 'NEW_DAY') {
    void self.registration.showNotification(`EURUSD levels for ${d.date ?? ''}`, {
      body: `${d.n ?? 0} levels ready. Tap to view.`,
      icon: '/icon-192.png',
      tag: `levels-${d.date ?? ''}`,
    })
  }
})

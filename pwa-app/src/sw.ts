/// <reference lib="webworker" />
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'

declare const self: ServiceWorkerGlobalScope

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

self.addEventListener('install', (e: ExtendableEvent) => {
  e.waitUntil(
    caches.open('levels-json').then((c) =>
      Promise.all([
        c.add('/levels.json').catch(() => undefined),
        c.add('/bias.json').catch(() => undefined),
      ]))
  )
  self.skipWaiting()
})

self.addEventListener('activate', (e: ExtendableEvent) => {
  e.waitUntil(self.clients.claim())
})

// levels.json + bias.json: network-first, fall back to cache
self.addEventListener('fetch', (event: FetchEvent) => {
  const url = new URL(event.request.url)
  const jsons = url.pathname === '/levels.json' || url.pathname === '/bias.json'
  if (jsons && event.request.method === 'GET') {
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
  const ne = event as unknown as { notification: Notification & { data?: { url?: string } } }
  ne.notification.close()
  const target = ne.notification.data?.url || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((cs: readonly unknown[]) => {
      const c = cs[0] as WindowClient | undefined
      return c ? c.focus() : self.clients.openWindow(target)
    })
  )
})

// Web Push from eurusd-push worker: { title, body, tag, url }
self.addEventListener('push', (event: PushEvent) => {
  let data: { title?: string; body?: string; tag?: string; url?: string } = {}
  try {
    data = (event.data?.json() as typeof data) || {}
  } catch {
    data = { body: event.data?.text() || '' }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'EURUSD news', {
      body: data.body || '',
      icon: '/icon-192.png',
      tag: data.tag || 'news',
      data: { url: data.url || '/' },
    })
  )
})

self.addEventListener('message', (event: ExtendableMessageEvent) => {
  const d = (event.data || {}) as { type?: string; date?: string; n?: number; bias?: string } | undefined
  if (d && d.type === 'NEW_DAY') {
    void self.registration.showNotification(`EURUSD levels for ${d.date ?? ''}`, {
      body: `${d.n ?? 0} levels ready, ATR updated.${d.bias ? ` Bias ${d.bias}.` : ''} Tap to view.`,
      icon: '/icon-192.png',
      tag: `levels-${d.date ?? ''}`,
    })
  }
})

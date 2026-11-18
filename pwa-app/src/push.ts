// Web Push subscription management against the eurusd-push Cloudflare Worker.

export const PUSH_API = (
  (import.meta.env.VITE_PUSH_API as string | undefined) ||
  'https://eurusd-push.dumyskhue84.workers.dev'
).replace(/\/+$/, '')

// VAPID application server public key (ES256 P-256). Pairs with the private
// key stored as the worker secret VAPID_PRIVATE_KEY.
const VAPID_PUBLIC_KEY =
  'BMc69gjBD_D_i8Dc44S4hDFLD9kEllfKnDesmLApm-D9XWWeI4Lfei_r63PEZ0U0RWx_2RA4x2BTQO3OTOcIauU'

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(b64)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export async function isSubscribed(): Promise<boolean> {
  if (!pushSupported()) return false
  try {
    const reg = await navigator.serviceWorker.getRegistration()
    const sub = await reg?.pushManager.getSubscription()
    return !!sub
  } catch {
    return false
  }
}

export type EnableResult = 'ok' | 'denied' | 'unsupported' | 'network'

export async function enablePush(): Promise<EnableResult> {
  if (!pushSupported()) return 'unsupported'
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') return 'denied'
  const reg = await navigator.serviceWorker.ready
  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    })
  }
  try {
    const res = await fetch(`${PUSH_API}/api/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription: sub.toJSON(), page: location.origin }),
    })
    if (!res.ok) {
      await sub.unsubscribe().catch(() => undefined)
      return 'network'
    }
    return 'ok'
  } catch {
    await sub.unsubscribe().catch(() => undefined)
    return 'network'
  }
}

export async function disablePush(): Promise<void> {
  if (!pushSupported()) return
  try {
    const reg = await navigator.serviceWorker.getRegistration()
    const sub = await reg?.pushManager.getSubscription()
    if (!sub) return
    const endpoint = sub.endpoint
    await fetch(`${PUSH_API}/api/unsubscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint }),
    }).catch(() => undefined)
    await sub.unsubscribe().catch(() => undefined)
  } catch {
    // best effort
  }
}

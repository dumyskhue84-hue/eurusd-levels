export async function requestPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) return 'denied'
  if (Notification.permission === 'granted') return 'granted'
  return Notification.requestPermission()
}

export async function notifyNewDay(date: string, n: number, bias?: string) {
  if (Notification.permission !== 'granted') return
  const reg = await navigator.serviceWorker.ready
  await reg.showNotification(`EURUSD levels for ${date}`, {
    body: `${n} levels ready, ATR updated.${bias ? ` Bias ${bias}.` : ''} Tap to view.`,
    icon: '/icon-192.png',
    tag: `levels-${date}`,
    silent: false,
  })
}

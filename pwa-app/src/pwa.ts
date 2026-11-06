// Auto-updating registration. VitePWA injects `virtual:pwa-register`.
// We keep this wrapper minimal so it type-checks with or without the
// virtual module present during local `tsc` runs in plain `tsc` mode.
async function register() {
  if (!('serviceWorker' in navigator)) return
  try {
    await navigator.serviceWorker.register('/sw.js')
  } catch (e) {
    console.error('SW registration failed:', e)
  }
}

export function initPWA() {
  void register()
}

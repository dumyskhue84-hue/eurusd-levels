import './style.css'
import type { LevelsFile } from './level-types'
import { requestPermission, notifyNewDay } from './notify'

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `
  <main>
    <header>
      <h1>EURUSD Daily Levels</h1>
      <p id="meta">Loading…</p>
      <button id="notify">Enable daily notifications</button>
    </header>
    <section id="cards"></section>
    <footer><small>UTC day boundary (forex). Levels only, no entries. Offline cached.</small></footer>
  </main>
`

async function load() {
  // request permission early so Android allows notifications
  if (Notification.permission === 'default') { /* only on user tap */ }
  const res = await fetch('/levels.json', { cache: 'no-cache' })
  if (!res.ok) throw new Error('levels.json not found')
  const data: LevelsFile = await res.json()
  document.querySelector('#meta')!.textContent =
    `${data.pair} · ${data.date} (UTC) · anchor ${data.anchor_close.toFixed(5)} · ATR ${data.atr_pips.toFixed(1)} pips · zone ±${data.zone_pips} pips · from ${data.generated_from}`

  const cards = document.querySelector('#cards')!
  const show = data.levels.filter((l) => l.primary || l.type !== 'ROUND').slice(0, 10)
  cards.innerHTML = show.map((l) => `
    <article class="card ${l.primary ? 'primary' : ''}">
      <div class="price">${l.price.toFixed(5)}</div>
      <div class="type">${l.type} · ${l.note}</div>
      <div class="zone">[${l.zone_low.toFixed(5)}, ${l.zone_high.toFixed(5)}] · ${l.approach_side.replace('_', ' ')}</div>
      <div class="respect">
        touches ${l.respect.touches} · reject ${l.respect.reject_rate ?? '—'} · break ${l.respect.break_rate ?? '—'}
      </div>
      <div class="expiry">expires ${l.expiry}</div>
    </article>
  `).join('')

  // daily notification: new date (new day starts 00:00 UTC)
  const lastDate = localStorage.getItem('levels-date')
  if (lastDate !== data.date) {
    localStorage.setItem('levels-date', data.date)
    if (Notification.permission === 'granted') {
      notifyNewDay(data.date, data.levels.length)
      // also nudge SW in case page is backgrounded
      if ('serviceWorker' in navigator) {
        const reg = await navigator.serviceWorker.ready
        reg.active?.postMessage({ type: 'NEW_DAY', date: data.date, n: data.levels.length })
      }
    }
  }
}

document.querySelector('#notify')!.addEventListener('click', async () => {
  const p = await requestPermission()
  const btn = document.querySelector('#notify') as HTMLButtonElement
  btn.textContent = p === 'granted' ? 'Notifications enabled' : 'Notifications blocked'
  btn.disabled = true
})

load().catch((e) => { document.querySelector('#meta')!.textContent = 'Could not load levels: ' + e.message })

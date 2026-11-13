import './style.css'
import type { LevelsFile, BiasFile } from './level-types'
import { requestPermission, notifyNewDay } from './notify'
import { initInstallButton } from './install'
import { initPWA } from './pwa'

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `
  <main>
    <header>
      <h1>EURUSD Daily Levels</h1>
      <p id="meta">Loading…</p>
      <div class="actions">
        <button id="notify">Enable daily notifications</button>
        <button id="install">Install app</button>
      </div>
      <div id="install-steps" style="margin-top:10px">
        <p><strong>Android Chrome:</strong> tap ⋮ menu → <em>Add to Home screen</em> or <em>Install app</em>.</p>
        <p><strong>Note:</strong> "Install app" prompt appears in Chrome after the page is interacted with at least once. If you don't see it, use the menu above.</p>
        <p><strong>iPhone Safari:</strong> Share → Add to Home Screen.</p>
      </div>
      <div id="stale" style="display:none;margin-top:10px;padding:10px;border:1px solid #b58900;border-radius:10px;background:#2a2300">
        <strong>Levels may be stale.</strong> <span id="stale-msg"></span>
      </div>
    </header>
    <section id="bias"></section>
    <section id="cards"></section>
    <footer><small>UTC day boundary (forex). Levels only, no entries. Offline cached.</small></footer>
  </main>
`

initPWA()
initInstallButton('install', 'install-steps')

const esc = (s: string) => s.replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

const ARROW: Record<string, string> = { bullish: '▲', bearish: '▼', neutral: '●' }

async function loadBias(): Promise<BiasFile | null> {
  try {
    const res = await fetch('/bias.json', { cache: 'no-cache' })
    if (!res.ok) return null
    const b: BiasFile = await res.json()
    return b.bias ? b : null // null bias = feed error or no lean -> hide card
  } catch {
    return null
  }
}

function renderBias(b: BiasFile) {
  if (!b.bias) return
  const el = document.querySelector('#bias')!
  const win = `${b.window.start}–${b.window.end} ${b.window.tz}`
  const target = b.target
    ? `expect move toward <strong>${b.target.price.toFixed(5)}</strong> ${esc(b.target.type)}` +
      ` · ${b.target.distance_pips} pips · approach ${b.target.approach_side.replace('_', ' ')}`
    : 'no target level in bias direction'
  const events = b.events.map((e) => {
    const dir = e.watch ? '○' : e.vote > 0 ? '↑' : '↓'
    const dirCls = e.watch ? 'watch' : e.vote > 0 ? 'up' : 'down'
    const nums = (e.forecast || e.previous)
      ? `<span class="nums">f ${esc(e.forecast) || '—'} · p ${esc(e.previous) || '—'}</span>`
      : ''
    return `<li class="ev${e.watch ? ' is-watch' : ''}">
      <span class="ev-time">${e.time}</span>
      <span class="imp ${e.impact.toLowerCase()}">${e.impact[0]}</span>
      <span class="ev-title">${e.country} · ${esc(e.title)}</span>
      <span class="ev-dir ${dirCls}">${dir}</span>
      ${nums}
    </li>`
  }).join('')
  el.innerHTML = `
    <article class="card bias ${b.bias}">
      <div class="bias-head">
        <span class="bias-badge">${ARROW[b.bias] ?? '●'} ${b.bias.toUpperCase()}</span>
        <span class="bias-conf">${Math.round((b.confidence ?? 0) * 100)}% conf</span>
      </div>
      <div class="bias-win">news window ${win} · score ${b.score}</div>
      <div class="bias-target">${target}</div>
      <ul class="bias-events">${events}</ul>
      <div class="bias-note">${esc(b.disclaimer)}</div>
    </article>`
}

async function load() {
  // request permission early so Android allows notifications
  if (Notification.permission === 'default') { /* only on user tap */ }
  const [res, bias] = await Promise.all([
    fetch('/levels.json', { cache: 'no-cache' }),
    loadBias(),
  ])
  if (!res.ok) throw new Error('levels.json not found')
  const data: LevelsFile = await res.json()
  document.querySelector('#meta')!.textContent =
    `${data.pair} · ${data.date} (UTC) · anchor ${data.anchor_close.toFixed(5)} · ATR ${data.atr_pips.toFixed(1)} pips · zone ±${data.zone_pips} pips · from ${data.generated_from}`

  // staleness banner: date must be today (UTC) or tomorrow (if generated after 00:00)
  const todayUTC = new Date().toISOString().slice(0, 10)
  const stale = document.getElementById('stale')
  const staleMsg = document.getElementById('stale-msg')
  if (data.date !== todayUTC) {
    stale!.style.display = 'block'
    staleMsg!.textContent = `Levels generated for ${data.date} (today ${todayUTC}). Pull to refresh may be pending — data pipeline may be delayed.`
  } else {
    stale!.style.display = 'none'
  }

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

  if (bias) renderBias(bias)

  // daily notification: new date (new day starts 00:00 UTC)
  const lastDate = localStorage.getItem('levels-date')
  if (lastDate !== data.date) {
    localStorage.setItem('levels-date', data.date)
    if (Notification.permission === 'granted') {
      const biasLabel = bias
        ? `${bias.bias}${bias.target ? ` → ${bias.target.price.toFixed(5)}` : ''}`
        : undefined
      notifyNewDay(data.date, data.levels.length, biasLabel)
      // also nudge SW in case page is backgrounded
      if ('serviceWorker' in navigator) {
        const reg = await navigator.serviceWorker.ready
        reg.active?.postMessage({ type: 'NEW_DAY', date: data.date, n: data.levels.length, bias: biasLabel })
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

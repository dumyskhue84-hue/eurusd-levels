import './style.css'
import type { LevelsFile, BiasFile, BiasEvent, ActualsFile, LiveBias } from './level-types'
import { notifyNewDay } from './notify'
import {
  PUSH_API, pushSupported, isSubscribed, enablePush, disablePush, syncPushTz,
} from './push'
import { initInstallButton } from './install'
import { initPWA } from './pwa'

const TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const clockFmt = new Intl.DateTimeFormat(undefined, {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const TZ_LABEL = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })
  .formatToParts(new Date()).find((p) => p.type === 'timeZoneName')?.value || 'local'

function localTime(hhmm: string | null | undefined, date: string): string {
  if (!hhmm) return '—'
  let iso = `${date}T${hhmm}:00Z`
  if (hhmm === '24:00') {
    const next = new Date(`${date}T00:00:00Z`)
    next.setUTCDate(next.getUTCDate() + 1)
    iso = next.toISOString().replace('.000Z', 'Z')
  }
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? hhmm : clockFmt.format(d)
}

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `
  <main>
    <header>
      <h1>EURUSD Daily Levels</h1>
      <p id="meta">Loading…</p>
      <div class="actions">
        <button id="notify">Enable news alerts</button>
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
    <footer><small>Times in ${TZ_LABEL} (${TIME_ZONE}). Forex day boundary 00:00 UTC. Levels only, no entries. Offline cached.</small></footer>
  </main>
`

initPWA()
initInstallButton('install', 'install-steps')

const esc = (s: string) => s.replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

const ARROW: Record<string, string> = { bullish: '▲', bearish: '▼', neutral: '●' }

function fmtRemaining(ms: number): string {
  if (ms <= 0) return 'window ended'
  const mins = Math.floor(ms / 60_000)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return h ? `in ${h}h ${m}m` : `in ${m}m`
}

const eventById = new Map<string, BiasEvent>()
let actualsTimer: ReturnType<typeof setInterval> | undefined
let validTimer: ReturnType<typeof setInterval> | undefined
let currentBias: BiasFile | null = null
let currentLive: LiveBias | null = null
let liveKey = ''

// Live release values from the push worker (TradingView-backed): paints
// "a 0.3%" into each event row once the news is out.
async function pollActuals(date: string): Promise<void> {
  try {
    const res = await fetch(`${PUSH_API}/api/actuals/${date}`, { cache: 'no-cache' })
    if (!res.ok) return
    const data: ActualsFile = await res.json()
    for (const [id, a] of Object.entries(data)) {
      const e = eventById.get(id)
      const nums = document.querySelector(`.ev[data-eid="${CSS.escape(id)}"] .nums`)
      if (!e || !nums) continue
      let act = nums.querySelector('.act') as HTMLSpanElement | null
      if (!act) {
        act = document.createElement('span')
        act.className = 'act'
        nums.append(document.createTextNode(' · '), act)
      }
      const val = a.actual == null || a.actual === '' ? '—' : String(a.actual)
      const d = a.dir ?? 0
      act.textContent = `a ${val}`
      act.className = `act ${d > 0 ? 'ok' : d < 0 ? 'bad' : 'flat'}`
      act.title = `released ${localTime(a.time, date)} ${TZ_LABEL}`
    }
  } catch {
    // offline or worker unreachable — retry on next tick
  }
}

function startActualsPolling(date: string): void {
  void pollActuals(date)
  if (actualsTimer) clearInterval(actualsTimer)
  actualsTimer = setInterval(() => void pollActuals(date), 60_000)
}

async function loadLiveBias(date: string): Promise<LiveBias | null> {
  try {
    const res = await fetch(`${PUSH_API}/api/live-bias/${date}`, { cache: 'no-cache' })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

function startLiveBiasPolling(date: string): void {
  const tick = async () => {
    const live = await loadLiveBias(date)
    const key = `${live?.state || ''}|${live?.generated_at || ''}`
    if (key === liveKey) return
    liveKey = key
    currentLive = live
    if (currentBias) {
      renderBias(currentBias, currentLive)
      void pollActuals(date)
    }
  }
  void tick()
  setInterval(() => void tick(), 60_000)
}

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

function renderBias(b: BiasFile, live: LiveBias | null = null) {
  if (!b.bias) return
  const liveState = live?.state && live.state !== 'neutral' ? live.state : null
  const display = liveState || b.bias
  const overridden = !!liveState && liveState !== b.bias
  const el = document.querySelector('#bias')!
  const win = `${localTime(b.window.start, b.date)}–${localTime(b.window.end, b.date)} ${TZ_LABEL}`
  const target = b.target
    ? `expect move toward <strong>${b.target.price.toFixed(5)}</strong> ${esc(b.target.type)}` +
      ` · ${b.target.distance_pips} pips · approach ${b.target.approach_side.replace('_', ' ')}`
    : 'no target level in bias direction'
  const windows = (b.windows ?? []).map((w) => {
    const arrow = w.direction === 'bearish' ? '▼' : '▲'
    const t = `${w.cause}${w.target_price != null ? ` → ${w.target_price.toFixed(5)} (${w.target_pips}p)` : ''}`
    return `<span class="win ${w.direction}" title="${esc(t)}">${arrow} ${localTime(w.start, b.date)}–${localTime(w.end, b.date)}</span>`
  }).join('')
  const winHtml = windows ? `<div class="bias-windows">${windows}</div>` : ''
  const validUntil = overridden && live?.until ? live.until
    : b.bias !== 'neutral' ? b.valid_until : null
  const utcNow = new Date().toISOString().slice(11, 16)
  const untilDate = validUntil && validUntil < utcNow
    ? new Date(Date.now() + 86_400_000).toISOString().slice(0, 10) : b.date
  const localUntil = localTime(validUntil, untilDate)
  const validHtml = validUntil
    ? `<span class="bias-valid" id="bias-valid" title="Directional window ends ${localUntil} ${TZ_LABEL}">until ${localUntil} ${TZ_LABEL}</span>`
    : ''
  const basisLabel = b.basis === 'calendar+news' ? 'calendar + news'
    : b.basis === 'news' ? 'headlines'
    : b.basis === 'calendar' ? 'calendar' : ''
  const basisHtml = basisLabel
    ? `<span class="bias-basis" title="What drove this bias">${basisLabel}</span>` : ''
  const topHead = b.news?.headlines?.[0]
  const newsHtml = topHead
    ? `<div class="bias-news" title="${esc((b.news?.headlines ?? []).map((h) => h.title).join(' | '))}"><span class="tone ${topHead.tone}">${topHead.tone}</span><span class="news-title">${esc(topHead.title)}</span></div>`
    : ''
  const liveHead = live?.news?.headlines?.[0]
  const liveHtml = overridden
    ? `<div class="bias-live-note" title="Unexpected news changed the daily bias">news flipped ${b.bias} → ${display}: ${esc(liveHead?.title || 'new headline flow')}</div>`
    : ''
  const events = b.events.map((e) => {
    eventById.set(e.id, e)
    const dir = e.watch ? '○' : e.vote > 0 ? '↑' : '↓'
    const dirCls = e.watch ? 'watch' : e.vote > 0 ? 'up' : 'down'
    const tgt = e.vote > 0 ? e.targets?.up : e.vote < 0 ? e.targets?.down : null
    const arrow = e.vote > 0 ? '▲' : e.vote < 0 ? '▼' : '±'
    const tgtTxt = tgt ? `${arrow}${tgt.price.toFixed(5)}` : `±${e.expected_pips}p`
    const tgtCls = e.vote > 0 ? 'up' : e.vote < 0 ? 'down' : 'range'
    const tgtTitle = tgt
      ? `${tgt.label} · ${tgt.pips} pips from anchor`
      : `expected ±${e.expected_pips} pips`
    const nums = (e.forecast || e.previous || e.actual)
      ? `<span class="nums">${e.actual ? `a ${esc(e.actual)} · ` : ''}f ${esc(e.forecast) || '—'} · p ${esc(e.previous) || '—'}${e.proxy ? ' · proxy' : ''}</span>`
      : ''
    return `<li class="ev${e.watch ? ' is-watch' : ''}" data-eid="${esc(e.id)}">
      <span class="ev-time" title="${e.time} UTC">${localTime(e.time, b.date)}</span>
      <span class="imp ${e.impact.toLowerCase()}">${e.impact[0]}</span>
      <span class="ev-title">${e.country} · ${esc(e.title)}</span>
      <span class="ev-tgt ${tgtCls}" title="${esc(tgtTitle)}">${tgtTxt}</span>
      <span class="ev-dir ${dirCls}">${dir}</span>
      ${nums}
    </li>`
  }).join('')
  const quiet = b.events.length === 0
    ? '<div class="bias-note">No High/Medium market-moving news today.</div>'
    : ''
  el.innerHTML = `
    <article class="card bias ${display}">
      <div class="bias-head">
        <span class="bias-badge">${ARROW[display] ?? '●'} ${display.toUpperCase()}</span>
        <span class="bias-head-right">${overridden ? '<span class="live-badge">LIVE</span>' : ''}${validHtml}${basisHtml}<span class="bias-conf">${Math.round((b.confidence ?? 0) * 100)}% conf</span></span>
      </div>
      <div class="bias-win">news window ${win} · calendar ${b.score}${b.news ? ` · headlines ${b.news.score}` : ''}${live ? ` · live ${live.score}` : ''}${b.valid_from && !overridden ? ` · active ${localTime(b.valid_from, b.date)}–${localUntil}` : ''}</div>
      <div class="bias-target">${target}</div>
      ${liveHtml}
      ${newsHtml}
      ${winHtml}
      <ul class="bias-events">${events}</ul>
      ${quiet}
      <div class="bias-note">${esc(b.disclaimer)}</div>
    </article>`

  if (validTimer) clearInterval(validTimer)
  if (validUntil) {
    const node = el.querySelector<HTMLSpanElement>('#bias-valid')!
    const expiry = Date.parse(`${untilDate}T${validUntil}:00Z`)
    const tick = () => {
      const remain = expiry - Date.now()
      node.textContent = remain > 0
        ? `until ${localUntil} ${TZ_LABEL} · ${fmtRemaining(remain)}`
        : `ended ${localUntil} ${TZ_LABEL}`
      node.classList.toggle('expired', remain <= 0)
    }
    tick()
    validTimer = setInterval(tick, 30_000)
  }
}

async function load() {
  // request permission early so Android allows notifications
  if (Notification.permission === 'default') { /* only on user tap */ }
  const [res, bias, live] = await Promise.all([
    fetch('/levels.json', { cache: 'no-cache' }),
    loadBias(),
    loadLiveBias(new Date().toISOString().slice(0, 10)),
  ])
  if (!res.ok) throw new Error('levels.json not found')
  const data: LevelsFile = await res.json()
  currentBias = bias
  currentLive = live
  liveKey = `${live?.state || ''}|${live?.generated_at || ''}`
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

  if (bias) renderBias(bias, live)
  if (bias && bias.events.length) {
    startActualsPolling(bias.date)
    startLiveBiasPolling(bias.date)
  }

  // daily notification: new date (new day starts 00:00 UTC)
  const lastDate = localStorage.getItem('levels-date')
  if (lastDate !== data.date) {
    localStorage.setItem('levels-date', data.date)
    if (Notification.permission === 'granted') {
      const shown = (live?.state && live.state !== 'neutral' ? live.state : bias?.bias) || ''
      const until = (live?.state && live.state !== 'neutral' && live.until) ? live.until : bias?.valid_until
      const biasLabel = bias
        ? `${shown}${until ? ` until ${localTime(until, bias.date)} ${TZ_LABEL}` : ''}${bias.target ? ` → ${bias.target.price.toFixed(5)}` : ''}`
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

const notifyBtn = document.querySelector('#notify') as HTMLButtonElement

async function refreshNotifyBtn(): Promise<void> {
  if (!pushSupported()) {
    notifyBtn.textContent = 'Push not supported on this browser'
    notifyBtn.disabled = true
    return
  }
  const on = await isSubscribed()
  if (on) await syncPushTz()
  notifyBtn.textContent = on
    ? 'News alerts ON · tap to turn off'
    : 'Enable news alerts'
  notifyBtn.disabled = false
}

notifyBtn.addEventListener('click', async () => {
  notifyBtn.disabled = true
  try {
    if (await isSubscribed()) {
      await disablePush()
      notifyBtn.textContent = 'News alerts off'
    } else {
      const r = await enablePush()
      notifyBtn.textContent = r === 'ok'
        ? 'News alerts ON'
        : r === 'denied'
          ? 'Notifications blocked — allow them in browser settings'
          : r === 'unsupported'
            ? 'Push not supported on this browser'
            : 'Could not reach push service — tap to retry'
    }
  } finally {
    notifyBtn.disabled = false
    if (await isSubscribed()) notifyBtn.textContent = 'News alerts ON · tap to turn off'
  }
})

load().catch((e) => { document.querySelector('#meta')!.textContent = 'Could not load levels: ' + e.message })
void refreshNotifyBtn()

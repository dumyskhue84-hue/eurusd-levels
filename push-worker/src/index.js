// eurusd-push: Web Push delivery for EURUSD news briefings + release outcomes.
//
// POST /api/subscribe {subscription}   -> KV SUBS
// POST /api/unsubscribe {endpoint}
// GET  /api/actuals/:date              -> released values for the app card
// GET  /api/health | /api/vapid-key | /api/debug/tv
// cron */5 * * * * :
//   1. daily briefing  -> 1h before the day's first High/Medium event
//      (06:00 UTC quiet days, skipped on weekends)
//   2. per-event outcome pushes from the TradingView calendar actuals
import { sendPush } from './webpush.js'

const BIAS_URL = 'https://eurusd-levels.pages.dev/bias.json'
const TV_URL = 'https://economic-calendar.tradingview.com/events'
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'
const ALLOWED_ORIGINS = [
  'https://eurusd-levels.pages.dev',
  'http://localhost:5173',
  'http://127.0.0.1:5173',
]
// higher = surprise drives EURUSD the same way as "actual > forecast"
const INVERTED = {
  USD: ['unemployment claims', 'initial jobless claims', 'jobless claims', 'unemployment rate'],
  EUR: ['unemployment rate'],
}
const COUNTRY_MAP = {
  USD: ['US'],
  EUR: ['EU', 'DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'IE', 'FI', 'PT', 'GR'],
}
// normalized title pairs that mean the same release on TV vs ForexFactory
const TITLE_EQ = [
  ['nonfarmemploymentchange', 'nonfarmpayrolls'],
  ['nonfarmemploymentchange', 'changeinnonfarmpayrolls'],
  ['unemploymentclaims', 'initialjoblessclaims'],
  ['unemploymentclaims', 'joblessclaims'],
  ['continuingclaims', 'continuingjoblessclaims'],
  ['federalfundsrate', 'interestratedecision'],
  ['corepcepricemom', 'corepcepriceindexmom'],
  ['pcepricemom', 'pcepriceindexmom'],
  ['averagehourlyearningsmom', 'averagehourlyearningsyoy'],
  ['businessinventoriesmom', 'businessinventoriesm/m'],
]

// Live headline watch: re-scores central-bank tone during the day and fires
// when it would flip the daily bias (mirrors scripts/daily_bias.py).
const NEWS_QUERIES = [
  ['Fed', 'https://news.google.com/rss/search?q=Federal+Reserve+inflation+rates+when:1d&hl=en-US&gl=US&ceid=US:en', -1],
  ['ECB', 'https://news.google.com/rss/search?q=ECB+inflation+rates+when:1d&hl=en-US&gl=US&ceid=US:en', 1],
]
const HAWKISH = ['rate hike', 'hike', 'hawkish', 'tighten', 'higher rates',
  'higher for longer', 'aggressive', 'shock', 'hot inflation',
  'persistent inflation', 'raise rates', 'rate increase', 'basis point',
  'half-point', 'quarter-point', 'more hikes', 'multiple hikes', 'rate rise']
const DOVISH = ['rate cut', 'cut rates', 'dovish', 'easing', 'pause hikes',
  'inflation cools', 'cooling inflation', 'softer inflation', 'lower rates',
  'rate reduction', 'fewer hikes']
const NEWS_NEGATORS = ['reject', 'rules out', 'rule out', 'oppose', 'against',
  'pushback', 'unlikely', 'no rate hike', 'not raise', 'fewer hikes']
const NEWS_MIXED = ['split', 'divided', 'mixed signals']
const NEWS_WEIGHTS = [1, 0.7, 0.5, 0.35, 0.25, 0.18]
const BIAS_FLIP_MIN = 1.2 // ignore weak noise around zero

const TTL_DAY = 172800 // 2d for state keys

// ---------- small utils ----------
const hhmmToMin = (s) => Number(s.slice(0, 2)) * 60 + Number(s.slice(3, 5))
const minToHHMM = (m) =>
  `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`

function tzLabel(tz) {
  try {
    return new Intl.DateTimeFormat('en-GB', { timeZone: tz, timeZoneName: 'short' })
      .formatToParts(new Date()).find((p) => p.type === 'timeZoneName')?.value || ''
  } catch { return '' }
}

function localTimeUTC(date, hhmm, tz) {
  let d = new Date(`${date}T${hhmm}:00Z`)
  if (hhmm === '24:00') d = new Date(Date.parse(`${date}T00:00:00Z`) + 86400000)
  if (Number.isNaN(d.getTime())) return hhmm
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).format(d)
  } catch { return hhmm }
}

function localizeText(text, date, tz) {
  if (!text || !tz) return text
  const label = tzLabel(tz)
  return text
    .replace(/\b(\d{2}):(\d{2})\b/g, (_, h, m) => localTimeUTC(date, `${h}:${m}`, tz))
    .replace(/\bUTC\b/g, label || '')
}

// ---------- live headline scoring ----------
export function headlineTone(text) {
  const t = String(text || '').toLowerCase()
  if (NEWS_MIXED.some((k) => t.includes(k))) return null
  const hawk = HAWKISH.filter((k) => t.includes(k)).length
  const dove = DOVISH.filter((k) => t.includes(k)).length
  if (hawk === dove) return null
  let tone = hawk > dove ? 'hawkish' : 'dovish'
  if (NEWS_NEGATORS.some((k) => t.includes(k))) tone = tone === 'hawkish' ? 'dovish' : 'hawkish'
  return tone
}

function decodeXml(s) {
  return String(s || '')
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&amp;/g, '&').replace(/&quot;/g, '"')
    .replace(/&#0*39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/<[^>]*>/g, '').trim()
}

export function parseRss(xml) {
  const out = []
  for (const block of String(xml || '').match(/<item>[\s\S]*?<\/item>/g) || []) {
    const title = decodeXml(block.match(/<title>([\s\S]*?)<\/title>/)?.[1])
    const ts = Date.parse(decodeXml(block.match(/<pubDate>([\s\S]*?)<\/pubDate>/)?.[1]))
    if (title) out.push({ title, ts })
  }
  return out
}

export function scoreHeadlines(items, now) {
  const seen = new Set()
  const scored = []
  for (const it of items || []) {
    const clean = it.title.includes(' - ')
      ? it.title.slice(0, it.title.lastIndexOf(' - ')) : it.title
    const key = clean.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 60)
    if (!key || seen.has(key)) continue
    seen.add(key)
    const tone = headlineTone(clean)
    if (!tone) continue
    if (Number.isFinite(it.ts)) {
      if (it.ts > now.getTime() + 3600000 || now.getTime() - it.ts > 36 * 3600000) continue
    }
    scored.push({
      title: clean.slice(0, 120), tone, sign: it.sign,
      vote: it.sign * (tone === 'hawkish' ? 1 : -1),
      time: Number.isFinite(it.ts) ? new Date(it.ts).toISOString().slice(11, 16) : null,
      ts: Number.isFinite(it.ts) ? it.ts : 0,
    })
  }
  scored.sort((a, b) => b.ts - a.ts)
  const top = scored.slice(0, NEWS_WEIGHTS.length)
  const score = top.reduce((sum, h, i) => sum + h.vote * NEWS_WEIGHTS[i], 0)
  return {
    score: Math.round(score * 100) / 100,
    confidence: Math.min(1, Math.abs(score) / 3),
    headlines: top.map(({ ts, ...h }) => h),
    last_time: top.find((h) => h.time)?.time || null,
  }
}

export function biasState(score) {
  return score > 0 ? 'bullish' : score < 0 ? 'bearish' : 'neutral'
}

export function detectBiasChange(bias, news, baseline) {
  const cal = Number(bias?.score) || 0
  const live = cal + (Number(news?.score) || 0)
  const from = baseline || bias?.bias
  const to = biasState(live)
  if (!from || !to || from === to || Math.abs(live) < BIAS_FLIP_MIN) return null
  return {
    from, to, score: Math.round(live * 100) / 100,
    headline: news?.headlines?.[0]?.title || 'new headline flow',
    until: new Date(Date.now() + 4 * 3600000).toISOString().slice(11, 16),
  }
}

async function fetchLiveNews(env, now) {
  const key = 'news:live'
  try {
    const cached = await env.SUBS.get(key, 'json')
    if (cached && now.getTime() - cached.t < 300000) return cached
  } catch { /* refetch */ }
  const items = []
  for (const [, url, sign] of NEWS_QUERIES) {
    let res = null
    for (const init of [{ headers: { 'User-Agent': UA } }, {}]) {
      try {
        res = await fetch(`${url}&cb=${now.getTime()}`, init)
        if (res.ok) break
      } catch { /* try next */ }
    }
    if (!res?.ok) continue
    try {
      for (const it of parseRss(await res.text())) items.push({ ...it, sign })
    } catch { /* skip malformed feed */ }
  }
  if (!items.length) return null
  const result = { t: now.getTime(), ...scoreHeadlines(items, now) }
  try {
    await env.SUBS.put(key, JSON.stringify(result), { expirationTtl: 600 })
  } catch { /* cache optional */ }
  return result
}

function parseNum(s) {
  if (s == null) return null
  const t = String(s).replace(/,/g, '').trim()
  const m = t.match(/-?\d+(\.\d+)?/)
  if (!m) return null
  let v = parseFloat(m[0])
  if (/[kK]\s*$/.test(t)) v *= 1e3
  else if (/[mM]\s*$/.test(t)) v *= 1e6
  else if (/[bB]\s*$/.test(t)) v *= 1e9
  return v
}

function normTitle(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/m\/m/g, 'mom').replace(/y\/y/g, 'yoy').replace(/q\/q/g, 'qoq')
    .replace(/[^a-z0-9]/g, '')
}

function tokenScore(a, b) {
  const ta = new Set(String(a).toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 2))
  const tb = new Set(String(b).toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 2))
  if (!ta.size || !tb.size) return 0
  let common = 0
  for (const t of ta) if (tb.has(t)) common++
  return common / Math.min(ta.size, tb.size)
}

function corsFor(origin) {
  if (!origin) return {}
  const ok = ALLOWED_ORIGINS.includes(origin) ||
    /^https:\/\/[\w-]+\.eurusd-levels\.pages\.dev$/.test(origin)
  if (!ok) return {}
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  }
}

const json = (data, status = 200, cors = {}) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...cors },
  })

// ---------- KV helpers ----------
async function listSubs(env) {
  const out = []
  let cursor
  do {
    const page = await env.SUBS.list({ prefix: 'sub:', cursor })
    for (const k of page.keys) {
      const v = await env.SUBS.get(k.name, 'json')
      if (v && v.endpoint && v.keys?.p256dh) out.push(v)
    }
    cursor = page.list_complete ? undefined : page.cursor
  } while (cursor)
  return out
}

async function broadcast(env, subs, msg) {
  let ok = 0
  const dead = []
  for (const sub of subs) {
    try {
      const r = await sendPush(env, sub, msg)
      if (r.ok) ok++
      else if (r.status === 404 || r.status === 410) dead.push(sub)
      else console.log(`push failed ${r.status} ${sub.endpoint.slice(0, 70)}`)
    } catch (e) {
      console.log(`push error ${e?.message}`)
    }
  }
  for (const s of dead) await env.SUBS.delete(`sub:${s.endpoint}`)
  return ok
}

// Send the same message per subscriber timezone (tz captured at subscribe).
async function broadcastLocalized(env, subs, msg, date) {
  const groups = new Map()
  for (const s of subs) {
    const tz = s.tz || 'UTC'
    if (!groups.has(tz)) groups.set(tz, [])
    groups.get(tz).push(s)
  }
  let ok = 0
  for (const [tz, group] of groups) {
    ok += await broadcast(env, group, {
      ...msg,
      title: localizeText(msg.title, date, tz),
      body: localizeText(msg.body, date, tz),
    })
  }
  return ok
}

// ---------- data sources ----------
async function fetchBias() {
  try {
    const res = await fetch(`${BIAS_URL}?cb=${Date.now()}`, { cache: 'no-store' })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function fetchTvRows(env, date) {
  const key = `tv:${date}`
  try {
    const cached = await env.SUBS.get(key, 'json')
    if (cached && Date.now() - cached.t < 60_000) return cached.rows
  } catch { /* refetch */ }
  try {
    const url = `${TV_URL}?from=${date}T00:00:00.000Z&to=${date}T23:59:59.000Z`
    const res = await fetch(url, {
      headers: { 'User-Agent': UA, Origin: 'https://www.tradingview.com', Referer: 'https://www.tradingview.com/' },
    })
    if (!res.ok) return null
    const data = await res.json()
    const rows = Array.isArray(data.result) ? data.result : []
    await env.SUBS.put(key, JSON.stringify({ t: Date.now(), rows }), { expirationTtl: 120 })
    return rows
  } catch {
    return null
  }
}

export function matchEvent(event, rows) {
  const evTs = Date.parse(`${event.date}T${event.time}:00Z`)
  const allowed = COUNTRY_MAP[event.country] || []
  const et = normTitle(event.title)
  let best = null
  for (const row of rows || []) {
    if (!allowed.includes(row.country)) continue
    const t = Date.parse(row.date)
    if (!Number.isFinite(t) || Math.abs(t - evTs) > 15 * 60_000) continue
    const actual = row.actual ?? row.actualRaw
    if (actual == null || actual === '' || actual === '\u00a0' || actual === '&nbsp;') continue
    const rt = normTitle(row.title || row.indicator)
    let tier = 0
    if (rt && rt === et) tier = 4
    else if (TITLE_EQ.some(([a, b]) => (et === a && rt === b) || (et === b && rt === a))) tier = 3
    else if (rt && et && (rt.includes(et) || et.includes(rt))) tier = 2
    else if (tokenScore(event.title, row.title) >= 0.6) tier = 1
    if (tier > 0 && (!best || tier > best.tier)) best = { tier, row }
  }
  return best?.row || null
}

// ---------- outcome composition ----------
export function outcomeDir(event, actual) {
  const a = parseNum(actual)
  const f = parseNum(event.forecast)
  const p = parseNum(event.previous)
  let cmp = null
  if (a != null && f != null) cmp = Math.sign(a - f)
  else if (a != null && p != null) cmp = Math.sign(a - p)
  const vote = event.vote || 0
  if (cmp == null || cmp === 0) return vote // in line / no consensus -> lean holds
  const t = event.title.toLowerCase()
  const inverted = (INVERTED[event.country] || []).some((k) => t.includes(k))
  if (event.country === 'USD') return inverted ? cmp : -cmp
  return inverted ? -cmp : cmp
}

export function composeOutcome(bias, event, row) {
  const actual = String(row.actual ?? row.actualRaw)
  const dir = outcomeDir(event, actual)
  const f = event.forecast
  const a = parseNum(actual)
  const fc = parseNum(f)
  const inLine = a != null && fc != null && a === fc

  const bits = [`actual ${actual}${f ? ` (f ${f})` : ''}`]
  if (!inLine && a != null && fc != null) bits.push(a > fc ? 'above forecast' : 'below forecast')

  if (inLine) bits.push(dir ? 'in line, lean holds' : 'in line')
  else if (dir > 0) bits.push(event.country === 'EUR' ? 'EUR strong' : 'USD weak')
  else if (dir < 0) bits.push(event.country === 'EUR' ? 'EUR weak' : 'USD strong')
  else bits.push('no direction')

  const rel = hhmmToMin(event.time)
  const win = (bias.windows || []).find((w) => (w.event_ids || []).includes(event.id))
  const winDir = win ? (win.direction === 'bullish' ? 1 : -1) : 0
  if (dir !== 0) {
    if (win && winDir === dir) bits.push(`window ${win.start}-${win.end}`)
    else bits.push(`window ${minToHHMM(rel)}-${minToHHMM(Math.min(rel + 240, 1439))}`)
  }

  const tgt = dir > 0 ? event.targets?.up : dir < 0 ? event.targets?.down : null
  if (tgt) bits.push(`target ${tgt.price} (${tgt.pips}p)`)

  const body = bits.join(' · ')
  return {
    title: `${event.country} ${event.title} → ${actual}`,
    body: body.length > 400 ? body.slice(397) + '…' : body,
    tag: `out-${event.id}`,
    url: '/',
    _dir: dir,
    _inLine: inLine,
  }
}

// ---------- cron ----------
export function briefingDue(bias, now) {
  const events = bias.events || []
  let mins
  if (events.length) {
    let first = Infinity
    for (const e of events) first = Math.min(first, hhmmToMin(e.time))
    mins = Math.max(first - 60, 10) // >= 00:10 UTC (pipeline finishes 00:05)
  } else {
    mins = 6 * 60 // quiet-day note at 06:00 UTC
  }
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, mins, 0))
}

async function storeActual(env, date, id, info) {
  const key = `actuals:${date}`
  const map = (await env.SUBS.get(key, 'json')) || {}
  map[id] = info
  await env.SUBS.put(key, JSON.stringify(map), { expirationTtl: TTL_DAY })
}

async function processOutcomes(env, bias, today, now, subs) {
  const events = bias.events || []
  const pending = events.filter((e) => {
    const rel = Date.parse(`${today}T${e.time}:00Z`)
    return Number.isFinite(rel) && now.getTime() >= rel
  })
  if (!pending.length) return
  const rows = await fetchTvRows(env, today)
  if (!rows) return
  for (const e of pending) {
    if (!e.id) continue // pre-targets bias schema: no stable id for dedupe
    const doneKey = `done:${e.id}`
    if (subs.length && await env.SUBS.get(doneKey)) continue
    const row = matchEvent({ ...e, date: bias.date }, rows)
    if (!row) continue
    const msg = composeOutcome(bias, e, row)
    await storeActual(env, today, e.id, {
      actual: String(row.actual ?? row.actualRaw ?? ''),
      dir: msg._dir,
      time: e.time,
    })
    delete msg._dir
    delete msg._inLine
    if (!subs.length) {
      // No recipients yet: mark processed so a later subscriber doesn't
      // receive stale outcomes; actuals above still power the app card.
      await env.SUBS.put(doneKey, JSON.stringify({ at: now.toISOString(), quiet: true }),
        { expirationTtl: TTL_DAY })
      continue
    }
    const n = await broadcastLocalized(env, subs, msg, today)
    if (n > 0) {
      await env.SUBS.put(doneKey, JSON.stringify({ at: now.toISOString() }),
        { expirationTtl: TTL_DAY })
    }
  }
}

export async function run(env, opts = {}) {
  const now = opts.now || new Date()
  const today = now.toISOString().slice(0, 10)
  const bias = opts.bias || await fetchBias()
  if (!bias || bias.error || bias.date !== today) return
  const events = bias.events || []
  const subs = await listSubs(env)

  // 1) daily briefing
  if (subs.length && bias.briefing) {
    const sentKey = `sent:briefing:${today}`
    if (!await env.SUBS.get(sentKey)) {
      const quietWeekend = events.length === 0 && [0, 6].includes(now.getUTCDay())
      if (quietWeekend) {
        await env.SUBS.put(sentKey, JSON.stringify({ skipped: 'weekend' }),
          { expirationTtl: TTL_DAY })
      } else if (now >= briefingDue(bias, now)) {
        // Too late if the first event already started (delayed pipeline):
        // outcome pushes cover released events instead.
        let stale = false
        if (events.length) {
          const first = Math.min(...events.map((e) => hhmmToMin(e.time)))
          const firstTs = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(),
            now.getUTCDate(), 0, first, 0)
          stale = now.getTime() >= firstTs
        }
        if (stale) {
          await env.SUBS.put(sentKey, JSON.stringify({ skipped: 'stale' }),
            { expirationTtl: TTL_DAY })
        } else {
          const n = await broadcastLocalized(env, subs, {
            title: bias.briefing.title,
            body: bias.briefing.body,
            tag: `briefing-${today}`,
            url: '/',
          }, today)
          if (n > 0) {
            await env.SUBS.put(sentKey, JSON.stringify({ at: now.toISOString(), n }),
              { expirationTtl: TTL_DAY })
          }
        }
      }
    }
  }

  // 2) release outcomes (+ actuals for the app card)
  await processOutcomes(env, bias, today, now, subs)

  // 3) intraday headline watch -> live bias + change notifications
  await watchNewsBias(env, bias, today, now, subs)
}

async function watchNewsBias(env, bias, today, now, subs) {
  const news = await fetchLiveNews(env, now)
  if (!news) return
  const live = Math.round(((Number(bias.score) || 0) + news.score) * 100) / 100
  await env.SUBS.put(`livebias:${today}`, JSON.stringify({
    date: today, state: biasState(live), score: live, baseline: bias.bias,
    news, until: new Date(now.getTime() + 4 * 3600000).toISOString().slice(11, 16),
    generated_at: now.toISOString(),
  }), { expirationTtl: TTL_DAY })

  const last = await env.SUBS.get(`biaschange:last:${today}`, 'json')
  const change = detectBiasChange(bias, news, last?.state || bias.bias)
  if (!change || !subs.length) return
  const count = Number((await env.SUBS.get(`biaschange:count:${today}`, 'json'))?.n || 0)
  if (count >= 3) return
  const cool = await env.SUBS.get(`biaschange:cooldown:${today}`, 'json')
  if (cool && now.getTime() - Number(cool.t || 0) < 30 * 60000) return

  const short = change.headline.length > 90
    ? change.headline.slice(0, 89) + '…' : change.headline
  const n = await broadcastLocalized(env, subs, {
    title: `EURUSD bias change: ${change.to.toUpperCase()} (was ${change.from})`,
    body: `${short} · score ${change.score} · until ${change.until} UTC`,
    tag: `biaschange-${today}-${change.to}`,
    url: '/',
  }, today)
  if (n > 0) {
    await env.SUBS.put(`biaschange:last:${today}`,
      JSON.stringify({ state: change.to }), { expirationTtl: TTL_DAY })
    await env.SUBS.put(`biaschange:count:${today}`,
      JSON.stringify({ n: count + 1 }), { expirationTtl: TTL_DAY })
    await env.SUBS.put(`biaschange:cooldown:${today}`,
      JSON.stringify({ t: now.getTime() }), { expirationTtl: TTL_DAY })
  }
}

// ---------- HTTP ----------
async function handleFetch(request, env) {
  const url = new URL(request.url)
  const cors = corsFor(request.headers.get('Origin') || undefined)
  const path = url.pathname

  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: cors })
  }

  if (path === '/api/health') {
    let count = 0
    try {
      const page = await env.SUBS.list({ prefix: 'sub:' })
      count = page.keys.length
    } catch { /* KV unavailable */ }
    return json({ ok: true, subs: count }, 200, cors)
  }

  if (path === '/api/vapid-key') {
    const { VAPID_PUBLIC_KEY } = await import('./webpush.js')
    return json({ publicKey: VAPID_PUBLIC_KEY }, 200, cors)
  }

  if (path.startsWith('/api/actuals/') && request.method === 'GET') {
    const date = path.slice('/api/actuals/'.length)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return json({ error: 'bad date' }, 400, cors)
    const map = (await env.SUBS.get(`actuals:${date}`, 'json')) || {}
    return json(map, 200, cors)
  }

  if (path.startsWith('/api/live-bias/') && request.method === 'GET') {
    const date = path.slice('/api/live-bias/'.length)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return json({ error: 'bad date' }, 400, cors)
    const live = (await env.SUBS.get(`livebias:${date}`, 'json')) || null
    return json(live, 200, cors)
  }

  if (path === '/api/subscribe' && request.method === 'POST') {
    let body
    try {
      body = await request.json()
    } catch {
      return json({ error: 'bad json' }, 400, cors)
    }
    const sub = body?.subscription
    if (!sub?.endpoint?.startsWith('https://') || !sub.keys?.p256dh || !sub.keys?.auth) {
      return json({ error: 'bad subscription' }, 400, cors)
    }
      await env.SUBS.put(`sub:${sub.endpoint}`, JSON.stringify({
        ...sub,
        created_at: new Date().toISOString(),
        page: typeof body.page === 'string' ? body.page.slice(0, 200) : '',
        tz: typeof body.tz === 'string' && body.tz.length <= 64 ? body.tz : 'UTC',
      }))
    return json({ ok: true }, 200, cors)
  }

  if (path === '/api/unsubscribe' && request.method === 'POST') {
    let body
    try {
      body = await request.json()
    } catch {
      return json({ error: 'bad json' }, 400, cors)
    }
    if (typeof body?.endpoint === 'string') {
      await env.SUBS.delete(`sub:${body.endpoint}`)
    }
    return json({ ok: true }, 200, cors)
  }

  if (path === '/api/debug/news') {
    const now = new Date()
    const debug = []
    for (const [bank, url, sign] of NEWS_QUERIES) {
      for (const init of [{ headers: { 'User-Agent': UA } }, {}]) {
        try {
          const res = await fetch(`${url}&cb=${now.getTime()}`, init)
          const xml = res.ok ? await res.text() : ''
          debug.push({ bank, status: res.status, bytes: xml.length,
            items: parseRss(xml).length, ua: !!init.headers })
          if (res.ok) break
        } catch (e) {
          debug.push({ bank, error: String(e?.message || e), ua: !!init.headers })
        }
      }
    }
    const live = await env.SUBS.get(`livebias:${now.toISOString().slice(0, 10)}`, 'json')
    return json({ debug, live: live ? { state: live.state, score: live.score } : null }, 200, cors)
  }

  if (path === '/api/debug/probe') {
    const urls = String(url.searchParams.get('urls') || '').split('|').filter(Boolean).slice(0, 8)
    const out = []
    for (const u of urls) {
      try {
        const res = await fetch(u, { headers: { 'User-Agent': UA } })
        const txt = res.ok ? await res.text() : ''
        out.push({ u: u.slice(0, 90), status: res.status, bytes: txt.length,
          items: parseRss(txt).length })
      } catch (e) {
        out.push({ u: u.slice(0, 90), error: String(e?.message || e) })
      }
    }
    return json(out, 200, cors)
  }

  if (path === '/api/debug/tv') {
    const date = url.searchParams.get('date') || new Date().toISOString().slice(0, 10)
    const rows = await fetchTvRows(env, date)
    if (!rows) return json({ error: 'tv fetch failed' }, 502, cors)
    const sample = rows.slice(0, 5).map((r) => ({
      date: r.date, country: r.country, title: r.title, actual: r.actual,
    }))
    return json({ date, count: rows.length, sample }, 200, cors)
  }

  return json({ error: 'not found' }, 404, cors)
}

export default {
  fetch(request, env) {
    return handleFetch(request, env).catch((e) =>
      json({ error: String(e?.message || e) }, 500,
        corsFor(request.headers.get('Origin') || undefined)))
  },
  scheduled(_event, env, ctx) {
    ctx.waitUntil(run(env).catch((e) => console.error('cron failed', e)))
  },
}

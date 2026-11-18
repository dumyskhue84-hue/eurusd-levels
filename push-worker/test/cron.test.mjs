// Cron logic tests: outcome composition, event matching, briefing timing,
// and a full run() pass against a fake KV + stubbed fetch.
// Run: node push-worker/test/cron.test.mjs
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  matchEvent, outcomeDir, composeOutcome, briefingDue, run,
  headlineTone, parseRss, scoreHeadlines, biasState, detectBiasChange,
} from '../src/index.js'

// ---- fake environment ----
class FakeKV {
  constructor() { this.m = new Map() }
  async get(k, type) {
    const v = this.m.get(k)
    if (v == null) return null
    return type === 'json' ? JSON.parse(v) : v
  }
  async put(k, v) { this.m.set(k, String(v)) }
  async delete(k) { this.m.delete(k) }
  async list({ prefix = '' } = {}) {
    const keys = [...this.m.keys()].filter((k) => k.startsWith(prefix))
      .sort().map((name) => ({ name }))
    return { keys, list_complete: true }
  }
}

const VAPID_PRIVATE_KEY = fs.readFileSync(
  new URL('../vapid_private.b64', import.meta.url), 'utf8').trim()

const SUB = {
  endpoint: 'https://push.example.test/sub-1',
  keys: {
    p256dh: 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4',
    auth: 'BTBZMqHH6r4Tts7J_aSIgg',
  },
}

// ---- bias / TV fixtures (first event 01:00 UTC) ----
const BIAS = {
  date: '2026-11-16',
  events: [{
    id: 'us-cpi-mom-0100',
    country: 'USD',
    title: 'CPI m/m',
    time: '01:00',
    vote: -1,
    forecast: '0.3%',
    previous: '0.4%',
    expected_pips: 40,
    targets: {
      up: { price: '1.13000', pips: 40 },
      down: { price: '1.12000', pips: 40 },
    },
  }],
  windows: [{
    direction: 'bearish',
    start: '01:00',
    end: '05:00',
    event_ids: ['us-cpi-mom-0100'],
  }],
  briefing: {
    title: 'Today: CPI m/m 01:00 UTC',
    body: 'USD CPI m/m at 01:00 UTC. Expect ~40p. EURUSD \u25bc bias 01:00-05:00, target 1.12000 (40p).',
  },
}

const TV_ROWS = [{
  date: '2026-11-16T01:00:00.000Z',
  country: 'US',
  title: 'CPI m/m',
  actual: '0.5%',
  forecast: '0.3%',
}]

// ---- fetch spy ----
const pushCalls = []
const realFetch = globalThis.fetch
function stubFetch(rows) {
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url)
    if (u.includes('push.example.test')) {
      pushCalls.push({ url: u, init })
      return { ok: true, status: 201 }
    }
    if (u.includes('economic-calendar.tradingview.com')) {
      return { ok: true, json: async () => ({ result: rows }) }
    }
    throw new Error(`unexpected fetch: ${u}`)
  }
}

function freshEnv() {
  const kv = new FakeKV()
  return {
    SUBS: kv,
    VAPID_PRIVATE_KEY,
    VAPID_SUBJECT: 'mailto:test@example.com',
    _kv: kv,
  }
}

async function unitTests() {
  const ev = { ...BIAS.events[0], date: BIAS.date }

  // --- matchEvent ---
  assert.ok(matchEvent(ev, TV_ROWS), 'exact title match')
  assert.equal(matchEvent(ev, [{ ...TV_ROWS[0], country: 'DE' }]), null,
    'country mismatch rejected')
  assert.equal(matchEvent(ev, [{ ...TV_ROWS[0], date: '2026-11-16T01:30:00.000Z' }]), null,
    'time +/-15m enforced')
  assert.equal(matchEvent(ev, [{ ...TV_ROWS[0], actual: null }]), null,
    'missing actual skipped')

  const pair = matchEvent(
    { id: 'x', country: 'USD', title: 'Non-Farm Payrolls', time: '13:30', date: BIAS.date },
    [{ date: '2026-11-16T13:30:00.000Z', country: 'US', title: 'Nonfarm Payrolls', actual: '199K' }])
  assert.ok(pair, 'TITLE_EQ pair match (NFP)')

  // --- outcomeDir ---
  assert.equal(outcomeDir(BIAS.events[0], '0.5%'), -1, 'hot USD CPI -> bearish EURUSD')
  assert.equal(outcomeDir(BIAS.events[0], '0.3%'), BIAS.events[0].vote, 'in-line -> lean holds')
  assert.equal(outcomeDir(
    { country: 'USD', title: 'Initial Jobless Claims', vote: -1, forecast: '220K' }, '250K'),
  1, 'inverted claims: high actual -> bullish')

  // --- composeOutcome ---
  const msg = composeOutcome(BIAS, BIAS.events[0], TV_ROWS[0])
  assert.equal(msg.title, 'USD CPI m/m \u2192 0.5%')
  for (const frag of ['above forecast', 'USD strong', 'window 01:00-05:00', 'target 1.12000 (40p)']) {
    assert.ok(msg.body.includes(frag), `body has "${frag}": ${msg.body}`)
  }
  assert.equal(msg.tag, 'out-us-cpi-mom-0100')

  // --- briefingDue ---
  const now = new Date('2026-11-16T00:00:00Z')
  assert.equal(briefingDue(BIAS, now).toISOString(), '2026-11-16T00:10:00.000Z',
    'first 01:00 -> due 00:10 (clamped to 00:10)')
  const b2 = { ...BIAS, events: [{ time: '09:00' }] }
  assert.equal(briefingDue(b2, now).toISOString(), '2026-11-16T08:00:00.000Z', '1h before first')
  const quiet = { ...BIAS, events: [] }
  assert.equal(briefingDue(quiet, now).toISOString(), '2026-11-16T06:00:00.000Z', 'quiet -> 06:00')

  // --- live headline watch ---
  assert.equal(headlineTone('Fed to hike rates 50bp'), 'hawkish')
  assert.equal(headlineTone('Fed rejects December rate hike'), 'dovish')
  assert.equal(headlineTone('Fed officials split on rate hike'), null)
  const stamp = new Date().toUTCString()
  const rss = `<rss><channel><item><title>Fed's Waller Urges Rate Hike - CNBC</title><pubDate>${stamp}</pubDate></item></channel></rss>`
  assert.equal(parseRss(rss).length, 1, 'RSS item parsed')
  const scored = scoreHeadlines(parseRss(rss).map((x) => ({ ...x, sign: -1 })), new Date())
  assert.ok(scored.score < 0, 'hawkish Fed -> bearish EURUSD score')
  assert.equal(biasState(-2), 'bearish')
  assert.equal(biasState(2), 'bullish')
  const flip = detectBiasChange(
    { score: -0.7, bias: 'bearish' },
    { score: 3, headlines: [{ title: 'Fed pivots to rate cuts' }] }, 'bearish')
  assert.equal(flip?.to, 'bullish', 'dovish flow flips bearish day to bullish')
  assert.equal(detectBiasChange(
    { score: -0.7, bias: 'bearish' },
    { score: 0.2, headlines: [] }, 'bearish'), null, 'weak noise ignored')

  console.log('cron unit: OK')
}

async function integrationTests() {
  stubFetch(TV_ROWS)
  const env = freshEnv()
  await env.SUBS.put(`sub:${SUB.endpoint}`, JSON.stringify(SUB))

  // Pass 1 (00:15): briefing due (00:10), CPI not released yet.
  await run(env, { now: new Date('2026-11-16T00:15:00Z'), bias: BIAS })
  assert.ok(await env.SUBS.get('sent:briefing:2026-11-16'), 'briefing sent before first event')
  assert.equal(await env.SUBS.get('done:us-cpi-mom-0100'), null, 'outcome not yet processed')
  assert.equal(pushCalls.length, 1, 'only briefing pushed')

  // Pass 2 (01:05): CPI released -> outcome pushed; briefing not repeated.
  await run(env, { now: new Date('2026-11-16T01:05:00Z'), bias: BIAS })
  assert.equal(pushCalls.length, 2, 'briefing + outcome pushed')
  const actuals = await env.SUBS.get('actuals:2026-11-16', 'json')
  assert.equal(actuals['us-cpi-mom-0100'].actual, '0.5%', 'actual stored')
  assert.equal(actuals['us-cpi-mom-0100'].dir, -1, 'dir stored')
  assert.equal(actuals['us-cpi-mom-0100'].time, '01:00', 'time stored')

  // Pass 3 (02:00): fully deduped, no extra pushes.
  await run(env, { now: new Date('2026-11-16T02:00:00Z'), bias: BIAS })
  assert.equal(pushCalls.length, 2, 'no duplicate pushes')

  // No subscribers: outcome still recorded (actuals + done), nothing pushed,
  // briefing not marked (a later subscriber may still get it).
  const env0 = freshEnv()
  await run(env0, { now: new Date('2026-11-16T01:05:00Z'), bias: BIAS })
  assert.ok(await env0.SUBS.get('done:us-cpi-mom-0100'), 'done marked even with 0 subs')
  const a0 = await env0.SUBS.get('actuals:2026-11-16', 'json')
  assert.equal(a0['us-cpi-mom-0100'].actual, '0.5%', 'actuals stored with 0 subs')
  assert.equal(await env0.SUBS.get('sent:briefing:2026-11-16'), null,
    'briefing not marked with 0 subs')
  assert.equal(pushCalls.length, 2, '0 subs -> nothing pushed')

  // Stale briefing: pipeline ran after the first event started -> skip briefing.
  const envStale = freshEnv()
  await envStale.SUBS.put(`sub:${SUB.endpoint}`, JSON.stringify(SUB))
  await run(envStale, {
    now: new Date('2026-11-16T05:00:00Z'),
    bias: { ...BIAS, events: [{ ...BIAS.events[0], time: '04:00' }] },
  })
  const stale = await envStale.SUBS.get('sent:briefing:2026-11-16', 'json')
  assert.equal(stale.skipped, 'stale', 'late briefing recorded as stale')
  assert.equal(pushCalls.length, 2, 'stale briefing pushed nothing')

  // Weekend quiet-day note: marked skipped, no push.
  const env2 = freshEnv()
  await env2.SUBS.put(`sub:${SUB.endpoint}`, JSON.stringify(SUB))
  await run(env2, {
    now: new Date('2026-11-21T00:20:00Z'), // Saturday
    bias: { date: '2026-11-21', events: [], briefing: BIAS.briefing, windows: [] },
  })
  const skip = await env2.SUBS.get('sent:briefing:2026-11-21', 'json')
  assert.equal(skip.skipped, 'weekend', 'weekend skip recorded')
  assert.equal(pushCalls.length, 2, 'weekend sent nothing')

  // Weekday quiet-day note: sends at 06:00 UTC, not before.
  const env3 = freshEnv()
  await env3.SUBS.put(`sub:${SUB.endpoint}`, JSON.stringify(SUB))
  await run(env3, {
    now: new Date('2026-11-20T05:59:00Z'), // Friday before 06:00
    bias: { date: '2026-11-20', events: [], briefing: BIAS.briefing, windows: [] },
  })
  assert.equal(await env3.SUBS.get('sent:briefing:2026-11-20'), null, 'quiet note waits for 06:00')
  await run(env3, {
    now: new Date('2026-11-20T06:05:00Z'),
    bias: { date: '2026-11-20', events: [], briefing: BIAS.briefing, windows: [] },
  })
  assert.ok(await env3.SUBS.get('sent:briefing:2026-11-20'), 'quiet note sent at 06:00')
  assert.equal(pushCalls.length, 3, 'one quiet-day push')

  globalThis.fetch = realFetch
  console.log('cron integration: OK')
}

async function main() {
  await unitTests()
  await integrationTests()
  console.log('cron.test: all OK')
}

main().catch((e) => {
  globalThis.fetch = realFetch
  console.error(e)
  process.exit(1)
})

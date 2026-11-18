export interface Level {
  price: number
  type: string
  note: string
  approach_side: 'from_below' | 'from_above'
  zone_low: number
  zone_high: number
  zone_pips: number
  expiry: string
  respect: {
    touches: number
    reject_rate: number | null
    break_rate: number | null
    median_exc_atr: number | null
    last_test: string | null
  }
  primary: boolean
}

export interface LevelsFile {
  pair: string
  date: string
  generated_from: string
  anchor_close: number
  atr: number
  atr_pips: number
  zone_pips: number
  timezone: string
  history_days: number
  levels: Level[]
}

export interface EventTarget {
  price: number
  pips: number
  label: string
}

export interface BiasEvent {
  title: string
  country: string
  time: string
  impact: 'High' | 'Medium'
  forecast: string
  previous: string
  signal: string | null
  vote: number
  watch: boolean
  id: string
  expected_pips: number
  targets: { up: EventTarget | null; down: EventTarget | null }
}

export interface BiasWindow {
  direction: 'bullish' | 'bearish'
  start: string
  end: string
  event_ids: string[]
  cause: string
  target_price: number | null
  target_pips: number | null
}

export interface Briefing {
  title: string
  body: string
}

export interface BiasTarget {
  price: number
  type: string
  note: string
  zone_low: number
  zone_high: number
  distance_pips: number
  approach_side: string
}

export interface BiasFile {
  pair: string
  date: string
  window: { start: string; end: string; tz: string }
  bias: 'bullish' | 'bearish' | 'neutral' | null
  confidence: number | null
  score: number | null
  events: BiasEvent[]
  windows: BiasWindow[]
  valid_from: string | null
  valid_until: string | null
  target: BiasTarget | null
  briefing: Briefing | null
  generated_at: string
  disclaimer: string
  error?: string
}

export interface ActualInfo {
  actual: string | number | null
  dir: number | null
  time: string
}

export type ActualsFile = Record<string, ActualInfo>

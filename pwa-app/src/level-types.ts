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

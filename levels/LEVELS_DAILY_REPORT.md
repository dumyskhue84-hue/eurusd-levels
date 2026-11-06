# Daily-updated EURUSD levels -- report

Backtest: 2,133 trading days 2020-01-01 -> 2026-10-30 (warm-up 60d excluded from generation).
Default zone +-15 pips, proximity 1.5xATR, max 10 levels/day, min separation 10 pips, expiry 5d, episode gap 60 min.
All candidates use data <= prior close (no look-ahead). Test = 5m high/low enters zone.

## Tests per day by zone width

| zone (pips) | total tests | distinct/day median | % days >=4 distinct | mean distinct/day |
|---|---|---|---|---|
| 10 | 22,546 | 5 | 86.2% | 5.31 |
| 15 | 24,448 | 6 | 93.7% | 5.90 |
| 25 | 26,807 | 7 | 97.0% | 6.85 |

Verdict on 'at least 4 levels tested a day': see % days >=4 at the 15-pip default zone.

## Tests by type (15-pip zone)

| type | tests | break_rate | dwell_med_min |
|---|---|---|---|
| ATR_DN | 956 | 0.02 | 70 |
| ATR_UP | 961 | 0.03 | 80 |
| H20 | 169 | 0.04 | 85 |
| H5 | 214 | 0.02 | 88 |
| L20 | 189 | 0.04 | 85 |
| L5 | 231 | 0.03 | 105 |
| PC | 3876 | 0.04 | 225 |
| PDH | 487 | 0.04 | 125 |
| PDL | 461 | 0.04 | 120 |
| PIVH | 546 | 0.03 | 120 |
| PIVL | 550 | 0.03 | 85 |
| ROUND | 15020 | 0.04 | 105 |
| VAP | 788 | 0.05 | 98 |

## By year (15-pip zone)

| year | days | median distinct | % days >=4 | mean |
|---|---|---|---|---|
| 2020 | 313 | 6 | 78.9% | 5.32 |
| 2021 | 311 | 6 | 96.8% | 5.63 |
| 2022 | 312 | 7 | 99.0% | 6.92 |
| 2023 | 311 | 6 | 92.9% | 6.06 |
| 2024 | 314 | 5 | 94.0% | 5.54 |
| 2025 | 313 | 6 | 98.4% | 6.27 |
| 2026 | 259 | 5 | 96.1% | 5.50 |

Caveats: zone width dominates hit rates; 2023 sparse in source (~13% fewer rows); HistData volume=0 so VAP is time-at-price; levels are descriptions, not signals.

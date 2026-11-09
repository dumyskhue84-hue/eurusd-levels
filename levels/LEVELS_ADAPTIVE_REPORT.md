# Adaptive ATR ladder -- report

Days 2024-11-10 -> 2026-11-09 (390 trading days). Proximity 2.5xA, min separation 0.15xA, max 10/day. Anchor prior close, A=ATR14 prior day. Rungs 0.4/0.8/1.2/1.6/2.0 A. Headline counts exclude 25-pip ROUND grid.

## zone z=0.15 (half-width 0.15xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 222 | 3 | 2 | 10.4% | 0.78 | 0.02 |
| large 1-2x | 149 | 5 | 4 | 58.4% | 0.74 | 0.06 |
| expansion 2-3x | 17 | 5 | 4 | 64.7% | 0.46 | 0.23 |
| explosive >3x | 2 | 6 | 4 | 100.0% | 0.36 | 0.08 |

Overall (all regimes): median core distinct 3, mean 2.62, % >=4 core 31.5%, median coverage 0.88

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 953 | 0.05 | 0.20 |
| PC | 666 | 0.05 | 0.20 |
| RUNG_UP | 317 | 0.06 | 0.21 |
| RUNG_DN | 289 | 0.07 | 0.21 |
| PIVH | 128 | 0.06 | 0.21 |
| PDL | 125 | 0.04 | 0.20 |
| PDH | 116 | 0.07 | 0.21 |
| PIVL | 115 | 0.03 | 0.20 |
| H5 | 77 | 0.03 | 0.21 |
| L5 | 64 | 0.03 | 0.22 |

## zone z=0.25 (half-width 0.25xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 222 | 4 | 3 | 20.3% | 0.84 | 0.01 |
| large 1-2x | 149 | 6 | 4 | 70.5% | 0.84 | 0.02 |
| expansion 2-3x | 17 | 6 | 4 | 64.7% | 0.56 | 0.09 |
| explosive >3x | 2 | 6 | 4 | 100.0% | 0.45 | 0.00 |

Overall (all regimes): median core distinct 3, mean 3.00, % >=4 core 41.8%, median coverage 1.00

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 1013 | 0.01 | 0.30 |
| PC | 586 | 0.02 | 0.30 |
| RUNG_UP | 368 | 0.03 | 0.30 |
| RUNG_DN | 356 | 0.03 | 0.31 |
| PIVH | 150 | 0.02 | 0.30 |
| PDH | 140 | 0.03 | 0.29 |
| PIVL | 138 | 0.01 | 0.30 |
| PDL | 128 | 0.02 | 0.29 |
| H5 | 103 | 0.01 | 0.30 |
| L5 | 76 | 0.00 | 0.30 |

## zone z=0.4 (half-width 0.4xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 222 | 5 | 3 | 46.8% | 0.84 | 0.00 |
| large 1-2x | 149 | 7 | 5 | 78.5% | 0.85 | 0.01 |
| expansion 2-3x | 17 | 7 | 5 | 70.6% | 0.60 | 0.05 |
| explosive >3x | 2 | 7 | 5 | 100.0% | 0.49 | 0.00 |

Overall (all regimes): median core distinct 4, mean 3.62, % >=4 core 60.3%, median coverage 1.00

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 976 | 0.01 | 0.45 |
| RUNG_UP | 541 | 0.01 | 0.45 |
| PC | 508 | 0.01 | 0.44 |
| RUNG_DN | 504 | 0.00 | 0.45 |
| PIVH | 183 | 0.00 | 0.45 |
| PDH | 162 | 0.01 | 0.44 |
| PDL | 140 | 0.01 | 0.44 |
| H5 | 125 | 0.01 | 0.44 |
| PIVL | 125 | 0.00 | 0.45 |
| L5 | 98 | 0.01 | 0.45 |

Caveats: ATR14 lags day-1 explosions (range is measured vs prior-day A); zones wider than rung spacing merge overlaps -- min separation 0.15A vs spacing 0.4A at z=0.40 zones overlap by design (report 'core' distinct at z=0.40 is an upper bound); 2023 sparse; volume=0.
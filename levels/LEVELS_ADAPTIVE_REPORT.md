# Adaptive ATR ladder -- report

Days 2024-11-10 -> 2026-11-09 (623 trading days). Proximity 2.5xA, min separation 0.15xA, max 10/day. Anchor prior close, A=ATR14 prior day. Rungs 0.4/0.8/1.2/1.6/2.0 A. Headline counts exclude 25-pip ROUND grid.

## zone z=0.15 (half-width 0.15xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 353 | 3 | 2 | 13.0% | 0.83 | 0.02 |
| large 1-2x | 238 | 5 | 4 | 64.3% | 0.79 | 0.07 |
| expansion 2-3x | 28 | 6 | 5 | 82.1% | 0.54 | 0.22 |
| explosive >3x | 4 | 6 | 5 | 100.0% | 0.40 | 0.14 |

Overall (all regimes): median core distinct 3, mean 2.92, % >=4 core 36.3%, median coverage 0.88

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 1481 | 0.05 | 0.20 |
| PC | 1114 | 0.04 | 0.20 |
| RUNG_UP | 617 | 0.05 | 0.21 |
| RUNG_DN | 587 | 0.08 | 0.21 |
| PDL | 232 | 0.06 | 0.20 |
| PIVH | 214 | 0.07 | 0.21 |
| PDH | 211 | 0.08 | 0.20 |
| PIVL | 181 | 0.06 | 0.21 |
| L5 | 139 | 0.05 | 0.21 |
| H5 | 119 | 0.07 | 0.21 |

## zone z=0.25 (half-width 0.25xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 353 | 4 | 3 | 26.1% | 0.90 | 0.01 |
| large 1-2x | 238 | 6 | 4 | 76.1% | 0.90 | 0.02 |
| expansion 2-3x | 28 | 6 | 5 | 82.1% | 0.66 | 0.10 |
| explosive >3x | 4 | 7 | 6 | 100.0% | 0.49 | 0.04 |

Overall (all regimes): median core distinct 3, mean 3.35, % >=4 core 48.2%, median coverage 1.00

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 1561 | 0.01 | 0.30 |
| PC | 990 | 0.02 | 0.30 |
| RUNG_UP | 722 | 0.03 | 0.30 |
| RUNG_DN | 712 | 0.02 | 0.31 |
| PDH | 271 | 0.03 | 0.30 |
| PDL | 234 | 0.03 | 0.30 |
| PIVH | 229 | 0.01 | 0.30 |
| PIVL | 201 | 0.01 | 0.30 |
| L5 | 152 | 0.01 | 0.30 |
| H5 | 151 | 0.01 | 0.30 |

## zone z=0.4 (half-width 0.4xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 353 | 5 | 4 | 52.4% | 0.90 | 0.00 |
| large 1-2x | 238 | 7 | 5 | 85.3% | 0.90 | 0.01 |
| expansion 2-3x | 28 | 7 | 6 | 85.7% | 0.71 | 0.05 |
| explosive >3x | 4 | 8 | 6 | 100.0% | 0.54 | 0.03 |

Overall (all regimes): median core distinct 4, mean 4.01, % >=4 core 66.8%, median coverage 1.00

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 1535 | 0.01 | 0.45 |
| RUNG_UP | 1000 | 0.01 | 0.45 |
| RUNG_DN | 992 | 0.00 | 0.45 |
| PC | 882 | 0.01 | 0.45 |
| PDH | 302 | 0.01 | 0.44 |
| PIVH | 265 | 0.00 | 0.45 |
| PDL | 251 | 0.01 | 0.45 |
| PIVL | 215 | 0.00 | 0.45 |
| L5 | 190 | 0.01 | 0.45 |
| H5 | 181 | 0.01 | 0.44 |

Caveats: ATR14 lags day-1 explosions (range is measured vs prior-day A); zones wider than rung spacing merge overlaps -- min separation 0.15A vs spacing 0.4A at z=0.40 zones overlap by design (report 'core' distinct at z=0.40 is an upper bound); 2023 sparse; volume=0.
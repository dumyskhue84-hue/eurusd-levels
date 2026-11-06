# Adaptive ATR ladder -- report

Days 2020-01-01 -> 2026-10-30 (2,133 trading days). Proximity 2.5xA, min separation 0.15xA, max 10/day. Anchor prior close, A=ATR14 prior day. Rungs 0.4/0.8/1.2/1.6/2.0 A. Headline counts exclude 25-pip ROUND grid.

## zone z=0.15 (half-width 0.15xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 1170 | 4 | 2 | 16.0% | 0.89 | 0.02 |
| large 1-2x | 871 | 6 | 4 | 67.9% | 0.85 | 0.07 |
| expansion 2-3x | 83 | 7 | 5 | 89.2% | 0.64 | 0.19 |
| explosive >3x | 9 | 6 | 5 | 100.0% | 0.45 | 0.38 |

Overall (all regimes): median core distinct 3, mean 3.16, % >=4 core 40.4%, median coverage 0.89

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 5455 | 0.05 | 0.20 |
| PC | 4154 | 0.05 | 0.20 |
| RUNG_UP | 2399 | 0.06 | 0.20 |
| RUNG_DN | 2372 | 0.06 | 0.21 |
| PDL | 836 | 0.05 | 0.20 |
| PDH | 786 | 0.05 | 0.20 |
| PIVL | 767 | 0.05 | 0.20 |
| PIVH | 722 | 0.07 | 0.21 |
| L5 | 542 | 0.05 | 0.21 |
| H5 | 485 | 0.06 | 0.20 |

## zone z=0.25 (half-width 0.25xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 1170 | 4 | 3 | 28.5% | 0.97 | 0.01 |
| large 1-2x | 871 | 6 | 5 | 78.9% | 0.96 | 0.02 |
| expansion 2-3x | 83 | 7 | 5 | 91.6% | 0.77 | 0.10 |
| explosive >3x | 9 | 7 | 6 | 100.0% | 0.54 | 0.28 |

Overall (all regimes): median core distinct 4, mean 3.60, % >=4 core 51.9%, median coverage 1.00

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 6030 | 0.02 | 0.30 |
| PC | 3807 | 0.02 | 0.30 |
| RUNG_UP | 2914 | 0.02 | 0.30 |
| RUNG_DN | 2862 | 0.02 | 0.30 |
| PDL | 944 | 0.02 | 0.30 |
| PDH | 922 | 0.03 | 0.30 |
| PIVL | 849 | 0.01 | 0.30 |
| PIVH | 824 | 0.02 | 0.30 |
| L5 | 647 | 0.01 | 0.30 |
| H5 | 604 | 0.02 | 0.30 |

## zone z=0.4 (half-width 0.4xA)

| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |
|---|---|---|---|---|---|---|
| normal <1x | 1170 | 5 | 4 | 54.4% | 0.97 | 0.00 |
| large 1-2x | 871 | 7 | 5 | 89.8% | 0.97 | 0.01 |
| expansion 2-3x | 83 | 8 | 6 | 96.4% | 0.82 | 0.04 |
| explosive >3x | 9 | 8 | 6 | 100.0% | 0.58 | 0.13 |

Overall (all regimes): median core distinct 4, mean 4.29, % >=4 core 70.7%, median coverage 1.00

| type | tests | break rate | median excursion (ATR) |
|---|---|---|---|
| ROUND | 6609 | 0.01 | 0.44 |
| RUNG_DN | 3993 | 0.00 | 0.45 |
| RUNG_UP | 3942 | 0.01 | 0.45 |
| PC | 3528 | 0.01 | 0.44 |
| PDL | 1005 | 0.00 | 0.44 |
| PIVL | 1001 | 0.00 | 0.45 |
| PDH | 989 | 0.01 | 0.44 |
| PIVH | 927 | 0.01 | 0.45 |
| L5 | 702 | 0.01 | 0.45 |
| H5 | 697 | 0.01 | 0.44 |

Caveats: ATR14 lags day-1 explosions (range is measured vs prior-day A); zones wider than rung spacing merge overlaps -- min separation 0.15A vs spacing 0.4A at z=0.40 zones overlap by design (report 'core' distinct at z=0.40 is an upper bound); 2023 sparse; volume=0.
# EURUSD levels of interest -- lifespan analysis

Data: 5m bars 500,453 from 2020-01-01 17:00:00+00:00 to 2026-10-30 15:55:00+00:00 (UTC).
Daily ATR14 median = 0.0064 (~64 pips). Pivot cluster eps = 0.0032, touch tolerance tol = 0.0016 (0.25*ATR).
HistData M1 volume is 0 / tick_count==5 for every 5m bar, so volume-at-price uses bar counts, not real traded volume.

## Definitions (reproducible)

**A. Pivot levels** -- fractal pivots (5 bars each side) on daily highs/lows, clustered within eps. Lifespan: first pivot date (birth) -> first touch -> last touch, touch = daily close within tol. `episodes` counts return visits separated by >10d; `max_gap_days` is the longest absence; `break_date` = first close >3*tol away after birth; `survived_days` = birth/break span.
**B. VAP / round-number levels** -- 25-pip price histogram (0.95?1.26), peaks >1.15? mean bars; plus human floors 1.00/1.05/1.10/1.15/1.20/1.25 with tol 25 pips. Pre-existing, so birth is left-censored (first touch may predate 2020); lifespan measured touch-to-touch within sample.
**C. Consolidation ranges** -- rolling high-low band (60-day, fallback 30-day / fixed-band if no episodes) with width < 1.5xATR14 or fixed band, merged into episodes, kept if >=5 days. Lifespan = episode start -> end.
**Dwell (5m)** -- for each human/VP level, minutes spent inside +/-25 pips per visit-episode (runs separated by >50 bars away). Median/p90/max reported.

## A. Top pivot levels by pivot count (strongest magnets)

| level | type | pivots | first_pivot | last_pivot | first_touch | last_touch | span_days | touch_days | episodes | max_gap_days | break_date | survived_days |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.0944 | resistance | 12 | 2022-04-21 | 2025-03-18 | 2023-04-17 | 2025-04-06 | 720 | 40 | 13 | 158 | 2023-04-24 | 7 |
| 1.0769 | support | 11 | 2020-02-20 | 2024-10-23 | 2020-03-19 | 2025-03-26 | 1833 | 47 | 15 | 725 | 2020-03-20 | 1 |
| 1.0999 | resistance | 9 | 2020-04-14 | 2025-03-18 | 2020-05-27 | 2024-10-07 | 1594 | 28 | 11 | 652 | 2020-05-28 | 1 |
| 1.1563 | support | 9 | 2025-07-17 | 2026-09-02 | 2025-07-29 | 2026-09-13 | 411 | 23 | 7 | 128 | 2025-07-30 | 1 |
| 1.1651 | resistance | 8 | 2021-10-19 | 2026-09-09 | 2021-10-19 | 2026-09-09 | 1786 | 44 | 11 | 1382 | 2021-10-25 | 6 |
| 1.1912 | resistance | 8 | 2020-08-06 | 2026-02-10 | 2020-08-28 | 2026-02-10 | 1992 | 25 | 7 | 1675 | 2020-08-31 | 3 |
| 1.1134 | resistance | 7 | 2020-03-27 | 2025-04-03 | 2020-03-27 | 2026-10-28 | 2406 | 21 | 8 | 757 | 2020-03-29 | 2 |
| 1.0721 | support | 7 | 2020-04-24 | 2025-03-26 | 2022-04-25 | 2024-11-10 | 930 | 47 | 13 | 215 | 2022-04-26 | 1 |
| 1.0620 | resistance | 6 | 2022-05-04 | 2024-12-06 | 2022-05-04 | 2025-03-04 | 1035 | 21 | 9 | 221 | 2022-05-05 | 1 |
| 1.1746 | support | 6 | 2020-08-12 | 2026-02-19 | 2020-09-16 | 2026-05-12 | 2064 | 50 | 16 | 1383 | 2020-09-17 | 1 |
| 1.1484 | resistance | 6 | 2020-03-08 | 2026-07-15 | 2021-11-10 | 2026-09-21 | 1776 | 12 | 8 | 1256 | 2021-11-15 | 5 |
| 1.1797 | resistance | 6 | 2021-08-13 | 2026-05-06 | 2021-08-13 | 2026-05-08 | 1729 | 30 | 9 | 1384 | 2021-08-17 | 4 |

Full table: `levels/pivot_levels.csv` (all clusters). Lifespan summary (all levels):
- span_days: median 515, p75 1719, max 2482
- touch_days: median 16; episodes: max 18, median 6
- survived_days: median 2 (cap is sample end -> censored if no break)

## B. Round-number and VAP-peak levels

| level | source | first_touch | last_touch | span_days | touch_days | episodes | max_gap_days | break_date | survived_days | bars_inside_5m | dwell_med_min | dwell_p90 | dwell_max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.0000 | round-number | 2022-08-24 | 2022-11-07 | 75 | 10 | 3 | 39 | 2022-08-28 | 4 | 3716 | 400.0 | 1703.0000000000005 | 3930.0 |
| 1.0500 | round-number | 2022-04-27 | 2025-03-03 | 1041 | 42 | 8 | 406 | 2022-05-04 | 7 | 10019 | 330.0 | 1828.000000000001 | 4760.0 |
| 1.0537 | VAP-peak | 2022-04-28 | 2025-02-23 | 1032 | 53 | 8 | 381 | 2022-05-04 | 6 | 12173 | 470.0 | 2087.9999999999995 | 3875.0 |
| 1.0737 | VAP-peak | 2020-03-22 | 2024-11-10 | 1694 | 70 | 15 | 764 | 2020-03-25 | 3 | 15963 | 305.0 | 2609.0 | 5005.0 |
| 1.0862 | VAP-peak | 2020-02-12 | 2025-03-16 | 1859 | 110 | 17 | 663 | 2020-02-27 | 15 | 28385 | 355.0 | 2470.0 | 7005.0 |
| 1.1000 | round-number | 2020-01-24 | 2025-04-09 | 1902 | 61 | 18 | 652 | 2020-01-31 | 7 | 13021 | 465.0 | 2207.999999999998 | 4530.0 |
| 1.1037 | VAP-peak | 2020-01-23 | 2025-04-08 | 1902 | 55 | 13 | 702 | 2020-02-07 | 15 | 10873 | 515.0 | 2158.0 | 4580.0 |
| 1.1137 | VAP-peak | 2020-01-03 | 2026-10-30 | 2492 | 45 | 13 | 605 | 2020-01-23 | 20 | 9772 | 365.0 | 2212.0000000000014 | 7290.0 |
| 1.1237 | VAP-peak | 2020-03-05 | 2026-10-25 | 2425 | 49 | 9 | 659 | 2020-03-08 | 3 | 9661 | 390.0 | 2081.0 | 6710.0 |
| 1.1337 | VAP-peak | 2020-03-10 | 2026-09-30 | 2395 | 60 | 9 | 1143 | 2020-03-12 | 2 | 13766 | 477.5 | 2182.499999999998 | 5940.0 |
| 1.1437 | VAP-peak | 2020-07-17 | 2026-09-22 | 2258 | 38 | 9 | 1209 | 2020-07-21 | 4 | 10452 | 260.0 | 2580.000000000002 | 6665.0 |
| 1.1500 | round-number | 2021-11-10 | 2026-09-20 | 1775 | 28 | 11 | 1257 | 2021-11-15 | 5 | 6545 | 215.0 | 1576.0000000000002 | 4345.0 |
| 1.1637 | VAP-peak | 2020-07-23 | 2026-09-09 | 2239 | 82 | 14 | 1363 | 2020-07-27 | 4 | 20431 | 295.0 | 2332.0 | 10160.0 |
| 1.1737 | VAP-peak | 2020-07-27 | 2026-05-12 | 2115 | 89 | 16 | 1370 | 2020-07-30 | 3 | 21754 | 430.0 | 3080.0 | 7265.0 |
| 1.1787 | VAP-peak | 2020-07-29 | 2026-05-08 | 2109 | 89 | 16 | 1383 | 2020-07-30 | 1 | 20804 | 540.0 | 2530.0 | 10655.0 |
| 1.2000 | round-number | 2020-08-31 | 2026-01-28 | 1976 | 12 | 6 | 1686 | 2020-09-01 | 1 | 2556 | 440.0 | 892.5 | 2835.0 |

VAP bins (25 pips), only peaks listed: share = fraction of all 5m bars in bin.

| bin | center | bars | share |
|---|---|---|---|
| 1.0525-1.0550 | 1.0537 | 6,146 | 1.23% |
| 1.0725-1.0750 | 1.0737 | 9,493 | 1.90% |
| 1.0850-1.0875 | 1.0862 | 14,676 | 2.93% |
| 1.1025-1.1050 | 1.1037 | 5,878 | 1.17% |
| 1.1125-1.1150 | 1.1137 | 5,019 | 1.00% |
| 1.1225-1.1250 | 1.1237 | 5,063 | 1.01% |
| 1.1325-1.1350 | 1.1337 | 7,478 | 1.49% |
| 1.1425-1.1450 | 1.1437 | 5,664 | 1.13% |
| 1.1625-1.1650 | 1.1637 | 11,021 | 2.20% |
| 1.1725-1.1750 | 1.1737 | 11,710 | 2.34% |
| 1.1775-1.1800 | 1.1787 | 10,431 | 2.08% |

Full tables: `levels/vp_round_levels.csv` + `levels/vap_bins.csv`.

## C. Consolidation episodes (>=5d)

Total episodes: 9. Median duration 9d, longest 23d. Past episodes do NOT predict the next -- quote durations as historical description, not expectation.

| start | end | days | low | high | width | center |
|---|---|---|---|---|---|---|
| 2021-12-20 | 2022-01-11 | 23 | 1.1221 | 1.1386 | 0.0165 | 1.1304 |
| 2021-07-30 | 2021-08-10 | 12 | 1.1709 | 1.1908 | 0.0199 | 1.1809 |
| 2021-11-01 | 2021-11-09 | 9 | 1.1513 | 1.1692 | 0.0179 | 1.1603 |
| 2026-01-06 | 2026-01-14 | 9 | 1.1618 | 1.1808 | 0.0190 | 1.1713 |
| 2025-11-24 | 2025-12-02 | 9 | 1.1469 | 1.1666 | 0.0197 | 1.1567 |
| 2026-07-23 | 2026-07-31 | 9 | 1.1353 | 1.1547 | 0.0194 | 1.1450 |
| 2024-06-06 | 2024-06-13 | 8 | 1.0719 | 1.0916 | 0.0197 | 1.0818 |
| 2026-09-08 | 2026-09-15 | 8 | 1.1512 | 1.1711 | 0.0200 | 1.1612 |
| 2024-09-20 | 2024-09-24 | 5 | 1.1002 | 1.1201 | 0.0200 | 1.1102 |

Full table: `levels/consolidation_episodes.csv`.

## Key caveats

1. **Left-censoring:** levels existing before 2020 show first_touch at/near sample start; true lifespan is longer than measured. Pivot `birth` uses first pivot in-sample (not pre-2020 history).
2. **Tolerance drives everything:** halving tol roughly halves touch counts; treat exact lifespan numbers as order-of-magnitude, not precision.
3. **Break ? invalidation:** `break_date` is first excursion >3*tol; many levels are re-tested later (that is why `last_touch` can follow `break_date`).
4. **`survived_days`** is right-censored when no break occurs in-sample.
5. **No volume data** in HistData M1 (volume==0), so VAP reflects time spent at price, not traded size -- a time-at-price, not a true order-flow, map.
6. **2023 sparse** in source: ~13% fewer M1 rows than other full years; that year under-represents touches/episodes.

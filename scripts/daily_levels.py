#!/usr/bin/env python3
"""Daily-updated EURUSD levels: generate from prior close only (no look-ahead),
scan 5m bars for tests, report tests/day incl. % days >= 4.

Defaults: zone +-15 pips (0.0015), proximity 1.5xATR14, max 10 levels/day,
min separation 10 pips, expiry 5 trading days or 2xATR move (tracked),
episode separation 60 min. Sensitivities for 10/15/25 pip zones are computed
from the same candidate stream (zones are just band widths around levels).

Outputs:
  levels/daily_levels.parquet    day x level (kept candidates)
  levels/daily_levels_all.parquet  every candidate before pruning
  levels/daily_tests.csv         one row per test episode
  levels/LEVELS_DAILY_REPORT.md
  charts/10_daily_levels_sample.png, 11_tests_per_day.png, 12_daily_stats.png
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "data" / "processed"
LEVELS = BASE / "levels"
CHARTS = BASE / "charts"
LEVELS.mkdir(exist_ok=True)

PIP = 0.0001
ZONE_DEFAULT = 15 * PIP        # 0.0015
PROX_MULT = 1.5
MAX_LEVELS = 10
MIN_SEP = 10 * PIP
EXPIRY_DAYS = 5
EP_SEP_MIN = 60
WARMUP_DAYS = 60

def load():
    df = pd.read_parquet(PROC / "eurusd_5m.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

def daily(df):
    g = df.set_index("timestamp")
    out = pd.DataFrame({
        "open": g["open"].resample("1D").first(),
        "high": g["high"].resample("1D").max(),
        "low": g["low"].resample("1D").min(),
        "close": g["close"].resample("1D").last(),
        "bars": g["close"].resample("1D").count(),
    }).dropna(subset=["close"])
    # exclude empty weekend days: no bars -> drop
    out = out[out["bars"] >= 50]
    tr = pd.concat([(out["high"] - out["low"]),
                    (out["high"] - out["close"].shift(1)).abs(),
                    (out["low"] - out["close"].shift(1)).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    return out

def cluster(values, eps):
    """Greedy 1-D clustering sorted by price; return cluster means."""
    if len(values) == 0:
        return []
    vals = sorted(values)
    clusters = [[vals[0]]]
    for v in vals[1:]:
        if abs(v - np.mean(clusters[-1])) <= eps:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [float(np.mean(c)) for c in clusters]

def candidates_for_day(day_idx: int, d: pd.DataFrame, df5: pd.DataFrame) -> list[dict]:
    """All candidates for day T using ONLY rows with date < T (prior close)."""
    if day_idx < WARMUP_DAYS:
        return []
    prior = d.iloc[:day_idx]  # up to T-1 inclusive
    t = d.index[day_idx]
    prior_close = float(prior["close"].iloc[-1])
    atr = float(prior["atr14"].iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        atr = float(prior["atr14"].median())
    prox = PROX_MULT * atr
    cands = []
    def add(price, typ, note=""):
        cands.append({"date": t, "level": float(price), "type": typ,
                      "prior_close": prior_close, "atr14": atr, "note": note})
    # 1. prior day / 5-day extremes
    add(float(prior["high"].iloc[-1]), "PDH", "prior day high")
    add(float(prior["low"].iloc[-1]), "PDL", "prior day low")
    add(prior_close, "PC", "prior close")
    add(float(prior["high"].tail(5).max()), "H5", "5d high")
    add(float(prior["low"].tail(5).min()), "L5", "5d low")
    add(float(prior["high"].tail(20).max()), "H20", "20d high")
    add(float(prior["low"].tail(20).min()), "L20", "20d low")
    # 2. rolling fractal pivots (60d window, k=3)
    win = prior.tail(60)
    hi = win["high"].values; lo = win["low"].values
    piv_hi, piv_lo = [], []
    for i in range(3, len(win) - 3):
        if hi[i] == hi[i-3:i+4].max() and (hi[i-3:i+4] == hi[i]).sum() == 1:
            piv_hi.append(float(hi[i]))
        if lo[i] == lo[i-3:i+4].min() and (lo[i-3:i+4] == lo[i]).sum() == 1:
            piv_lo.append(float(lo[i]))
    for v in cluster(piv_hi, 0.3 * atr)[:4]:
        add(v, "PIVH", "60d pivot high")
    for v in cluster(piv_lo, 0.3 * atr)[:4]:
        add(v, "PIVL", "60d pivot low")
    # 3. ATR bands around prior close
    for mlt in (0.5, 1.0):
        add(prior_close + mlt * atr, "ATR_UP", f"PC+{mlt}ATR")
        add(prior_close - mlt * atr, "ATR_DN", f"PC-{mlt}ATR")
    # 4. nearest 10-pip round numbers within 1xATR
    for step in (10 * PIP,):
        cands_round = []
        base = prior_close
        for k in range(-12, 13):
            lv = round(base / step) * step + k * step
            if abs(lv - base) <= 1.0 * atr + 1e-12 and abs(lv - base) > 1e-9:
                cands_round.append(lv)
        for lv in sorted(set(cands_round)):
            add(lv, "ROUND", "10-pip round")
    # 5. 180d time-at-price peaks (top 3 in range)
    start = t - pd.Timedelta(days=180)
    seg = df5[(df5["timestamp"] < t) & (df5["timestamp"] >= start)]
    if len(seg) > 1000:
        bins = np.arange(0.95, 1.26, 0.0025)
        hist, edges = np.histogram(seg["close"].values, bins=bins)
        mean = hist.mean()
        peaks = []
        for i in range(1, len(hist) - 1):
            if hist[i] >= hist[i-1] and hist[i] >= hist[i+1] and hist[i] > 1.15 * mean:
                c = float((edges[i] + edges[i+1]) / 2)
                if abs(c - prior_close) <= prox:
                    peaks.append((int(hist[i]), c))
        for _, c in sorted(peaks, reverse=True)[:3]:
            add(c, "VAP", "180d time-at-price peak")
    # tag proximity
    for c in cands:
        c["dist_atr"] = abs(c["level"] - prior_close) / atr
    return cands

def prune(cands, prior_close, atr, zone=ZONE_DEFAULT, max_levels=MAX_LEVELS):
    prox = PROX_MULT * atr
    near = [c for c in cands if abs(c["level"] - prior_close) <= prox]
    # sort: closest first, stable by type priority
    near.sort(key=lambda c: (abs(c["level"] - prior_close), c["type"]))
    kept = []
    for c in near:
        if any(abs(c["level"] - k["level"]) < MIN_SEP for k in kept):
            continue
        kept.append(c)
        if len(kept) >= max_levels:
            break
    return kept

def build_levels(df5, d, zone=ZONE_DEFAULT):
    all_rows, kept_rows = [], []
    for i, t in enumerate(d.index):
        cands = candidates_for_day(i, d, df5)
        all_rows.extend(cands)
        kept = prune(cands, float(d["close"].iloc[i-1]) if i > 0 else float(d["close"].iloc[0]),
                     float(d["atr14"].iloc[i-1]) if i > 0 and np.isfinite(d["atr14"].iloc[i-1]) else float(d["atr14"].median())) if cands else []
        for c in kept:
            c2 = dict(c)
            c2["zone_half"] = zone
            c2["expiry"] = t + pd.Timedelta(days=EXPIRY_DAYS)
            kept_rows.append(c2)
    all_df = pd.DataFrame(all_rows)
    kept_df = pd.DataFrame(kept_rows)
    return all_df, kept_df

def scan_tests(df5, kept_df, zone=ZONE_DEFAULT, ep_sep_min=EP_SEP_MIN):
    """Detect test episodes: 5m high/low enters [level-zone, level+zone];
    episodes separated by >= ep_sep_min minutes out of zone."""
    if len(kept_df) == 0:
        return pd.DataFrame()
    df5 = df5.copy()
    df5["day"] = df5["timestamp"].dt.floor("1D")
    close_by_day = df5.groupby("day")["close"].apply(list)
    tests = []
    # index bars by day for speed
    by_day = {day: g for day, g in df5.groupby("day")}
    for _, lv in kept_df.iterrows():
        day = lv["date"].normalize() if hasattr(lv["date"], "normalize") else pd.Timestamp(lv["date"]).normalize()
        g = by_day.get(day)
        if g is None:
            continue
        lo_z, hi_z = lv["level"] - zone, lv["level"] + zone
        ts = g["timestamp"].values
        hi = g["high"].values; lo = g["low"].values; cl = g["close"].values
        inside = (hi >= lo_z) & (lo <= hi_z)
        if not inside.any():
            continue
        # episode segmentation
        idx = np.where(inside)[0]
        gaps = np.diff(idx)
        # time gaps in minutes
        tvals = ts[idx].astype("datetime64[ns]").astype(np.int64) / 60_000_000_000
        breaks = np.where(np.diff(tvals) > ep_sep_min)[0]
        segs = []
        start = 0
        for b in list(breaks) + [len(idx) - 1]:
            segs.append(idx[start:b + 1])
            start = b + 1
        for seg in segs:
            first_b, last_b = seg[0], seg[-1]
            first_t = g["timestamp"].iloc[first_b]
            last_t = g["timestamp"].iloc[last_b]
            seg_cl = cl[seg]
            seg_hi = hi[seg]; seg_lo = lo[seg]
            # outcome: close after episode (last bar of seg) vs zone
            last_close = float(cl[last_b])
            if last_close > hi_z + zone:
                outcome = "break_up"
            elif last_close < lo_z - zone:
                outcome = "break_dn"
            else:
                outcome = "reject_or_dwell"
            # break detection: extreme close beyond zone after entry
            max_close = float(seg_cl.max()); min_close = float(seg_cl.min())
            broken = ("break_up" if max_close > hi_z + zone else
                      "break_dn" if min_close < lo_z - zone else outcome)
            if broken != outcome:
                outcome = broken
            # excursion vs level
            fav = max(0.0, (max_close - lv["level"]) if outcome != "break_dn" else (lv["level"] - min_close))
            adv = max(0.0, (lv["level"] - min_close) if outcome != "break_up" else (max_close - lv["level"]))
            tests.append({"date": day, "level": float(lv["level"]), "type": lv["type"],
                          "zone_half": zone, "first_bar": first_t, "last_bar": last_t,
                          "n_bars": int(len(seg)), "outcome": outcome,
                          "max_close": max_close, "min_close": min_close,
                          "dwell_min": int(len(seg) * 5),
                          "excursion_max": float(max(max_close - lv["level"], lv["level"] - min_close))})
    return pd.DataFrame(tests)

def summarise(tests, kept_df, d, zone):
    if len(tests) == 0:
        return pd.DataFrame(), {}
    tests["date"] = pd.to_datetime(tests["date"], utc=True)
    # distinct levels tested per day
    per_day = tests.groupby("date").agg(
        tests=("level", "count"),
        distinct_levels=("level", "nunique"),
        break_rate=("outcome", lambda s: (s.str.startswith("break")).mean()),
        reject_rate=("outcome", lambda s: (s == "reject_or_dwell").mean()),
        dwell_med_min=("dwell_min", "median"),
    ).reset_index()
    # ensure all trading days appear (0 tests)
    all_days = pd.DataFrame({"date": pd.to_datetime(d.index, utc=True)})
    per_day = all_days.merge(per_day, on="date", how="left").fillna({"tests": 0, "distinct_levels": 0})
    for c in ["break_rate", "reject_rate", "dwell_med_min"]:
        per_day[c] = per_day[c].fillna(0.0)
    per_day["zone"] = zone
    return per_day, {"tests": len(tests), "distinct_med": float(per_day["distinct_levels"].median()),
                     "pct_ge4": float((per_day["distinct_levels"] >= 4).mean() * 100)}

def write_report(all_summary, tests_by_zone, kept_df, d):
    L = []
    L.append("# Daily-updated EURUSD levels -- report")
    L.append("")
    L.append(f"Backtest: {len(d):,} trading days {d.index[0].date()} -> {d.index[-1].date()} (warm-up 60d excluded from generation).")
    L.append(f"Default zone +-{ZONE_DEFAULT/PIP:.0f} pips, proximity {PROX_MULT}xATR, max {MAX_LEVELS} levels/day, "
             f"min separation {MIN_SEP/PIP:.0f} pips, expiry {EXPIRY_DAYS}d, episode gap {EP_SEP_MIN} min.")
    L.append("All candidates use data <= prior close (no look-ahead). Test = 5m high/low enters zone.")
    L.append("")
    L.append("## Tests per day by zone width")
    L.append("")
    L.append("| zone (pips) | total tests | distinct/day median | % days >=4 distinct | mean distinct/day |")
    L.append("|---|---|---|---|---|")
    for zone, (per_day, stats) in all_summary.items():
        L.append(f"| {zone/PIP:.0f} | {int(stats['tests']):,} | {stats['distinct_med']:.0f} | {stats['pct_ge4']:.1f}% | {per_day['distinct_levels'].mean():.2f} |")
    L.append("")
    L.append("Verdict on 'at least 4 levels tested a day': see % days >=4 at the 15-pip default zone.")
    L.append("")
    L.append("## Tests by type (15-pip zone)")
    L.append("")
    by_type = tests_by_zone[ZONE_DEFAULT].groupby("type").agg(
        n=("level", "count"), distinct=("level", "nunique"),
        break_rate=("outcome", lambda s: float((s.str.startswith("break")).mean())),
        dwell=("dwell_min", "median")).round(2).reset_index()
    L.append("| type | tests | break_rate | dwell_med_min |")
    L.append("|---|---|---|---|")
    for _, r in by_type.iterrows():
        L.append(f"| {r['type']} | {int(r['n'])} | {r['break_rate']:.2f} | {r['dwell']:.0f} |")
    L.append("")
    L.append("## By year (15-pip zone)")
    L.append("")
    pd15 = all_summary[ZONE_DEFAULT][0].copy()
    pd15["year"] = pd.to_datetime(pd15["date"]).dt.year
    yr = pd15.groupby("year").agg(days=("date", "count"), med=("distinct_levels", "median"),
                                  pct4=("distinct_levels", lambda s: float((s >= 4).mean() * 100)),
                                  mean=("distinct_levels", "mean")).round(2).reset_index()
    L.append("| year | days | median distinct | % days >=4 | mean |")
    L.append("|---|---|---|---|---|")
    for _, r in yr.iterrows():
        L.append(f"| {int(r['year'])} | {int(r['days'])} | {r['med']:.0f} | {r['pct4']:.1f}% | {r['mean']:.2f} |")
    L.append("")
    L.append("Caveats: zone width dominates hit rates; 2023 sparse in source (~13% fewer rows); "
             "HistData volume=0 so VAP is time-at-price; levels are descriptions, not signals.")
    L.append("")
    (LEVELS / "LEVELS_DAILY_REPORT.md").write_text("\n".join(str(x) for x in L), encoding="utf-8")
    print("wrote", LEVELS / "LEVELS_DAILY_REPORT.md")

def charts(d, kept_df, df5, per_day15):
    try:
        from matplotlib.ticker import FuncFormatter
    except Exception:
        pass
    # sample week overlay
    if len(kept_df):
        days = sorted(pd.to_datetime(kept_df["date"], utc=True).unique())
        sample_day = pd.Timestamp(days[len(days)//2]) if len(days) > 10 else pd.Timestamp(days[0])
        sd = sample_day.floor("D")
        g = df5[(df5["timestamp"] >= sd) & (df5["timestamp"] < sd + pd.Timedelta(days=1))]
        lv = kept_df[pd.to_datetime(kept_df["date"], utc=True).dt.floor("D") == sd.floor("D")]
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(g["timestamp"], g["close"], lw=0.7)
        for _, r in lv.iterrows():
            ax.axhline(float(r["level"]), alpha=0.6, label=f"{r['level']:.4f} {r['type']}")
            ax.axhspan(r["level"] - ZONE_DEFAULT, r["level"] + ZONE_DEFAULT, alpha=0.08)
        ax.set_title(f"5m close + kept levels (zone 15 pips), {sd.date()}")
        ax.legend(fontsize=8, ncol=2)
        ax.grid(alpha=0.3)
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(CHARTS / "10_daily_levels_sample.png", dpi=150)
        plt.close(fig)
        print("wrote", CHARTS / "10_daily_levels_sample.png")
    # tests per day histogram
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(per_day15["distinct_levels"].clip(upper=10), bins=range(0, 11))
    ax.set_title("Distinct levels tested per day (15-pip zones)")
    ax.set_xlabel("distinct levels"); ax.set_ylabel("days")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHARTS / "11_tests_per_day.png", dpi=150)
    plt.close(fig)
    print("wrote", CHARTS / "11_tests_per_day.png")
    # rolling % days >=4 (by month)
    s = per_day15.set_index("date")["distinct_levels"]
    m = s.resample("ME").mean()
    pct = (s.resample("ME").apply(lambda x: (x >= 4).mean() * 100))
    fig, ax = plt.subplots(figsize=(14, 5))
    ax2 = ax.twinx()
    ax.bar(m.index, m.values, width=20, label="mean distinct/day")
    ax2.plot(pct.index, pct.values, "r-", label="% days >=4")
    ax.set_title("Daily levels: monthly mean distinct tests + % days >=4")
    ax.set_ylabel("mean distinct"); ax2.set_ylabel("% days >=4")
    fig.tight_layout()
    fig.savefig(CHARTS / "12_daily_stats.png", dpi=150)
    plt.close(fig)
    print("wrote", CHARTS / "12_daily_stats.png")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD: print levels for that day (from prior close)")
    ap.add_argument("--limit-days", type=int, default=None, help="backtest only first N trading days (debug)")
    args = ap.parse_args()

    df5 = load()
    d = daily(df5)
    print(f"5m bars {len(df5):,} daily {len(d)} {d.index[0].date()} -> {d.index[-1].date()}")

    if args.date:
        t = pd.Timestamp(args.date, tz="UTC").normalize()
        idx = d.index.get_indexer([t], method="nearest")[0]
        i = int(idx)
        cands = candidates_for_day(i, d, df5)
        kept = prune(cands, float(d["close"].iloc[i-1]), float(d["atr14"].iloc[i-1]))
        print(f"Levels for {args.date} (from prior close {d['close'].iloc[i-1]:.4f}, ATR {float(d['atr14'].iloc[i-1]):.4f}):")
        for c in kept:
            print(f"  {c['level']:.4f} {c['type']:<6} zone [{c['level']-ZONE_DEFAULT:.4f}, {c['level']+ZONE_DEFAULT:.4f}] ({c['note']})")
        if not kept:
            print("  (no levels -- warm-up or no candidates in range)")
        return

    if args.limit_days:
        d = d.iloc[:args.limit_days]

    all_df, kept_df = build_levels(df5, d)
    print(f"days with levels: {kept_df['date'].nunique() if len(kept_df) else 0} / {len(d)}")
    print(f"kept level-days: {len(kept_df):,}")
    all_df.to_parquet(LEVELS / "daily_levels_all.parquet", index=False)
    kept_df.to_parquet(LEVELS / "daily_levels.parquet", index=False)

    summary = {}
    tests_by_zone = {}
    for zone in (10 * PIP, 15 * PIP, 25 * PIP):
        tests = scan_tests(df5, kept_df, zone=zone)
        tests_by_zone[zone] = tests
        per_day, stats = summarise(tests, kept_df, d, zone)
        summary[zone] = (per_day, stats)
        print(f"zone {zone/PIP:.0f} pips: tests={stats.get('tests',0):,} median distinct/day={stats.get('distinct_med',0):.0f} pct>=4={stats.get('pct_ge4',0):.1f}%")
        per_day.to_csv(LEVELS / f"tests_per_day_{int(zone/PIP)}pips.csv", index=False)
    tests_by_zone[ZONE_DEFAULT].to_csv(LEVELS / "daily_tests.csv", index=False)
    write_report(summary, tests_by_zone, kept_df, d)
    charts(d, kept_df, df5, summary[ZONE_DEFAULT][0])

if __name__ == "__main__":
    main()

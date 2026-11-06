#!/usr/bin/env python3
"""Adaptive ATR ladder for big-move days.
Levels generated from prior close only. Anchor = prior close, A = ATR14(T-1).
Zone half-width = z*A per day (z swept over 0.15/0.25/0.40). Ladder rungs:
anchor +- k*A for k = 0.4/0.8/1.2/1.6/2.0. Plus PDH/PDL, 5-day extremes,
60-day pivot highs/lows. 25-pip ROUND only as secondary, excluded from headline.
Proximity <= 2.5*A, min separation 0.15*A, max 10 kept/day.
Test: 5m high/low enters level+-zone (per-day zone). Episodes >=60min apart.
Regimes by that day's range / that day's A: normal <1x, large 1-2x,
expansion 2-3x, explosive >3x. Coverage = fraction of day high-low span
covered by union of tested rungs +-zone. Break: episode-end close >=1 zone
beyond level. Outputs: levels/daily_levels_adaptive.parquet,
levels/daily_tests_adaptive.csv, levels/LEVELS_ADAPTIVE_REPORT.md,
charts/13_adaptive_sample.png, 14_adaptive_regime.png
"""
from __future__ import annotations
import argparse
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
PROX_MULT = 2.5
MAX_LEVELS = 10
MIN_SEP_MULT = 0.15
WARMUP = 60
EP_SEP_MIN = 60
RUNGS = [0.4, 0.8, 1.2, 1.6, 2.0]

def load():
    df = pd.read_parquet(PROC / "eurusd_5m.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def daily(df):
    g = df.set_index("timestamp")
    out = pd.DataFrame({
        "high": g["high"].resample("1D").max(),
        "low": g["low"].resample("1D").min(),
        "close": g["close"].resample("1D").last(),
        "bars": g["close"].resample("1D").count(),
    }).dropna(subset=["close"])
    out = out[out["bars"] >= 50]
    tr = pd.concat([(out["high"] - out["low"]),
                    (out["high"] - out["close"].shift(1)).abs(),
                    (out["low"] - out["close"].shift(1)).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["range"] = out["high"] - out["low"]
    return out

def cluster(values, eps):
    if len(values) == 0:
        return []
    vals = sorted(values)
    cl = [[vals[0]]]
    for v in vals[1:]:
        if abs(v - np.mean(cl[-1])) <= eps:
            cl[-1].append(v)
        else:
            cl.append([v])
    return [float(np.mean(c)) for c in cl]

def candidates(i, d, df5):
    if i < WARMUP:
        return [], None, None
    prior = d.iloc[:i]
    t = d.index[i]
    pc = float(prior["close"].iloc[-1])
    A = float(prior["atr14"].iloc[-1])
    if not np.isfinite(A) or A <= 0:
        A = float(prior["atr14"].median())
    prox = PROX_MULT * A
    cands = []
    def add(price, typ, note=""):
        cands.append({"date": t, "level": float(price), "type": typ,
                      "prior_close": pc, "A": A, "note": note})
    for k in RUNGS:
        add(pc + k * A, "RUNG_UP", f"PC+{k}A")
        add(pc - k * A, "RUNG_DN", f"PC-{k}A")
    add(float(prior["high"].iloc[-1]), "PDH", "prior day high")
    add(float(prior["low"].iloc[-1]), "PDL", "prior day low")
    add(pc, "PC", "prior close")
    add(float(prior["high"].tail(5).max()), "H5", "5d high")
    add(float(prior["low"].tail(5).min()), "L5", "5d low")
    win = prior.tail(60)
    hi = win["high"].values; lo = win["low"].values
    ph, pl = [], []
    for j in range(3, len(win) - 3):
        if hi[j] == hi[j-3:j+4].max() and (hi[j-3:j+4] == hi[j]).sum() == 1:
            ph.append(float(hi[j]))
        if lo[j] == lo[j-3:j+4].min() and (lo[j-3:j+4] == lo[j]).sum() == 1:
            pl.append(float(lo[j]))
    for v in cluster(ph, 0.3 * A)[:4]:
        add(v, "PIVH", "60d pivot high")
    for v in cluster(pl, 0.3 * A)[:4]:
        add(v, "PIVL", "60d pivot low")
    for k in range(-2, 3):  # 25-pip grid within 1xA, secondary
        lv = round(pc / 0.0025) * 0.0025 + k * 0.0025
        if 0 < abs(lv - pc) <= 1.0 * A + 1e-12:
            add(lv, "ROUND", "25-pip")
    return cands, pc, A

def prune(cands, pc, A):
    near = [c for c in cands if abs(c["level"] - pc) <= PROX_MULT * A]
    near.sort(key=lambda c: (abs(c["level"] - pc), c["type"]))
    kept = []
    for c in near:
        if any(abs(c["level"] - k["level"]) < MIN_SEP_MULT * A for k in kept):
            continue
        kept.append(c)
        if len(kept) >= MAX_LEVELS:
            break
    return kept

def regime(range_atr):
    if range_atr < 1: return "normal <1x"
    if range_atr < 2: return "large 1-2x"
    if range_atr < 3: return "expansion 2-3x"
    return "explosive >3x"

def build(df5, d):
    all_rows, kept_rows = [], []
    for i, t in enumerate(d.index):
        cands, pc, A = candidates(i, d, df5)
        all_rows.extend(cands)
        kept = prune(cands, pc, A) if cands else []
        for c in kept:
            kept_rows.append(dict(c))
    return pd.DataFrame(all_rows), pd.DataFrame(kept_rows)

def scan_day(g, level, A, z):
    zone = z * A
    lo_z, hi_z = level - zone, level + zone
    hi = g["high"].values; lo = g["low"].values; cl = g["close"].values
    inside = (hi >= lo_z) & (lo <= hi_z)
    if not inside.any():
        return [], (lo_z, hi_z)
    idx = np.where(inside)[0]
    tvals = g["timestamp"].values[idx].astype("datetime64[ns]").astype(np.int64) / 60_000_000_000
    breaks = np.where(np.diff(tvals) > EP_SEP_MIN)[0]
    eps = []
    start = 0
    for b in list(breaks) + [len(idx) - 1]:
        eps.append(idx[start:b+1]); start = b + 1
    out = []
    for seg in eps:
        fb, lb = seg[0], seg[-1]
        last_close = float(cl[lb])
        if last_close > hi_z + zone: oc = "break_up"
        elif last_close < lo_z - zone: oc = "break_dn"
        else: oc = "reject_or_dwell"
        out.append({"first_bar": g["timestamp"].iloc[fb], "last_bar": g["timestamp"].iloc[lb],
                    "n_bars": int(len(seg)), "outcome": oc,
                    "max_close": float(cl[seg].max()), "min_close": float(cl[seg].min()),
                    "dwell_min": int(len(seg) * 5)})
    return out, (lo_z, hi_z)

def analyse(df5, d, kept_df, z):
    df5 = df5.copy()
    df5["day"] = df5["timestamp"].dt.floor("1D")
    by_day = {day: g for day, g in df5.groupby("day")}
    tests = []
    daily_rows = []
    kept_by_day = {day: grp for day, grp in kept_df.groupby(pd.to_datetime(kept_df["date"], utc=True).dt.floor("D"))} if len(kept_df) else {}
    for i, (t, row) in enumerate(d.iterrows()):
        day = pd.Timestamp(t).floor("D")
        A_prior = float(d["atr14"].iloc[i-1]) if i > 0 and np.isfinite(d["atr14"].iloc[i-1]) else float(d["atr14"].median())
        rng = float(row["range"]); rax = rng / A_prior if A_prior > 0 else np.nan
        reg = regime(rax) if np.isfinite(rax) else "unknown"
        g = by_day.get(day)
        day_tests = []
        covered = []  # intervals of tested rungs
        if g is not None and len(kept_by_day):
            grp = kept_by_day.get(day)
            if grp is not None:
                for _, lv in grp.iterrows():
                    A = float(lv["A"])
                    eps, (lo_z, hi_z) = scan_day(g, float(lv["level"]), A, z)
                    if not eps:
                        continue
                    covered.append((lo_z, hi_z))
                    for e in eps:
                        fav = max(0.0, (e["max_close"] - float(lv["level"])) if e["outcome"] != "break_dn" else (float(lv["level"]) - e["min_close"]))
                        adv = max(0.0, (float(lv["level"]) - e["min_close"]) if e["outcome"] != "break_up" else (e["max_close"] - float(lv["level"])))
                        tests.append({"date": day, "level": float(lv["level"]), "type": lv["type"],
                                      "A": A, "zone": z * A, "z": z, **e,
                                      "fav_atr": fav / A, "adv_atr": adv / A,
                                      "exc_atr": max(e["max_close"] - float(lv["level"]), float(lv["level"]) - e["min_close"]) / A,
                                      "regime": reg, "range_atr": rax})
                        day_tests.append(e)
        # coverage: union of tested intervals over [day low, day high]
        cov = 0.0
        if covered and rng > 0:
            day_lo, day_hi = float(row["low"]), float(row["high"])
            clipped = sorted([(max(a, day_lo), min(b, day_hi)) for a, b in covered if max(a, day_lo) < min(b, day_hi)])
            merged = []
            for a, b in clipped:
                if merged and a <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:
                    merged.append((a, b))
            cov = sum(b - a for a, b in merged) / rng if rng > 0 else 0.0
        distinct = len({round(x["level"] if "level" in x else 0, 6) for x in day_tests}) if False else None
        # distinct levels tested = count of kept groups with eps; approximated via tests
        daily_rows.append({"date": day, "A_prior": A_prior, "range": rng, "range_atr": rax,
                           "regime": reg, "coverage": cov, "n_tests": len(day_tests)})
    day_df = pd.DataFrame(daily_rows).merge(
        pd.DataFrame(tests).groupby("date")["level"].nunique().rename("distinct"),
        left_on="date", right_index=True, how="left").fillna({"distinct": 0})
    # tests without ROUND in headline
    tests_df = pd.DataFrame(tests)
    core = tests_df[tests_df["type"] != "ROUND"] if len(tests_df) else tests_df
    core_distinct = core.groupby("date")["level"].nunique() if len(core) else pd.Series(dtype=float)
    day_df["distinct_core"] = day_df["date"].map(core_distinct).fillna(0)
    day_df["zone"] = z
    return tests_df, day_df

def write_report(by_z, kept_df, d):
    L = []
    L.append("# Adaptive ATR ladder -- report")
    L.append("")
    L.append(f"Days {d.index[0].date()} -> {d.index[-1].date()} ({len(d):,} trading days). "
             "Proximity 2.5xA, min separation 0.15xA, max 10/day. Anchor prior close, A=ATR14 prior day. "
             "Rungs 0.4/0.8/1.2/1.6/2.0 A. Headline counts exclude 25-pip ROUND grid.")
    L.append("")
    for z in sorted(by_z):
        tests, day_df = by_z[z]
        L.append(f"## zone z={z} (half-width {z}xA)")
        L.append("")
        L.append("| regime | days | median distinct (all) | median distinct (core) | % >=4 core | mean coverage | break rate |")
        L.append("|---|---|---|---|---|---|---|")
        t2 = tests.copy() if len(tests) else pd.DataFrame(columns=["regime", "outcome"])
        for reg in ["normal <1x", "large 1-2x", "expansion 2-3x", "explosive >3x"]:
            s = day_df[day_df["regime"] == reg]
            if len(s) == 0:
                continue
            br = float((t2[t2["regime"] == reg]["outcome"].str.startswith("break")).mean()) if len(t2[t2["regime"] == reg]) else float("nan")
            L.append(f"| {reg} | {len(s)} | {s['distinct'].median():.0f} | {s['distinct_core'].median():.0f} | "
                     f"{(s['distinct_core'] >= 4).mean()*100:.1f}% | {s['coverage'].mean():.2f} | {br:.2f} |")
        s_all = day_df
        L.append("")
        L.append(f"Overall (all regimes): median core distinct {s_all['distinct_core'].median():.0f}, "
                 f"mean {s_all['distinct_core'].mean():.2f}, % >=4 core {(s_all['distinct_core'] >= 4).mean()*100:.1f}%, "
                 f"median coverage {s_all['coverage'].median():.2f}")
        L.append("")
        bt = t2.groupby("type").agg(n=("level", "count"),
                                     br=("outcome", lambda x: float((x.str.startswith("break")).mean())),
                                     exc=("exc_atr", "median")).round(2).reset_index()
        L.append("| type | tests | break rate | median excursion (ATR) |")
        L.append("|---|---|---|---|")
        for _, r in bt.sort_values("n", ascending=False).iterrows():
            L.append(f"| {r['type']} | {int(r['n'])} | {r['br']:.2f} | {r['exc']:.2f} |")
        L.append("")
    L.append("Caveats: ATR14 lags day-1 explosions (range is measured vs prior-day A); zones wider than rung spacing merge overlaps -- "
             "min separation 0.15A vs spacing 0.4A at z=0.40 zones overlap by design (report 'core' distinct at z=0.40 is an upper bound); "
             "2023 sparse; volume=0.")
    (LEVELS / "LEVELS_ADAPTIVE_REPORT.md").write_text("\n".join(str(x) for x in L), encoding="utf-8")
    print("wrote", LEVELS / "LEVELS_ADAPTIVE_REPORT.md")

def charts(df5, d, kept_df, day_df_z25, tests_z25):
    # expansion vs normal sample days
    cand = day_df_z25[day_df_z25["regime"].isin(["normal <1x", "expansion 2-3x", "explosive >3x"])].copy()
    chosen = []
    for reg in ["normal <1x", "expansion 2-3x", "explosive >3x"]:
        s = cand[cand["regime"] == reg]
        if len(s):
            s = s.sort_values("range_atr")
            chosen.append(s.iloc[len(s)//2]["date"])
    fig, axes = plt.subplots(len(chosen), 1, figsize=(14, 4 * len(chosen)), sharex=False)
    axes = axes if isinstance(axes, (list, np.ndarray)) else [axes]
    for ax, day in zip(axes, chosen):
        day = pd.Timestamp(day)
        g = df5[(df5["timestamp"] >= day.floor("D")) & (df5["timestamp"] < day.floor("D") + pd.Timedelta(days=1))]
        lv = kept_df[pd.to_datetime(kept_df["date"], utc=True).dt.floor("D") == day.floor("D")]
        ax.plot(g["timestamp"], g["close"], lw=0.8, label="5m close")
        if len(lv):
            A = float(lv["A"].iloc[0]); z = 0.25
            for _, r in lv.iterrows():
                ax.axhline(float(r["level"]), alpha=0.5, label=f"{r['level']:.4f} {r['type']}")
                ax.axhspan(r["level"] - z * float(r["A"]), r["level"] + z * float(r["A"]), alpha=0.07)
        row = day_df_z25[day_df_z25["date"] == day]
        ax.set_title(f"{day.date()} {row['regime'].iloc[0] if len(row) else ''} range_atr={row['range_atr'].iloc[0]:.2f} A={float(row['A_prior'].iloc[0]):.4f}" if len(row) else f"{day.date()}")
        ax.legend(fontsize=7, ncol=3); ax.grid(alpha=0.3)
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.tight_layout()
    fig.savefig(CHARTS / "13_adaptive_sample.png", dpi=150)
    plt.close(fig)
    print("wrote", CHARTS / "13_adaptive_sample.png")
    # regime box: distinct core by regime
    fig, ax = plt.subplots(figsize=(10, 5))
    regs = ["normal <1x", "large 1-2x", "expansion 2-3x", "explosive >3x"]
    data = [day_df_z25[day_df_z25["regime"] == r]["distinct_core"] for r in regs]
    ax.boxplot(data, tick_labels=regs)
    ax.set_title("Core distinct levels tested/day by range regime (z=0.25)")
    ax.set_ylabel("distinct core / day"); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHARTS / "14_adaptive_regime.png", dpi=150)
    plt.close(fig)
    print("wrote", CHARTS / "14_adaptive_regime.png")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-days", type=int, default=None)
    args = ap.parse_args()
    df5 = load(); d = daily(df5)
    print(f"5m {len(df5):,} daily {len(d)} {d.index[0].date()} -> {d.index[-1].date()}")
    if args.limit_days:
        d = d.iloc[:args.limit_days]
    all_df, kept_df = build(df5, d)
    print(f"kept {len(kept_df):,} over {kept_df['date'].nunique() if len(kept_df) else 0} days")
    all_df.to_parquet(LEVELS / "daily_levels_adaptive_all.parquet", index=False)
    kept_df.to_parquet(LEVELS / "daily_levels_adaptive.parquet", index=False)
    by_z = {}
    for z in (0.15, 0.25, 0.40):
        tests, day_df = analyse(df5, d, kept_df, z)
        by_z[z] = (tests, day_df)
        core = day_df["distinct_core"]
        print(f"z={z}: tests={len(tests):,} core median {core.median():.0f} mean {core.mean():.2f} pct>=4 {(core>=4).mean()*100:.1f}% med coverage {day_df['coverage'].median():.2f}")
        day_df.to_csv(LEVELS / f"adaptive_per_day_z{z}.csv", index=False)
    by_z[0.25][0].to_csv(LEVELS / "daily_tests_adaptive.csv", index=False)
    write_report(by_z, kept_df, d)
    charts(df5, d, kept_df, by_z[0.25][1], by_z[0.25][0])

if __name__ == "__main__":
    main()

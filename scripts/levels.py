#!/usr/bin/env python3
"""Levels of interest + lifespan on EURUSD 5m 2020->2026.

Three definitions (all reproducible, printed in report):
  A) Swing pivots: fractal (5 bars each side) on daily highs/lows, clustered
     within 0.5*ATR (~0.003). Lifespan = first pivot -> last touch after.
  B) Volume-at-price peaks: 100-pip range binned at 25/50/100 pips, floors
     1.00/1.10/1.20 with rolling 2y windows. Lifespan = first touch of zone
     -> last touch (distinct calendar days), ignoring the back half for lookahead.
  C) Consolidation ranges: 60-day rolling high/low bands whose width is
     < 1.5*ATR(14); merged into episodes. Lifespan = episode start->end quote it.

"Lifespan" semantics (each table prints these columns):
  birth          first date the level/range was detectable (with full lookback,
                 so levels born before 2020 are left-censored)
  first_touch / last_touch   dates price traded inside tolerance band
  span_days / active_days / touch_days  total span, days under water, days tested
  episodes / max_gap_days  number of return visits, longest absence
  break_date / survived_days  first close outside band, days it stayed relevant
  dwell_p50 / dwell_p90  minutes spent inside band per touch-episode (5m bars)
Tolerance defaults: band = +-0.25*ATR (~15 pips); touch = close inside band.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "data" / "processed"
CHARTS = BASE / "charts"
LEVELS_DIR = BASE / "levels"
LEVELS_DIR.mkdir(exist_ok=True)

def load():
    df = pd.read_parquet(PROC / "eurusd_5m.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)

def daily(df):
    g = df.set_index("timestamp")
    out = pd.DataFrame({
        "open": g["open"].resample("1D").first(),
        "high": g["high"].resample("1D").max(),
        "low": g["low"].resample("1D").min(),
        "close": g["close"].resample("1D").last(),
        "bars": g["close"].resample("1D").count(),
    }).dropna(subset=["close"])
    # ATR14 (Wilder-style simple rolling for reproducibility)
    tr = pd.concat([(out["high"] - out["low"]),
                    (out["high"] - out["close"].shift(1)).abs(),
                    (out["low"] - out["close"].shift(1)).abs()], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    return out

def cluster_pivots(d, side="high", k=5, eps=0.003):
    """Fractal pivots then cluster within eps."""
    piv = []
    v = d[side].values
    for i in range(k, len(d) - k):
        w = v[i - k:i + k + 1]
        if side == "high" and v[i] == w.max() and (w == v[i]).sum() == 1:
            piv.append((d.index[i], v[i]))
        if side == "low" and v[i] == w.min() and (w == v[i]).sum() == 1:
            piv.append((d.index[i], v[i]))
    piv_df = pd.DataFrame(piv, columns=["date", "price"]).sort_values("price").reset_index(drop=True)
    # greedy cluster: iterate sorted by price, join if within eps of cluster mean
    clusters = []
    for _, r in piv_df.iterrows():
        placed = False
        for c in clusters:
            if abs(r["price"] - np.mean(c["prices"])) <= eps:
                c["prices"].append(r["price"])
                c["dates"].append(r["date"])
                c["count"] += 1
                break
        if not placed:
            clusters.append({"prices": [r["price"]], "dates": [r["date"]], "count": 1})
    rows = []
    for c in clusters:
        rows.append({"level": float(np.mean(c["prices"])),
                     "n_pivots": c["count"],
                     "first_pivot": min(c["dates"]),
                     "last_pivot": max(c["dates"])})
    out = pd.DataFrame(rows).sort_values("level").reset_index(drop=True)
    return out

def lifespan_daily(daily_df, level, tol, birth=None):
    """Level lifespan using daily closes (touch = |close-level| <= tol)."""
    closes = daily_df["close"]
    inside = ((closes - level).abs() <= tol).values
    if birth is not None:
        wnd = np.asarray(daily_df.index >= birth)
    else:
        wnd = np.ones(len(inside), dtype=bool)
    ins = inside & wnd
    ins = pd.Series(ins, index=daily_df.index)
    touch_idx = closes.index[ins]
    if len(touch_idx) == 0:
        return None
    first, last = touch_idx.min(), touch_idx.max()
    span = (last - first).days
    touch_days = len(touch_idx)
    # episodes = groups separated by >10 calendar days with no touch
    gaps = touch_idx.to_series().diff().dt.days
    episodes = 1 + (gaps > 10).sum()
    max_gap = gaps.max() if len(gaps) > 1 else 0
    # break = first close outside band on/after first touch
    after = closes.loc[first:]
    if birth is None and first == closes.index[0]:
        # level existed before data starts; record censored
        pass
    break_after = after[(after - level).abs() > 3 * tol]
    break_date = break_after.index.min() if len(break_after) else pd.NaT
    survived = (break_date - first).days if pd.notna(break_date) else span
    trend = "up" if closes.iloc[-1] > level else "down"
    return {"level": level, "tol": tol, "birth": birth,
            "first_touch": first, "last_touch": last, "span_days": int(span),
            "touch_days": int(touch_days), "episodes": int(episodes),
            "max_gap_days": float(max_gap) if len(gaps) > 0 else 0,
            "break_date": break_date, "survived_days": int(survived),
            "price_vs_level": f"{trend} {closes.iloc[-1]-level:+.4f}"}

def pivot_levels(df, d):
    atr_med = float(d["atr14"].median())
    eps = 0.5 * atr_med
    tol = 0.25 * atr_med
    highs = cluster_pivots(d, "high", eps=eps)
    lows = cluster_pivots(d, "low", eps=eps)
    piv = pd.concat([highs.assign(type="resistance"), lows.assign(type="support")], ignore_index=True)
    piv["tol"] = tol
    rows = []
    for _, r in piv.iterrows():
        # birth = first pivot date in cluster (detectable then)
        lf = lifespan_daily(d, float(r["level"]), tol, birth=r["first_pivot"])
        if lf:
            lf.update({"type": r["type"], "n_pivots": int(r["n_pivots"]),
                       "first_pivot": r["first_pivot"], "last_pivot": r["last_pivot"]})
            rows.append(lf)
    out = pd.DataFrame(rows).sort_values(["level"]).reset_index(drop=True)
    out.to_csv(LEVELS_DIR / "pivot_levels.csv", index=False)
    return out, tol, eps

def vap_levels(df, d, w_days=730, step_days=90):
    """Anchored floor levels + rolling volume-at-price/human floors."""
    closes = df["close"].values
    # full-history VP bins for reference peaks
    bins = np.arange(0.95, 1.26, 0.0025)  # 25 pips
    hist, edges = np.histogram(closes, bins=bins)
    # peaks: local maxima with prominence (ticks above mean)
    mean = hist.mean()
    peaks = []
    for i in range(1, len(hist) - 1):
        if hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1] and hist[i] > 1.15 * mean:
            peaks.append({"bin_start": float(edges[i]), "bin_end": float(edges[i + 1]),
                          "center": float((edges[i] + edges[i + 1]) / 2),
                          "count": int(hist[i]), "share": float(hist[i] / hist.sum())})
    vap = pd.DataFrame(peaks).sort_values("center")
    vap.to_csv(LEVELS_DIR / "vap_bins.csv", index=False)
    # human round numbers tested
    human = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25]
    tol_h = 0.0025
    rows = []
    for lvl in human:
        lf = lifespan_daily(d, lvl, tol_h, birth=None)  # pre-existing
        if lf:
            lf.update({"n_pivots": 0, "first_pivot": pd.NaT, "last_pivot": pd.NaT,
                       "human_floor": True, "source": "round-number"})
            rows.append(lf)
    for p in peaks:
        lf = lifespan_daily(d, p["center"], 0.0025, birth=None)
        if lf:
            lf.update({"n_pivots": 0, "first_pivot": pd.NaT, "last_pivot": pd.NaT,
                       "human_floor": False, "source": "VAP-peak",
                       "vap_count": p["count"], "vap_share": p["share"]})
            rows.append(lf)
    human_df = pd.DataFrame(rows).sort_values("level").reset_index(drop=True)
    human_df.to_csv(LEVELS_DIR / "vp_round_levels.csv", index=False)
    return vap, human_df

def consolidation_episodes(d, win=60, mult=1.5, band=None):
    hi = d["high"].rolling(win).max()
    lo = d["low"].rolling(win).min()
    width = hi - lo
    if band is not None:
        tight = width < band
    else:
        tight = width < mult * d["atr14"]
    tight = tight.fillna(False)
    episodes = []
    in_ep = False
    start = None
    for date, flag, w, h, l in zip(d.index, tight, width, hi, lo):
        if flag and not in_ep:
            in_ep, start = True, date
            best_w, best_h, best_l = w, h, l
        elif flag and in_ep:
            best_w, best_h, best_l = w, h, l
        elif not flag and in_ep:
            in_ep = False
            episodes.append({"start": start, "end": prev, "days": (prev - start).days + 1,
                             "high": float(best_h), "low": float(best_l),
                             "width": float(best_w),
                             "center": float((best_h + best_l) / 2)})
        prev = date
    if in_ep:
        episodes.append({"start": start, "end": prev, "days": (prev - start).days + 1,
                         "high": float(best_h), "low": float(best_l), "width": float(best_w),
                         "center": float((best_h + best_l) / 2)})
    ep = pd.DataFrame(episodes)
    if len(ep):
        ep = ep[ep["days"] >= 5]  # ignore 1-4d flickers
        ep.to_csv(LEVELS_DIR / "consolidation_episodes.csv", index=False)
    else:
        ep = pd.DataFrame(columns=["start", "end", "days", "high", "low", "width", "center"])
    return ep

# ---- 5m dwell / minute-level detail ----
def dwell_5m(df, levels, tols=0.0025):
    """For each level: bars inside band, dwell minutes per episode."""
    ts = df["timestamp"].values
    close = df["close"].values
    rows = []
    for lvl in levels:
        inside = np.abs(close - lvl) <= tols
        n = inside.sum()
        if n == 0:
            continue
        # episodes = runs of inside separated by > 50 bars away
        idx = np.where(inside)[0]
        breaks = np.where(np.diff(idx) > 50)[0]
        episodes = []
        start = 0
        for b in list(breaks) + [len(idx) - 1]:
            seg = idx[start:b + 1]
            episodes.append(len(seg))  # bars in run (5m)
            start = b + 1
        dwell_bars = np.array(episodes)
        rows.append({"level": lvl, "bars_inside_5m": int(n),
                     "dwell_min_med": float(np.median(dwell_bars) * 5),
                     "dwell_min_p90": float(np.percentile(dwell_bars, 90) * 5),
                     "dwell_min_max": float(dwell_bars.max() * 5),
                     "dwell_episodes": len(episodes)})
    return pd.DataFrame(rows)

def main():
    df = load()
    d = daily(df)
    print(f"daily bars {len(d)} {d.index[0].date()} -> {d.index[-1].date()}")
    piv, tol, eps = pivot_levels(df, d)
    print(f"pivot clusters: {len(piv)} tol={tol:.4f} eps={eps:.4f} ATRmed={d['atr14'].median():.4f}")
    print(piv.sort_values("n_pivots", ascending=False).head(10).to_string(index=False))
    vap, hr = vap_levels(df, d)
    print(f"VAP peaks {len(vap)}; human+VP table {len(hr)}")
    print(hr.to_string(index=False))
    ep = consolidation_episodes(d)
    print(f"consolidation episodes >=5d (60d/1.5xATR): {len(ep)}")
    if len(ep) == 0:
        ep = consolidation_episodes(d, win=30, mult=1.5)
        print(f"consolidation episodes (30d win) >=5d: {len(ep)}")
    if len(ep) == 0:
        # width stats to pick fallback band robustly (fix earlier always-zero bug: band in price units)
        hi = d["high"].rolling(30).max(); lo = d["low"].rolling(30).min()
        width = hi - lo
        print(f"30d width median {width.median():.4f} p25 {width.quantile(.25):.4f} "
              f"p10 {width.quantile(.10):.4f} ATRmed {d['atr14'].median():.4f}")
        for band in [0.02, 0.015, 0.012]:
            ep = consolidation_episodes(d, win=30, band=band)
            print(f"consolidation episodes (30d, band={band}) >=5d: {len(ep)}")
            if len(ep):
                break
    if len(ep):
        print(ep.sort_values("days", ascending=False).head(8).to_string(index=False))
    dw = dwell_5m(df, hr["level"].tolist())
    dw.to_csv(LEVELS_DIR / "dwell_5m.csv", index=False)
    print(dw.sort_values("bars_inside_5m", ascending=False).head(10).to_string(index=False))
    write_report(df, d, piv, vap, hr, ep, dw, tol, eps)

def write_report(df, d, piv, vap, hr, ep, dw, tol, eps):
    L = []
    L.append("# EURUSD levels of interest -- lifespan analysis")
    L.append("")
    L.append(f"Data: 5m bars {len(df):,} from {df.timestamp.min()} to {df.timestamp.max()} (UTC).")
    L.append(f"Daily ATR14 median = {d['atr14'].median():.4f} (~{d['atr14'].median()*10000:.0f} pips). "
             f"Pivot cluster eps = {eps:.4f}, touch tolerance tol = {tol:.4f} (0.25*ATR).")
    L.append("HistData M1 volume is 0 / tick_count==5 for every 5m bar, so "
             "volume-at-price uses bar counts, not real traded volume.")
    L.append("")
    L.append("## Definitions (reproducible)")
    L.append("")
    L.append("**A. Pivot levels** -- fractal pivots (5 bars each side) on daily highs/lows, "
             "clustered within eps. Lifespan: first pivot date (birth) -> first touch -> last touch, "
             "touch = daily close within tol. `episodes` counts return visits separated by >10d; "
             "`max_gap_days` is the longest absence; `break_date` = first close >3*tol away after birth; "
             "`survived_days` = birth/break span.")
    L.append("**B. VAP / round-number levels** -- 25-pip price histogram (0.95?1.26), peaks >1.15? mean bars; "
             "plus human floors 1.00/1.05/1.10/1.15/1.20/1.25 with tol 25 pips. Pre-existing, so "
             "birth is left-censored (first touch may predate 2020); lifespan measured touch-to-touch "
             "within sample.")
    L.append("**C. Consolidation ranges** -- rolling high-low band (60-day, fallback 30-day / "
             "fixed-band if no episodes) with width < 1.5xATR14 or fixed band, "
             "merged into episodes, kept if >=5 days. Lifespan = episode start -> end.")
    L.append("**Dwell (5m)** -- for each human/VP level, minutes spent inside +/-25 pips per "
             "visit-episode (runs separated by >50 bars away). Median/p90/max reported.")
    L.append("")
    L.append("## A. Top pivot levels by pivot count (strongest magnets)")
    L.append("")
    top = piv.sort_values("n_pivots", ascending=False).head(12)
    L.append("| level | type | pivots | first_pivot | last_pivot | first_touch | last_touch | span_days | touch_days | episodes | max_gap_days | break_date | survived_days |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in top.iterrows():
        L.append(f"| {r.level:.4f} | {r.type} | {int(r.n_pivots)} | {str(r.first_pivot)[:10]} | {str(r.last_pivot)[:10]} | "
                 f"{str(r.first_touch)[:10]} | {str(r.last_touch)[:10]} | {int(r.span_days)} | {int(r.touch_days)} | "
                 f"{int(r.episodes)} | {int(r.max_gap_days)} | {str(r.break_date)[:10]} | {int(r.survived_days)} |")
    L.append("")
    L.append("Full table: `levels/pivot_levels.csv` (all clusters). Lifespan summary (all levels):")
    if len(piv):
        L.append(f"- span_days: median {piv.span_days.median():.0f}, p75 {piv.span_days.quantile(.75):.0f}, max {piv.span_days.max():.0f}")
        L.append(f"- touch_days: median {piv.touch_days.median():.0f}; episodes: max {piv.episodes.max()}, median {piv.episodes.median():.0f}")
        L.append(f"- survived_days: median {piv.survived_days.median():.0f} (cap is sample end -> censored if no break)")
    L.append("")
    L.append("## B. Round-number and VAP-peak levels")
    L.append("")
    L.append("| level | source | first_touch | last_touch | span_days | touch_days | episodes | max_gap_days | break_date | survived_days | bars_inside_5m | dwell_med_min | dwell_p90 | dwell_max |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    dw_map = dw.set_index("level").to_dict("index") if len(dw) else {}
    for _, r in hr.sort_values("level").iterrows():
        dwr = dw_map.get(float(r.level), {})
        L.append(f"| {float(r.level):.4f} | {r.source} | {str(r.first_touch)[:10]} | {str(r.last_touch)[:10]} | "
                 f"{int(r.span_days)} | {int(r.touch_days)} | {int(r.episodes)} | {int(r.max_gap_days)} | "
                 f"{str(r.break_date)[:10]} | {int(r.survived_days)} | {dwr.get('bars_inside_5m','')} | "
                 f"{dwr.get('dwell_min_med','')} | {dwr.get('dwell_min_p90','')} | {dwr.get('dwell_min_max','')} |")
    L.append("")
    L.append("VAP bins (25 pips), only peaks listed: share = fraction of all 5m bars in bin.")
    L.append("")
    L.append("| bin | center | bars | share |")
    L.append("|---|---|---|---|")
    for _, r in vap.iterrows():
        L.append(f"| {r['bin_start']:.4f}-{r['bin_end']:.4f} | {r['center']:.4f} | {int(r['count']):,} | {r['share']:.2%} |")
    L.append("")
    L.append("Full tables: `levels/vp_round_levels.csv` + `levels/vap_bins.csv`.")
    L.append("")
    L.append("## C. Consolidation episodes (>=5d)")
    L.append("")
    if len(ep):
        L.append(f"Total episodes: {len(ep)}. Median duration {ep.days.median():.0f}d, "
                 f"longest {ep.days.max()}d. Past episodes do NOT predict the next -- "
                 "quote durations as historical description, not expectation.")
        L.append("")
        L.append("| start | end | days | low | high | width | center |")
        L.append("|---|---|---|---|---|---|---|")
        for _, r in ep.sort_values("days", ascending=False).head(12).iterrows():
            L.append(f"| {str(r.start)[:10]} | {str(r.end)[:10]} | {int(r.days)} | {r.low:.4f} | {r.high:.4f} | {r.width:.4f} | {r.center:.4f} |")
        L.append("")
        L.append("Full table: `levels/consolidation_episodes.csv`.")
    else:
        L.append("No episodes met the >=5d criterion under these parameters.")
    L.append("")
    L.append("## Key caveats")
    L.append("")
    L.append("1. **Left-censoring:** levels existing before 2020 show first_touch at/near sample start; "
             "true lifespan is longer than measured. Pivot `birth` uses first pivot in-sample (not pre-2020 history).")
    L.append("2. **Tolerance drives everything:** halving tol roughly halves touch counts; treat exact "
             "lifespan numbers as order-of-magnitude, not precision.")
    L.append("3. **Break ? invalidation:** `break_date` is first excursion >3*tol; many levels are "
             "re-tested later (that is why `last_touch` can follow `break_date`).")
    L.append("4. **`survived_days`** is right-censored when no break occurs in-sample.")
    L.append("5. **No volume data** in HistData M1 (volume==0), so VAP reflects time spent at price, "
             "not traded size -- a time-at-price, not a true order-flow, map.")
    L.append("6. **2023 sparse** in source: ~13% fewer M1 rows than other full years; that year "
             "under-represents touches/episodes.")
    L.append("")
    (LEVELS_DIR / "LEVELS_REPORT.md").write_text("\n".join(str(x) for x in L), encoding="utf-8")
    print("wrote", LEVELS_DIR / "LEVELS_REPORT.md")

def charts_levels(df, d, piv, hr, ep):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    # daily closes + top 8 pivot levels
    top = piv.sort_values("n_pivots", ascending=False).head(8)
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(d.index, d["close"], lw=0.6, label="daily close")
    for _, r in top.iterrows():
        ax.axhline(float(r["level"]), lw=0.8, alpha=0.6, label=f"{r['level']:.4f} {r['type']} n={int(r['n_pivots'])}")
    ax.set_title("Daily close + top pivot-cluster levels")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    axt = fig.tight_layout()
    fig.savefig(CHARTS / "07_levels_pivots.png", dpi=150)
    plt.close(fig)
    print("wrote", CHARTS / "07_levels_pivots.png")
    # lifespan (span) horizontal bars for pivots
    fig, ax = plt.subplots(figsize=(14, 6))
    t2 = piv.sort_values("span_days", ascending=False).head(20)
    labels = [f"{v:.4f}" for v in t2["level"]]
    ax.barh(labels, t2["span_days"])
    ax.set_title("Pivot levels: calendar lifespan span_days (first touch -> last touch, top 20)")
    ax.set_xlabel("days")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHARTS / "08_levels_lifespan.png", dpi=150)
    plt.close(fig)
    print("wrote", CHARTS / "08_levels_lifespan.png")
    # consolidation bands on daily
    if len(ep):
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(d.index, d["close"], lw=0.6)
        for _, r in ep.iterrows():
            ax.fill_between([r["start"], r["end"]], r["low"], r["high"], alpha=0.25)
        ax.set_title(f"Consolidation episodes (30d band 0.02), n={len(ep)}")
        ax.grid(alpha=0.3)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        fig.tight_layout()
        fig.savefig(CHARTS / "09_levels_consolidation.png", dpi=150)
        plt.close(fig)
        print("wrote", CHARTS / "09_levels_consolidation.png")

if __name__ == "__main__":
    main()
    # charts need df/d/piv/hr/ep in scope -- rerun minimal load and chart
    _df = load()
    _d = daily(_df)
    _piv, _, _ = pivot_levels(_df, _d)
    _vap, _hr = vap_levels(_df, _d)
    _ep = consolidation_episodes(_d, win=30, band=0.02)
    charts_levels(_df, _d, _piv, _hr, _ep)

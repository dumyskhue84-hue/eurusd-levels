#!/usr/bin/env python3
"""Realized intraday volatility study for EURUSD news sizing.

Measures the median full-hour range (high-low, in pips) for each UTC hour
across the 5m history, plus a multiplier vs the overall median hour range.
daily_bias.py uses the multiplier to size per-event expected moves:

    expected_pips = atr_pips * frac[impact] * clamp(hour_mult, 0.6, 1.6)

Output: data/cache/news_hour_vol.json
  { generated_at, window_minutes, days, overall_med_pips,
    hours: { "0": { med_pips, p75_pips, obs, mult }, ... } }

Missing/short history -> writes all multipliers 1.0 (neutral) and exits 0.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PARQUET = BASE / "data" / "processed" / "eurusd_5m.parquet"
OUT = BASE / "data" / "cache" / "news_hour_vol.json"
PIP = 0.0001
MIN_OBS_PER_HOUR = 20


def neutral(reason: str) -> dict:
    print(f"WARNING: news_study neutral ({reason})", flush=True)
    hours = {str(h): {"med_pips": None, "p75_pips": None, "obs": 0, "mult": 1.0}
             for h in range(24)}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_minutes": 60,
        "days": 0,
        "overall_med_pips": None,
        "hours": hours,
        "note": reason,
    }


def compute() -> dict:
    try:
        import pandas as pd
    except ImportError:
        return neutral("pandas not installed")
    if not PARQUET.exists():
        return neutral("parquet missing")
    try:
        df = pd.read_parquet(PARQUET, columns=["timestamp", "high", "low"])
    except Exception as e:  # noqa: BLE001
        return neutral(f"parquet read failed: {e}")
    if df.empty or len(df) < 1000:
        return neutral("too few bars")
    df = df.sort_values("timestamp")
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df = df.assign(h=ts.dt.hour, day=ts.dt.date)
    ranges = df.groupby(["day", "h"]).agg(
        hi=("high", "max"), lo=("low", "min"), n=("low", "size"))
    ranges = ranges[ranges["n"] >= 2]  # drop partial hours
    if ranges.empty:
        return neutral("no full hours")
    exc = (ranges["hi"] - ranges["lo"]) / PIP
    days = int(ranges.reset_index()["day"].nunique())
    if days < 20:
        return neutral(f"only {days} days of history")
    by_h = exc.groupby(level="h")
    overall = float(exc.median())
    hours = {}
    for h in range(24):
        try:
            g = by_h.get_group(h)
        except KeyError:
            hours[str(h)] = {"med_pips": None, "p75_pips": None, "obs": 0, "mult": 1.0}
            continue
        med = float(g.median())
        obs = int(g.size)
        mult = round(med / overall, 3) if overall > 0 and obs >= MIN_OBS_PER_HOUR else 1.0
        hours[str(h)] = {
            "med_pips": round(med, 1),
            "p75_pips": round(float(g.quantile(0.75)), 1),
            "obs": obs,
            "mult": mult,
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_minutes": 60,
        "days": days,
        "overall_med_pips": round(overall, 1),
        "hours": hours,
    }


def main() -> None:
    out = compute()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    top = sorted(
        ((h, v["mult"]) for h, v in out["hours"].items() if v["mult"] != 1.0),
        key=lambda x: -x[1])[:5]
    print(f"wrote {OUT.relative_to(BASE)} days={out['days']} "
          f"overall_med_pips={out['overall_med_pips']} "
          f"top_hours={[(h, m) for h, m in top]}", flush=True)


if __name__ == "__main__":
    sys.exit(main())

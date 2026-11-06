#!/usr/bin/env python3
"""Generate levels.json for the PWA: today's EURUSD adaptive levels from the
existing daily_adaptive engine pieces, plus respect stats from prior tests.

Input: data/processed/eurusd_5m.parquet + levels/daily_tests_adaptive.csv
Output: public/levels.json  (date, anchor, ATR, zone_pips, levels[] with
        price, type, approach_side, zone_low/high, expiry, respect stats)
Timezone: levels are for the day starting 00:00 UTC (forex day boundary used
by HistData 5m bars). History requirement: 180 days rolling for VAP.
"""
from __future__ import annotations
from pathlib import Path
import json, sys
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))
import daily_adaptive as da  # noqa: E402

PUBLIC = BASE / "public"
PUBLIC.mkdir(exist_ok=True)

def touch_price(df5, level, zone):
    """Quick approach side from 5m close distance."""
    recent = df5.tail(288)["close"]  # last ~24h of 5m
    return "from_below" if recent.iloc[-1] < level else "from_above"

def respect_stats(tests: pd.DataFrame, level: float, typ: str) -> dict:
    """Aggregate stats from prior adaptive tests for this level+type."""
    if tests.empty:
        return {"touches": 0, "reject_rate": None, "break_rate": None,
                "median_exc_atr": None, "last_test": None}
    sub = tests[(tests["type"] == typ) & ((tests["level"] - level).abs() < 0.002)]
    if sub.empty:
        return {"touches": 0, "reject_rate": None, "break_rate": None,
                "median_exc_atr": None, "last_test": None}
    br = float(sub["outcome"].str.startswith("break").mean())
    return {"touches": int(len(sub)),
            "reject_rate": round(1 - br, 3),
            "break_rate": round(br, 3),
            "median_exc_atr": round(float(sub["exc_atr"].median()), 3),
            "last_test": str(sub["date"].max())}

def main():
    df5 = da.load(); d = da.daily(df5)
    # last fully completed day index
    i = len(d) - 1  # levels for NEXT day after last bar
    # if today is past the last bar's day, levels are for the coming day
    target = d.index[-1] + pd.Timedelta(days=1)
    cands, pc, A = da.candidates(i, d, df5)
    kept = da.prune(cands, pc, A)
    zone = 0.25 * A
    zone_pips = round(zone / 0.0001, 1)

    try:
        tests = pd.read_csv(BASE / "levels" / "daily_tests_adaptive.csv")
        tests["date"] = pd.to_datetime(tests["date"], utc=True)
    except Exception:
        tests = pd.DataFrame()

    levels = []
    for c in kept:
        lvl = float(c["level"])
        lo, hi = lvl - zone, lvl + zone
        rs = respect_stats(tests, lvl, c["type"])
        levels.append({
            "price": round(lvl, 5),
            "type": c["type"],
            "note": c["note"],
            "approach_side": touch_price(df5, lvl, zone),
            "zone_low": round(lo, 5),
            "zone_high": round(hi, 5),
            "zone_pips": zone_pips,
            "expiry": str((target + pd.Timedelta(days=5)).date()),
            "respect": rs,
            "primary": c["type"] != "ROUND" and c["type"] != "PC",
        })

    out = {
        "pair": "EURUSD",
        "date": str(target.date()),
        "generated_from": str(d.index[-1].date()),
        "anchor_close": round(pc, 5),
        "atr": round(A, 5),
        "atr_pips": round(A / 0.0001, 1),
        "zone_pips": zone_pips,
        "timezone": "UTC",
        "history_days": 180,
        "levels": levels,
    }
    p = PUBLIC / "levels.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {p} date={out['date']} n={len(levels)}")

if __name__ == "__main__":
    main()

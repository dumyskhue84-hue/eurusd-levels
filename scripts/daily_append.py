#!/usr/bin/env python3
"""Append recent EURUSD 5m bars from Dukascopy daily tail -> same 5m OHLC type.

HistData is primary history (M1 ASCII -> 5m, via pipeline.py). Dukascopy is
only the daily tail (last 10 days) because HistData publishes monthly and
lags. Data type is identical: spot FX 5m OHLC, UTC, from tick/M1 aggregation.

Use:
  python scripts/daily_append.py              # fetch last ~10d tail, append
  python scripts/daily_append.py --days 10
  python scripts/daily_append.py --dry-run

Idempotent. Exit 1 on fetch failure (no silent fallback).
Requires: node + dukascopy-node, OR falls back to direct .bi5 fetch.
"""
from __future__ import annotations
import argparse, sys, json, subprocess, tempfile
from pathlib import Path
import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "data" / "processed"
PARQUET = PROC / "eurusd_5m.parquet"

# Dukascopy symbol / timeframe for EURUSD
SYMBOL = "eurusd"
TAIL_DAYS = 10
# Direct .bi5 endpoint: https://datafeed.dukascopy.com/datafeed/eur/usd/... 
# We use dukascopy-node (npm) because it handles .bi5 LZMA reliably.
NPM_PKGS = ["dukascopy-node"]

def _which(exe: str) -> str:
    import shutil
    p = shutil.which(exe)
    if p:
        return p
    for cand in (f"C:/Program Files/nodejs/{exe}.exe", f"C:/Program Files/nodejs/{exe}.CMD", f"C:/Program Files/nodejs/{exe}"):
        if Path(cand).exists():
            return cand
    return exe

def fetch_via_dukascopy_node(days: int) -> pd.DataFrame:
    """Run a small node script using dukascopy-node to fetch last N days 5m."""
    import tempfile, os, textwrap
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Single range fetch (CLI proves this works reliably). Dukascopy
        # returns ms epochs (1793... = 2026). getHistoricalRates with
        # from/to Date objects is correct; per-day sleeps caused epoch 0.
        script = tmp / "fetch.cjs"
        script.write_text(textwrap.dedent(f"""
            const {{ getHistoricalRates }} = require('dukascopy-node');
            (async () => {{
              const end = new Date();
              const start = new Date(Date.now() - {days} * 86400000);
              start.setUTCHours(0,0,0,0);
              try {{
                const data = await getHistoricalRates({{
                  instrument: '{SYMBOL}',
                  dates: {{ from: start, to: end }},
                  timeframe: 'm5',
                  format: 'json'
                }});
                console.log(JSON.stringify(data));
              }} catch (e) {{
                console.error(e);
                process.exit(1);
              }}
            }})();
        """), encoding="utf-8")
        # install dukascopy-node if needed locally
        npm = _which("npm")
        node = _which("node")
        res = subprocess.run(
            [npm, "install", "--prefix", str(tmp), "dukascopy-node"],
            capture_output=True, text=True, timeout=120,
        )
        if res.returncode != 0:
            raise RuntimeError(f"dukascopy-node install failed: {res.stderr[-1000:]}")
        # run
        r = subprocess.run(
            [node, str(script)],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            raise RuntimeError(f"dukascopy-node fetch failed: {r.stderr[-2000:]}")
        data = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else []
    if not data:
        raise RuntimeError("dukascopy-node returned no bars")
    df = pd.DataFrame(data)
    # dukascopy-node returns timestamps as ms epochs; convert explicitly
    ts_raw = df.get("timestamp", df.get("time", df.get("date")))
    ts = pd.to_datetime(ts_raw, unit="ms", utc=True, errors="coerce")
    out = pd.DataFrame({
        "timestamp": ts,
        "open": df.get("open", df.get("Open")).astype(float),
        "high": df.get("high", df.get("High")).astype(float),
        "low": df.get("low", df.get("Low")).astype(float),
        "close": df.get("close", df.get("Close")).astype(float),
    })
    out["tick_count"] = 5
    out["volume"] = 0.0
    return out.sort_values("timestamp").drop_duplicates(subset="timestamp").dropna(subset=["timestamp"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=TAIL_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not PARQUET.exists():
        raise SystemExit(f"snapshot not found: {PARQUET} — run scripts/pipeline.py first")
    old = pd.read_parquet(PARQUET)
    old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
    old = old.sort_values("timestamp")
    print(f"snapshot: {len(old):,} bars, {old['timestamp'].min()} -> {old['timestamp'].max()}", flush=True)

    try:
        new = fetch_via_dukascopy_node(args.days)
    except Exception as e:
        print(f"FAIL: Dukascopy fetch failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"dukascopy fetched: {len(new):,} bars, {new['timestamp'].min()} -> {new['timestamp'].max()}", flush=True)

    # append tail, THEN trim. Added is measured before trim so a 2y trim
    # doesn't mask genuine appends.
    merged_full = pd.concat([old, new], ignore_index=True)
    merged_full = merged_full.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    merged_full["timestamp"] = merged_full["timestamp"].dt.floor("5min")
    merged_full = merged_full.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    merged_full = merged_full.sort_values("timestamp")
    added = len(merged_full) - len(old)
    print(f"merged (pre-trim): {len(merged_full):,} bars (added {added:,} new)", flush=True)
    # keep last 2 years (180d VAP minimum + margin)
    cutoff = merged_full["timestamp"].max() - pd.Timedelta(days=730)
    merged = merged_full[merged_full["timestamp"] >= cutoff]
    if added <= 0:
        print("nothing new; snapshot unchanged")
        return

    if args.dry_run:
        print(f"dry-run: would write {len(merged):,} bars to {PARQUET}")
        return

    merged.to_parquet(PARQUET, index=False)
    print(f"wrote {PARQUET} ({PARQUET.stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    main()

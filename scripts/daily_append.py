#!/usr/bin/env python3
"""Append recent EURUSD 5m bars from yfinance (daily tail) to the snapshot parquet.

Use:
  python scripts/daily_append.py              # fetch last ~10d tail, append
  python scripts/daily_append.py --days 10    # explicit lookback
  python scripts/daily_append.py --dry-run    # fetch and report, don't write

The HistData snapshot (data/processed/eurusd_5m.parquet, last 2y committed)
provides the 180-day VAP history. yfinance 5m is limited to 60 days, which is
fine — we only need the fresh tail beyond the snapshot's last bar.

Idempotent: re-running the same day appends nothing new.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
PROC = BASE / "data" / "processed"
PARQUET = PROC / "eurusd_5m.parquet"

# yfinance symbol / interval for EURUSD 5m
SYMBOL = "EURUSD=X"
# last 10 days is a safe overlap window (weekends/holidays return fewer bars)
TAIL_DAYS = 10

def fetch_tail(days: int = TAIL_DAYS) -> pd.DataFrame:
    import yfinance as yf
    # period in days; yfinance 5m requires period <= 60d
    period = f"{days}d"
    df = yf.download(SYMBOL, period=period, interval="5m", auto_adjust=False,
                     progress=False, timeout=60)
    if df is None or len(df) == 0:
        # Retry once with single-ticker mode (multi-level columns quirk)
        df = yf.Ticker(SYMBOL).history(period=period, interval="5m")
    if df is None or len(df) == 0:
        raise RuntimeError(f"yfinance returned no data for {SYMBOL} ({period})")
    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.reset_index().rename(columns={"index": "timestamp", "Date": "timestamp", "Datetime": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Keep OHLC only; drop volume (HistData volume is 0 anyway)
    out = pd.DataFrame({
        "timestamp": df["timestamp"],
        "open": df["Open"].astype(float),
        "high": df["High"].astype(float),
        "low": df["Low"].astype(float),
        "close": df["Close"].astype(float),
    })
    out["tick_count"] = 5
    out["volume"] = 0.0
    return out.sort_values("timestamp").drop_duplicates(subset="timestamp")

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

    new = fetch_tail(args.days)
    print(f"yfinance fetched: {len(new):,} bars, {new['timestamp'].min()} -> {new['timestamp'].max()}", flush=True)

    merged = pd.concat([old, new], ignore_index=True)
    merged = merged.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    # floor to 5m to match HistData alignment (yfinance already 5m, but be safe)
    merged["timestamp"] = merged["timestamp"].dt.floor("5min")
    # re-dedup after floor (in case floor merged two rows)
    merged = merged.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    added = len(merged) - len(old)
    print(f"merged: {len(merged):,} bars (added {added:,} new)", flush=True)
    if added <= 0:
        print("nothing new; snapshot unchanged")
        return

    # keep only the last 2 years (~730d) to keep the committed snapshot small
    cutoff = merged["timestamp"].max() - pd.Timedelta(days=730)
    merged = merged[merged["timestamp"] >= cutoff]
    print(f"after 2y trim: {len(merged):,} bars from {merged['timestamp'].min()}", flush=True)

    if args.dry_run:
        print(f"dry-run: would write {len(merged):,} bars to {PARQUET}")
        return

    merged.to_parquet(PARQUET, index=False)
    print(f"wrote {PARQUET} ({PARQUET.stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    main()

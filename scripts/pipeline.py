#!/usr/bin/env python3
"""EURUSD M1 -> 5m pipeline using HistData ASCII M1 zips.
Yearly files 2020-2025 + monthly 2026-01..10. Resumable, cached in data/raw/.
"""
from __future__ import annotations
import re, sys, zipfile, io, hashlib
from pathlib import Path
from datetime import date
import requests
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw"
PROC = BASE / "data" / "processed"
CHARTS = BASE / "charts"
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)
CHARTS.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PAIR = "EURUSD"
TIMEFRAME = "M1"
PLATFORM = "ASCII"

def build_targets():
    """Dynamic target list: yearly files 2020..<current> + monthly for the
    current year (current month + prior month overlap for publish lag).
    HistData still publishes yearly files for past years and monthly for 2026+,
    so yearly targets stop at the current year. This never hardcodes an end month."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    cur_year = today.year
    years = list(range(2020, cur_year))  # 2020..<current> yearly files
    targets = [(str(y), str(y), str(y), str(y)) for y in years]
    # monthly: current month and prior month (in case current not yet published)
    seen = set()
    for offset in (0, 1):  # current, prior
        y, m = today.year, today.month - offset
        while m <= 0:
            m += 12; y -= 1
        label = f"{y}-{m:02d}"
        if label in seen:
            continue
        seen.add(label)
        targets.append((label, str(y), f"{y}{m:02d}", f"{y}/{m}"))
        if m == 1 and y >= 2020:
            break
    # also ensure at least the last two monthly files exist for steady state
    # (if current month zip is 404, download_one returns None and we keep
    # the prior month which is already cached)
    return targets

TARGETS = build_targets()

def listing_url(date_val: str, datemonth: str, suffix: str) -> str:
    return f"https://www.histdata.com/download-free-forex-historical-data/?/{PLATFORM.lower()}/1-minute-bar-quotes/eurusd/{suffix}"

def get_token(session: requests.Session, date_val: str, datemonth: str, suffix: str) -> tuple[str | None, str]:
    url = listing_url(date_val, datemonth, suffix)
    r = session.get(url, timeout=60, headers=UA)
    r.raise_for_status()
    m = re.search(r'name="tk"\s+id="tk"\s+value="([^"]+)"', r.text)
    return (m.group(1) if m else None), url

def download_one(session: requests.Session, label: str, date_val: str, datemonth: str, suffix: str) -> Path | None:
    dest = RAW / f"HISTDATA_COM_{PLATFORM}_{PAIR}_{TIMEFRAME}_{label.replace('-','')}.zip"
    if dest.exists() and dest.stat().st_size > 1000:
        # verify zip
        try:
            with zipfile.ZipFile(dest) as z:
                if z.namelist():
                    print(f"[skip] {label} cached ({dest.name}, {dest.stat().st_size/1e6:.1f} MB)", flush=True)
                    return dest
        except Exception:
            pass
    tk, referer = get_token(session, date_val, datemonth, suffix)
    if not tk:
        print(f"[fail] {label}: no token", flush=True)
        return None
    data = {"tk": tk, "date": date_val, "datemonth": datemonth,
            "platform": PLATFORM, "timeframe": TIMEFRAME, "fxpair": PAIR}
    headers = dict(UA)
    headers["Referer"] = referer
    r = session.post("https://www.histdata.com/get.php", data=data, timeout=300, headers=headers)
    ctype = r.headers.get("content-type", "")
    if "zip" not in ctype and "octet" not in ctype and "application" not in ctype:
        print(f"[fail] {label}: unexpected content-type {ctype} ({len(r.content)} bytes) body={r.text[:500]}", flush=True)
        return None
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(r.content)
    if tmp.stat().st_size < 1000:
        print(f"[fail] {label}: tiny file", flush=True)
        tmp.unlink(missing_ok=True)
        return None
    with zipfile.ZipFile(tmp) as z:
        names = z.namelist()
        assert names, "empty zip"
    tmp.rename(dest)
    print(f"[done] {label} -> {dest.name} ({dest.stat().st_size/1e6:.1f} MB)", flush=True)
    return dest

def parse_m1_csv(path: Path) -> pd.DataFrame:
    # HistData ASCII: YYYYMMDD HHMMSS;open;high;low;close;volume
    df = pd.read_csv(path, sep=";", header=None,
                     names=["dt", "open", "high", "low", "close", "volume"],
                     dtype={"dt": str, "open": float, "high": float, "low": float, "close": float, "volume": float})
    df["timestamp"] = pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S", utc=True)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]

def read_zip(zpath: Path) -> pd.DataFrame:
    frames = []
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if name.lower().endswith(".csv"):
                with z.open(name) as f:
                    txt = io.TextIOWrapper(f, encoding="utf-8", errors="ignore")
                    # stream via pandas
                    frames.append(pd.read_csv(txt, sep=";", header=None,
                        names=["dt","open","high","low","close","volume"],
                        dtype={"dt": str, "open": float, "high": float, "low": float, "close": float, "volume": float},
                        parse_dates=False))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S", utc=True)
    return df[["timestamp","open","high","low","close","volume"]]

def to_5m(m1: pd.DataFrame) -> pd.DataFrame:
    m1 = m1.drop_duplicates(subset="timestamp").sort_values("timestamp").set_index("timestamp")
    # floor to 5min (already aligned to minute; use floor)
    idx = m1.index.floor("5min")
    g = m1.groupby(idx)
    agg = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "tick_count": g.size(),
        "volume": g["volume"].sum(),
    })
    agg.index.name = "timestamp"
    return agg.reset_index()

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    targets = [t for t in TARGETS if only is None or t[0] == only]
    session = requests.Session()
    zips = []
    for label, dv, dm, suf in targets:
        p = download_one(session, label, dv, dm, suf)
        if p:
            zips.append(p)
    if not zips:
        print("No data downloaded.")
        return
    parts = []
    for zp in zips:
        m1 = read_zip(zp)
        if m1.empty:
            continue
        m1 = m1.drop_duplicates(subset="timestamp").sort_values("timestamp")
        parts.append(m1)
        print(f"{zp.name}: {len(m1):,} M1 rows, {m1.timestamp.min()} -> {m1.timestamp.max()}", flush=True)
    if not parts:
        print("No data parsed.")
        return
    m1all = pd.concat(parts, ignore_index=True).drop_duplicates(subset="timestamp").sort_values("timestamp")
    print(f"Combined M1: {len(m1all):,}", flush=True)
    m5 = to_5m(m1all)
    print(f"5m bars: {len(m5):,}", flush=True)
    # QC
    bad = ((m5["high"] < m5[["open","close"]].max(axis=1)) | (m5["low"] > m5[["open","close"]].min(axis=1))).sum()
    print(f"OHLC violations (H<max(O,C) or L>min(O,C)): {bad}")
    # gaps > 30 min (weekends will dominate gap list)
    delta = m5["timestamp"].diff().dropna()
    gaps = delta[delta > pd.Timedelta(minutes=30)]
    print(f"Gaps >30min: {len(gaps)} (max {gaps.max() if len(gaps) else 'n/a'})")
    out = PROC / "eurusd_5m.parquet"
    m5.to_parquet(out, index=False)
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")
    # sample CSV (first 1000 + last 1000)
    m5.head(1000).to_csv(PROC / "eurusd_5m_sample_head.csv", index=False)
    m5.tail(1000).to_csv(PROC / "eurusd_5m_sample_tail.csv", index=False)
    # yearly counts
    print(m5.groupby(m5["timestamp"].dt.year).size().to_string())
    print(m5.head(3).to_string())
    print(m5.tail(3).to_string())

if __name__ == "__main__":
    main()

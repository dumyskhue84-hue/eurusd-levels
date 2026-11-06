#!/usr/bin/env python3
"""Generate EURUSD charts from data/processed/eurusd_5m.parquet."""
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

def load() -> pd.DataFrame:
    df = pd.read_parquet(PROC / "eurusd_5m.parquet")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["ret"] = np.log(df["close"] / df["close"].shift(1))
    return df

def save(fig, name: str):
    fig.tight_layout()
    p = CHARTS / name
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print(f"wrote {p}")

def overview(df):
    fig, ax = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    ax[0].plot(df["timestamp"], df["close"], lw=0.6)
    ax[0].set_title("EURUSD 5m close (UTC) — full range")
    ax[0].set_ylabel("Price")
    ax[0].grid(alpha=0.3)
    vol = df["ret"].rolling(288 * 30).std() * 100  # ~30d of 288 bars/day
    ax[1].plot(df["timestamp"], vol, lw=0.6)
    ax[1].set_title("30d rolling stdev of 5m log returns (%)")
    ax[1].set_ylabel("Vol %")
    ax[1].grid(alpha=0.3)
    fig.autofmt_xdate()
    save(fig, "01_overview.png")

def yearly(df):
    for y in sorted(df["timestamp"].dt.year.unique()):
        d = df[df["timestamp"].dt.year == y]
        if len(d) < 500:
            continue
        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(d["timestamp"], d["close"], lw=0.5)
        ax.set_title(f"EURUSD {int(y)} — 5m close, {len(d):,} bars")
        ax.set_ylabel("Price")
        ax.grid(alpha=0.3)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        save(fig, f"02_yearly_{int(y)}.png")

def daily_ret_hist(df):
    d = df.set_index("timestamp")["close"].resample("1D").last().dropna()
    r = d.pct_change().dropna() * 100
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(r, bins=120)
    axes[0].set_title("Daily returns (%) histogram")
    axes[0].set_ylabel("Count")
    axes[0].set_xlabel("Daily return %")
    axes[0].grid(alpha=0.3)
    yearly_ret = d.resample("YE").last().pct_change().dropna() * 100
    axes[1].bar([str(i.date()) for i in yearly_ret.index], yearly_ret.values)
    axes[1].set_title("Yearly close-to-close return (%)")
    axes[1].set_ylabel("%")
    axes[1].grid(alpha=0.3)
    save(fig, "03_returns.png")
    print("Yearly returns (%):")
    print(yearly_ret.round(2).to_string())

def candlestick_sample(df):
    # 2-week sample per year: pick first week-ish of each year present
    for y in sorted(df["timestamp"].dt.year.unique()):
        d = df[df["timestamp"].dt.year == y].iloc[: 288 * 10]  # ~10 days
        if len(d) < 500:
            continue
        fig, ax = plt.subplots(figsize=(14, 6))
        w = 2.5 / 24  # width in days
        up, dn = "#2ca02c", "#d62728"
        for t, o, h, l, c in zip(d["timestamp"], d["open"], d["high"], d["low"], d["close"]):
            col = up if c >= o else dn
            ax.plot([t, t], [l, h], color=col, lw=0.5)
            ax.bar(t, abs(c - o), width=w, bottom=min(o, c), color=col)
        ax.set_title(f"EURUSD 5m candles — first 10 trading days of {int(y)}")
        ax.set_ylabel("Price")
        ax.grid(alpha=0.3)
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        fig.autofmt_xdate()
        save(fig, f"04_candles_{int(y)}.png")

def intraday(df):
    d = df.copy()
    d["hour"] = d["timestamp"].dt.hour
    d["weekday"] = d["timestamp"].dt.weekday
    # mean 5m return by hour
    by_hour = d.groupby("hour")["ret"].mean() * 10000  # bps
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].bar(by_hour.index, by_hour.values)
    axes[0].set_title("Mean 5m log return (bps) by UTC hour")
    axes[0].set_xlabel("Hour (UTC)")
    axes[0].set_ylabel("bps")
    axes[0].grid(alpha=0.3)
    axes[0].axhline(0, color="k", lw=0.8)
    # heatmap weekday x hour mean return
    pv = d.groupby(["weekday", "hour"])["ret"].mean().unstack() * 10000
    im = axes[1].imshow(pv.values, aspect="auto", cmap="RdYlGn")
    axes[1].set_title("Heatmap: mean 5m return (bps), weekday x hour")
    axes[1].set_xticks(range(24))
    axes[1].set_xticklabels(range(24), fontsize=7)
    axes[1].set_yticks(range(5))
    axes[1].set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri"])
    axes[1].set_xlabel("Hour (UTC)")
    fig.colorbar(im, ax=axes[1], label="bps")
    save(fig, "05_intraday.png")

def drawdown(df):
    d = df.set_index("timestamp")["close"].resample("1D").last().dropna()
    dd = d / d.cummax() - 1
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(dd.index, dd * 100, lw=0.7)
    ax.set_title("Daily close drawdown from ATH (%)")
    ax.set_ylabel("%")
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    save(fig, "06_drawdown.png")
    worst = dd.min()
    print(f"Worst daily drawdown: {worst*100:.1f}% at {dd.idxmin()}")

def qc_report(df):
    lines = []
    lines.append(f"Bars: {len(df):,}")
    lines.append(f"Range: {df.timestamp.min()} -> {df.timestamp.max()}")
    lines.append("Yearly counts:")
    counts = df.groupby(df["timestamp"].dt.year).size()
    for y, n in counts.items():
        lines.append(f"  {y}: {n:,}")
    bad = ((df["high"] < df[["open","close"]].max(axis=1)) | (df["low"] > df[["open","close"]].min(axis=1))).sum()
    lines.append(f"OHLC violations: {int(bad)}")
    delta = df["timestamp"].diff().dropna()
    gaps = delta[delta > pd.Timedelta(minutes=30)]
    lines.append(f"Gaps >30min: {len(gaps)}")
    if len(gaps):
        lines.append(f"Largest gap: {gaps.max()}")
        lines.append("Top 20 gaps:")
        top = gaps.sort_values(ascending=False).head(20)
        # map back to gap start times
        idx = top.index
        for i in idx:
            lines.append(f"  {df.timestamp[i-1]} -> {df.timestamp[i]} ({top.loc[i]})")
    lines.append(f"First 3:\n{df.head(3).to_string(index=False)}")
    lines.append(f"Last 3:\n{df.tail(3).to_string(index=False)}")
    txt = "\n".join(str(x) for x in lines)
    (PROC / "qc_report.txt").write_text(txt, encoding="utf-8")
    print(txt)

def main():
    df = load()
    print(f"Loaded {len(df):,} bars {df.timestamp.min()} -> {df.timestamp.max()}")
    overview(df)
    yearly(df)
    daily_ret_hist(df)
    candlestick_sample(df)
    intraday(df)
    drawdown(df)
    qc_report(df)

if __name__ == "__main__":
    main()

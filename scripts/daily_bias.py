#!/usr/bin/env python3
"""Economic-calendar bias for EURUSD: High/Medium USD/EUR events inside a
UTC window, scored from forecast-vs-previous, mapped to a target level.

Source: Forex Factory week feed (free JSON, no key):
  https://nfs.faireconomy.media/ff_calendar_thisweek.json

Usage:
  python scripts/daily_bias.py                       # full day, levels.json date
  python scripts/daily_bias.py --window 08:00-12:00  # UTC window
  python scripts/daily_bias.py --date 2026-11-13 --min-impact High

Output: public/bias.json
  { pair, date, window, bias, confidence, score, events[], target, ... }
bias: bullish | bearish | neutral | null (null = feed error, target = null).
Direction is a pre-release lean (forecast vs previous), not a surprise tracker.
"""
from __future__ import annotations
import argparse, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1]
PUBLIC = BASE / "public"
PUBLIC.mkdir(exist_ok=True)
CACHE = BASE / "data" / "cache" / "ff_calendar_thisweek.json"
CACHE.parent.mkdir(parents=True, exist_ok=True)

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
COUNTRIES = {"USD", "EUR"}
IMPACT_W = {"High": 2, "Medium": 1}
# higher forecast = weaker currency for these titles (vote flips)
INVERTED = {
    "USD": ("unemployment claims", "initial jobless claims", "jobless claims",
            "unemployment rate"),
    "EUR": ("unemployment rate",),
}
PIP = 0.0001


def parse_num(s: str) -> float | None:
    if not s:
        return None
    m = re.match(r"-?\d+(?:\.\d+)?", s.strip().replace(",", ""))
    return float(m.group(0)) if m else None


def parse_window(spec: str) -> tuple[int, int]:
    m = re.match(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$", spec)
    if not m:
        raise SystemExit(f"bad --window {spec!r}, expected HH:MM-HH:MM (UTC)")
    a = int(m.group(1)) * 60 + int(m.group(2))
    b = int(m.group(3)) * 60 + int(m.group(4))
    if a >= 1440 or b > 1440 or (a == b):
        raise SystemExit(f"bad --window {spec!r}")
    return a, b


def in_window(mins: int, start: int, end: int) -> bool:
    return (start <= mins < end) if start <= end else (mins >= start or mins < end)


def event_vote(country: str, title: str, forecast: str, previous: str) -> tuple[int, str | None]:
    """Return (vote, signal). vote: +1 EURUSD up, -1 down, 0 no lean.
    signal None => volatility watch (no comparable numbers)."""
    f, p = parse_num(forecast), parse_num(previous)
    if f is None or p is None or f == p:
        return 0, None
    cmp_ = 1 if f > p else -1
    t = title.lower()
    inverted = any(k in t for k in INVERTED[country])
    if country == "USD":
        # hotter USD data -> USD stronger -> EURUSD lower
        vote = cmp_ if inverted else -cmp_
        signal = "usd_weak" if vote > 0 else "usd_strong"
    else:
        # hotter EUR data -> EUR stronger -> EURUSD higher
        vote = -cmp_ if inverted else cmp_
        signal = "eur_strong" if vote > 0 else "eur_weak"
    return vote, signal


def pick_target(levels_file: dict, bias: str, date: str) -> dict | None:
    anchor = levels_file.get("anchor_close")
    if anchor is None or bias not in ("bullish", "bearish"):
        return None
    cands = []
    for l in levels_file.get("levels", []):
        if l.get("expiry", "9999") < date:
            continue
        price = l["price"]
        if bias == "bullish" and price > anchor:
            cands.append(l)
        elif bias == "bearish" and price < anchor:
            cands.append(l)
    if not cands:
        return None
    cands.sort(key=lambda l: (abs(l["price"] - anchor), not l.get("primary", False)))
    l = cands[0]
    return {
        "price": l["price"],
        "type": l["type"],
        "note": l.get("note", ""),
        "zone_low": l["zone_low"],
        "zone_high": l["zone_high"],
        "distance_pips": round(abs(l["price"] - anchor) / PIP, 1),
        "approach_side": l["approach_side"],
    }


def load_levels() -> dict | None:
    p = PUBLIC / "levels.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fetch_events(date: str, start: int, end: int, min_impact: str) -> list[dict]:
    raw = None
    r = None
    for attempt, delay in enumerate((0, 3, 8)):
        if delay:
            time.sleep(delay)
        try:
            r = requests.get(FEED, headers=UA, timeout=15)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            raw = r.json()
            CACHE.write_text(json.dumps(raw), encoding="utf-8")
            break
        if r.status_code != 429:
            break
    if raw is None:
        # rate-limited or network down: fall back to last cached week feed
        try:
            raw = json.loads(CACHE.read_text(encoding="utf-8"))
            print(f"WARNING: using cached calendar {CACHE} "
                  f"(fetch failed: {r.status_code if r is not None else 'network'})",
                  flush=True)
        except Exception:
            if r is not None:
                r.raise_for_status()
            raise RuntimeError("calendar fetch failed and no cache present")
    order = {"High": 0, "Medium": 1, "Low": 2, "Holiday": 3}
    keep_max = 0 if min_impact == "High" else 1
    out = []
    for e in raw:
        if e.get("country") not in COUNTRIES:
            continue
        if order.get(e.get("impact", ""), 9) > keep_max:
            continue
        try:
            dt = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        except Exception:
            continue
        if dt.date().isoformat() != date:
            continue
        mins = dt.hour * 60 + dt.minute
        if not in_window(mins, start, end):
            continue
        out.append({
            "title": e.get("title", ""),
            "country": e["country"],
            "time": dt.strftime("%H:%M"),
            "impact": e.get("impact", ""),
            "forecast": e.get("forecast", "") or "",
            "previous": e.get("previous", "") or "",
        })
    out.sort(key=lambda e: e["time"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="00:00-24:00", help="UTC HH:MM-HH:MM")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: levels.json date)")
    ap.add_argument("--min-impact", choices=["High", "Medium"], default="Medium")
    args = ap.parse_args()

    start, end = parse_window(args.window)
    levels_file = load_levels()
    date = args.date or (levels_file or {}).get("date") or datetime.now(timezone.utc).date().isoformat()
    win = {"start": args.window.split("-")[0], "end": args.window.split("-")[1], "tz": "UTC"}

    out = {
        "pair": "EURUSD",
        "date": date,
        "window": win,
        "bias": None,
        "confidence": None,
        "score": None,
        "events": [],
        "target": None,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": "Calendar-based expectation, not a trading signal.",
    }

    try:
        events = fetch_events(date, start, end, args.min_impact)
    except Exception as e:
        out["error"] = f"calendar fetch failed: {e}"
        (PUBLIC / "bias.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"WROTE bias.json with error: {e}", flush=True)
        return

    total_w = 0
    score = 0
    for e in events:
        vote, signal = event_vote(e["country"], e["title"], e["forecast"], e["previous"])
        w = IMPACT_W[e["impact"]]
        total_w += w
        score += w * vote
        e["signal"] = signal
        e["vote"] = vote
        e["watch"] = signal is None
        out["events"].append(e)

    bias = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
    out["bias"] = bias
    out["score"] = score
    out["confidence"] = round(abs(score) / total_w, 2) if total_w else 0.0
    out["target"] = pick_target(levels_file, bias, date) if levels_file else None

    (PUBLIC / "bias.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    tgt = out["target"]
    tgt_s = f" -> {tgt['price']} ({tgt['type']}, {tgt['distance_pips']} pips)" if tgt else " -> no target"
    print(f"wrote public/bias.json date={date} window={args.window} "
          f"bias={bias} score={score} conf={out['confidence']} "
          f"events={len(events)}{tgt_s}", flush=True)


if __name__ == "__main__":
    main()

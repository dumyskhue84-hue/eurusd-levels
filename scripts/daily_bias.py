#!/usr/bin/env python3
"""Economic-calendar bias for EURUSD: High/Medium USD/EUR events inside a
UTC window, scored from forecast-vs-previous, mapped to a target level.

Each event additionally gets a sized expected move and directional price
targets, plus day-level bullish/bearish time windows and a pre-rendered
push briefing:

  expected_pips = atr_pips * frac[impact] * clamp(hour_mult, 0.6, 1.6)
      hour_mult from data/cache/news_hour_vol.json (scripts/news_study.py)
  targets.up / targets.down = nearest unexpired level beyond anchor_close
      within 1.5x expected_pips each side, else synthetic anchor +- expected
  windows[] = post-release drift windows: open at a directional event,
      close at the next opposite-direction event or last same-direction
      event + --window-hours (default 4h), capped 23:59 UTC
  briefing = {title, body} pre-rendered for the Web Push daily briefing

Source: Forex Factory week feed (free JSON, no key):
  https://nfs.faireconomy.media/ff_calendar_thisweek.json

Usage:
  python scripts/daily_bias.py                       # full day, today (UTC)
  python scripts/daily_bias.py --window 08:00-12:00  # UTC window
  python scripts/daily_bias.py --date 2026-11-13 --min-impact High
  python scripts/daily_bias.py --window-hours 3      # shorter bias windows

Output: public/bias.json
  { pair, date, window, bias, confidence, score, events[], windows[],
    valid_from, valid_until, target, briefing, ... }
bias: bullish | bearish | neutral | null (null = feed error, target = null).
valid_from / valid_until = start/end (HH:MM UTC) of the first directional
  window matching the day's bias; null when the day has no directional lean.
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
# per-impact share of daily ATR expected to print around a release
FRAC = {"High": 0.40, "Medium": 0.20}
# fallback when levels.json (ATR) is unavailable, pips before hour mult
FALLBACK_PIPS = {"High": 25.0, "Medium": 12.0}
HOUR_CLAMP = (0.6, 1.6)
DEFAULT_WINDOW_HOURS = 4.0
DAY_END_MIN = 1439  # 23:59 UTC


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


def hhmm(mins: int) -> str:
    mins = max(0, min(int(mins), DAY_END_MIN))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def parse_hhmm(s: str) -> int | None:
    try:
        h, m = int(s[:2]), int(s[3:5])
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except (ValueError, TypeError):
        return None
    return None


def slug_id(date: str, time: str, country: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    return f"{date}T{time}-{country}-{slug}"


def load_hour_vol() -> dict:
    """{hour_str: {mult, med_pips}} from scripts/news_study.py, {} if absent."""
    p = CACHE.parent / "news_hour_vol.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        hours = data.get("hours") or {}
        return {h: v for h, v in hours.items() if isinstance(v, dict)}
    except Exception:
        return {}


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


def level_target(levels_file: dict | None, date: str, anchor: float | None,
                 expected_pips: float, direction: int) -> dict | None:
    """Nearest unexpired level beyond anchor in `direction` (+1/-1) within
    1.5x expected_pips, else a synthetic anchor +- expected estimate."""
    if anchor is None or not levels_file:
        return None
    limit = 1.5 * expected_pips * PIP
    cands = []
    for l in levels_file.get("levels", []):
        if l.get("expiry", "9999") < date:
            continue
        dist = (l["price"] - anchor) * direction
        if dist <= 0 or dist > limit:
            continue
        cands.append((dist, not l.get("primary", False), l))
    if cands:
        cands.sort(key=lambda t: (t[0], t[1]))
        l = cands[0][2]
        return {
            "price": round(l["price"], 5),
            "pips": round(abs(l["price"] - anchor) / PIP, 1),
            "label": l["type"],
        }
    price = anchor + direction * expected_pips * PIP
    return {"price": round(price, 5), "pips": expected_pips, "label": "EST"}


def build_windows(events: list[dict], window_hours: float) -> list[dict]:
    """Directional time windows from the day's directional (vote != 0) events.
    A window opens at an event, extends through same-direction events, and
    closes at the next opposite-direction event, else last same-direction
    event + window_hours, capped at 23:59 UTC."""
    step = int(round(window_hours * 60))
    dirs = []
    for e in events:
        if e.get("vote"):
            m = parse_hhmm(e.get("time", ""))
            if m is not None:
                dirs.append((m, e))
    dirs.sort(key=lambda x: x[0])

    def close_end(cur: dict, cap: int | None) -> int:
        e = min(cur["last"] + step, cap if cap is not None else DAY_END_MIN,
                DAY_END_MIN)
        if e <= cur["start"]:
            e = min(cur["start"] + 60, DAY_END_MIN)
        return e

    groups = []
    cur = None
    for m, e in dirs:
        d = "bullish" if e["vote"] > 0 else "bearish"
        if cur is None or d != cur["direction"]:
            if cur is not None:
                groups.append((cur, close_end(cur, m)))
            cur = {"direction": d, "start": m, "last": m, "events": [e]}
        else:
            cur["last"] = m
            cur["events"].append(e)
    if cur is not None:
        groups.append((cur, close_end(cur, None)))

    out = []
    for cur, end in groups:
        key = max(cur["events"],
                  key=lambda e: (IMPACT_W.get(e["impact"], 0), e["time"]))
        side = "up" if cur["direction"] == "bullish" else "down"
        tgt = (key.get("targets") or {}).get(side) or {}
        out.append({
            "direction": cur["direction"],
            "start": hhmm(cur["start"]),
            "end": hhmm(end),
            "event_ids": [e.get("id") for e in cur["events"]],
            "cause": key["title"],
            "target_price": tgt.get("price"),
            "target_pips": tgt.get("pips"),
        })
    return out


def bias_valid_window(bias: str, windows: list[dict]) -> dict | None:
    """First directional window matching the day's bias -> {start, end}.

    A directional day (bullish/bearish) always has at least one matching
    window, since windows are built from the same event votes. Returns None
    for a neutral day, where no single expiry can be claimed.
    """
    if bias not in ("bullish", "bearish"):
        return None
    matches = [w for w in windows if w.get("direction") == bias]
    if not matches:
        return None
    matches.sort(key=lambda w: parse_hhmm(w.get("start", "")) or 0)
    w = matches[0]
    return {"start": w["start"], "end": w["end"]}


def make_briefing(events: list[dict], bias: str, target: dict | None,
                  windows: list[dict], valid_until: str | None = None) -> dict:
    """Pre-render the daily Web Push briefing text."""
    if not events:
        return {
            "title": "EURUSD: quiet day",
            "body": "No High/Medium USD/EUR news today (UTC).",
        }
    first = events[0]["time"]
    headline = f"{bias} until {valid_until}" if valid_until else bias
    title = (f"EURUSD {headline}: {len(events)} event"
             f"{'s' if len(events) != 1 else ''}, first {first} UTC")

    arrow = lambda v: "▲" if v > 0 else "▼" if v < 0 else "±"  # noqa: E731
    lines = []
    for e in events[:3]:
        short = e["title"] if len(e["title"]) <= 24 else e["title"][:23] + "…"
        v = e.get("vote", 0)
        side = "up" if v > 0 else "down"
        tgt = ((e.get("targets") or {}).get(side) if v else None)
        if tgt:
            tail = f"{arrow(v)}{tgt['price']} ({tgt['pips']}p)"
        else:
            tail = f"±{e.get('expected_pips', 0)}p"
        lines.append(f"{e['time']} {short} {tail}")
    if len(events) > 3:
        lines.append(f"+{len(events) - 3} more")
    if windows:
        w = " ".join(f"{'▼' if x['direction'] == 'bearish' else '▲'}"
                     f"{x['start']}-{x['end']}" for x in windows[:3])
        lines.append(w)
    if valid_until and bias in ("bullish", "bearish"):
        lines.append(f"until {valid_until} UTC")
    if target and bias in ("bullish", "bearish"):
        lines.append(f"aim {target['price']}")
    body = " · ".join(lines)
    if len(body) > 400:
        body = body[:397] + "…"
    return {"title": title, "body": body}


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
    ap.add_argument("--date", default=None,
                    help="YYYY-MM-DD (default: today, UTC - the news calendar day)")
    ap.add_argument("--min-impact", choices=["High", "Medium"], default="Medium")
    ap.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_HOURS,
                    help="max length of a directional bias window (hours)")
    args = ap.parse_args()

    start, end = parse_window(args.window)
    levels_file = load_levels()
    # News calendar day = today (UTC). levels.json "date" is the *next* session
    # day after the last bar and must not be used here: the push worker matches
    # bias.date against the current UTC date to decide whether to run.
    date = args.date or datetime.now(timezone.utc).date().isoformat()
    win = {"start": args.window.split("-")[0], "end": args.window.split("-")[1], "tz": "UTC"}

    out = {
        "pair": "EURUSD",
        "date": date,
        "window": win,
        "bias": None,
        "confidence": None,
        "score": None,
        "events": [],
        "windows": [],
        "valid_from": None,
        "valid_until": None,
        "target": None,
        "briefing": None,
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

    hour_vol = load_hour_vol()
    atr_pips = (levels_file or {}).get("atr_pips")
    anchor = (levels_file or {}).get("anchor_close")

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
        e["id"] = slug_id(date, e["time"], e["country"], e["title"])
        hour = parse_hhmm(e["time"])
        mult = hour_vol.get(str((hour or 0) // 60), {}).get("mult", 1.0) or 1.0
        mult = max(HOUR_CLAMP[0], min(float(mult), HOUR_CLAMP[1]))
        base = (atr_pips * FRAC[e["impact"]] if atr_pips
                else FALLBACK_PIPS[e["impact"]])
        e["expected_pips"] = round(base * mult, 1)
        e["targets"] = {
            "up": level_target(levels_file, date, anchor, e["expected_pips"], 1),
            "down": level_target(levels_file, date, anchor, e["expected_pips"], -1),
        }
        out["events"].append(e)

    bias = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
    out["bias"] = bias
    out["score"] = score
    out["confidence"] = round(abs(score) / total_w, 2) if total_w else 0.0
    out["target"] = pick_target(levels_file, bias, date) if levels_file else None
    out["windows"] = build_windows(out["events"], args.window_hours)
    valid = bias_valid_window(bias, out["windows"])
    out["valid_from"] = valid["start"] if valid else None
    out["valid_until"] = valid["end"] if valid else None
    out["briefing"] = make_briefing(out["events"], bias, out["target"],
                                    out["windows"], out["valid_until"])

    (PUBLIC / "bias.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    tgt = out["target"]
    tgt_s = f" -> {tgt['price']} ({tgt['type']}, {tgt['distance_pips']} pips)" if tgt else " -> no target"
    win_s = " ".join(f"{w['direction'][:3]}:{w['start']}-{w['end']}"
                     for w in out["windows"])
    valid_s = (f" valid={out['valid_from']}-{out['valid_until']}"
               if out["valid_until"] else " valid=none")
    print(f"wrote public/bias.json date={date} window={args.window} "
          f"bias={bias} score={score} conf={out['confidence']} "
          f"events={len(events)} windows=[{win_s}]{valid_s}{tgt_s}", flush=True)


if __name__ == "__main__":
    main()

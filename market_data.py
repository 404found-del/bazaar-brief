#!/usr/bin/env python3
"""
Live market data for Bazaar Brief.

Deliberately auth-free. Kite Connect was the obvious choice until the docs
confirmed its access token expires at 6 AM daily "(regulatory requirement)"
and needs an interactive 2FA login to renew — a daily manual chore is exactly
what this project exists to avoid. Yahoo Finance needs no credentials, never
expires, and is reachable from CI.

Sector performance is COMPUTED from constituents rather than read off twelve
separate sector-index feeds: fewer moving parts, and it degrades to "some
sectors" instead of failing when one feed is down.

    from market_data import fetch_day
    data = fetch_day()      # -> the same dict shape sample_spec.json uses
"""
from __future__ import annotations

import datetime as dt
import os
import sys

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

INDICES = [
    ("Nifty 50",   "^NSEI"),
    ("Sensex",     "^BSESN"),
    ("Nifty Bank", "^NSEBANK"),
    ("India VIX",  "^INDIAVIX"),
]

# Nifty 50 constituents with the sector we speak about them in.
# Index membership changes a couple of times a year — worth a review each
# March and September. A ticker that stops returning data is skipped, never
# fatal, so a stale entry degrades the post rather than breaking it.
CONSTITUENTS = {
    "HDFCBANK": ("HDFC Bank", "Bank"),
    "ICICIBANK": ("ICICI Bank", "Bank"),
    "SBIN": ("SBI", "Bank"),
    "KOTAKBANK": ("Kotak Bank", "Bank"),
    "AXISBANK": ("Axis Bank", "Bank"),
    "INDUSINDBK": ("IndusInd Bank", "Bank"),
    "BAJFINANCE": ("Bajaj Finance", "Fin Services"),
    "BAJAJFINSV": ("Bajaj Finserv", "Fin Services"),
    "SBILIFE": ("SBI Life", "Fin Services"),
    "HDFCLIFE": ("HDFC Life", "Fin Services"),
    "SHRIRAMFIN": ("Shriram Finance", "Fin Services"),
    "JIOFIN": ("Jio Financial", "Fin Services"),
    "TCS": ("TCS", "IT"),
    "INFY": ("Infosys", "IT"),
    "HCLTECH": ("HCL Tech", "IT"),
    "WIPRO": ("Wipro", "IT"),
    "TECHM": ("Tech Mahindra", "IT"),
    "RELIANCE": ("Reliance", "Energy"),
    "ONGC": ("ONGC", "Energy"),
    "BPCL": ("BPCL", "Energy"),
    "COALINDIA": ("Coal India", "Energy"),
    "NTPC": ("NTPC", "Energy"),
    "POWERGRID": ("Power Grid", "Energy"),
    "HINDUNILVR": ("HUL", "FMCG"),
    "ITC": ("ITC", "FMCG"),
    "NESTLEIND": ("Nestle India", "FMCG"),
    "BRITANNIA": ("Britannia", "FMCG"),
    "TATACONSUM": ("Tata Consumer", "FMCG"),
    "MARUTI": ("Maruti", "Auto"),
    "TMCV": ("Tata Motors", "Auto"),        # renamed at the 2025 demerger
    "M&M": ("M&M", "Auto"),
    "BAJAJ-AUTO": ("Bajaj Auto", "Auto"),
    "EICHERMOT": ("Eicher Motors", "Auto"),
    "HEROMOTOCO": ("Hero MotoCorp", "Auto"),
    "SUNPHARMA": ("Sun Pharma", "Pharma"),
    "DRREDDY": ("Dr Reddy's", "Pharma"),
    "CIPLA": ("Cipla", "Pharma"),
    "APOLLOHOSP": ("Apollo Hospitals", "Pharma"),
    "TATASTEEL": ("Tata Steel", "Metal"),
    "HINDALCO": ("Hindalco", "Metal"),
    "JSWSTEEL": ("JSW Steel", "Metal"),
    "ULTRACEMCO": ("UltraTech", "Cement"),
    "GRASIM": ("Grasim", "Cement"),
    "LT": ("L&T", "Infra"),
    "ADANIENT": ("Adani Enterprises", "Infra"),
    "ADANIPORTS": ("Adani Ports", "Infra"),
    "BHARTIARTL": ("Bharti Airtel", "Telecom"),
    "TITAN": ("Titan", "Consumer"),
    "ASIANPAINT": ("Asian Paints", "Consumer"),
    "TRENT": ("Trent", "Consumer"),
}


class DataError(RuntimeError):
    pass


def _pct(close, prev):
    if prev in (None, 0):
        return None
    return (close - prev) / prev * 100.0


CLOSE_HOUR_IST = 16         # NSE closes 15:30; give the feed until 16:00.
HOLIDAY_TOLERANCE = 2       # Sessions we may legitimately be behind, because
                            # we carry no NSE holiday calendar.


def expected_session(now=None, mode="same_day"):
    """The session this post is supposed to be about.

    "Roughly recent" is not good enough. Yahoo's daily bar for Indian indices
    lags the close by hours, so a wrap posted at 18:00 IST can silently carry
    the PREVIOUS session — one day old, well inside any loose tolerance, and
    completely wrong. The guard has to know which session it is owed.

    mode="same_day"        an evening wrap; wants today's close
    mode="previous_session" a morning brief; wants the last completed session
    """
    now = now or dt.datetime.now(IST)
    d = now.date()
    if mode == "same_day":
        if now.hour < CLOSE_HOUR_IST:
            d -= dt.timedelta(days=1)      # today's session isn't settled yet
    else:
        d -= dt.timedelta(days=1)
    while d.weekday() >= 5:                # Sat/Sun -> walk back to Friday
        d -= dt.timedelta(days=1)
    return d


def _sessions_between(a, b):
    """Weekdays from a to b, exclusive of a. Holidays are invisible to us."""
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def _last_two_closes(hist):
    """Return (close, prev, date_of_close).

    The DATE matters as much as the number. Everything downstream labels the
    post with a session date, and a wrap that says "Friday" over Wednesday's
    close is worse than no post at all.
    """
    h = hist.dropna(subset=["Close"])
    if len(h) < 2:
        return None, None, None
    closes = h["Close"].tolist()
    asof = h.index[-1]
    asof = asof.date() if hasattr(asof, "date") else None
    return closes[-1], closes[-2], asof


def check_freshness(asof, mode="same_day", now=None):
    """Refuse to publish the wrong session.

    Raises rather than warns: a wrong-session post cannot be walked back once
    it is on the grid, and an account that publishes stale numbers once is not
    trusted again.
    """
    if asof is None:
        raise DataError("no date on the latest bar — refusing to publish undated numbers")

    want = expected_session(now, mode)
    if asof > want:
        raise DataError(f"latest bar {asof} is ahead of the expected session {want} — "
                        f"clock or feed is wrong")

    behind = _sessions_between(asof, want)
    if behind == 0:
        return 0
    if behind <= HOLIDAY_TOLERANCE:
        # Could be a market holiday, could be a lagging feed. We cannot tell
        # them apart without a holiday calendar, so say so loudly and let the
        # post carry the session date the data actually has.
        print(f"  ! data is {behind} session(s) behind the expected {want} "
              f"(market holiday, or a lagging feed)", file=sys.stderr)
        return behind
    raise DataError(
        f"latest bar {asof} is {behind} sessions behind the expected session {want}. "
        f"The feed is stale — publishing this would misdate the market.")


def fetch_indices(yf):
    out, asof = [], None
    for name, ticker in INDICES:
        try:
            h = yf.Ticker(ticker).history(period="7d")
            close, prev, bar_date = _last_two_closes(h)
            if close is None:
                print(f"  ! {name} ({ticker}): no usable history", file=sys.stderr)
                continue
            if name == "Nifty 50":
                asof = bar_date
            out.append({"name": name, "close": round(close, 2),
                        "chg": round(close - prev, 2),
                        "pct": round(_pct(close, prev), 2),
                        "asof": str(bar_date)})
        except Exception as e:
            print(f"  ! {name} ({ticker}): {type(e).__name__}: {e}", file=sys.stderr)
    if not out or out[0]["name"] != "Nifty 50":
        raise DataError("Nifty 50 is mandatory and could not be fetched")
    return out, asof


def fetch_stocks(yf):
    """One batched download beats 50 sequential requests, and Yahoo
    rate-limits the latter."""
    symbols = [f"{s}.NS" for s in CONSTITUENTS]
    data = yf.download(symbols, period="7d", group_by="ticker",
                       progress=False, threads=True, auto_adjust=False)
    rows, missing = [], []
    for sym, (label, sector) in CONSTITUENTS.items():
        try:
            h = data[f"{sym}.NS"].dropna(subset=["Close"])
            close, prev, _ = _last_two_closes(h)
            if close is None:
                missing.append(sym)
                continue
            rows.append({"name": label, "sector": sector,
                         "pct": round(_pct(close, prev), 2),
                         "close": round(close, 2)})
        except Exception:
            missing.append(sym)            # a dropped constituent is not fatal
    if missing:
        # Index membership changes and tickers get renamed after demergers.
        # Surfaced every run so the list gets maintained instead of silently rotting.
        print(f"  ! {len(missing)} constituent(s) returned nothing: "
              f"{', '.join(missing)}", file=sys.stderr)
    if len(rows) < 40:
        raise DataError(f"only {len(rows)} of {len(CONSTITUENTS)} stocks returned data — "
                        f"too thin to describe the market honestly")
    return rows


def sectors_from(rows):
    """Equal-weighted average move per sector. Not the official index level —
    the slide says 'sector map', and the shape of the day is what matters."""
    buckets = {}
    for r in rows:
        buckets.setdefault(r["sector"], []).append(r["pct"])
    return [{"name": k, "pct": round(sum(v) / len(v), 2)}
            for k, v in sorted(buckets.items())]


def breadth_from(rows):
    up = sum(1 for r in rows if r["pct"] > 0)
    return {"advances": up, "declines": len(rows) - up, "total": len(rows)}


def fetch_flows():
    """FII/DII is NSE-only and NSE blocks non-Indian IPs, so this will
    usually fail on a CI runner. Returning None is a supported outcome:
    the post swaps in the breadth slide instead of carrying a blank."""
    return None


def fetch_day():
    try:
        import yfinance as yf
    except ImportError:
        raise DataError("yfinance is not installed (pip install yfinance)")

    print("fetching indices…")
    indices, asof = fetch_indices(yf)

    # Do this BEFORE anything else is computed. Everything downstream stamps a
    # session date onto the post, and numbers under the wrong date are worse
    # than no post at all.
    mode = os.environ.get("BB_MODE", "previous_session")
    age = check_freshness(asof, mode)
    print(f"data as of {asof} ({age} day(s) old) — freshness OK")

    print("fetching constituents…")
    stocks = fetch_stocks(yf)

    ranked = sorted(stocks, key=lambda r: -r["pct"])
    data = {
        # The kicker names the SESSION, not the day the job happened to run.
        "kicker": f"Yesterday's close · {asof:%a %d %b %Y}",
        "asof": str(asof),
        "indices": indices,
        "gainers": [{"name": r["name"], "pct": r["pct"]} for r in ranked[:5]],
        "losers": [{"name": r["name"], "pct": r["pct"]} for r in ranked[-5:]][::-1],
        "sectors": sectors_from(stocks),
        "breadth": breadth_from(stocks),
        "flows": fetch_flows(),
        "_source": "yahoo",
        "_stocks": len(stocks),
    }
    return data



# =========================================================================
# The week
#
# A separate path rather than a generalisation of the daily one. The daily
# code is about to start publishing unattended and a refactor underneath it
# buys nothing; the duplication here is small and deliberate.
#
# The window is chosen by DATE, never by counting back five bars. A week with
# a Wednesday holiday has four sessions, and counting would quietly reach
# back into the previous week and label the result "this week".
# =========================================================================

MIN_WEEK_SESSIONS = 2       # a holiday-shortened week is still a week
WEEK_PERIOD = "1mo"         # needs the session before Monday for the baseline


def _series(hist):
    """[(date, close)] ascending, NaNs dropped. Plain Python from here on."""
    h = hist.dropna(subset=["Close"])
    out = []
    for idx, close in zip(h.index, h["Close"].tolist()):
        d = idx.date() if hasattr(idx, "date") else None
        if d is not None:
            out.append((d, float(close)))
    return out


def week_bounds(asof):
    """Monday of asof's week, through asof itself."""
    return asof - dt.timedelta(days=asof.weekday()), asof


def week_move(series, monday, friday):
    """The week's move, or None if the week is too thin to describe.

    A dict rather than a tuple: callers pick fields by name, so adding one
    later cannot silently shift what an existing caller reads.

    The baseline is the last close BEFORE Monday, so the week's move is
    measured from where the previous week left off — a Monday gap belongs to
    this week, not the last one.
    """
    inside = [(d, c) for d, c in series if monday <= d <= friday]
    before = [c for d, c in series if d < monday]
    if len(inside) < MIN_WEEK_SESSIONS or not before:
        return None
    closes = [before[-1]] + [c for _, c in inside]
    if not closes[0]:
        return None
    return {"close": round(closes[-1], 2),
            "chg": round(closes[-1] - closes[0], 2),
            # Session-by-session, because a week that climbs steadily and a
            # week that round-trips have the same endpoints and are not the
            # same week. Endpoints alone throw that away.
            "path": [{"d": day.isoformat(),
                      "pct": round((c - prev) / prev * 100.0, 2) if prev else 0.0}
                     for (day, c), prev in zip(inside, closes[:-1])],
            "pct": round((closes[-1] - closes[0]) / closes[0] * 100.0, 2),
            "up_days": sum(1 for i in range(1, len(closes))
                           if closes[i] > closes[i - 1]),
            "sessions": len(inside)}


def fetch_indices_week(yf, monday=None):
    out, asof = [], None
    for name, ticker in INDICES:
        try:
            s = _series(yf.Ticker(ticker).history(period=WEEK_PERIOD))
            if not s:
                print(f"  ! {name} ({ticker}): no usable history", file=sys.stderr)
                continue
            end = s[-1][0]
            mon = monday or week_bounds(end)[0]
            m = week_move(s, mon, end)
            if m is None:
                print(f"  ! {name} ({ticker}): not enough of the week to measure",
                      file=sys.stderr)
                continue
            if name == "Nifty 50":
                asof = end
            out.append({"name": name, "asof": str(end), **m})
        except Exception as e:
            print(f"  ! {name} ({ticker}): {type(e).__name__}: {e}", file=sys.stderr)
    if not out or out[0]["name"] != "Nifty 50":
        raise DataError("Nifty 50 is mandatory and could not be fetched")
    return out, asof


def fetch_stocks_week(yf, monday, friday):
    symbols = [f"{s}.NS" for s in CONSTITUENTS]
    data = yf.download(symbols, period=WEEK_PERIOD, group_by="ticker",
                       progress=False, threads=True, auto_adjust=False)
    rows, missing = [], []
    for sym, (label, sector) in CONSTITUENTS.items():
        try:
            m = week_move(_series(data[f"{sym}.NS"]), monday, friday)
            if m is None:
                missing.append(sym)
                continue
            rows.append({"name": label, "sector": sector, "pct": m["pct"],
                         "up_days": m["up_days"], "sessions": m["sessions"]})
        except Exception:
            missing.append(sym)
    if missing:
        print(f"  ! {len(missing)} constituent(s) returned nothing: "
              f"{', '.join(missing)}", file=sys.stderr)
    if len(rows) < 40:
        raise DataError(f"only {len(rows)} of {len(CONSTITUENTS)} stocks returned data — "
                        f"too thin to describe the week honestly")
    return rows


def streaks_from(rows):
    """The thing a daily post structurally cannot show.

    A stock that gains 0.4% every session for a week never once appears in a
    day's top five, and finishes the week up 2%. Consistency is invisible at
    a one-day horizon, which is exactly why it is worth a slide.
    """
    full = [r for r in rows if r["sessions"] >= 3]

    def up_by(miss):
        return sorted([r for r in full if r["sessions"] - r["up_days"] == miss],
                      key=lambda r: -r["pct"])

    def down_by(miss):
        return sorted([r for r in full if r["up_days"] == miss],
                      key=lambda r: r["pct"])

    # A perfect five-session run is rare — some weeks nobody manages one. The
    # near-misses are the same story one day weaker, and without them the
    # slide is empty more often than not.
    return {"up_every": up_by(0), "down_every": down_by(0),
            "up_most": up_by(1), "down_most": down_by(1)}


def week_label(monday, friday):
    if monday.month == friday.month:
        return f"{monday:%d}\u2013{friday:%d %b %Y}"
    return f"{monday:%d %b}\u2013{friday:%d %b %Y}"


def fetch_week():
    try:
        import yfinance as yf
    except ImportError:
        raise DataError("yfinance is not installed (pip install yfinance)")

    print("fetching indices…")
    indices, asof = fetch_indices_week(yf)

    # Same guard as the daily path, same reason: a wrap labelled with the
    # wrong week is worse than no wrap. On a Saturday the session owed is
    # Friday, which is what previous_session resolves to.
    age = check_freshness(asof, os.environ.get("BB_MODE", "previous_session"))
    print(f"week ends {asof} ({age} session(s) old) — freshness OK")

    monday, friday = week_bounds(asof)
    print(f"fetching constituents for {monday} … {friday}")
    stocks = fetch_stocks_week(yf, monday, friday)

    ranked = sorted(stocks, key=lambda r: -r["pct"])
    sessions = max((r["sessions"] for r in stocks), default=0)
    return {
        "kicker": f"The week · {week_label(monday, friday)}",
        "asof": str(asof),
        "week": {"start": str(monday), "end": str(friday), "sessions": sessions},
        "indices": indices,
        "path": indices[0].get("path") or [],
        "gainers": [{"name": r["name"], "pct": r["pct"], "up_days": r["up_days"]}
                    for r in ranked[:5]],
        "losers": [{"name": r["name"], "pct": r["pct"], "up_days": r["up_days"]}
                   for r in ranked[-5:]][::-1],
        "sectors": sectors_from(stocks),
        "breadth": breadth_from(stocks),
        "streaks": streaks_from(stocks),
        "flows": None,
        "_source": "yahoo",
        "_stocks": len(stocks),
        "_weekly": True,
    }

if __name__ == "__main__":
    import json
    d = fetch_week() if "--week" in sys.argv else fetch_day()
    d.pop("_stocks", None)
    print(json.dumps(d, indent=2))

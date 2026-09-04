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
    "LTIM": ("LTIMindtree", "IT"),
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
    "TATAMOTORS": ("Tata Motors", "Auto"),
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


def _last_two_closes(hist):
    """Yahoo occasionally serves a partial bar for the current session, so
    take the last two settled rows rather than assuming row -1 is today."""
    closes = [c for c in hist["Close"].tolist() if c == c]     # drop NaN
    if len(closes) < 2:
        return None, None
    return closes[-1], closes[-2]


def fetch_indices(yf):
    out = []
    for name, ticker in INDICES:
        try:
            h = yf.Ticker(ticker).history(period="7d")
            close, prev = _last_two_closes(h)
            if close is None:
                print(f"  ! {name} ({ticker}): no usable history", file=sys.stderr)
                continue
            out.append({"name": name, "close": round(close, 2),
                        "chg": round(close - prev, 2),
                        "pct": round(_pct(close, prev), 2)})
        except Exception as e:
            print(f"  ! {name} ({ticker}): {type(e).__name__}: {e}", file=sys.stderr)
    if not out or out[0]["name"] != "Nifty 50":
        raise DataError("Nifty 50 is mandatory and could not be fetched")
    return out


def fetch_stocks(yf):
    """One batched download beats 50 sequential requests, and Yahoo
    rate-limits the latter."""
    symbols = [f"{s}.NS" for s in CONSTITUENTS]
    data = yf.download(symbols, period="7d", group_by="ticker",
                       progress=False, threads=True, auto_adjust=False)
    rows = []
    for sym, (label, sector) in CONSTITUENTS.items():
        try:
            h = data[f"{sym}.NS"].dropna(subset=["Close"])
            close, prev = _last_two_closes(h)
            if close is None:
                continue
            rows.append({"name": label, "sector": sector,
                         "pct": round(_pct(close, prev), 2),
                         "close": round(close, 2)})
        except Exception:
            continue                       # a dropped constituent is not fatal
    if len(rows) < 20:
        raise DataError(f"only {len(rows)} of {len(CONSTITUENTS)} stocks returned data")
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
    indices = fetch_indices(yf)
    print("fetching constituents…")
    stocks = fetch_stocks(yf)

    ranked = sorted(stocks, key=lambda r: -r["pct"])
    data = {
        "kicker": f"Daily wrap · {dt.datetime.now(IST):%a %d %b %Y}",
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


if __name__ == "__main__":
    import json
    d = fetch_day()
    d.pop("_stocks", None)
    print(json.dumps(d, indent=2))

#!/usr/bin/env python3
"""
The Saturday wrap: one week, end to end.

Same renderers, same voice, same publishing path as the weekday brief — a
different window over the data and copy written for it. What makes it worth
posting is the thing a daily post structurally cannot show: a stock that
adds a little every session never reaches a day's movers list and still
finishes the week meaningfully higher.

    python run_weekly.py --base-url https://example.com/bazaar-brief
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import story_week
import build_carousel_week
from run_daily import build_video, load_local_env, render_slides

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLIDE_COUNT = 6


def load_data(sample: bool):
    if sample:
        d = json.load(open("sample_week.json", encoding="utf-8"))
        d["_source"] = "sample"
    else:
        import market_data
        d = market_data.fetch_week()

    d.setdefault("cta", "The week that was, before Monday opens.")
    # The renderers default to a one-day horizon; say so where it differs.
    sess = (d.get("week") or {}).get("sessions") or 5
    d["hero_label"] = f"Nifty 50 · {sess} sessions"
    d["call_kicker"] = "The weekly call"
    d["call_lede"] = "Your call for next week"
    d["h_movers"] = "The week's<br>biggest moves"
    d["h_sectors"] = "Which sectors<br>carried the week"
    d["disclaimer"] = story_week.DISCLAIMER
    d["call"] = story_week.build_call(d)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="use sample_week.json instead of live market data")
    ap.add_argument("--base-url", required=True,
                    help="public root the slides will be served from")
    ap.add_argument("--pages-dir", default="docs",
                    help="directory GitHub Pages serves (default: docs)")
    a = ap.parse_args()
    load_local_env()

    data = load_data(a.sample)
    story_week.apply(data)
    print(f"angle  : {data['headline']}  (score {data['_angle_score']})")

    # Named for the week it covers, not the day the job ran — the same reason
    # the kicker names the session rather than the runtime.
    stamp = f"week-{data['asof']}"
    outdir = os.path.join(a.pages_dir, "slides", stamp)
    paths = render_slides(data, outdir, builder=build_carousel_week.build_html)
    if len(paths) != SLIDE_COUNT:
        sys.exit(f"expected {SLIDE_COUNT} slides, rendered {len(paths)}")

    base = a.base_url.rstrip("/")
    urls = [f"{base}/slides/{stamp}/{os.path.basename(p)}" for p in paths]

    reel_path = build_video(data, outdir, weekly=True)
    reel_url = f"{base}/slides/{stamp}/reel.mp4"
    with open("reel_url.txt", "w", encoding="utf-8") as f:
        f.write(reel_url)

    with open("urls.json", "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=2)
    cap = story_week.caption(data)
    with open("caption.txt", "w", encoding="utf-8") as f:
        f.write(cap)
    # The Reel needs its own: the carousel caption ends with a swipe
    # instruction, and a Reel has nothing to swipe.
    with open("caption_reel.txt", "w", encoding="utf-8") as f:
        f.write(story_week.caption(data, reel=True))

    print(f"slides : {len(paths)} -> {outdir}")
    print(f"reel   : {reel_url}  ({os.path.getsize(reel_path)/1e6:.2f} MB)")
    print(f"caption: {len(cap)} chars")
    for u in urls:
        print(f"  {u}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One day's post, end to end: data -> angle -> slides -> caption -> URLs.

Writes into the Pages directory so the rendered slides get a public https
URL, which is the only kind Meta will fetch. Emits urls.json and caption.txt
for publish.py to consume.

    python run_daily.py --sample --base-url https://user.github.io/bazaar-brief
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import story
from build_carousel import render

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLIDE_COUNT = 6


def load_data(sample: bool):
    if sample:
        d = json.load(open("sample_spec.json", encoding="utf-8"))
        d["_source"] = "sample"
        return d
    # The live data layer lands here: Kite primary, yfinance + NSE archives
    # as fallbacks, all normalised to this same shape.
    raise SystemExit("Live data source not wired up yet — run with --sample for now.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="use sample_spec.json instead of live market data")
    ap.add_argument("--base-url", required=True,
                    help="public root the slides will be served from")
    ap.add_argument("--pages-dir", default="docs",
                    help="directory GitHub Pages serves (default: docs)")
    a = ap.parse_args()

    today = dt.datetime.now(IST)
    stamp = today.strftime("%Y-%m-%d")

    data = load_data(a.sample)
    story.apply(data)
    print(f"angle  : {data['headline']}  (score {data['_angle_score']})")

    outdir = os.path.join(a.pages_dir, "slides", stamp)
    paths = render_slides(data, outdir)
    if len(paths) != SLIDE_COUNT:
        sys.exit(f"expected {SLIDE_COUNT} slides, rendered {len(paths)}")

    base = a.base_url.rstrip("/")
    urls = [f"{base}/slides/{stamp}/{os.path.basename(p)}" for p in paths]

    with open("urls.json", "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=2)
    cap = story.caption(data)
    with open("caption.txt", "w", encoding="utf-8") as f:
        f.write(cap)

    print(f"slides : {len(paths)} -> {outdir}")
    print(f"caption: {len(cap)} chars")
    for u in urls:
        print(f"  {u}")


def render_slides(data, outdir):
    """Write the spec next to the slides so a post is reproducible later."""
    os.makedirs(outdir, exist_ok=True)
    spec_path = os.path.join(outdir, "spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return render(spec_path, outdir)


if __name__ == "__main__":
    main()

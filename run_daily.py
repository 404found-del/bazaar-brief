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
from build_reel import render as render_reel
import narrate

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLIDE_COUNT = 6


def load_data(sample: bool):
    if sample:
        d = json.load(open("sample_spec.json", encoding="utf-8"))
        d["_source"] = "sample"
        return d

    import market_data
    d = market_data.fetch_day()

    # Editorial furniture the data layer has no opinion about.
    d.setdefault("cta", "Yesterday's market, before today's opens.")
    d["disclaimer"] = story.DISCLAIMER
    d["call"] = build_call(d)
    return d


def build_call(d):
    """Tomorrow's prediction, pinned to a round number near today's close.

    Yesterday's result is filled in by the comment-scoring step once that
    exists; until then the slide runs without the scoreboard strip.
    """
    close = d["indices"][0]["close"]
    level = round(close / 50) * 50            # nearest 50 reads as a real level
    return {
        "yesterday": None,
        "today": {
            # Posted before the open, so the call resolves at TODAY's close and
            # gets scored tomorrow morning. A same-day loop beats an overnight
            # one: people come back to find out whether they were right.
            "question": f"Nifty at today's close: above or below {level:,.0f}?",
            "level": level,                 # numeric, for the spoken version
            "a": "ABOVE", "b": "BELOW",
            "ask": "Comment your call before 9:15 — I score it tomorrow morning.",
        },
        # Switched on once ManyChat exists to answer it. Until then the
        # slide simply doesn't make the offer.
        "dm_keyword": os.environ.get("BB_DM_KEYWORD") or None,
        "dm_promise": "the full sector table and every Nifty 50 move",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="use sample_spec.json instead of live market data")
    ap.add_argument("--base-url", required=True,
                    help="public root the slides will be served from")
    ap.add_argument("--pages-dir", default="docs",
                    help="directory GitHub Pages serves (default: docs)")
    a = ap.parse_args()
    load_local_env()

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

    # The Reel is the discovery vehicle; the carousel is what converts the
    # people it brings. Same data, same day, different job.
    reel_path = build_video(data, outdir)
    reel_url = f"{base}/slides/{stamp}/reel.mp4"
    with open("reel_url.txt", "w", encoding="utf-8") as f:
        f.write(reel_url)

    with open("urls.json", "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=2)
    cap = story.caption(data)
    with open("caption.txt", "w", encoding="utf-8") as f:
        f.write(cap)

    print(f"slides : {len(paths)} -> {outdir}")
    print(f"reel   : {reel_url}  ({os.path.getsize(reel_path)/1e6:.2f} MB)")
    print(f"caption: {len(cap)} chars")
    for u in urls:
        print(f"  {u}")


def load_local_env(name=".env"):
    """Local runs read .env; CI passes real environment variables.

    setdefault, not assignment: a value already in the environment always
    wins, so this can never quietly override what a workflow set.
    """
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_video(data, outdir, weekly=False):
    """Narration-first Reel build. Shared by the daily brief and the weekly wrap.

    Narration comes FIRST: the scene timings are measured from how long each
    line actually takes to say. No voice configured is a supported outcome —
    the Reel then renders silent on its default timings.

    One copy on purpose. Two runners with their own version of this is how a
    fix lands in one and not the other.
    """
    reel_path = os.path.join(outdir, "reel.mp4")
    spec = spec_path_for(outdir)
    clips = narrate.narrate(data, os.path.join(outdir, "vo"), weekly=weekly)
    if clips:
        timings = narrate.scene_timings(clips)
        total = max(b for _, _, b in timings)
        silent = os.path.join(outdir, "_silent.mp4")
        render_reel(spec, silent, scenes=timings)
        track = os.path.join(outdir, "vo", "track.wav")
        narrate.mix_track(clips, timings, track, total)
        narrate.mux(silent, track, reel_path)
        os.remove(silent)
    else:
        print("no voice configured — rendering a silent reel")
        render_reel(spec, reel_path)
    return reel_path


def spec_path_for(outdir):
    return os.path.join(outdir, "spec.json")


def render_slides(data, outdir, builder=None):
    """Write the spec next to the slides so a post is reproducible later."""
    os.makedirs(outdir, exist_ok=True)
    spec_path = os.path.join(outdir, "spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return render(spec_path, outdir, builder=builder)


if __name__ == "__main__":
    main()

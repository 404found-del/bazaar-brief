# Bazaar Brief

Automated daily NSE market-wrap carousels for Instagram (@bazaar_brief).

## How it runs

A scheduled GitHub Action fires after market close (3:30 PM IST), fetches the
day's data, picks a story angle, renders six 1080x1350 slides, and publishes
the carousel to Instagram via the Meta Graph API.

    market data  ->  story.py  ->  build_carousel.py  ->  Graph API
    (Kite/NSE)       the angle     six PNG slides        auto-publish

## Files

| File | Does what |
|---|---|
| `story.py` | Decides what each day's post is *about*. Seven angle detectors, scored; the winner writes the headline and deck. |
| `build_carousel.py` | Renders a post spec into six Instagram slides via headless Chromium. |
| `sample_spec.json` | A worked example of the data shape the renderer expects. |

## Local run

    pip install playwright && playwright install chromium
    python build_carousel.py sample_spec.json out

Slides land in `out/`.

## Secrets

Nothing sensitive lives in this repo. Credentials go in `.env` locally
(gitignored) and in GitHub repository Secrets for the scheduled run.

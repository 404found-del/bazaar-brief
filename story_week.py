#!/usr/bin/env python3
"""
The editorial layer for the Saturday wrap.

Separate from story.py on purpose. The daily angles are about to start
publishing unattended and there is nothing to gain from making them
generic; what they share is imported, and the rest is written for a
horizon a daily post cannot see.

That horizon is the whole point. A stock that adds 0.4% every session for
five days never once appears in a day's top five and finishes the week up
2%. Consistency is structurally invisible at a one-day range, so it leads
the list of angles here rather than sitting in a footnote.
"""
from __future__ import annotations

from story import DISCLAIMER, HASHTAGS, _fmt, prose

MIN_STREAK_MOVE = 1.5      # below this, "up every day" is just noise with a pattern
QUIET_WEEK = 0.5           # |Nifty| under this is a week that went nowhere
BIG_WEEK = 2.0
SWEEP_GAP = 2.0            # points clear of the runner-up


def _nifty(d):
    return d["indices"][0]


def _streaks(d):
    s = d.get("streaks") or {}
    return s.get("up_every") or [], s.get("down_every") or []


def _sessions(d):
    return (d.get("week") or {}).get("sessions") or 5


_SPELLED = {2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def _spell(n, cap=False):
    """Headlines spell small numbers; digits read as data, not prose."""
    w = _SPELLED.get(n)
    if not w:
        return str(n)
    return w if cap else w.lower()


# ---------------------------------------------------------------- angles

def w_angle_grinder(d):
    """The week's quiet compounder — the one story a daily post cannot tell."""
    up, _ = _streaks(d)
    if not up:
        return None
    top = up[0]
    if top["pct"] < MIN_STREAK_MOVE:
        return None
    loud = {g["name"] for g in d["gainers"][:3]}
    # Worth more when it is NOT already the week's obvious winner: the point
    # is that it went unnoticed, not that it went up.
    score = 45 if top["name"] in loud else 58
    n = len(up)
    if n == 1:
        others = ""
    elif n == 2:
        others = f" {up[1]['name']} did the same."
    else:
        others = f" {_spell(n - 1, cap=True)} other names did the same."
    return (score,
            f"{top['name']} never had a red day.",
            f"It rose in all {top['sessions']} sessions and finished the week "
            f"{_fmt(top['pct'])}. No single day was big enough to reach a "
            f"daily movers list.{others}")


def w_angle_bleeder(d):
    """Same idea, pointing down. People hold these."""
    _, down = _streaks(d)
    if not down:
        return None
    worst = down[0]
    if worst["pct"] > -MIN_STREAK_MOVE:
        return None
    sess = worst.get("sessions", 5)
    return (52,
            f"{worst['name']} fell every single session.",
            f"{_spell(sess, cap=True)} chances to bounce, none taken — "
            f"{_fmt(worst['pct'])} across the week. Steady selling looks nothing "
            f"like a crash and does the same damage.")


def w_angle_breadth(d):
    """The index had a week the market did not."""
    n, b = _nifty(d), d.get("breadth") or {}
    total = b.get("total") or 0
    if not total:
        return None
    adv, dec = b.get("advances", 0), b.get("declines", 0)
    if n["pct"] > 0 and dec > adv:
        return (50, "The index had a good week. Most of it didn't.",
                f"Nifty finished {_fmt(n['pct'])}, but only {adv} of {total} "
                f"constituents rose. The average stock had a worse week than "
                f"the number suggests.")
    if n["pct"] < 0 and adv > dec:
        return (50, "The index fell. Most stocks didn't.",
                f"Nifty finished {_fmt(n['pct'])} while {adv} of {total} "
                f"constituents rose. The damage was concentrated in the "
                f"handful of names that carry the index.")
    return None


def w_angle_big(d):
    n = _nifty(d)
    if abs(n["pct"]) < BIG_WEEK:
        return None
    b = d.get("breadth") or {}
    way = "up" if n["pct"] > 0 else "down"
    return (46, f"A {abs(n['pct']):.1f}% week.",
            f"Nifty closed the week {_fmt(n['pct'])} at {n['close']:,.2f}, "
            f"{way} in {n.get('up_days', 0)} of {n.get('sessions', 5)} sessions, "
            f"with {b.get('advances', 0)} of {b.get('total', 50)} constituents "
            f"higher.")


def w_angle_sweep(d):
    s = sorted(d["sectors"], key=lambda x: -x["pct"])
    if len(s) < 2 or s[0]["pct"] - s[1]["pct"] < SWEEP_GAP:
        return None
    return (42, f"{prose(s[0]['name'])} ran away with the week.",
            f"{_fmt(s[0]['pct'])} against {_fmt(s[1]['pct'])} for the next best "
            f"sector — a {s[0]['pct'] - s[1]['pct']:.1f} point gap. "
            f"{prose(s[-1]['name'])} finished last at {_fmt(s[-1]['pct'])}.")


def w_angle_nowhere(d):
    """Five sessions of movement that cancelled out."""
    n = _nifty(d)
    if abs(n["pct"]) >= QUIET_WEEK:
        return None
    sess = n.get("sessions", 5)
    up = n.get("up_days", 0)
    if up in (0, sess):          # a straight line is a different story
        return None
    return (38, f"{_spell(sess, cap=True)} sessions. Nowhere.",
            f"Nifty ended the week {_fmt(n['pct'])} at {n['close']:,.2f} after "
            f"rising on {up} of {sess} days. All that movement, and the week "
            f"finished where it started.")


def w_angle_default(d):
    n, b = _nifty(d), d.get("breadth") or {}
    lead = max(d["sectors"], key=lambda s: s["pct"])
    return (10, f"{prose(lead['name'])} led the week.",
            f"Nifty finished {_fmt(n['pct'])} at {n['close']:,.2f}, with "
            f"{prose(lead['name'])} the strongest sector at {_fmt(lead['pct'])} "
            f"and {b.get('advances', 0)} of {b.get('total', 50)} constituents "
            f"higher.")


ANGLES = [w_angle_grinder, w_angle_bleeder, w_angle_breadth, w_angle_big,
          w_angle_sweep, w_angle_nowhere, w_angle_default]


def pick(d):
    hits = [h for h in (a(d) for a in ANGLES) if h]
    return max(hits, key=lambda h: h[0])


# ------------------------------------------------------------------ call

def build_call(d):
    """A week-long version of the daily question.

    Same ritual, longer horizon: ABOVE or BELOW, resolved next Saturday
    rather than tonight. Keeping the shape identical is deliberate — the
    weekday habit and the weekend habit should feel like one thing.
    """
    close = _nifty(d)["close"]
    level = round(close / 50) * 50
    return {
        "yesterday": None,
        "today": {
            "question": f"Nifty at next Friday's close: above or below {level:,.0f}?",
            "level": level,
            "a": "ABOVE", "b": "BELOW",
            "ask": "Comment your call — I score it next Saturday.",
        },
        "dm_keyword": None,
        "dm_promise": "the full week's sector table and every Nifty 50 move",
    }


# --------------------------------------------------------------- caption

def caption(d, limit=2200, reel=False):
    n, b = _nifty(d), d.get("breadth") or {}
    c = d.get("call", {}).get("today", {})
    up, down = _streaks(d)

    numbers = (f"Nifty {_fmt(n['pct'])} for the week at {n['close']:,.2f}  ·  "
               f"{b.get('advances', 0)} up / {b.get('declines', 0)} down")

    parts = [d["headline"], d["deck"], numbers]

    # The streak line is the reason to read a weekly post at all, so it goes
    # above the fold rather than into the swipe.
    if up:
        names = ", ".join(f"{r['name']} ({_fmt(r['pct'])})" for r in up[:3])
        parts.append(f"Rose every session: {names}")
    if down:
        names = ", ".join(f"{r['name']} ({_fmt(r['pct'])})" for r in down[:3])
        parts.append(f"Fell every session: {names}")

    parts.append(f"{c.get('question')}\n{c.get('ask')}" if c.get("question")
                 else "What are you watching next week?")
    # "Swipe" is a carousel instruction. On a Reel there is nothing to swipe,
    # and the first post shipped telling viewers to do exactly that.
    parts += [("The week's sector map and every big move are in the carousel."
               if reel else "Swipe for the week's sector map and every big move."),
              DISCLAIMER, HASHTAGS]

    body = "\n\n".join(parts)
    if len(body) > limit:
        body = body[: body.rindex("\n\n")].rstrip()
    return body[:limit]


def apply(d):
    score, headline, deck = pick(d)
    d["headline"], d["deck"], d["_angle_score"] = headline, deck, score
    d["movers_prompt"] = "Holding any of these? Drop the name below."
    d["flows_prompt"] = ("Which of these do you think keeps running next week?"
                         if (d.get("streaks") or {}).get("up_every")
                         else "Did your week look like the index's?")
    return d

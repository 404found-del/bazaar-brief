#!/usr/bin/env python3
"""
The angle engine.

Given a day's market data, decide what the post is ABOUT. This is the
difference between a publication and a bot that prints a table: a bot says
"Nifty +0.84%", an editor says "Banks did all the heavy lifting."

Each angle is a detector. It either fires on the day's data or it doesn't,
and returns a newsworthiness score. The highest scorer writes the headline.
"""
from __future__ import annotations


# Index names are abbreviated on the slides ("Bank", "Fin Services") but that
# reads like a database field in a sentence. This is how they're spoken.
SECTOR_PROSE = {
    "Bank": "Banks", "PSU Bank": "PSU banks", "Fin Services": "Financials",
    "IT": "IT", "FMCG": "FMCG", "Auto": "Autos", "Pharma": "Pharma",
    "Metal": "Metals", "Realty": "Realty", "Media": "Media",
    "Energy": "Energy", "Consumer Dur": "Consumer durables",
    "Oil & Gas": "Oil and gas", "Infra": "Infrastructure",
}


def prose(name):
    return SECTOR_PROSE.get(name, name)


def _breadth(sectors):
    up = sum(1 for s in sectors if s["pct"] > 0)
    return up, len(sectors) - up


def _fmt(v, unit="%"):
    return f"{v:+.2f}{unit}"


# ---------------------------------------------------------------- angles
# Each returns (score, headline, deck) or None. Scores are comparable:
# roughly "how surprising is this to someone who follows the market".

def angle_breadth_divergence(d):
    """Index up while most sectors fall — the most under-reported daily story."""
    nifty = d["indices"][0]["pct"]
    up, down = _breadth(d["sectors"])
    if nifty > 0.2 and down > up:
        lead = max(d["sectors"], key=lambda s: s["pct"])
        return (
            85 + min(down - up, 6) * 2,
            f"{prose(lead['name'])} did all the heavy lifting.",
            f"Nifty finished {_fmt(nifty)}, but {down} of {len(d['sectors'])} sectors "
            f"closed red. One sector carried the index.",
        )
    if nifty < -0.2 and up > down:
        lag = min(d["sectors"], key=lambda s: s["pct"])
        return (
            83,
            f"{prose(lag['name'])} dragged the whole market down.",
            f"Nifty fell {abs(nifty):.2f}% even though {up} of {len(d['sectors'])} sectors "
            f"finished green. The damage was concentrated.",
        )
    return None


def angle_fii_dii_divergence(d):
    """Foreign selling absorbed by domestic buying, or the reverse."""
    if not d.get("flows"):
        return None                       # NSE-only feed; often unavailable
    f, di = d["flows"]["fii"], d["flows"]["dii"]
    nifty = d["indices"][0]["pct"]
    if f < -500 and di > 500 and nifty > 0:
        return (
            80,
            "Foreigners sold. It didn't matter.",
            f"FIIs pulled ₹{abs(f):,.0f} crore out. Domestic funds put "
            f"₹{di:,.0f} crore in — and the index still closed {_fmt(nifty)}.",
        )
    if f > 500 and di < -500:
        return (
            72,
            "The two big money pools disagreed.",
            f"Foreign funds bought ₹{f:,.0f} crore while domestic funds sold "
            f"₹{abs(di):,.0f} crore. They rarely split this cleanly.",
        )
    return None


def angle_narrow_rally(d):
    """The index rose but most of its own stocks fell.

    A cap-weighted index can be dragged up by three heavyweights while the
    other forty-seven fall. Most people's portfolios follow the forty-seven,
    which is why this gap is worth naming.
    """
    b = d.get("breadth")
    if not b or not b.get("total"):
        return None
    nifty = d["indices"][0]["pct"]
    adv, dec, tot = b["advances"], b["declines"], b["total"]
    if nifty > 0.15 and dec > adv:
        return (92, "The index went up. Most stocks didn't.",
                f"Nifty closed {_fmt(nifty)}, but only {adv} of its {tot} stocks rose. "
                f"A handful of heavyweights carried the whole thing.")
    if nifty < -0.15 and adv > dec:
        return (88, "Red headline, green portfolio.",
                f"Nifty fell {abs(nifty):.2f}% while {adv} of its {tot} stocks actually "
                f"rose. The damage was concentrated in the big names.")
    return None


def angle_vix(d):
    """A volatility shock is always the story when it happens."""
    vix = next((i for i in d["indices"] if "VIX" in i["name"].upper()), None)
    if not vix:
        return None
    if vix["pct"] >= 10:
        return (
            90,
            "Fear just jumped.",
            f"India VIX spiked {_fmt(vix['pct'])} to {vix['close']:.2f}. "
            f"That is the market pricing in a bumpier road ahead.",
        )
    if vix["pct"] <= -8:
        return (
            70,
            "The market exhaled.",
            f"India VIX collapsed {_fmt(vix['pct'])} to {vix['close']:.2f} — "
            f"traders paying a lot less for protection than they were yesterday.",
        )
    return None


def angle_big_move(d):
    """A large index move speaks for itself.

    `sessions_since` is set by the data layer when it has enough history to
    say "best day in N sessions" truthfully. Without it we say nothing about
    history rather than reaching for a vague word like "weeks" — an unearned
    superlative is how a feed loses the people who actually know the market.
    """
    n = d["indices"][0]
    p = n["pct"]
    if abs(p) < 1.5:
        return None
    since = d.get("sessions_since")
    if p > 0:
        head = f"Nifty's best day in {since} sessions." if since else "That was a big one."
        return (95, head,
                f"The index closed up {abs(p):.2f}% at {n['close']:,.0f}. Moves this "
                f"size are worth understanding rather than celebrating.")
    head = f"Nifty's worst day in {since} sessions." if since else "That one hurt."
    return (95, head,
            f"The index fell {abs(p):.2f}% to {n['close']:,.0f}. Here's where the "
            f"damage actually landed.")


def angle_flat(d):
    """A genuinely nothing day is still a story if you frame it honestly."""
    n = d["indices"][0]
    if abs(n["pct"]) < 0.15:
        up, down = _breadth(d["sectors"])
        return (
            40,
            "A whole lot of nothing.",
            f"Nifty moved {_fmt(n['pct'])} — but underneath, {up} sectors rose and "
            f"{down} fell. The index hid a lot of movement.",
        )
    return None


def angle_broad(d):
    """Everything green, or everything red."""
    ups = [s for s in d["sectors"] if s["pct"] > 0]
    if len(ups) == len(d["sectors"]):
        return (78, "Every single sector closed green.",
                "Not one of the twelve finished red. Broad days like this say more "
                "about sentiment than any one stock does.")
    if not ups:
        return (82, "Nowhere to hide.",
                "All twelve sectors closed red. On days like this, diversification "
                "inside equities does nothing for you.")
    return None


def angle_default(d):
    n = d["indices"][0]
    lead = max(d["sectors"], key=lambda s: s["pct"])
    return (10, f"{prose(lead['name'])} led. The rest followed.",
            f"Nifty closed {_fmt(n['pct'])} at {n['close']:,.2f}, with "
            f"{prose(lead['name'])} the strongest sector at {_fmt(lead['pct'])}.")


ANGLES = [
    angle_big_move, angle_narrow_rally, angle_vix, angle_breadth_divergence,
    angle_fii_dii_divergence, angle_broad, angle_flat, angle_default,
]


def pick(d):
    """Return the best (score, headline, deck) for the day."""
    hits = [a(d) for a in ANGLES]
    hits = [h for h in hits if h]
    return max(hits, key=lambda h: h[0])


def prompts(d):
    """The comment prompts, chosen to suit the day rather than a fixed script."""
    movers = "Holding any of these five? Drop the name below."
    if not d.get("flows"):
        b = d.get("breadth") or {}
        if b.get("advances", 0) >= b.get("declines", 0):
            return movers, "More risers than fallers. Does that match how it felt?"
        return movers, "More fell than rose today. Bought anything into it?"
    f, di = d["flows"]["fii"], d["flows"]["dii"]
    if f < 0 and di > 0:
        flows = "Who's right here — FIIs or DIIs? Tell me below."
    elif f > 0 and di > 0:
        flows = "Both sides bought today. Bullish, or a crowded trade?"
    else:
        flows = "Both sides sold today. Caution, or an overreaction?"
    return movers, flows


HASHTAGS = (
    "#nifty50 #sensex #niftybank #nse #stockmarketindia #indianstockmarket "
    "#sharemarket #dalalstreet #investing #marketwrap #fiidii #stockmarketnews"
)

DISCLAIMER = (
    "Exchange data via Yahoo Finance; sector moves are equal-weighted averages "
    "of Nifty 50 constituents, not official index levels. Educational only — "
    "not investment advice and not a recommendation to buy or sell. "
    "Not SEBI-registered. Consult a registered adviser before investing."
)


def caption(d, limit=2200):
    """Instagram caption.

    The first line is doing almost all the work — it is the only part visible
    before "more" — so it carries the hook, and the ask goes high rather than
    buried under the hashtags where nobody reads it.
    """
    n = d["indices"][0]
    c = d.get("call", {}).get("today", {})
    ask = (f"{c.get('question')}\n"
           f"Comment {c.get('a', 'ABOVE')} or {c.get('b', 'BELOW')} before the 9:15 open — "
           f"I score every call tomorrow morning."
           ) if c.get("question") else "What are you watching tomorrow?"

    if d.get("flows"):
        numbers = (f"Nifty {_fmt(n['pct'])} at {n['close']:,.2f}  ·  "
                   f"FII {d['flows']['fii']:+,.0f} cr  ·  DII {d['flows']['dii']:+,.0f} cr")
    else:
        b = d.get("breadth") or {}
        numbers = (f"Nifty {_fmt(n['pct'])} at {n['close']:,.2f}  ·  "
                   f"{b.get('advances', 0)} up / {b.get('declines', 0)} down")

    body = "\n\n".join([
        d["headline"],
        d["deck"],
        numbers,
        ask,
        "Swipe for the sector map and the full mover list.",
        DISCLAIMER,
        HASHTAGS,
    ])

    if len(body) > limit:                     # drop hashtags before truncating words
        body = body[: body.rindex("\n\n")].rstrip()
    return body[:limit]


def apply(d):
    """Fill a raw data dict with its editorial layer, in place."""
    score, headline, deck = pick(d)
    d["headline"], d["deck"], d["_angle_score"] = headline, deck, score
    d["movers_prompt"], d["flows_prompt"] = prompts(d)
    return d

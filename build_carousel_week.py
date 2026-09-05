#!/usr/bin/env python3
"""
The weekly carousel: the daily deck with its two weakest slides replaced.

The first version of the wrap was the daily carousel with weekly numbers
poured into it, and it read exactly like that. Two slides were carrying no
weight:

  slide 2  two index levels and 60% empty space — the least interesting
           fact about a week
  slide 5  a breadth bar the sector map already implies

They are replaced by the two things only a week can show: the path it took
to get there, and the names that moved in the same direction every single
session. Everything else is reused from build_carousel, headings aside.
"""
from __future__ import annotations

import datetime as dt

from build_carousel import (BRAND, CSS, cls, foot, sign, slide1, slide3,
                            slide4, slide6)

WEEK_CSS = """
/* ---- slide 2: the week's path ---- */
.wpathwrap { position:relative; margin-top:46px; }
/* One continuous axis across the whole chart. Per-column segments break at
   every flex gap and stop reading as a zero line. 42px value row + half of
   the 470px chart. */
.wzeroline { position:absolute; left:0; right:0; top:277px; height:2px;
             background:rgba(255,255,255,.20); }
.wpath { display:flex; gap:20px; }
.wcol { flex:1; display:flex; flex-direction:column; align-items:center; }
.wval { font-size:29px; font-weight:800; height:42px; letter-spacing:-.01em; }
.wchart { width:100%; height:470px; display:flex; flex-direction:column; }
.wtop { flex:1; display:flex; align-items:flex-end; }
.wbot { flex:1; display:flex; align-items:flex-start; }
.wzero { height:2px; background:rgba(255,255,255,.14); }
.wbar { width:100%; }
.wbar.u { border-radius:9px 9px 0 0; background:#12b912; }
.wbar.d { border-radius:0 0 9px 9px; background:#e04a4a; }
.wday { margin-top:22px; font-size:27px; font-weight:750; letter-spacing:.08em;
        text-transform:uppercase; color:#86857f; }
.wsum { margin-top:46px; display:flex; gap:18px; }
.wsum .s { flex:1; border:1px solid rgba(255,255,255,.08); border-radius:20px;
           padding:24px 26px; }
.wsum .s b { display:block; font-size:23px; color:#9d9c96; font-weight:650;
             margin-bottom:8px; }
.wsum .s span { font-size:37px; font-weight:800; letter-spacing:-.02em; }
.widx { margin-top:26px; display:flex; gap:14px; flex-wrap:wrap; }
.widx span { font-size:26px; font-weight:650; color:#9d9c96;
             border:1px solid rgba(255,255,255,.08); border-radius:999px;
             padding:14px 24px; }
.widx b { font-weight:800; margin-left:10px; }

/* ---- slide 5: the streaks ---- */
.wstreak { display:flex; gap:30px; margin-top:38px; }
.wsc { flex:1; }
.wsrow { display:flex; align-items:center; gap:14px; padding:22px 0;
         border-bottom:1px solid rgba(255,255,255,.06); }
.wsrow > .m { flex:1; min-width:0; }      /* without this the value never
                                             reaches the right edge */
.wsname { font-size:30px; font-weight:700; color:#e6e5e0; }
.wsval { font-size:30px; font-weight:800; letter-spacing:-.01em; }
.wdots { display:flex; gap:5px; margin-top:8px; }
.wdot { width:13px; height:13px; border-radius:50%; box-sizing:border-box; }
.wrec { font-size:22px; color:#7f7e78; font-weight:650; margin-left:10px; }
.wempty { font-size:26px; color:#6e6d68; padding:24px 0; font-weight:600;
          line-height:1.45; }
.wnote { font-size:25px; color:#86857f; font-weight:550; margin-top:30px;
         line-height:1.5; }
"""

DAYS = "%a"


def _day(iso):
    return dt.date.fromisoformat(iso).strftime(DAYS)


def slide_path(d):
    """The shape of the week, session by session.

    Two weeks can finish +1.2% having done completely different things — one
    grinding up every day, one crashing Monday and recovering all week. The
    index number cannot tell them apart. This can.
    """
    path = d.get("path") or []
    mx = max((abs(p["pct"]) for p in path), default=0) or 1

    cols = ""
    for p in path:
        h = max(abs(p["pct"]) / mx * 100, 5)
        up = p["pct"] >= 0
        bar = f'<div class="wbar {"u" if up else "d"}" style="height:{h:.1f}%"></div>'
        cols += f"""<div class="wcol">
          <div class="wval num {cls(p['pct'])}">{sign(p['pct'])}%</div>
          <div class="wchart">
            <div class="wtop">{bar if up else ""}</div>
            <div class="wzero"></div>
            <div class="wbot">{"" if up else bar}</div>
          </div>
          <div class="wday">{_day(p['d'])}</div>
        </div>"""

    n = d["indices"][0]
    others = "".join(
        f'<span>{i["name"]}<b class="num {cls(i["pct"])}">{sign(i["pct"])}%</b></span>'
        for i in d["indices"][1:])
    ups = sum(1 for p in path if p["pct"] >= 0)
    big = max(path, key=lambda p: abs(p["pct"])) if path else None

    cards = f"""<div class="s"><b>Net for the week</b>
        <span class="num {cls(n['pct'])}">{sign(n['pct'])}%</span></div>
      <div class="s"><b>Up / down days</b>
        <span class="num">{ups} / {len(path) - ups}</span></div>"""
    if big:
        cards += f"""<div class="s"><b>Biggest single day</b>
        <span class="num {cls(big['pct'])}">{_day(big['d'])} {sign(big['pct'])}%</span></div>"""

    return f"""
<div class="slide"><div class="z">
  <div class="kicker"><span class="dot"></span>The week, day by day</div>
  <div style="margin-top:40px"><h2>{d.get('h_path') or 'How the week<br>actually went'}</h2></div>
  <div class="wpathwrap"><div class="wzeroline"></div>
    <div class="wpath">{cols}</div></div>
  <div class="wsum">{cards}</div>
  <div class="widx">{others}</div>
</div>{foot(2,6)}</div>"""


def _rows(items, positive, limit=5):
    """Rows with the exact record spelled out.

    Perfect and near-perfect runs sit in one list because a five-session
    sweep is rare enough that a purist slide is blank most weeks. The dots
    keep it honest: four filled and one hollow is not the same claim as five
    filled, and the row says which it is.
    """
    if not items:
        return ('<div class="wempty">Nobody managed it this week. Every name '
                'had at least two days going the other way.</div>')
    colour = "#12b912" if positive else "#e04a4a"
    out = ""
    for r in items[:limit]:
        n = r.get("sessions") or 5
        good = r["up_days"] if positive else n - r["up_days"]
        dots = "".join(
            f'<span class="wdot" style="background:{colour}"></span>' if i < good
            else f'<span class="wdot" style="border:2px solid {colour}"></span>'
            for i in range(n))
        out += f"""<div class="wsrow">
          <div class="m">
            <div class="wsname">{r['name']}</div>
            <div class="wdots">{dots}<span class="wrec">{good} of {n}</span></div>
          </div>
          <div class="wsval num {cls(r['pct'])}">{sign(r['pct'])}%</div>
        </div>"""
    return out


def slide_streaks(d):
    """The names that never changed direction.

    A stock adding 0.4% a session never reaches a daily movers list and ends
    the week up 2%. That is invisible at a one-day range, which is the whole
    argument for a weekly post existing.
    """
    st = d.get("streaks") or {}
    up = (st.get("up_every") or []) + (st.get("up_most") or [])
    down = (st.get("down_every") or []) + (st.get("down_most") or [])
    return f"""
<div class="slide"><div class="z">
  <div class="kicker"><span class="dot"></span>The quiet ones</div>
  <div style="margin-top:40px"><h2>{d.get('h_streaks') or 'The names that<br>kept going'}</h2></div>
  <div class="wstreak">
    <div class="wsc">
      <div class="col-head up">Grinding higher</div>
      {_rows(up, True)}
    </div>
    <div class="wsc">
      <div class="col-head down">Grinding lower</div>
      {_rows(down, False)}
    </div>
  </div>
  <div class="wnote">A name can do this without ever reaching a daily movers
    list — small moves, repeated, don't look like much until Friday.</div>
  <div class="prompt-line">{d.get('flows_prompt', '')}</div>
</div>{foot(5,6)}</div>"""


def build_html(d):
    slides = (slide1(d) + slide_path(d) + slide3(d)
              + slide4(d) + slide_streaks(d) + slide6(d))
    return f"<meta charset='utf-8'><style>{CSS}{WEEK_CSS}</style>{slides}"

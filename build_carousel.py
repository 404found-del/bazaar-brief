#!/usr/bin/env python3
"""
Daily market-wrap carousel renderer.
Takes a post spec (dict/JSON) -> renders 5 Instagram slides at 1080x1350.

This is the render layer of the pipeline. The data layer feeds it a spec;
nothing here knows where the numbers came from.
"""
import json, os, sys, subprocess

W, H = 1080, 1350

BRAND = {
    "name": "BAZAAR BRIEF",
    "handle": "@bazaar_brief",
}

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#050505; }
.slide {
  width:1080px; height:1350px; position:relative; overflow:hidden;
  background:#0a0a0b;
  font-family:"Inter","Inter Display",system-ui,sans-serif;
  color:#ffffff;
  padding:76px 76px 68px 76px;
  display:flex; flex-direction:column;
}
.slide::after{
  content:""; position:absolute; inset:0; pointer-events:none;
  background:radial-gradient(120% 70% at 50% -10%, rgba(57,135,229,0.13), transparent 62%);
}
.z { position:relative; z-index:2; flex:1; display:flex; flex-direction:column; }
.spread { justify-content:space-between; }

/* ---- shared chrome ---- */
.kicker {
  font-size:23px; font-weight:700; letter-spacing:.18em; text-transform:uppercase;
  color:#7f7e78; display:flex; align-items:center; gap:14px;
}
.kicker .dot { width:9px; height:9px; border-radius:50%; background:#3987e5; }
.foot {
  position:relative; z-index:2; flex:0 0 auto;
  margin-top:44px; display:flex; flex-direction:row;
  align-items:center; justify-content:space-between;
  font-size:21px; color:#6e6d68; font-weight:600; letter-spacing:.04em;
}
.foot .brand { color:#a9a8a2; font-weight:800; letter-spacing:.12em; }
.swipe { display:flex; align-items:center; gap:10px; color:#3987e5; font-weight:700; }

h1 { font-size:96px; line-height:1.02; font-weight:800; letter-spacing:-0.035em; }
h2 { font-size:60px; line-height:1.08; font-weight:800; letter-spacing:-0.03em; }
.sub { font-size:28px; line-height:1.45; color:#a9a8a2; font-weight:450; }

.num { font-variant-numeric:tabular-nums; }
.up   { color:#12b912; }
.down { color:#e04a4a; }

/* ---- slide 1 hero ---- */
.hero-figure { font-size:210px; font-weight:800; letter-spacing:-0.05em; line-height:0.9; }
.hero-label { font-size:26px; color:#86857f; font-weight:600; letter-spacing:.06em; text-transform:uppercase; }

/* ---- stat tiles ---- */
.tiles { display:grid; grid-template-columns:1fr 1fr; gap:22px; margin-top:52px; }
.tile {
  background:#141417; border:1px solid rgba(255,255,255,0.07);
  border-radius:22px; padding:40px 34px 36px 34px; min-height:296px;
  display:flex; flex-direction:column; justify-content:center;
}
.tile .t-name { font-size:24px; color:#86857f; font-weight:650; letter-spacing:.04em; }
.tile .t-val  { font-size:62px; font-weight:800; letter-spacing:-0.03em; margin-top:12px; }
.tile .t-chg  { font-size:29px; font-weight:700; margin-top:8px; }

/* ---- bars ---- */
.barwrap { margin-top:26px; }
.bar-row { display:flex; align-items:center; gap:20px; margin-bottom:22px; }
.bar-name { width:262px; font-size:29px; font-weight:650; color:#e6e5e0; }
.bar-track { flex:1; height:40px; display:flex; align-items:center; }
.bar-fill { height:40px; border-radius:4px; }
.bar-val { width:135px; text-align:right; font-size:29px; font-weight:750; }
.col-head { font-size:27px; font-weight:750; letter-spacing:.1em; text-transform:uppercase; margin-bottom:14px; }

/* ---- heatmap ---- */
.heat { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-top:44px; }
.cell {
  border-radius:18px; padding:30px 26px; min-height:158px;
  display:flex; flex-direction:column; justify-content:space-between;
  border:1px solid rgba(255,255,255,0.07);
}
.cell .c-name { font-size:25px; font-weight:650; color:#f2f1ec; line-height:1.2; }
.cell .c-val { font-size:44px; font-weight:800; letter-spacing:-0.02em; }

/* ---- flows ---- */
.flow { display:flex; gap:22px; margin-top:46px; }
.flow-card {
  flex:1; background:#141417; border:1px solid rgba(255,255,255,0.07);
  border-radius:22px; padding:38px 34px;
}
.flow-card .f-name { font-size:25px; color:#86857f; font-weight:650; letter-spacing:.05em; }
.flow-card .f-val { font-size:66px; font-weight:800; letter-spacing:-0.03em; margin-top:14px; }
.flow-card .f-note { font-size:22px; color:#6e6d68; margin-top:10px; font-weight:500; }

.disclaimer {
  margin-top:38px; font-size:19px; line-height:1.5; color:#5d5c58;
  border-top:1px solid rgba(255,255,255,0.08); padding-top:22px; font-weight:500;
}
.cta {
  margin-top:40px; background:#141417; border:1px solid rgba(57,135,229,0.35);
  border-radius:22px; padding:34px 36px;
}
.cta .c-big { font-size:38px; font-weight:800; letter-spacing:-0.02em; line-height:1.25; }
.cta .c-small { font-size:24px; color:#a9a8a2; margin-top:12px; font-weight:500; }

/* ---- the call: engagement engine ---- */
.result {
  background:#141417; border:1px solid rgba(255,255,255,0.08);
  border-radius:18px; padding:26px 30px;
  display:flex; align-items:center; gap:22px;
}
.result .badge {
  flex:0 0 auto; font-size:21px; font-weight:800; letter-spacing:.08em;
  padding:10px 18px; border-radius:999px;
}
.badge.win  { background:rgba(18,185,18,0.16);  color:#12b912; border:1px solid rgba(18,185,18,0.4); }
.badge.miss { background:rgba(224,74,74,0.16);  color:#e04a4a; border:1px solid rgba(224,74,74,0.4); }
.result .r-txt { font-size:24px; line-height:1.4; color:#c9c8c2; font-weight:550; }
.result .r-txt b { color:#ffffff; font-weight:800; }

.qbig { font-size:70px; font-weight:800; letter-spacing:-0.03em; line-height:1.1; }
.chips { display:flex; gap:20px; margin-top:38px; }
.chip {
  flex:1; text-align:center; border-radius:20px; padding:38px 20px;
  font-size:46px; font-weight:800; letter-spacing:.02em;
}
.chip.a { background:rgba(18,185,18,0.14); border:2px solid rgba(18,185,18,0.5); color:#12b912; }
.chip.b { background:rgba(224,74,74,0.14); border:2px solid rgba(224,74,74,0.5); color:#e04a4a; }
.chip small { display:block; font-size:20px; font-weight:650; color:#8f8e88; letter-spacing:.06em; margin-top:10px; }
.ask { font-size:32px; font-weight:750; color:#ffffff; margin-top:32px; text-align:center; }

.dmbox {
  margin-top:34px; background:rgba(57,135,229,0.10);
  border:1px solid rgba(57,135,229,0.42); border-radius:20px; padding:30px 32px;
}
.dmbox .d-big { font-size:31px; font-weight:800; line-height:1.3; }
.dmbox .d-big em { font-style:normal; color:#5ea0f0; }
.dmbox .d-small { font-size:22px; color:#9d9c96; margin-top:10px; font-weight:500; }

.thindisc { margin-top:auto; padding-top:24px; font-size:17px; line-height:1.45; color:#4f4e4b; font-weight:500; }
.prompt-line { font-size:27px; font-weight:700; color:#5ea0f0; margin-top:22px; }
"""


MINUS = "−"  # true minus sign, not a hyphen


def sign(v):
    return f"+{v:.2f}" if v >= 0 else f"{MINUS}{abs(v):.2f}"


def cls(v):
    return "up" if v >= 0 else "down"


def heat_bg(pct, maxmag):
    """Diverging fill. Colour is ordered by magnitude; every cell also carries
    its numeric value, so colour never carries the meaning alone."""
    a = min(abs(pct) / maxmag, 1.0) if maxmag else 0
    alpha = 0.10 + 0.42 * a
    rgb = "18,185,18" if pct >= 0 else "224,74,74"
    return f"rgba({rgb},{alpha:.3f})"


def foot(page, total, swipe=True):
    s = '<div class="swipe">Swipe &rsaquo;</div>' if swipe else '<div class="swipe">Follow for daily</div>'
    return (f'<div class="foot"><div class="brand">{BRAND["handle"]}</div>'
            f'{s}<div>{page}/{total}</div></div>')


def slide1(d):
    idx = d["indices"][0]
    return f"""
<div class="slide"><div class="z spread">
  <div class="kicker"><span class="dot"></span>{d['kicker']}</div>
  <h1>{d['headline']}</h1>
  <div>
    <div class="hero-label">{idx['name']} · Close</div>
    <div class="hero-figure num {cls(idx['pct'])}" style="margin-top:18px">{sign(idx['pct'])}%</div>
    <div class="sub num" style="margin-top:26px">{idx['close']:,.2f} &nbsp;·&nbsp; {sign(idx['chg'])} pts</div>
  </div>
  <div class="sub" style="max-width:900px">{d['deck']}</div>
</div>{foot(1,6)}</div>"""


def slide2(d):
    tiles = ""
    for i in d["indices"]:
        tiles += f"""<div class="tile">
          <div class="t-name">{i['name']}</div>
          <div class="t-val num">{i['close']:,.2f}</div>
          <div class="t-chg num {cls(i['pct'])}">{sign(i['pct'])}% &nbsp;({sign(i['chg'])})</div>
        </div>"""
    return f"""
<div class="slide"><div class="z">
  <div class="kicker"><span class="dot"></span>The scoreboard</div>
  <div style="margin-top:44px"><h2>Where the market<br>closed today</h2></div>
  <div class="tiles">{tiles}</div>
</div>{foot(2,6)}</div>"""


def bars(rows, positive, mx):
    """mx is shared across gainers and losers so bar lengths are comparable
    on one scale — a -2.6% bar must not look as long as a +3.4% bar."""
    color = "#12b912" if positive else "#e04a4a"
    out = ""
    for r in rows:
        w = max(abs(r["pct"]) / mx * 100, 6)
        out += f"""<div class="bar-row">
          <div class="bar-name">{r['name']}</div>
          <div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div></div>
          <div class="bar-val num {cls(r['pct'])}">{sign(r['pct'])}%</div>
        </div>"""
    return out


def slide3(d):
    mx = max(abs(r["pct"]) for r in d["gainers"] + d["losers"]) or 1
    return f"""
<div class="slide"><div class="z spread">
  <div>
    <div class="kicker"><span class="dot"></span>Movers</div>
    <div style="margin-top:40px"><h2>Biggest moves<br>in the Nifty 50</h2></div>
  </div>
  <div class="barwrap">
    <div class="col-head up">Top gainers</div>
    {bars(d['gainers'], True, mx)}
  </div>
  <div class="barwrap">
    <div class="col-head down">Top losers</div>
    {bars(d['losers'], False, mx)}
    <div class="prompt-line">{d['movers_prompt']}</div>
  </div>
</div>{foot(3,6)}</div>"""


def slide4(d):
    mx = max(abs(s["pct"]) for s in d["sectors"]) or 1
    cells = ""
    # sorted best -> worst so the grid reads as one gradient
    for s in sorted(d["sectors"], key=lambda x: -x["pct"]):
        cells += f"""<div class="cell" style="background:{heat_bg(s['pct'], mx)}">
          <div class="c-name">{s['name']}</div>
          <div class="c-val num {cls(s['pct'])}">{sign(s['pct'])}%</div>
        </div>"""
    return f"""
<div class="slide"><div class="z">
  <div class="kicker"><span class="dot"></span>Sector map</div>
  <div style="margin-top:40px"><h2>Which sectors<br>carried the day</h2></div>
  <div class="heat">{cells}</div>
</div>{foot(4,6)}</div>"""


def slide5(d):
    """Institutional flows when we have them, market breadth when we don't.

    FII/DII is published only by NSE, which blocks non-Indian IPs, so this
    slide must stand on its own without it rather than showing a blank card.
    """
    if not d.get("flows"):
        return slide5_breadth(d)
    f_ = d["flows"]
    return f"""
<div class="slide"><div class="z spread">
  <div>
    <div class="kicker"><span class="dot"></span>Who was buying</div>
    <div style="margin-top:40px"><h2>Institutional<br>flows</h2></div>
  </div>
  <div class="flow">
    <div class="flow-card">
      <div class="f-name">FII / FPI</div>
      <div class="f-val num {cls(f_['fii'])}">{sign(f_['fii'])}</div>
      <div class="f-note">&#8377; crore, cash market</div>
    </div>
    <div class="flow-card">
      <div class="f-name">DII</div>
      <div class="f-val num {cls(f_['dii'])}">{sign(f_['dii'])}</div>
      <div class="f-note">&#8377; crore, cash market</div>
    </div>
  </div>
  <div>
    <div class="sub">{d['flows_note']}</div>
    <div class="prompt-line">{d['flows_prompt']}</div>
  </div>
</div>{foot(5,6)}</div>"""


def slide5_breadth(d):
    b = d.get("breadth") or {"advances": 0, "declines": 0, "total": 0}
    adv, dec = b["advances"], b["declines"]
    total = max(b.get("total") or (adv + dec), 1)
    return f"""
<div class="slide"><div class="z spread">
  <div>
    <div class="kicker"><span class="dot"></span>Under the surface</div>
    <div style="margin-top:40px"><h2>How many actually<br>went up?</h2></div>
  </div>
  <div class="flow">
    <div class="flow-card">
      <div class="f-name">ADVANCED</div>
      <div class="f-val num up">{adv}</div>
      <div class="f-note">of {total} Nifty 50 stocks</div>
    </div>
    <div class="flow-card">
      <div class="f-name">DECLINED</div>
      <div class="f-val num down">{dec}</div>
      <div class="f-note">of {total} Nifty 50 stocks</div>
    </div>
  </div>
  <div>
    <div class="sub">{d.get('flows_note', 'The index is an average. This is the spread underneath it.')}</div>
    <div class="prompt-line">{d['flows_prompt']}</div>
  </div>
</div>{foot(5,6)}</div>"""


def slide6(d):
    c = d["call"]
    y, t = c.get("yesterday"), c["today"]

    # No scoreboard on day one, or on any day the comment scoring had
    # nothing to read. Better an honest gap than a fabricated result.
    if y:
        badge = "win" if y["correct"] else "miss"
        badge_txt = "CALLED IT" if y["correct"] else "MISSED IT"
        strip = (f'<div class="result" style="margin-top:34px">'
                 f'<div class="badge {badge}">{badge_txt}</div>'
                 f'<div class="r-txt"><b>{y["pct"]}%</b> of you said '
                 f'<b>{y["side"]}</b>. {y["result"]}</div></div>')
    else:
        strip = ""

    return f"""
<div class="slide"><div class="z">
  <div class="kicker"><span class="dot"></span>The daily call</div>
  {strip}
  <div style="margin-top:52px">
    <div class="hero-label">Your call for tomorrow</div>
    <div class="qbig" style="margin-top:16px">{t['question']}</div>
  </div>

  <div class="chips">
    <div class="chip a">{t['a']}<small>COMMENT THIS</small></div>
    <div class="chip b">{t['b']}<small>COMMENT THIS</small></div>
  </div>
  <div class="ask">{t['ask']}</div>

  <div class="dmbox">
    <div class="d-big">Want the numbers behind this? Comment <em>{c['dm_keyword']}</em></div>
    <div class="d-small">I'll DM you {c['dm_promise']} — free, no catch.</div>
  </div>

  <div class="thindisc">{d['disclaimer']}</div>
</div>{foot(6,6,swipe=False)}</div>"""


def build_html(d):
    slides = slide1(d) + slide2(d) + slide3(d) + slide4(d) + slide5(d) + slide6(d)
    return f"<style>{CSS}</style>{slides}"


def render(spec_path, outdir):
    from playwright.sync_api import sync_playwright
    d = json.load(open(spec_path))
    html = build_html(d)
    os.makedirs(outdir, exist_ok=True)
    hp = os.path.join(outdir, "_carousel.html")
    open(hp, "w").write(html)
    paths = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto("file://" + os.path.abspath(hp))
        pg.wait_for_timeout(600)
        for i, el in enumerate(pg.query_selector_all(".slide"), 1):
            out = os.path.join(outdir, f"slide{i}.png")
            el.screenshot(path=out)
            paths.append(out)
        b.close()
    return paths


if __name__ == "__main__":
    outs = render(sys.argv[1], sys.argv[2])
    print("\n".join(outs))

#!/usr/bin/env python3
"""
Daily Reel: the same market data as a 9:16 video.

Carousels convert people who already found you. Reels are what Instagram
shows to people who haven't. Same spec, same design language, different job.

Motion is DETERMINISTIC: a JS function positions everything for a given time
t, and we step it frame by frame. Screenshotting a CSS animation in real time
gives you whatever frames the machine happened to manage — fine on a laptop,
jittery on a loaded CI runner. This renders identically everywhere.

    python build_reel.py spec.json out/reel.mp4
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

W, H = 1080, 1920
FPS = 25
DURATION = 16.0                     # completion rate falls off a cliff past ~20s
BRAND = "@bazaar_brief"

# scene key -> (start, end) in seconds
SCENES = [
    ("hook",    0.0,  3.4),
    ("hero",    3.4,  7.0),
    ("sectors", 7.0, 10.8),
    ("movers", 10.8, 13.8),
    ("call",   13.8, 16.0),
]

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;background:#0a0a0b;overflow:hidden}
body{font-family:"Inter","Inter Display",system-ui,sans-serif;color:#fff}
.stage{position:absolute;inset:0}
.scene{position:absolute;inset:0;padding:270px 84px 430px;
  display:flex;flex-direction:column;justify-content:center;opacity:0}
.glow{position:absolute;inset:0;
  background:radial-gradient(120% 55% at 50% 0%,rgba(57,135,229,.18),transparent 62%)}
.kicker{position:absolute;top:150px;left:84px;right:84px;font-size:28px;font-weight:700;
  letter-spacing:.16em;text-transform:uppercase;color:#7f7e78;
  display:flex;align-items:center;gap:16px}
.kicker .hn{margin-left:auto;color:#a9a8a2;letter-spacing:.12em}
.kicker i{width:12px;height:12px;border-radius:50%;background:#3987e5;display:block}
.foot{position:absolute;bottom:96px;left:84px;right:84px;display:flex;
  justify-content:space-between;font-size:28px;font-weight:700;
  letter-spacing:.1em;color:#6e6d68}
.num{font-variant-numeric:tabular-nums}
.up{color:#12b912}.down{color:#e04a4a}

h1{font-size:118px;line-height:1.02;font-weight:800;letter-spacing:-.04em}
.deck{font-size:40px;line-height:1.4;color:#a9a8a2;margin-top:48px;font-weight:450}

.hero-label{font-size:34px;color:#86857f;font-weight:650;letter-spacing:.07em;
  text-transform:uppercase}
.hero{font-size:196px;font-weight:800;letter-spacing:-.055em;line-height:.9;margin-top:24px}
.hero-sub{font-size:44px;color:#a9a8a2;margin-top:36px;font-weight:500}

h2{font-size:70px;font-weight:800;letter-spacing:-.03em;line-height:1.06}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:56px}
.cell{border-radius:22px;padding:34px 28px;min-height:190px;border:1px solid rgba(255,255,255,.08);
  display:flex;flex-direction:column;justify-content:space-between}
.cell b{font-size:30px;font-weight:650;color:#f2f1ec}
.cell span{font-size:52px;font-weight:800;letter-spacing:-.02em}

.row{display:flex;align-items:center;gap:24px;margin-bottom:26px}
.row .nm{width:300px;font-size:34px;font-weight:650;color:#e6e5e0}
.row .track{flex:1;height:46px;display:flex;align-items:center}
.row .fill{height:46px;border-radius:5px}
.row .val{width:160px;text-align:right;font-size:34px;font-weight:750}
.lbl{font-size:32px;font-weight:750;letter-spacing:.1em;text-transform:uppercase;margin-bottom:18px}

.eyebrow{font-size:32px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;
  color:#7f7e78;text-align:center;margin-bottom:30px}
.q{font-size:94px;font-weight:800;letter-spacing:-.035em;line-height:1.05;text-align:center;
  text-wrap:balance}
.chips{display:flex;gap:24px;margin-top:70px}
.chip{flex:1;text-align:center;border-radius:30px;padding:70px 20px;font-size:70px;font-weight:800;
  letter-spacing:.01em}
.chip.a{background:rgba(18,185,18,.16);border:4px solid rgba(18,185,18,.62);color:#16d016}
.chip.b{background:rgba(224,74,74,.16);border:4px solid rgba(224,74,74,.62);color:#ef6a6a}
.ask{font-size:46px;font-weight:750;margin-top:62px;text-align:center;color:#fff}
.follow{margin-top:34px;text-align:center;font-size:32px;color:#7f7e78;font-weight:600}
.follow b{color:#5ea0f0;font-weight:800}
"""

JS = """
// Deterministic frame renderer. Everything is a pure function of t.
const SCENES = __SCENES__;
const ease = x => x<0?0 : x>1?1 : 1-Math.pow(1-x,3);

function frame(t){
  for (const [key, a, b] of SCENES){
    const el = document.getElementById(key);
    // 0.35s cross-fade in and out, so scenes overlap rather than cut hard.
    const inA = ease((t-a)/0.35);
    const outA = 1 - ease((t-(b-0.35))/0.35);
    const vis = Math.max(0, Math.min(inA, outA));
    el.style.opacity = vis;
    // A slow drift keeps the frame alive; static video reads as a screenshot.
    const p = (t-a)/(b-a);
    el.style.transform = `translateY(${(1-ease(inA))*40 - p*14}px)`;
    el.style.display = vis <= 0.001 ? 'none' : 'flex';

    if (vis > 0){
      el.querySelectorAll('[data-stagger]').forEach((n,i) => {
        const d = ease((t - a - 0.25 - i*0.07)/0.45);
        n.style.opacity = d;
        n.style.transform = `translateY(${(1-d)*26}px)`;
      });
      el.querySelectorAll('[data-grow]').forEach((n,i) => {
        const d = ease((t - a - 0.3 - i*0.09)/0.55);
        n.style.width = (parseFloat(n.dataset.grow) * d) + '%';
      });
      el.querySelectorAll('[data-count]').forEach(n => {
        const d = ease((t - a - 0.15)/0.9);
        const v = parseFloat(n.dataset.count) * d;
        n.textContent = (v>=0?'+':'\\u2212') + Math.abs(v).toFixed(2) + '%';
      });
    }
  }
}
window.frame = frame;
"""


def ffmpeg_bin():
    """Find ffmpeg, or say exactly how to get one.

    This has now failed on two platforms for two different reasons, so it
    tries three sources in descending order of how much they can be trusted:

    1. PATH — a real system install, if there is one.
    2. Playwright's cache. `playwright install` downloads an ffmpeg as a side
       effect, which is free and already present in CI. It is also the least
       dependable: the directory differs per OS, and so does the FILE NAME
       (ffmpeg-linux, ffmpeg-mac, ffmpeg-win64.exe). Match on a glob rather
       than a list of names — the list is what broke on Windows.
    3. imageio-ffmpeg, a pip package that bundles a static binary. Same name,
       same call, every OS. This is the one that ends the problem.
    """
    exe = shutil.which("ffmpeg")
    if exe:
        return exe

    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "",
             os.path.expanduser("~/.cache/ms-playwright"),                # Linux
             os.path.expanduser("~/Library/Caches/ms-playwright"),        # macOS
             os.path.join(os.environ.get("LOCALAPPDATA") or "", "ms-playwright")]
    searched = []
    for root in filter(None, roots):
        searched.append(root)
        for d in sorted(glob.glob(os.path.join(root, "ffmpeg-*")), reverse=True):
            for cand in sorted(glob.glob(os.path.join(d, "ffmpeg*"))):
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    return cand

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    raise RuntimeError(
        "ffmpeg not found. The fix, on any OS:\n"
        "    pip install imageio-ffmpeg\n"
        "(or install ffmpeg system-wide and put it on PATH).\n"
        "Looked on PATH and under: " + ", ".join(searched or ["(nothing)"]))


def sign(v):
    return f"+{v:.2f}" if v >= 0 else f"−{abs(v):.2f}"


def cls(v):
    return "up" if v >= 0 else "down"


def heat(pct, mx):
    a = 0.12 + 0.44 * min(abs(pct) / mx, 1.0) if mx else 0.12
    return f"rgba({'18,185,18' if pct >= 0 else '224,74,74'},{a:.3f})"


def build_html(d, scenes=SCENES):
    n = d["indices"][0]
    mx = max(abs(s["pct"]) for s in d["sectors"]) or 1

    cells = "".join(
        f'<div class="cell" data-stagger style="background:{heat(s["pct"], mx)}">'
        f'<b>{s["name"]}</b><span class="num {cls(s["pct"])}">{sign(s["pct"])}</span></div>'
        for s in sorted(d["sectors"], key=lambda x: -x["pct"])[:9])

    movers = d["gainers"][:3] + d["losers"][:3]
    bmx = max(abs(r["pct"]) for r in movers) or 1
    rows = ""
    for r in movers:
        up = r["pct"] >= 0
        rows += (f'<div class="row" data-stagger><div class="nm">{r["name"]}</div>'
                 f'<div class="track"><div class="fill" data-grow="{abs(r["pct"])/bmx*100:.1f}" '
                 f'style="width:0%;background:{"#12b912" if up else "#e04a4a"}"></div></div>'
                 f'<div class="val num {cls(r["pct"])}">{sign(r["pct"])}</div></div>')

    c = d["call"]["today"]

    def scene(key, inner):
        return f'<div class="scene" id="{key}">{inner}</div>'

    body = (
        '<div class="glow"></div>'
        + scene("hook", f'<h1 data-stagger>{d["headline"]}</h1>'
                        f'<div class="deck" data-stagger>{d["deck"]}</div>')
        + scene("hero", f'<div data-stagger><div class="hero-label">'
                        f'{d.get("hero_label") or "Nifty 50 · close"}</div>'
                        f'<div class="hero num {cls(n["pct"])}" data-count="{n["pct"]}">'
                        f'{sign(n["pct"])}</div>'
                        f'<div class="hero-sub num">{n["close"]:,.2f}</div></div>')
        + scene("sectors", f'<h2 data-stagger>Which sectors<br>carried the day</h2>'
                           f'<div class="grid">{cells}</div>')
        + scene("movers", f'<h2 data-stagger>The biggest moves</h2>'
                          f'<div style="margin-top:56px">{rows}</div>')
        + scene("call", f'<div class="eyebrow" data-stagger>Your call</div>'
                        f'<div class="q" data-stagger>{c["question"]}</div>'
                        f'<div class="chips"><div class="chip a" data-stagger>{c["a"]}</div>'
                        f'<div class="chip b" data-stagger>{c["b"]}</div></div>'
                        f'<div class="ask" data-stagger>Comment your call &#128071;</div>'
                        f'<div class="follow" data-stagger>New numbers every trading morning · '
                        f'<b>{BRAND}</b></div>')
        + f'<div class="kicker"><i></i>{d["kicker"]}<span class="hn">{BRAND}</span></div>'
    )
    js = JS.replace("__SCENES__", json.dumps([[k, a, b] for k, a, b in scenes]))
    return f"<meta charset='utf-8'><style>{CSS}</style>{body}<script>{js}</script>"


def render(spec_path, out_path, fps=FPS, duration=DURATION, scenes=None):
    from playwright.sync_api import sync_playwright
    d = json.load(open(spec_path, encoding="utf-8"))
    # Narration-driven timings win over the defaults: the picture should wait
    # for the voice, never cut across it.
    if scenes:
        duration = max(b for _, _, b in scenes)
    tmp = tempfile.mkdtemp(prefix="reel-")
    html = os.path.join(tmp, "reel.html")
    open(html, "w", encoding="utf-8").write(build_html(d, scenes or SCENES))

    total = int(fps * duration)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto("file://" + os.path.abspath(html))
        pg.wait_for_timeout(400)
        for i in range(total):
            pg.evaluate(f"frame({i / fps})")
            pg.screenshot(path=os.path.join(tmp, f"f{i:05d}.png"))
        b.close()

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    cmd = [
        ffmpeg_bin(), "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", os.path.join(tmp, "f%05d.png"),
        # yuv420p + even dimensions: without both, the file plays on a desktop
        # and shows a black screen on half of all phones.
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-crf", "20", "-movflags", "+faststart", "-r", str(fps),
        out_path,
    ]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out_path


if __name__ == "__main__":
    out = render(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out/reel.mp4")
    print(f"{out}  ({os.path.getsize(out)/1e6:.2f} MB)")

#!/usr/bin/env python3
"""
Narration: one spoken line per scene, and the timings the video should use.

Two ideas hold this together.

SPOKEN NUMBERS ARE NOT WRITTEN NUMBERS. A slide can say 23,897.70. Read aloud
that is "twenty-three thousand eight hundred and ninety-seven point seven
zero", which no human would say. Speech rounds. Everything here goes through
num2words with Indian numbering (lakh/crore), then gets rounded to what a
person would actually say.

THE VIDEO FOLLOWS THE VOICE, NOT THE OTHER WAY AROUND. We synthesise each
line first, measure it, and hand those durations to the renderer as scene
timings. Fitting speech into fixed scene lengths is how you get narration
clipped mid-word.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import wave
from xml.sax.saxutils import escape

from num2words import num2words

import story
from build_reel import ffmpeg_bin

PAD = 0.35            # breathing room after each line before the scene cuts
MIN_SCENE = 1.5

# Completion is what drives Reels reach, and completion falls off as length
# grows. 22s is the edge of the band a market brief can hold. The budget is
# ENFORCED rather than hoped for: script length is not stable, because the
# names in it are not. "HCL Tech" is a second; "Mahindra and Mahindra" is
# three. A script hand-tuned to fit today drifts over the line on its own.
MAX_TOTAL = 22.0
BASE_RATE = 4         # prosody rate the day's first read is done at
MAX_RATE = 16         # past this the numbers stop landing; better to cut a scene
DROP_ORDER = ("movers",)   # what goes first when even MAX_RATE is not enough --
                           # the movers are on the carousel in full anyway

# Losing a scene costs ~7 seconds of content. Doing that to claw back a tenth
# of a second is a far worse trade than simply shipping a Reel a shade long,
# so a scene is only sacrificed once the overrun is genuinely large.
HARD_LIMIT = 24.0


# --------------------------------------------------------------- numbers

def words(n):
    return num2words(n, lang="en_IN").replace(",", "")


def pct(v, up="up", down="down"):
    """0.84 -> 'up zero point eight four percent'."""
    d = up if v >= 0 else down
    return f"{d} {words(round(abs(v), 2))} percent"


def level(v):
    """23897.70 -> 'twenty-three nine hundred'.

    Rounded to the nearest 50 (the exact figure is on screen anyway) and said
    the way a dealing room says it: thousands, then the rest. "Twenty-three
    THOUSAND nine hundred" is a second longer and nobody talks like that.
    """
    n = int(round(v / 50.0) * 50)
    th, rest = divmod(n, 1000)
    if not th:
        return words(rest)
    return words(th) + " thousand" if not rest else f"{words(th)} {words(rest)}"


def crore(v):
    return f"{words(int(round(abs(v))))} crore"


# --------------------------------------------------------------- script

def lines(d):
    """One line per scene, in scene order. Short sentences: a long clause
    read by any synthesiser starts to drift."""
    n = d["indices"][0]
    b = d.get("breadth") or {}
    top = d["gainers"][0] if d.get("gainers") else None
    bot = d["losers"][0] if d.get("losers") else None
    sect = sorted(d["sectors"], key=lambda s: -s["pct"])
    c = d["call"]["today"]

    out = [("hook", d["headline"].rstrip("."))]

    # Terse on purpose. Every extra clause costs a second, and a second costs
    # completion — the metric Reels reach actually depends on.
    # Every clause costs a second and a second costs completion. "closed",
    # "stocks", "today" and the commas before each number all read as pauses
    # and carry nothing the picture is not already showing.
    hero = f"Nifty {pct(n['pct'])}."
    if b.get("total"):
        hero += f" {words(b['advances'])} of fifty rose."
    out.append(("hero", hero))

    lead, lag = story.prose(sect[0]["name"]), story.prose(sect[-1]["name"])
    out.append(("sectors", f"{lead} led, {lag} lagged."))

    if top and bot:
        out.append(("movers",
                    f"{top['name']} {pct(top['pct'])}. "
                    f"{bot['name']} {pct(bot['pct'])}."))

    lvl = c.get("level")
    spoken = (f"Above or below {level(lvl)}"
              if lvl else "Where does it close today")
    out.append(("call", f"{spoken}? Comment your call."))
    return out


# --------------------------------------------------------------- voices

class Piper:
    """Local neural TTS. Free, offline, no API key — but US/UK English only,
    which is why this is the fallback rather than the choice."""

    name = "piper"

    def __init__(self, model, rate=None):
        self.model = model
        self.rate = BASE_RATE if rate is None else rate

    def say(self, text, out_wav):
        # piper speaks in length-scale, where SHORTER is faster -- the
        # reciprocal of a percentage speed-up.
        scale = 0.96 / (1 + self.rate / 100.0)
        subprocess.run([sys.executable, "-m", "piper", "--model", self.model,
                        "--length-scale", f"{scale:.3f}", "--output_file", out_wav],
                       input=text.encode(), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_wav


class AzureIndian:
    """Azure Speech, en-IN neural. The only route to an Indian voice that
    doesn't need a paid tier: the free allowance is 500k characters a month
    and a day's narration is about 400. Needs AZURE_SPEECH_KEY and
    AZURE_SPEECH_REGION."""

    name = "azure-en-IN"

    def __init__(self, voice=None, rate=None):
        # Aarav — chosen by ear over Neerja/Prabhat/Ananya on a real script.
        # Overridable without a code change via AZURE_VOICE.
        # os.environ.get(k, default) returns "" when the variable is SET BUT
        # EMPTY -- which is exactly what a GitHub repo variable that was never
        # created evaluates to. `or` is the only form that falls back in both
        # the unset and the set-but-empty case.
        self.voice = voice or os.environ.get("AZURE_VOICE") or "en-IN-AaravNeural"
        self.key = (os.environ.get("AZURE_SPEECH_KEY") or "").strip()
        self.region = (os.environ.get("AZURE_SPEECH_REGION") or "").strip() or "centralindia"
        self.rate = BASE_RATE if rate is None else rate
        if not self.key:
            raise RuntimeError("AZURE_SPEECH_KEY is not set")

    def say(self, text, out_wav):
        import urllib.error
        import urllib.request
        # The xmlns is NOT optional. Azure parses this as a namespaced SSML
        # document and rejects it with a bodiless HTTP 400 without it -- which
        # reads exactly like a bad key or an unavailable voice, and isn't.
        # escape() matters too: the day M&M tops the movers list, unescaped
        # text makes this malformed and you get the same opaque 400.
        ssml = ("<speak version='1.0' "
                "xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-IN'>"
                f"<voice name='{self.voice}'>"
                f"<prosody rate='{self.rate:+d}%'>{escape(text)}</prosody>"
                "</voice></speak>")
        req = urllib.request.Request(
            f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
            data=ssml.encode("utf-8"),
            headers={"Ocp-Apim-Subscription-Key": self.key,
                     "Content-Type": "application/ssml+xml",
                     "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
                     "User-Agent": "bazaar-brief"},
            method="POST")
        # Azure explains a 400 in the response body. urllib throws that body
        # away unless you read it off the exception, which is how a rejected
        # voice name or a wrong region ends up looking like a generic failure.
        try:
            with urllib.request.urlopen(req, timeout=45) as r, open(out_wav, "wb") as f:
                f.write(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(
                f"Azure TTS {e.code} for voice '{self.voice}' in "
                f"region '{self.region}': {body or e.reason}") from None
        return out_wav


def pick_voice():
    """Indian voice when it's configured; the local one when it isn't."""
    if (os.environ.get("AZURE_SPEECH_KEY") or "").strip():
        return AzureIndian()
    model = os.environ.get("PIPER_MODEL")
    if model and os.path.exists(model):
        return Piper(model)
    return None


# --------------------------------------------------------------- timing

def wav_seconds(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def _synth(voice, script, outdir):
    """One pass over the script at the voice's current rate.

    Clips are (key, text, wav, scene_duration, speech_seconds). The last two
    differ: the scene has to hold the padding as well, and the padding does
    not get shorter when the voice speeds up.
    """
    clips = []
    for key, text in script:
        wav = os.path.join(outdir, f"vo_{key}.wav")
        voice.say(text, wav)
        raw = wav_seconds(wav)
        clips.append((key, text, wav, max(raw + PAD, MIN_SCENE), raw))
    return clips


def _total(clips):
    return sum(c[3] for c in clips)


def fit(voice, script, outdir, budget=MAX_TOTAL):
    """Read the script, and if it runs long, make it fit.

    Two levers, in order of how much they cost the viewer. Speaking a little
    faster costs almost nothing up to a point. Losing a scene costs real
    content, so it happens only when the first lever is exhausted -- and the
    scene that goes is the one whose information the carousel repeats in full.
    """
    clips = _synth(voice, script, outdir)
    if _total(clips) <= budget:
        return clips

    # Padding is fixed cost; only the speech itself responds to the rate.
    speech = sum(c[4] for c in clips)
    room = budget - (_total(clips) - speech)
    if room > 0:
        factor = speech / room
        # Ceil, not round: rounding down lands a hair OVER budget, which used
        # to be enough to trigger a scene drop.
        rate = min(MAX_RATE, math.ceil(((1 + voice.rate / 100.0) * factor - 1) * 100))
        if rate > voice.rate:
            print(f"  {_total(clips):.1f}s over the {budget:.0f}s budget — "
                  f"re-reading at {rate:+d}% instead of {voice.rate:+d}%")
            voice.rate = rate
            clips = _synth(voice, script, outdir)

    for key in DROP_ORDER:
        if _total(clips) <= HARD_LIMIT or len(clips) <= 2:
            break
        if any(c[0] == key for c in clips):
            print(f"  {_total(clips):.1f}s is past the {HARD_LIMIT:.0f}s hard limit even at "
                  f"{voice.rate:+d}% — dropping the "
                  f"'{key}' scene; it is on the carousel in full")
            clips = [c for c in clips if c[0] != key]
    return clips


def narrate(d, outdir, voice=None):
    """Synthesise the day's narration, inside the length budget.

    Returns None when no voice is configured — the Reel then renders silent
    on its default timings, which is a supported outcome, not a failure.
    """
    voice = voice or pick_voice()
    if voice is None:
        return None
    os.makedirs(outdir, exist_ok=True)
    clips = fit(voice, lines(d), outdir)
    for c in clips:
        print(f"  {c[0]:8} {c[3]:5.2f}s  {c[1][:64]}")
    total = _total(clips)
    print(f"  narration total {total:.1f}s at {voice.rate:+d}%")
    if total > HARD_LIMIT:
        # Only reachable if every lever ran out. A Reel a shade over the 22s
        # target is fine and says nothing; past the hard limit, every lever
        # has failed and the script itself is the problem.
        print(f"  ! {total:.1f}s is past the {HARD_LIMIT:.0f}s hard limit even after "
              f"speeding up and cutting a scene — the script needs shortening",
              file=sys.stderr)
    return clips


def scene_timings(clips):
    """Turn measured clip lengths into (key, start, end) windows.

    A scene missing from this list is never touched by the frame function, so
    it stays at its CSS opacity of 0 — dropping a clip drops its scene.
    """
    t, out = 0.0, []
    for c in clips:
        out.append((c[0], round(t, 3), round(t + c[3], 3)))
        t += c[3]
    return out


def mix_track(clips, timings, out_wav, total):
    """Lay each clip at its scene start on one silent bed of `total` seconds."""
    inputs, filters = [], []
    for i, (c, t) in enumerate(zip(clips, timings)):
        wav, start = c[2], t[1]
        inputs += ["-i", wav]
        filters.append(f"[{i}:a]adelay={int(start*1000)}|{int(start*1000)}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(clips)))
    filters.append(f"{mix}amix=inputs={len(clips)}:normalize=0,"
                   f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur={total}[out]")
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", *inputs,
                    "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-t", str(total), out_wav], check=True)
    return out_wav


def mux(video, audio, out_path):
    subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", video, "-i", audio,
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", out_path], check=True)
    return out_path


if __name__ == "__main__":
    import json
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    for k, t in lines(d):
        print(f"[{k}] {t}")

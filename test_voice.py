#!/usr/bin/env python3
"""
Try the Azure voices on a real line from the pipeline, before wiring anything
into CI.

    python test_voice.py

Reads AZURE_SPEECH_KEY / AZURE_SPEECH_REGION from .env, synthesises the same
sentence in several Indian-English voices, and writes one wav per voice so you
can play them back to back and pick. Nothing is published; nothing is changed.
"""
from __future__ import annotations

import os
import sys

import narrate

# A line with the two things that trip synthesisers up: a decimal read as
# words, and a large index level. If a voice handles this, it handles the job.
LINE = ("Nifty closed up zero point eight four percent. "
        "Only twenty of fifty stocks rose. Banks led, metals lagged. "
        "Above or below twenty-six thousand four hundred today? Comment your call.")

VOICES = [
    ("en-IN-NeerjaNeural",  "female, the long-standing default"),
    ("en-IN-PrabhatNeural", "male, the long-standing default"),
    ("en-IN-AnanyaNeural",  "female, newer and more conversational"),
    ("en-IN-AaravNeural",   "male, newer and more conversational"),
]


def load_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    if not os.environ.get("AZURE_SPEECH_KEY"):
        sys.exit("AZURE_SPEECH_KEY is not set. Put it in .env first.")
    region = os.environ.get("AZURE_SPEECH_REGION", "centralindia")
    print(f"region: {region}\n")

    outdir = "voice_samples"
    os.makedirs(outdir, exist_ok=True)
    ok = 0
    for name, note in VOICES:
        out = os.path.join(outdir, f"{name}.wav")
        try:
            narrate.AzureIndian(voice=name).say(LINE, out)
            kb = os.path.getsize(out) / 1024
            print(f"  OK    {name:24} {kb:7.0f} KB   ({note})")
            ok += 1
        except Exception as e:
            # Newer voices are not in every region; a failure here is a
            # "not available", not a broken key.
            msg = str(e)
            detail = getattr(getattr(e, "read", None), "__call__", None)
            print(f"  skip  {name:24} {type(e).__name__}: {msg[:70]}")

    if not ok:
        print("\nNo voice worked. If every line says HTTP 401, the key is wrong; "
              "if 403, the region does not match the resource.", file=sys.stderr)
        sys.exit(1)
    print(f"\n{ok} sample(s) in ./{outdir}/ — play them and pick one.")


if __name__ == "__main__":
    main()

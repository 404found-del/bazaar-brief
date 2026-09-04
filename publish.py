#!/usr/bin/env python3
"""
Instagram publisher for Bazaar Brief.

Publishes a 6-slide carousel via the Instagram API (Instagram Login flavour,
which lives on graph.instagram.com — NOT graph.facebook.com; using the wrong
host is the classic cause of "unsupported get request").

Publishing a carousel is three round trips, not one:
  1. one item container per image        POST /{ig_id}/media
  2. one carousel container over those   POST /{ig_id}/media  (media_type=CAROUSEL)
  3. publish the carousel container      POST /{ig_id}/media_publish

Images must already be at PUBLIC https URLs when step 1 runs — Meta fetches
them server-side. Local files and signed/expiring URLs will not work.

Usage:
    python publish.py --check                      # smoke-test credentials
    python publish.py --refresh                    # extend the token
    python publish.py --urls urls.json --caption caption.txt
    python publish.py ... --dry-run                # build but never publish
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = "v23.0"
BASE = os.environ.get("IG_API_BASE", f"https://graph.instagram.com/{API_VERSION}")
# Token refresh sits on the unversioned host.
REFRESH_BASE = "https://graph.instagram.com"

TIMEOUT = 60
MAX_CAPTION = 2200          # Instagram's hard limit
CAROUSEL_MIN, CAROUSEL_MAX = 2, 10


class PublishError(RuntimeError):
    """Carries Meta's own error payload, which is far more useful than a status code."""

    def __init__(self, message, payload=None):
        super().__init__(message)
        self.payload = payload or {}


# ----------------------------------------------------------------- transport

def _request(method, path, params=None, base=None):
    url = f"{base or BASE}{path}"
    data = urllib.parse.urlencode(params or {}).encode()
    if method == "GET":
        url = f"{url}?{data.decode()}" if data else url
        req = urllib.request.Request(url, method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"raw": raw}
        err = payload.get("error", {})
        raise PublishError(
            f"{method} {path} failed [{e.code}]: "
            f"{err.get('message') or payload.get('raw') or 'unknown error'}"
            + (f" (code {err['code']}" + (f"/{err['error_subcode']}" if err.get("error_subcode") else "") + ")"
               if err.get("code") else ""),
            payload,
        ) from None
    except urllib.error.URLError as e:
        raise PublishError(f"{method} {path} could not reach {base or BASE}: {e.reason}") from None


def get(path, **params):
    return _request("GET", path, params)


def post(path, **params):
    return _request("POST", path, params)


# ------------------------------------------------------------------ the flow

def whoami(token):
    """Ask the token who it is.

    Instagram has two ID namespaces and they are NOT interchangeable:
    the `17841...` Instagram Business Account ID belongs to the
    Facebook-login flavour on graph.facebook.com, while an Instagram-login
    token addresses the account by its own Instagram-scoped ID. Publishing
    to the wrong one fails obscurely, so we never trust a configured value —
    we resolve it from /me and use whatever the token itself reports.
    """
    return get("/me", fields="id,username,account_type", access_token=token)


def resolve_user_id(token, configured=None):
    me = whoami(token)
    real = str(me["id"])
    if configured and str(configured) != real:
        print(f"  note: .env has IG_BUSINESS_ACCOUNT_ID={configured}, but this "
              f"token addresses the account as {real}. Using {real}.")
    return real, me


def create_item(ig_id, token, image_url):
    """One un-published carousel child."""
    r = post(f"/{ig_id}/media",
             image_url=image_url, is_carousel_item="true", access_token=token)
    return r["id"]


def create_carousel(ig_id, token, children, caption):
    r = post(f"/{ig_id}/media",
             media_type="CAROUSEL", children=",".join(children),
             caption=caption, access_token=token)
    return r["id"]


def wait_ready(container_id, token, tries=20, delay=3):
    """A container is not publishable the instant it is created.

    Meta fetches and transcodes the media server-side; publishing an
    IN_PROGRESS container fails with an error that looks like a permissions
    problem and isn't. Poll until FINISHED.
    """
    for _ in range(tries):
        r = get(f"/{container_id}", fields="status_code,status", access_token=token)
        code = r.get("status_code")
        if code == "FINISHED":
            return True
        if code == "ERROR":
            raise PublishError(f"container {container_id} failed server-side: "
                               f"{r.get('status', 'no detail given')}", r)
        time.sleep(delay)
    raise PublishError(f"container {container_id} still not ready after "
                       f"{tries * delay}s — try again rather than republishing")


def publish_container(ig_id, token, creation_id):
    return post(f"/{ig_id}/media_publish",
                creation_id=creation_id, access_token=token)["id"]


def publish_carousel(ig_id, token, image_urls, caption, dry_run=False):
    if not CAROUSEL_MIN <= len(image_urls) <= CAROUSEL_MAX:
        raise PublishError(f"a carousel needs {CAROUSEL_MIN}-{CAROUSEL_MAX} images, "
                           f"got {len(image_urls)}")
    if len(caption) > MAX_CAPTION:
        raise PublishError(f"caption is {len(caption)} chars, limit is {MAX_CAPTION}")

    print(f"→ building {len(image_urls)} item containers")
    children = []
    for i, u in enumerate(image_urls, 1):
        cid = create_item(ig_id, token, u)
        children.append(cid)
        print(f"   {i}/{len(image_urls)}  {cid}")

    for cid in children:
        wait_ready(cid, token)

    carousel_id = create_carousel(ig_id, token, children, caption)
    print(f"→ carousel container {carousel_id}")
    wait_ready(carousel_id, token)

    if dry_run:
        print("→ dry run: container built and ready, NOT published")
        return None

    media_id = publish_container(ig_id, token, carousel_id)
    print(f"✓ published, media id {media_id}")
    return media_id


# ------------------------------------------------------------------- tokens

def refresh_token(token):
    """Long-lived IG tokens last 60 days and can be refreshed indefinitely,
    as long as the token is at least 24h old and not yet expired. No app
    secret needed for this flavour."""
    r = _request("GET", "/refresh_access_token",
                 {"grant_type": "ig_refresh_token", "access_token": token},
                 base=REFRESH_BASE)
    days = int(r.get("expires_in", 0)) // 86400
    print(f"✓ token refreshed, valid ~{days} days")
    return r["access_token"], days


# --------------------------------------------------------------------- cli

def load_env():
    """Read .env if present; real environment always wins (that's how CI works)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    tok = os.environ.get("META_LONG_LIVED_TOKEN", "").strip()
    ig = os.environ.get("IG_BUSINESS_ACCOUNT_ID", "").strip()  # cross-check only
    if not tok:
        sys.exit("Missing META_LONG_LIVED_TOKEN "
                 "(set it in .env locally, or as a GitHub repository Secret).")
    return ig, tok


def main():
    ap = argparse.ArgumentParser(description="Publish a Bazaar Brief carousel.")
    ap.add_argument("--check", action="store_true", help="verify credentials and exit")
    ap.add_argument("--refresh", action="store_true", help="refresh the long-lived token")
    ap.add_argument("--urls", help="JSON file: a list of public image URLs, in slide order")
    ap.add_argument("--caption", help="text file holding the caption")
    ap.add_argument("--dry-run", action="store_true",
                    help="build containers but stop short of publishing")
    a = ap.parse_args()

    configured, token = load_env()

    try:
        if a.check:
            ig_id, me = resolve_user_id(token, configured)
            print(f"✓ connected as @{me.get('username')} "
                  f"({me.get('account_type')}, publishing id {ig_id})")
            return
        if a.refresh:
            new, _ = refresh_token(token)
            print("Store this as META_LONG_LIVED_TOKEN "
                  "(it replaces the old one; the old one keeps working until it expires).")
            print(new)
            return
        if not a.urls or not a.caption:
            ap.error("--urls and --caption are required to publish")

        ig_id, _ = resolve_user_id(token, configured)
        urls = json.load(open(a.urls, encoding="utf-8"))
        caption = open(a.caption, encoding="utf-8").read().strip()
        publish_carousel(ig_id, token, urls, caption, dry_run=a.dry_run)

    except PublishError as e:
        print(f"✗ {e}", file=sys.stderr)
        if e.payload:
            print(json.dumps(e.payload, indent=2)[:1200], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

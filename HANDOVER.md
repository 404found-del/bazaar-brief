# Bazaar Brief — handover

Written so a new session (or a future you) can be useful in five minutes without
re-deriving decisions or re-discovering bugs that already cost a day.

**Keep this current.** Update it in the *same commit* as any change that alters
the state, a decision, or a gotcha below. There is no automation enforcing it —
a CI check would either cry wolf on every push or be a warning nobody sees, and
the doc is short enough that keeping it honest is cheaper than policing it.

Last updated: 2026-09-06, after the first live post.

---

## 1. What this is

A faceless Instagram account, **@bazaar_brief**, posting Indian market summaries
with as little manual work as possible. Every post is generated and published by
GitHub Actions — no human in the loop on a normal day.

Two formats, two jobs. **Reels** reach people who don't follow you; **carousels**
convert the ones they bring. Same data, same day, different purpose.

The differentiator is the **call-and-score loop**: each post asks a binary
question (Nifty above or below X?), and the next post scores it. That loop is
the reason people come back, and **it is not built yet** — see §7.

---

## 2. Current state

| | |
|---|---|
| Repo | `github.com/404found-del/bazaar-brief` (public) |
| Account | `@bazaar_brief` (Business) |
| Slides hosted at | `dataarchitect.studio/bazaar-brief` (GitHub Pages, custom domain) |
| Voice | Azure Speech, `en-IN-AaravNeural`, region `centralindia` (free tier) |
| Token expires | **2026-11-03** (recorded in `token_status.json`) |
| Monthly cost | ~₹0. Actions, Pages and Azure Speech all sit inside free tiers. |

**Posted so far:** one Reel, 2026-09-06, media id `17973385898932983` — the
weekly wrap for 31 Aug–04 Sep. Its caption wrongly ends with "Swipe for…"
(fixed in code afterwards; the live post may still say it).

**The carousel for that week never posted** — a Pages deploy failure skipped it.
Slides for `week-2026-09-04` may still be live on the domain because the cleanup
job only runs when the post job succeeds.

**Not yet run unattended:** the Monday 08:00 IST daily brief. That will be the
first fully hands-off post.

### Workflows

| File | Name | Schedule (UTC → IST) |
|---|---|---|
| `daily.yml` | Daily brief | `30 2 * * 1-5` → 08:00 IST, Mon–Fri |
| `weekly.yml` | Weekly wrap | `30 3 * * 6` → 09:00 IST, Sat |
| `token-guard.yml` | Token guard | `0 3 * * 1` → 08:30 IST, Mon |
| `data-check.yml` | Data check | manual only |

Manual runs default to `dry_run: yes`, which builds and transcodes both
containers but publishes nothing. Scheduled runs always publish.

---

## 3. How one post is made

```
market_data.fetch_day()/fetch_week()   live prices + freshness guard
        ↓
story.apply()/story_week.apply()       pick the angle, write headline + deck
        ↓
narrate.narrate()                      synthesise the voice FIRST, measure it
        ↓
build_carousel / build_reel            render slides, then video on those timings
        ↓
Pages deploy                           slides get a public https URL
        ↓
publish.py                             Meta fetches the URLs and posts
        ↓
cleanup job                            wipes the slides off the domain
```

**The voice comes before the video.** Scene timings are measured from how long
each line actually takes to say. Fitting speech into fixed scene lengths is how
you get narration clipped mid-word.

---

## 4. The files

| File | Does |
|---|---|
| `market_data.py` | Yahoo prices, 51 Nifty constituents, sector averages, breadth, weekly aggregation, **the freshness guard** |
| `story.py` | Daily angle engine — 8 detectors scored by newsworthiness, highest wins. Caption + disclaimer |
| `story_week.py` | Weekly angles. Leads on streaks, the thing a daily post cannot show |
| `build_carousel.py` | 6 slides, 1080×1350, Playwright screenshots |
| `build_carousel_week.py` | Weekly slide set: reuses 1/3/4/6, replaces 2 (the week's path) and 5 (streaks) |
| `build_reel.py` | 1080×1920 video, deterministic frame-by-frame rendering. Also `ffmpeg_bin()` |
| `narrate.py` | Azure TTS, spoken-number formatting, and the length budget |
| `run_daily.py` / `run_weekly.py` | Orchestration. `build_video()` is shared, deliberately |
| `publish.py` | Meta publishing, token guard, expiry bookkeeping |

`Claude outputs/` is **cruft** — stale copies of old workflow files
(`daily-1.yml`, `dry-run.yml`) and old test videos. Not live, safe to delete,
easy to mistake for real workflows.

---

## 5. Decisions that look wrong until you know why

**Kite Connect was rejected.** Its access token expires at 6 AM daily by
regulatory requirement and renewing needs interactive 2FA. Unusable for
unattended automation, whatever it costs. Yahoo via `yfinance` needs no auth.

**Sector moves are equal-weighted averages of Nifty 50 constituents**, not
official sector index levels. Cheaper and directionally right. The disclaimer
says so on every post — do not quietly drop that.

**The freshness guard raises, it does not warn.** Yahoo's daily bar lags the NSE
close by hours, so "roughly recent" data will happily carry the previous
session. A wrong-session post cannot be walked back once it is on the grid.

**The week window is chosen by DATE, never by counting back five bars.** A week
with a Wednesday holiday has four sessions; counting reaches into the previous
week. Tested: counting would have reported +16.67% for a week that was +5.00%.

**The weekly path is separate, not a generalisation of the daily one.** The
daily code publishes unattended; a refactor underneath it buys nothing. The one
shared piece is `build_video()`, because narration timing is fiddly and two
copies is how a fix lands in one and not the other.

**The token guard never writes.** Auto-refreshing weekly in CI would rotate the
live publishing credential, unattended, to prevent an outage — and
`/refresh_access_token` returns a *new* token string. Renewal stays manual,
about six times a year, prompted by a failing job. The alarm is the exit code:
GitHub emails on failure and says nothing about a warning.

**`ffmpeg_bin()` probes for libx264 rather than trusting a filename.** Playwright
ships an ffmpeg built only for recording webm — it exists, runs, and cannot
encode H.264.

**Slides are deleted from the domain after posting.** Instagram copies each
image when it builds the container and serves its own copy forever after, so
there is no reason for them to keep sitting on your domain.

**The Reel posts even if the carousel fails** (`always()` on that step), but not
the reverse. Losing the discovery post because the conversion post broke is the
wrong trade. Note the cost: a Pages failure silently drops the carousel.

---

## 6. Scars — bugs that already cost real time

**Instagram has two ID namespaces.** `17841…` belongs to the Facebook-login
flavour on `graph.facebook.com`; an Instagram-login token addresses the account
by its own scoped ID on `graph.instagram.com`. Never trust a configured ID —
`resolve_user_id()` asks `/me`.

**Windows defaults to cp1252.** Two faults, one loud and one not: writing the
carousel HTML raises on the true minus sign `−`, and `json.load(open(spec))`
does *not* raise — it silently turns en dashes into `â€"` and renders that onto
the slide. Every file open needs `encoding="utf-8"`.

**Azure SSML needs `xmlns='http://www.w3.org/2001/10/synthesis'`.** Without it,
a bodiless HTTP 400 that looks exactly like a bad key. Also XML-escape the text,
or the day M&M tops the movers list you get the same opaque 400.

**`os.environ.get(k, default)` returns `""` for a set-but-empty variable**, which
is what an uncreated GitHub repo variable evaluates to. Use `or`.

**"API access blocked" (OAuthException code 200) is app-level, not token-level.**
An invalid token says "Error validating access token". Check the App Dashboard
banner and app mode before touching the credential. Happened once; resolved in
the dashboard.

**Re-running a failed Actions run keeps the first attempt's artifacts**, so a
second upload under the same name leaves `deploy-pages` with two candidates and
it refuses. Artifacts are now named by `run_attempt`.

**A fix on disk is not a fix.** Twice, patched files were never committed and the
same traceback came back, reading as "the fix didn't work". Check
`git show HEAD:file` before concluding a fix failed.

---

## 7. Open items

**The scoreboard — this is the priority, and it is a public promise.** Live
captions say *"I score it next Saturday"* and the daily says *"I score every
call tomorrow morning."* Nothing scores anything: `call["yesterday"]` is
hardcoded `None` in `build_call()`. Deadlines are real — the daily's promise
comes due the morning after the first daily post; the weekly's next Saturday.
The cheap half needs only data already fetched (yesterday's question vs today's
actual close). The rich half — naming who called it right — needs comment
reading, and `instagram_business_manage_comments` **is already granted**.

**Token expires 2026-11-03.** `publish.py --refresh`, paste into the
`META_LONG_LIVED_TOKEN` secret, commit the updated `token_status.json`. The
guard will fail the Monday job from 14 days out.

**Bio** still needs updating to the morning-brief wording.

**The `week-2026-09-04` carousel** was never posted (§2).

**ManyChat DM funnel** — deferred until there is traffic worth funnelling.

---

## 8. Running it

```bash
# locally, invented data, fast
python run_weekly.py --sample --base-url https://dataarchitect.studio/bazaar-brief --pages-dir out_local

# locally, real market data
python run_weekly.py --base-url https://dataarchitect.studio/bazaar-brief --pages-dir out_local

# credentials
python publish.py --check          # who does this token think it is
python publish.py --guard          # alive? near expiry?
python publish.py --refresh        # new 60-day token (prints it; store it)
```

Local runs read `.env` (gitignored); CI passes real environment variables, which
always win. Needs `pip install -r requirements.txt` and
`python -m playwright install chromium`.

To publish: Actions → the workflow → Run workflow → `dry_run: no`. Meta fetches
media from a public URL, so publishing has to go through Pages — a local render
cannot publish even in principle.

---

## 9. Rules

- **Secrets never go in chat.** `.env` locally, GitHub Secrets in CI. An app
  secret was once exposed in a screenshot and had to be reset.
- **No auto-refreshing the publishing token** (§5).
- **No bought followers, engagement pods or follow/unfollow tools.** Permanent
  algorithmic damage, and bans specifically for finance accounts.
- **Push is a human action.** Claude commits; you push.

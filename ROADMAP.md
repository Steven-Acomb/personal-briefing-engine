# ROADMAP / Known Issues

Running list of deferred decisions and unresolved problems. Not a task tracker —
just the things we've hit and consciously parked.

---

## ISSUE-1: Audio voice quality (OPEN)

**Status:** parked at "good enough to keep moving." Default is OpenAI `echo`
(plain, no delivery instructions). Not loved — see below.

**What the owner wants:** something close to the ChatGPT app's **"Ember"** voice
(warm, natural, expressive). That quality bar is the target.

**What we learned (the hard way):**

- **Ember is unreachable via any API.** It's an OpenAI *Advanced Voice* (Realtime
  speech-to-speech) voice, exposed only in the ChatGPT app — not in the TTS API,
  and not selectable even in the Realtime API. So the exact voice is off the table.
- **OpenAI TTS API (`gpt-4o-mini-tts`)** — 11 fixed voices. Owner auditioned the
  male-leaning ones (alloy, ash, ballad, echo, fable, verse, onyx). Verdict: all
  "meh." `echo` (plain) was the least-bad → current default. The steerable
  `instructions` param changes delivery but didn't rescue it ("both meh").
- **ElevenLabs — RULED OUT.** Voices are much better, but the API is
  **subscription-only** (no pay-as-you-go), and the community "Voice Library"
  voices (the ones the owner actually wanted) are **blocked on the free tier** —
  they need a paid plan. Owner declined subscriptions **full stop**. The
  ElevenLabs backend code was removed; `core/tts.py` is now OpenAI-only.

**Usage-based (no-subscription, pay-per-character) alternatives — the real path
to Ember-adjacent quality when we revisit:**

| Provider | Quality | Price | Free allowance | Setup |
|---|---|---|---|---|
| **Google Cloud — Chirp 3 HD** | very natural | $30/M chars | **1M chars/mo free, ongoing** (a daily brief ≈ 75k/mo → effectively free forever) | GCP service-account creds (fiddly) |
| **Deepgram Aura-2** | natural, conversational | $15/M chars | **$200 signup credit** (~13M chars) | plain API key (easy) |
| **Cartesia Sonic** | most expressive | ~$35/M chars | trial credits | API key |
| **Amazon Polly (Generative)** | good | $30/M chars | 1M/mo, first 12 mo only | AWS setup |

**Next actions when we revisit:**
1. Trial **Deepgram Aura-2** (easiest, free $200 credit) and/or **Google Chirp 3
   HD** (permanently free at our volume) as an alternate backend inside
   `core/tts.py`.
2. Pick the best-sounding one, make it the default, keep `echo`-plain as the
   zero-setup fallback.

**Design note:** adding a provider is a new function + a small dispatch in
`synthesize_audio` (currently OpenAI-only — the multi-backend seam was removed
with ElevenLabs to avoid a framework with one backend; reintroduce it when the
second provider lands). This is a "which provider" decision, not a rearchitecture.

---

## Web UI (`web/`, localhost authoring + ops)

A localhost-only Flask app (`python -m web`, binds 127.0.0.1). Viewer + trigger
over the durable config/artifacts — deliberately NOT the scheduler (cron still
runs `scheduler.py once`; the server holds no run state).

- **M1 — authoring: DONE.** CRUD for sources + briefings via forms that write
  through `core/config_edit.py` (tomlkit round-trip, atomic validate-then-replace,
  comment-preserving). Delete of a referenced source is blocked.
- **M2 — operational: TODO.** Render `FAILED-<briefing>.txt` markers + a
  `logs/briefing.log` tail, and a per-briefing **Run Now** button (shell out to
  `scheduler.py once`, fire-and-forget + poll, in-flight guard).
- **Deferred (low priority):** a Discord **channel picker** (list channels the
  account can see → kills the F12/token-copy dance); a **"test source"** dry-fetch
  preview button (reuses the adapter path); **run-history** (extend the existing
  `store.brief` table to also record failed/attempted runs — NOT a new store, and
  it does not bundle with item-persistence). Consumption/audio is out of scope by
  decision (briefs are consumed as files synced to the phone).

## Remaining build-sequence work (planned, not blockers)

- **Telegram adapter** — DONE (`adapters/telegram.py`, Telethon userbot; wired
  into `gather_items`; validated end-to-end against real chats 2026-07-12).
- **Feed / research / news adapters** — now the priority (feeds are where the
  volume-and-signal is). See the **Adapter roadmap** below.
- **Email / web-page delivery** — currently the one `NotImplementedError` stub in
  `core/delivery.py`; local file drop is the only working target.

---

## Adapter roadmap (prioritized)

Chat sources (Discord, Telegram) are in. The volume-and-signal now lives in
**feeds** — the top of this list reflects that: these feeds plus the chats already
wired will fill a briefing far better than chasing more chat platforms. Ordered by
signal ÷ risk ÷ effort.

**Cross-cutting notes:**

- **`keyword_filter` earns its keep on feed-like sources.** Independent-item
  sources (everything feed-like below — each entry stands alone) should get
  aggressive per-briefing `keyword_filter` pre-synthesis. Threaded/chat sources
  should NOT (we cleared the filters off the Discord/Telegram sources — they strip
  conversation). `SourceConfig.keyword_filter` exists precisely for this split.
- **The model-choice knob goes live around here.** Synthesis is Opus-on-everything
  today (`core/synthesize.py`, hardcoded `claude-opus-4-8`). As feed count grows,
  daily cost bites — add a per-briefing (or global) model override so high-volume
  briefings can run on `claude-sonnet-5`. (Foreshadowed in HUMAN_TODO's cost note.)

### Tier 1 — build now (high signal, low risk, fixes the volume problem)

1. **Generic RSS adapter** — DONE (`adapters/rss.py`, `feedparser` + requests;
   wired into `gather_items`; validated against real feeds 2026-07-12). One
   adapter unlocks blogs, Substacks (`/feed`), trade press (Semiconductor
   Engineering, EE Times, IEEE Spectrum), podcasts, per-channel YouTube, Mastodon,
   Lobsters. v0 notes: entries need a parseable pubdate (dateless entries skipped);
   each entry's text is capped at 2000 chars to bound the prompt.
2. **Gmail-label newsletter adapter** — point it at a Gmail label you route
   newsletters into; the inbox becomes a universal newsletter aggregator (catches
   email-only surface that RSS misses: industry digests, Scholar alerts, email
   Substacks). Leverages the already-connected Gmail integration.
3. **arXiv** — clean API. `cs.AR` (computer architecture — the chip-design
   bullseye) + `cs.AI` / `cs.LG` / `eess.SP`. Independent-item; keyword filtering ideal.

### Tier 2 — clean and additive

4. **Hacker News** — Algolia API, keyword-filterable, broad tech signal, low effort.
5. **GitHub** — releases/activity on tracked repos + tools (BAG, EDA tooling).
   Clean API; "new release of X" punches above its slot for a working engineer.
6. **Semantic Scholar** — broader coverage + citation metadata beyond arXiv; lower
   marginal value once arXiv exists, but cheap.

### Tier 3 — feasible, verify terms first

7. **Reddit (specific subreddits)** — subreddit JSON / `.rss` works for low-volume
   personal reads, but API terms tightened/went paid in 2023 — verify before
   committing. `keyword_filter` applies.
8. **Prediction markets (Metaculus)** — clean API; surface movement on markets you
   follow. Niche-but-yours.

### Tier 4 — gated on a deliberate decision (judgment, not effort)

9. **Slack** — biggest want; API is good, a user token reads what you can see.
   **The gate:** routing an employer's internal comms through external LLM + TTS
   APIs is a real IP/confidentiality exposure at a chip-IP company and may touch
   confidentiality terms. Decide deliberately; consider scoping to specific
   low-sensitivity channels, not the whole workspace.
10. **Signal** — **reverses the HANDOFF § Scope exclusion of Signal.** Feasible via
    `signal-cli` as a linked device, but that puts a Signal device-identity + keys
    on the box — exactly the posture that exclusion was avoiding. Eyes-open only.

### Tier 5 — poor ROI / likely infeasible (kept for completeness)

11. **Twitter/X** — read API ~$100/mo (free tier won't do it), unofficial libs
    fragile, nitter effectively dead. Only path is a flaky per-account RSS bridge.
    Parked until access economics change.
12. **Blind** — no public API, work-email gated, aggressively anti-scraping. No
    clean path; parked.
13. **Instagram DMs** — no official personal-DM API; unofficial login-as-you libs
    are ban-bait. Lowest signal, highest account risk. Recommend against.

### Bonus / non-source elements

- **Google Calendar** — already connected; not a "tracked source" but surfacing
  today's / this-week's events as a briefing element is a cheap, natural daily add.

### Subsumed (folded into the above, NOT separate adapters)

- **Substack** → generic RSS (append `/feed` to a publication URL).
- **Industry newsletters** → RSS where feed-based, Gmail-label adapter where email-only.
- **Blogs, podcasts, YouTube channels, trade press, Mastodon, Lobsters** → generic RSS.

---

## ISSUE-2: Unattended scheduling / reboot survival — WON'T BUILD (decided 2026-07-11)

**Decision: keeping the process alive across reboots is the user's problem, not
this project's.** We will not ship OS-scheduler integration (systemd unit / Task
Scheduler XML / cron installers). Rationale:

- `scheduler.py run` holds **zero persistent state**. It's an in-memory
  APScheduler timer. The watermark, brief history, and the schedule itself all
  live on disk (SQLite + `briefings.toml`), so a manual `python scheduler.py run`
  after a reboot loses **nothing** — it reads the watermark back and continues.
- Missed runs **self-heal**. Ingestion is watermark-incremental with a lookback
  floor: `since = max(now − lookback, watermark)`. If a scheduled run is missed
  (box was off), the next run pulls everything since the last *successful* run.
  A reboot therefore delays a digest and merges it into the next one — it does
  not drop messages.

Given that, wrapping the launch in an OS scheduler buys only "fire at exactly
07:00 even if the machine was off at 07:00" and "don't re-type one command after
a reboot" — not worth a per-OS integration to maintain.

**If you want it unattended anyway:** put a single line in whatever scheduler
your OS already has — `python scheduler.py once --briefing NAME` on a timer (Task
Scheduler on Windows, cron/systemd-timer on Linux). That's a per-machine
deployment choice you make when you deploy; it's not code this repo owns.

## ISSUE-3: Failure visibility / observability — ADDRESSED (2026-07-11)

Was: scheduled runs printed to **stdout only** (lost when detached), and an
**expired Discord token** (or any source error) degraded to an empty/short brief
**silently** — `gather` skips a failing source by design, so nothing surfaced.

Built (`core/obs.py`, wired through `core/pipeline.py` + `scheduler.py`):

- **Rotating log file** `logs/briefing.log` (gitignored). Every run tees its
  `[gather]`/`[pipeline]` lines to it, so detached runs leave a trail. Console
  output is unchanged.
- **Error vs. empty is now distinguished.** A source that *errors* (bad/expired
  token, 403/404, unknown `source_id`) is recorded; a source that legitimately
  has nothing, or has no adapter yet, is not.
- **Loud failure marker** `briefs/FAILED-<briefing>.txt`, written when any source
  errors and auto-cleared on the next fully-clean run. Names the failed source +
  likely cause (token). The `BriefResult.failed` flag drives a `⚠` line in the
  scheduler output, and a partial brief is recorded with status `partial`.

**Still open (optional, lower priority):** a *push* alert (email/ntfy/etc.) on
failure — right now you have to see the marker/log. Ties into ISSUE-6 (token
expiry). A marker file is enough for a desktop-local tool; revisit if it ever
runs somewhere you don't look.

## ISSUE-4: No automated tests (OPEN)

Zero regression safety net — everything has been validated by manual runs. A
refactor could break ingestion/synthesis and nothing would catch it. At minimum:
unit tests for `store` (watermark logic), `config` loading, `models.parse_window`,
and the Discord normalizer against a captured API payload fixture.

## ISSUE-5: Discord adapter is v0 (OPEN, low urgency)

- Skips attachment/embed-only messages (no text → dropped).
- No thread / forum-channel support.
- One channel per source (no server-wide ingestion).
- 429 handling **raises** rather than backing off / retrying.

## ISSUE-6: Secret / token lifecycle (OPEN)

The Discord **user token expires periodically** → manual re-copy from the browser.
No expiry detection or reminder; ties into ISSUE-3 (a 401 should surface loudly,
not silently empty the brief).

## ISSUE-7: No cross-brief memory (OPEN)

The watermark dedups at the **message** level, but synthesis has no memory of
**what it already told you**. A slow-burning multi-day thread can be
re-summarized across successive briefs. (Flagged as open in HANDOFF.) Possible
fix later: feed the prior brief (or a summary of it) into the synthesis prompt.

## ISSUE-8: Undecided design questions (from HANDOFF)

- **Pre-filter vs. synthesis-filter policy** — both mechanisms exist
  (`keyword_filter` pre-filters; Claude also filters in the prompt). No decision
  on how much to lean on each (tokens/cost vs. control).

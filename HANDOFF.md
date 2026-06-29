# HANDOFF — Personal Briefing Engine

Planning happened in a Claude.ai chat (on mobile). This doc carries the full context so a fresh Claude Code session on desktop can pick up without re-litigating decisions. Read it top to bottom before writing code.

---

## What we're building

A **personal briefing engine**: a reduced layer over multiple information sources that boils them down into periodic (daily / weekly / sparser) briefings. The point is to *stop having to track the sources directly* — instead review a digest on a regular cadence.

Two kinds of sources:
1. **Social group chats** — Discord, Telegram (and eventually maybe X DMs).
2. **Public research / news** — EE, AI (esp. chip design), science/tech/engineering news.

Consumption: **audio (podcast-style) is the preferred mode**, but text briefings are equally first-class. Cross-device (phone + desktop). Implementation form is deliberately flexible — CLI tool run on the desktop that delivers via email / file drop / local web page is all acceptable. No requirement to build an app or hosted service.

This is a personal side project, vibecoded. Not production, not multi-user. Optimize for iteration speed and the owner actually using it.

---

## Owner context (matters for how to build)

- Experienced EE/software engineer. Skip hand-holding on Python, git, CLI basics. Direct answers first, flag uncertainty explicitly, don't hedge or pad.
- Runs Claude Code on both Windows and Ubuntu. Uses a git worktrees workflow. Default Claude Code mode is `plan`.
- Security-conscious. See the explicit security decisions below — they're not negotiable defaults, they're chosen constraints.

---

## Scope decisions (already made — don't relitigate)

**In:**
- **Discord** — *highest value source.* User-token approach (reads everything the account can already see, no bot-add permission needed). This is against Discord ToS; owner has weighed it and accepted the risk for personal, non-commercial use. Proceed without re-raising it as a blocker, but handle the token as account-sensitive (see Security).
- **Telegram** — one specific chat, but high enough ROI to include early. Telethon userbot (reads own account's chats).
- **Public research/news** — high value but still fuzzy in scope. Deliberately deferred until *after* core infra exists. Candidate sources: arXiv (`cs.AR`, `cs.AI`, `cs.LG`, `eess.SP`), Semantic Scholar, EE Times / Semiconductor Engineering / IEEE Spectrum (RSS), Hacker News (Algolia API).

**Deprioritized:**
- **X/Twitter DMs** — niche value, and API access is painful (DMs gated behind paid tiers). Park it. Revisit only if cheap access materializes.

**Explicitly out (security):**
- **Signal** and **iMessage** — not aggregating either, by choice. Don't propose them as sources even though iMessage's local `chat.db` is technically readable.

---

## Architecture

Two **separable subsystems** sharing a common output layer:

1. **Briefing engine** — the 80%. Source adapters → normalize → Claude synthesis → TTS/text → delivery. Very buildable, mostly independent of which sources exist.
2. **Chat ingestion** — the messier 20%, added incrementally per platform.

The seam between them is a **normalized item schema** every adapter emits. The synthesizer never sees platform-specific shapes — only normalized items. **Cross-source synthesis in a single Claude pass is the core value-add** (no existing tool does this well); design toward it.

**Text is the source of truth; audio is derived from it.** Always generate the written brief first, then TTS the script. This lets either mode be consumed and makes debugging the synthesis step not require listening to audio.

**Config lives in files (YAML/TOML), not a UI.** Do not build a settings/configuration interface. It will eat momentum and file-based config iterates faster for a personal tool. This is a deliberate call.

---

## Ontology

Four concepts. This is the central design artifact — get it right before building pipeline.

### Source
A specific place to ingest from. Granularity matters: **Discord = channel-level, not server-level** (a server's channels vary wildly in relevance). Telegram is naturally chat-level.

```
Source
  platform:        discord | telegram | arxiv | rss | hn | ...
  identifier:      channel_id / chat_id / feed_url / query / ...
  display_name:    human label, used in briefs ("telegram/chip-design")
  credentials_ref: pointer to a secret, NOT the secret itself
```

### Briefing
A named, scheduled output definition. Many-to-many with Sources (one channel can feed multiple briefings).

```
Briefing
  name
  schedule:              cron expr or named cadence (daily_morning, weekly_sunday, ...)
  lookback_window:       24h | 7d | ...
  sources:               [SourceConfig]
  synthesis_instruction: str   ← FIRST-CLASS. What to focus on, what to ignore,
                                  tone, length. Expect heavy iteration here.
  output:                [audio | text | both]
  delivery:              [local | email | ...]
```

### SourceConfig (join: Source ↔ Briefing)
Per-briefing filtering of a source.

```
SourceConfig
  source_id
  briefing_id
  channel_filter:  [optional sub-channels — e.g. only #chip-design, #papers]
  keyword_filter:  [optional]
```

### Brief (generated artifact)
One generated instance.

```
Brief
  briefing_id
  period:        (start, end)
  generated_at
  text_content:  markdown / script   ← source of truth
  audio_path:    path | null         ← derived
  status:        pending | ready | delivered
```

And the **normalized ingestion item** (the adapter seam):

```
IngestedItem
  source:      "telegram/chip-design-group"   (display_name)
  content:     str
  timestamp:   datetime
  topic_tags:  [str]    (optional; can be added at synthesis time instead)
  meta:        {author, link_back, ...}   (optional, for citations/links)
```

---

## Build sequence

1. **Ontology + config schema.** Lay down the dataclasses/models and a sample TOML/YAML config. No I/O yet.

2. **Validate the consumption experience with FAKE data first.** Before any ingestion is built: hand-craft a realistic batch of `IngestedItem`s, run them through a draft `synthesis_instruction` + Claude, generate the text brief, TTS it to an mp3, and **actually listen to it on a walk.** The synthesis prompt is where the real iteration cost lives, and it's cheap to tune with zero ingestion infrastructure. Don't build the pipeline until the output is something worth listening to.

3. **Core pipeline on test data.** Wire synthesize → TTS → delivery (email or file drop) end-to-end, still on fake/test items. Add the scheduler (APScheduler or plain cron).

4. **Integrate Discord + Telegram** with the owner's real target chats as the test cases. These are the first real adapters.

5. **Broaden to research/news sources** (arXiv, RSS, HN) for the technical briefings. This is where the source ontology earns its generality.

---

## Suggested stack

```
Python project
├── adapters/
│   ├── discord.py     # user-token (discord.py-self or raw gateway/HTTP)
│   ├── telegram.py    # Telethon userbot
│   ├── arxiv.py       # arxiv pkg
│   ├── rss.py         # feedparser (EE Times, Semiconductor Eng, IEEE Spectrum)
│   └── hn.py          # Algolia API
├── core/
│   ├── models.py      # the ontology above
│   ├── synthesize.py  # Claude API; per-source + cross-source pass
│   ├── tts.py         # OpenAI TTS (or ElevenLabs)
│   └── delivery.py    # email / local file / local web page
├── scheduler.py       # APScheduler or cron entrypoints
├── config/            # YAML or TOML — sources, briefings
└── briefs/            # generated text + audio output
```

Synthesis: Claude API. TTS: OpenAI TTS is cheap and good; ElevenLabs if voice quality matters more. Scheduling: cron is fine if the desktop is always on; APScheduler if you want it self-contained.

---

## Security / secrets (read before touching credentials)

This tool touches the owner's personal accounts. Handle accordingly:

- **Never commit secrets.** `.env` + `.gitignore` from commit #1. `credentials_ref` in config points to an env var name, never the value.
- **The Discord user token is full account access** if leaked — treat it as the most sensitive secret in the project. Not in config, not in logs, not in any brief output, not in any file that could get committed or synced.
- Same for Telegram API hash/session, Anthropic key, TTS key.
- If a session file (Telethon) is created, gitignore it — it's a live auth artifact.

---

## Open questions to resolve in-session

- Storage for `Brief` history — flat files vs. SQLite? (SQLite probably, low cost, queryable.)
- Delivery default for v1 — email vs. local file drop vs. tiny local web page hittable from phone?
- How much per-source pre-filtering before synthesis vs. letting Claude do the filtering in the synthesis pass? (Trade tokens vs. control.)
- Topic tagging: at ingestion or at synthesis time?
- Voice/format of the audio brief — single-narrator script is the obvious start.

---

## First step for Claude Code

Start at sequence step 1: scaffold the repo, define the ontology in `core/models.py`, and write a sample config (one fake Discord-style source, one fake Telegram source, one daily briefing) — then immediately move to step 2 (fake-data synthesis + TTS) so the consumption experience can be validated before any real ingestion is built.

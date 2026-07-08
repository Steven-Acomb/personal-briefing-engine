# Personal Briefing Engine

A reduced layer over multiple information sources (group chats + research/news)
that boils them into periodic **briefings** — so you review a digest on a
cadence instead of tracking every source directly. Audio (podcast-style) is a
first-class consumption mode; **text is the source of truth and audio is derived
from it.** Personal, single-user side project.

---

## Start here (orientation)

New to the repo — whether a human or a fresh Claude Code session — read these,
in order. Each has a distinct job; this README is just the map.

| Doc | What's in it |
|---|---|
| **[HANDOFF.md](HANDOFF.md)** | The design: vision, the ontology (Source / Briefing / SourceConfig / Brief / IngestedItem), scope decisions, and the non-negotiable security constraints. Read before writing code. |
| **[HUMAN_TODO.md](HUMAN_TODO.md)** | The setup only a human can do — API keys, Python environment, Discord token + channel. **Start here to get it running on a new machine.** |
| **[ROADMAP.md](ROADMAP.md)** | Current status, known gaps/issues (ISSUE-1..8), and remaining work with priorities. **Read before deciding what to build next.** |

---

## Status

Working end-to-end on real data: **Discord ingestion → cross-source Claude
synthesis → text brief → OpenAI TTS → local file-drop delivery**, with a SQLite
history + incremental per-source watermark, driven by APScheduler. The framework
is general and data-driven — adding a source is a config entry, not code.

Not yet built: Telegram + research/news adapters, email/web delivery, and the
operational "run it unattended, reliably" layer (supervision, logging, failure
alerts). See **ROADMAP.md** for the full list and what's highest-priority.

---

## Get it running

Full walkthrough (keys, environment, Discord token): **HUMAN_TODO.md**. Quick
version — requires Python ≥ 3.11:

```bash
cp .env.example .env                 # add ANTHROPIC_API_KEY (+ OPENAI_API_KEY for audio)
conda env create -f environment.yml  # or: uv sync  |  or: python -m venv .venv && pip install -e .
conda activate personal-briefing-engine
python run_fake.py --no-audio        # smoke test: a brief from fake data (needs only ANTHROPIC_API_KEY)
```

Resync after dependencies change: `conda env update -f environment.yml --prune`.
Dependencies live in `pyproject.toml` (single source of truth); `environment.yml`
just pins Python and installs from it.

---

## Running it

```bash
# dev / audition on fake data (tune the synthesis prompt, try voices)
python run_fake.py                 # + audio;  --no-audio = text only;  --wav = local-playable

# validate a Discord channel in isolation (read-only, no cost)
python -m adapters.discord <channel_id> --hours 24

# real pipeline (needs DISCORD_USER_TOKEN in .env + a real channel in config/sources.toml)
python scheduler.py list                    # briefings + next fire times
python scheduler.py once --briefing NAME    # run one now  (--dry-run = free wiring check)
python scheduler.py run                     # start the scheduling loop (blocks; fires on cron)
python scheduler.py history                 # past briefs (from SQLite)
```

Output → `briefs/` (gitignored): timestamped `.md`/`.mp3` plus a stable
`latest-<briefing>.*` pointer (the "delivery").

---

## Layout

```
core/
  models.py       # the ontology: Source, Briefing, SourceConfig, Brief, IngestedItem
  config.py       # load config/*.toml into the ontology
  fixtures.py     # hand-made fake IngestedItems (for run_fake.py)
  synthesize.py   # Claude synthesis — cross-source pass
  tts.py          # text -> audio (OpenAI echo-plain; see ROADMAP ISSUE-1)
  delivery.py     # local file drop (email / web page: not built)
  store.py        # SQLite: brief history + per-source watermark (text stays as files)
  pipeline.py     # run one briefing end-to-end: gather -> synth -> tts -> deliver
adapters/
  discord.py      # user-token REST history -> IngestedItem  (telegram/rss/hn: not built)
config/
  sources.toml    # where to read from (ships with one neutral example; add real channels)
  briefings.toml  # named scheduled digests + synthesis instructions
briefs/           # generated text + audio output (gitignored)
data/             # SQLite db (gitignored)
run_fake.py       # dev/audition runner (synthesize + voice A/B on fake data)
scheduler.py      # entrypoint: list / once / run / history
```

---

## Continuing development

The framework is data-driven — **sources and briefings are configuration, not
code.** Two seams are where new work plugs in:

- **New ingestion source** (Telegram, RSS, arXiv, HN): add an adapter that
  returns normalized `IngestedItem`s and a branch in
  `core/pipeline.py::gather_items`, which dispatches per `Source.platform`. Use
  `adapters/discord.py` as the reference implementation.
- **New TTS voice/provider**: `core/tts.py` (currently OpenAI-only). See ROADMAP
  ISSUE-1 for the queued usage-based options.

What to build next, and every known gap, lives in **ROADMAP.md**.

---

## Security

This tool touches personal accounts. Secrets live in `.env` only (gitignored);
config references them by env-var **name** via `credentials_ref`, never by value.
The **Discord user token is full account access** — treat it as the most
sensitive secret in the project. Full constraints: HANDOFF.md § Security.

# Personal Briefing Engine

A reduced layer over multiple information sources (group chats + research/news)
that boils them into periodic **briefings** — so you review a digest on a
cadence instead of tracking every source directly. Audio (podcast-style) is the
preferred consumption mode; text is the source of truth and audio is derived
from it.

Personal, single-user side project. See **[HANDOFF.md](HANDOFF.md)** for the
full design context, scope decisions, and security constraints — read it before
writing code.

## Layout

```
core/
  models.py       # the ontology: Source, Briefing, SourceConfig, Brief, IngestedItem
  synthesize.py   # (todo) Claude synthesis — per-source + cross-source pass
  tts.py          # (todo) text -> audio
  delivery.py     # (todo) local / email / local web page
adapters/         # (todo) discord, telegram, arxiv, rss, hn -> IngestedItem
config/
  sources.toml    # what to ingest from (fake placeholders for now)
  briefings.toml  # named scheduled digests + synthesis instructions
briefs/           # generated text + audio output (gitignored)
scheduler.py      # (todo) cron / APScheduler entrypoints
```

## Build sequence (from HANDOFF.md)

1. **Ontology + config schema** — dataclasses + sample TOML, no I/O. ← *done*
2. **Validate consumption with FAKE data** — hand-crafted `IngestedItem`s →
   synthesis → text brief → TTS → *actually listen to it* — before any real
   ingestion. ← *next*
3. Core pipeline on test data (synthesize → TTS → delivery + scheduler).
4. Integrate Discord + Telegram (first real adapters).
5. Broaden to research/news (arXiv, RSS, HN).

## Setup

```bash
cp .env.example .env      # fill in secrets; .env is gitignored
python -m venv .venv && source .venv/bin/activate
```

Requires Python ≥ 3.11 (`tomllib` is stdlib). No third-party deps yet.

## Security

This tool touches personal accounts. Secrets live in `.env` only; config
references them by env-var **name** via `credentials_ref`, never by value. The
Discord user token is full account access — treat it as the most sensitive
secret in the project. See HANDOFF.md § Security.

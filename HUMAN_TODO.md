# HUMAN_TODO — things only you can do

The code for build-sequence **step 2** (validate the consumption experience on
fake data) is written and wired. It can't run until you do the two things below:
get API keys, and pick/create a Python environment. Everything after that is a
single command.

Est. time: ~15 min, most of it waiting on account signup.

---

## 1. Get two API keys

These are **pay-per-use developer API keys**. They are NOT the same as a
Claude Pro / ChatGPT Plus subscription — a subscription won't work here, and a
key won't give you the chat apps. Each requires adding a payment method.

### a) Anthropic API key — REQUIRED (text synthesis)

1. Go to <https://console.anthropic.com>, sign in / sign up.
2. **Billing → add a payment method** and put a small amount of credit on it
   (even $5 is plenty to start — see cost note below).
3. **API keys → Create Key**. Copy it (starts with `sk-ant-...`). You only see
   it once.

Cost: this project uses `claude-opus-4-8`. One briefing from the fake data is a
few thousand tokens in, a few hundred out — well under **$0.10 per run**. If you
end up running briefings many times a day and want to cut cost, we can switch
the synthesis model to `claude-sonnet-5` (cheaper) later; Opus is the default
for best quality while we tune the prompt.

### b) OpenAI API key — OPTIONAL (audio / TTS only)

Only needed if you want the spoken audio brief. The written brief (the source of
truth) needs only the Anthropic key.

1. Go to <https://platform.openai.com>, sign in / sign up.
2. **Settings → Billing → add a payment method** (again ~$5 credit is plenty).
3. **API keys → Create new secret key**. Copy it (starts with `sk-...`).

Cost: TTS uses `gpt-4o-mini-tts`. A ~3-minute brief is a fraction of a cent.

> Later sources (Discord, Telegram) will need their own credentials. Ignore
> those for now — step 2 is fake data only. See HANDOFF.md § Security.

---

## 2. Put the keys in `.env`

The keys go in a local `.env` file, which is **gitignored** and must never be
committed (HANDOFF.md § Security — the Discord token especially is full account
access once we add it).

```bash
cp .env.example .env
```

Then edit `.env` and fill in:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # leave blank if skipping audio for now
```

Leave the other placeholders (Discord/Telegram) empty until we build those.

---

## 3. Create the Python environment

Pick ONE. **Recommended: conda** (matches your workflow; cross-platform).

Dependencies live in `pyproject.toml` in all cases — the commands below just
create an isolated env and install from it. Requires Python ≥ 3.11.

### Option A — conda (recommended)

```bash
conda env create -f environment.yml
conda activate personal-briefing-engine
```

To update after deps change: `conda env update -f environment.yml --prune`

### Option B — uv (if you'd rather not use conda)

`uv` is a single fast binary with a built-in lockfile — the slickest fresh-clone
setup. Install from <https://docs.astral.sh/uv/> then:

```bash
uv sync           # creates .venv and installs from pyproject.toml
uv run python run_fake.py --no-audio
```

### Option C — plain venv + pip (no extra tools)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

> Note: there's a stray `.venv/` in the repo from my scaffolding. It's
> gitignored. If you use conda or uv, you can delete it.

---

## 4. Run it

With the env active and `.env` filled in:

```bash
# Written brief only — needs just the Anthropic key. Start here.
python run_fake.py --no-audio

# Written brief + audio you can play on THIS machine (paplay is installed):
python run_fake.py --wav

# Written brief + mp3 for your phone (default; no mp3 player on this box):
python run_fake.py
```

Output lands in `briefs/` (gitignored): a `.md` (the written brief, source of
truth) and, unless `--no-audio`, a `.wav`/`.mp3`.

Listen to a wav locally:

```bash
paplay briefs/daily-morning-<timestamp>.wav
```

---

## 5. The actual point of step 2

Once it runs, **read the brief, then listen to the audio** (transfer the mp3 to
your phone and play it on a walk — that's the real test per HANDOFF.md § Build
sequence step 2).

Then iterate: the whole synthesis behavior is driven by the
`synthesis_instruction` field in **`config/briefings.toml`**. Edit that string,
re-run, compare. This is the cheapest place to tune the product and where most
of the iteration cost lives — no ingestion infrastructure needed. Tune the fake
data in `core/fixtures.py` too if you want to stress different scenarios.

When the output is genuinely worth listening to, we move to step 3 (real
pipeline + scheduler) and step 4 (Discord/Telegram ingestion).

---

## Troubleshooting

- **`anthropic.AuthenticationError` / 401** — key missing or wrong in `.env`, or
  `.env` not being loaded (run from the repo root; `run_fake.py` calls
  `load_dotenv()`).
- **`RateLimitError` / billing errors** — no credit on the account; add funds in
  the console.
- **Audio step fails but text worked** — `OPENAI_API_KEY` is missing/blank. Use
  `--no-audio` to skip it, or fill the key.
- **`ModuleNotFoundError`** — env not activated, or deps not installed
  (`pip install -e .` / `conda env update`).

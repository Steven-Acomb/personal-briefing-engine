# HUMAN_TODO — things only you can do

Checklist of things only you can do — get credentials and set up the environment.

- **§1–5 are the general setup** and apply to **any machine** — use them to get a
  fresh clone running on another computer.
- **§6 is the Discord credentials** needed to run on real data (build-sequence
  step 4).

Est. first-time setup: ~15 min, most of it waiting on account signup.

---

## 1. Get two API keys

These are **pay-per-use developer API keys** (no subscriptions). They are NOT
the same as a Claude Pro / ChatGPT Plus subscription — a subscription won't work
here, and a key won't give you the chat apps. Each requires adding a payment
method.

### a) Anthropic API key — REQUIRED (text synthesis)

1. Go to <https://console.anthropic.com>, sign in / sign up.
2. **Billing → add a payment method** and put a small amount of credit on it
   (even $5 is plenty to start — see cost note below).
3. **API keys → Create Key**. Copy it (starts with `sk-ant-...`). You only see
   it once.

Cost: this project uses `claude-opus-4-8`. One briefing is a few thousand tokens
in, a few hundred out — well under **$0.10 per run**. If you end up running many
times a day and want to cut cost, we can switch the synthesis model to
`claude-sonnet-5` (cheaper) later; Opus is the default for best quality.

### b) OpenAI API key — OPTIONAL (audio / TTS)

Only needed for the spoken audio brief; the written brief needs only the
Anthropic key. Audio uses OpenAI's `gpt-4o-mini-tts` with the `echo` voice
(plain). (ElevenLabs was evaluated and ruled out — subscription-only. The future
better-voice path is a usage-based provider like Deepgram/Google — see ROADMAP.)

1. Go to <https://platform.openai.com>, sign in / sign up.
2. **Settings → Billing → add a payment method** (~$5 credit is plenty).
3. **API keys → Create new secret key** (starts with `sk-...`).

Cost: OpenAI TTS is a fraction of a cent per brief.

---

## 2. Put the keys in `.env`

The keys go in a local `.env` file, which is **gitignored** and must never be
committed (HANDOFF.md § Security — the Discord token especially is full account
access once we add it).

```bash
cp .env.example .env
```

Then edit `.env` and fill in the values. **Do NOT add trailing `# comments` on a
value line** — `python-dotenv` reads them as part of the value (we hit this). The
lines:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DISCORD_USER_TOKEN=
```

- `ANTHROPIC_API_KEY` — **required** (text synthesis).
- `OPENAI_API_KEY` — audio (the `echo` voice). Skip if you only want text briefs.
- `DISCORD_USER_TOKEN` — for real data; see §6. Leave blank until then.

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

## 6. Real data — Discord (build-sequence step 4)

To run on real Discord data instead of fake fixtures you provide two things: your
**user token** (once) and the **channel ID** of each channel to aggregate.

### a) Discord user token → `.env`  (SENSITIVE — full account access)

Discord blocks the old console method, so use the browser Network tab:

1. Open Discord in a browser, press **F12** → **Network** tab.
2. Click any channel to generate traffic; type **`messages`** in the filter box.
3. Click a request to `discord.com/api/...` → **Headers** → **Request Headers**
   → copy the value of the **`authorization`** header (a long string, no "Bot ").
4. Put it in `.env` on its own line (no trailing comment):
   ```
   DISCORD_USER_TOKEN=<value>
   ```

Treat it like your password — `.env` only, never commit, never paste it into a
chat. If it ever leaks, change your Discord password (that invalidates all
tokens). Note: automating a user token is against Discord ToS; the risk is to
your own account (a tradeoff accepted per HANDOFF.md § Security).

### b) Channel IDs (not secret)

1. Discord → **User Settings (gear) → Advanced → Developer Mode: ON**.
2. Right-click a channel in the sidebar → **Copy Channel ID**.
3. Put the ID into `config/sources.toml` as the `identifier` of a `discord`
   source (replacing the fake placeholder), and set `display_name` to a readable
   label used in briefs (e.g. `"discord/chip-design"`).

### c) Test ingestion (read-only, no cost)

```bash
python -m adapters.discord <channel_id> --hours 24
```

Prints the last 24h of that channel, normalized into our message shape. No
Claude, no TTS, no cost — it just confirms the token + channel work before the
adapter is wired into the pipeline.

---

## Troubleshooting

- **`anthropic.AuthenticationError` / 401** — key missing or wrong in `.env`, or
  `.env` not being loaded (run from the repo root; `run_fake.py` calls
  `load_dotenv()`).
- **`RateLimitError` / billing errors** — no credit on the account; add funds in
  the console.
- **Audio step fails but text worked** — `OPENAI_API_KEY` is missing/blank. Use
  `--no-audio` to skip it, or fill the key.
- **`ModuleNotFoundError`** — env not activated, or deps not installed. After I
  add a dependency you must re-sync: `pip install -e .` (in the active env) or
  `conda env update -f environment.yml --prune`.
- **Discord `401`** — token invalid or expired; re-copy it from the Network tab.
- **Discord `403`** — wrong channel ID, or your account can't see that channel.
- **Discord `429`** — rate-limited; wait and retry (the adapter already paces
  and caps its requests).
- **Discord token but `Missing ... env var`** — the `DISCORD_USER_TOKEN` line has
  a trailing `# comment` (breaks parsing) or `.env` isn't in the repo root.

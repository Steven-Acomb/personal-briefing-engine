# HUMAN_TODO — things only you can do

Checklist of things only you can do — get credentials and set up the environment.
Applies to **any machine**; use it to get a fresh clone running.

- **§1–3** — API keys, `.env`, Python environment (the general setup).
- **§4** — smoke-test on fake data (no real ingestion needed).
- **§5–6** — run on real data: Discord credentials + the real pipeline.

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

---

## 4. Smoke test on fake data

First copy the config templates into place (the live files are gitignored, same
as `.env`, so they never carry your real channel IDs into git):

```bash
cp config/sources.toml.example config/sources.toml
cp config/briefings.toml.example config/briefings.toml
```

With the env active, `.env` filled in, and config copied, generate a brief from
the built-in fake fixtures — no real ingestion needed. The text path needs only
the Anthropic key; audio also needs the OpenAI key.

```bash
python run_fake.py --no-audio    # written brief only (text is the source of truth)
python run_fake.py               # + audio as .mp3
python run_fake.py --wav         # + audio as .wav (playable by paplay on Linux, if installed)
```

Output lands in `briefs/` (gitignored): a `.md` (the brief) and, unless
`--no-audio`, a `.wav`/`.mp3`. Read it — if it's coherent, the core pipeline
works and you're ready for real data (§6).

Tuning: the whole synthesis behavior is driven by the `synthesis_instruction`
field in **`config/briefings.toml`** — the cheapest place to iterate. Edit it,
re-run, compare. (`core/fixtures.py` holds the fake messages if you want to
stress different scenarios.)

---

## 5. Run on real data

Once §6 (Discord credentials) is done and `config/sources.toml` points at a real
channel, run the real pipeline via the scheduler — see the **"Running it"**
section of [README.md](README.md) for the `scheduler.py` commands
(`list` / `once` / `run` / `history`). Current status and what's left to build
are in [ROADMAP.md](ROADMAP.md).

---

## 6. Real data — Discord credentials

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

## 7. Real data — Telegram credentials (heavier setup than Discord)

Telegram doesn't use a copy-paste token. You register an app to get an
**API id + hash**, then do a **one-time interactive login** (your phone number →
a code Telegram texts you → your 2FA password if you have one). That login
creates a `*.session` file the adapter reuses afterward, including from the
scheduled 7 AM run. The session file is a live auth artifact — **gitignored, never
commit it** (HANDOFF § Security). Like Discord, this reads your own account's
chats (an MTProto userbot); the risk is to your own account, accepted per HANDOFF.

### a) Get your API id + hash  (SENSITIVE)

1. Go to <https://my.telegram.org> and log in with your phone number + the code.
2. Open **API development tools**, create an app (any title/short-name, platform
   "Desktop" is fine).
3. Copy the **`api_id`** (a number) and **`api_hash`** (a long hex string).

### b) Put them in `.env`

The lines already exist in `.env.example`; fill in the first two (leave
`TELEGRAM_SESSION` as `briefing` unless you want a different session name). No
trailing `# comments` on value lines.

```
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=<hex string>
TELEGRAM_SESSION=briefing
```

### c) One-time login (interactive — creates the session)

```bash
python -m adapters.telegram login
```

It prompts for your phone (international format, e.g. `+1...`), the code Telegram
sends you, and your 2FA password if set. On success it writes `briefing.session`
in the repo root and prints who you logged in as. You only do this once (re-run
if the session ever expires — you'll see a "session not authorized" error).

### d) Find the chat id(s) you want

```bash
python -m adapters.telegram list
```

Prints every chat your account is in as `chat_id / @username / title`. Note the
`chat_id` (or the `@username` if it has one) of each chat you want to aggregate.

### e) Validate a chat (read-only, no cost)

```bash
python -m adapters.telegram fetch <chat_id or @username> --hours 24
```

Confirms the login + chat work before wiring it into a briefing.

### f) Add the source

In the web UI (or `config/sources.toml`): a source with **platform `telegram`**,
**identifier** = the chat id or `@username`, and **credentials_ref** =
`TELEGRAM_SESSION`. Then add it to a briefing like any other source.

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
- **Telegram `Missing ... credentials`** — `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`
  not set in `.env` (get them from <https://my.telegram.org>, §7a).
- **Telegram `session not authorized`** — you haven't logged in yet, or the
  session expired. Run `python -m adapters.telegram login` (§7c).
- **Telegram `could not resolve chat`** — wrong id, or the account isn't in that
  chat. Prefer the `@username`; use `python -m adapters.telegram list` to find it.
- **Telegram login asks endlessly / `FloodWait`** — too many attempts; wait it
  out. Make sure the phone number is in international format (`+1...`).

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

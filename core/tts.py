"""Text-to-speech: render a brief (the source of truth) to audio via OpenAI TTS.

Default is the `echo` voice, **plain** (no delivery instructions) — the owner's
chosen default after auditioning the OpenAI voice set. `gpt-4o-mini-tts` is
steerable via an `instructions` prompt, but that's opt-in; plain is the default.

ElevenLabs was evaluated and ruled out (its API is subscription-only, and the
good voices require a paid plan). The future quality path is a usage-based
provider (Deepgram / Google) — see ROADMAP ISSUE-1. When we add one, it slots in
here behind `synthesize_audio` as an alternate backend.
"""

from __future__ import annotations

from pathlib import Path

MODEL = "gpt-4o-mini-tts"  # steerable OpenAI TTS model

# The 11 voices the OpenAI TTS API exposes.
VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "onyx", "nova", "sage", "shimmer", "verse",
]
VOICE = "echo"  # owner's pick

# Optional delivery steering (opt-in via `instructions=`). Owner preferred plain,
# so the default call passes no instructions.
INSTRUCTIONS = (
    "Voice: warm, natural, and engaging, like a knowledgeable friend giving you "
    "the morning download over coffee. Tone: conversational and relaxed. Pacing: "
    "unhurried, with natural pauses between topics. Avoid a flat, monotone read."
)

_FORMATS = {".mp3": "mp3", ".wav": "wav"}


def synthesize_audio(
    text: str,
    out_path: Path,
    *,
    voice: str = VOICE,
    instructions: str = "",
    client=None,
) -> Path:
    """Render `text` to audio at `out_path`. Format follows the extension
    (.mp3 for phone, .wav for local players). `instructions` steers delivery
    (empty = plain, the default). Returns the path written."""
    from openai import OpenAI  # lazy: --no-audio paths need no openai import

    fmt = _FORMATS.get(out_path.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported extension {out_path.suffix!r}; use .mp3/.wav")
    if voice not in VOICES:
        raise ValueError(f"Unknown voice {voice!r}; choose from {VOICES}")

    client = client or OpenAI()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = dict(model=MODEL, voice=voice, input=text, response_format=fmt)
    if instructions:  # omit entirely when empty (plain read)
        kwargs["instructions"] = instructions

    with client.audio.speech.with_streaming_response.create(**kwargs) as response:
        response.stream_to_file(out_path)
    return out_path

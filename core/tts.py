"""Text-to-speech: turn a written brief (the source of truth) into an mp3.

Default backend is OpenAI TTS (cheap, good enough to validate the listening
experience). Swap for ElevenLabs later if voice quality becomes the bottleneck.

NOTE: ChatGPT's "Advanced Voice" voices (Ember, Cove, ...) are NOT available in
this API — they run on OpenAI's Realtime speech-to-speech system, a different
endpoint. The TTS API exposes 11 fixed voices (see VOICES). The big quality
lever here is `INSTRUCTIONS`: gpt-4o-mini-tts is steerable, so a good delivery
prompt is what turns a flat monotone read into something listenable.
"""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI

# gpt-4o-mini-tts is the current steerable TTS model (honors `instructions`).
MODEL = "gpt-4o-mini-tts"

# The 11 voices the TTS API exposes. Try a few — taste varies.
VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "onyx", "nova", "sage", "shimmer", "verse",
]
VOICE = "echo"  # user's pick; steer delivery further via INSTRUCTIONS

# Delivery direction. This is where "monotone -> engaging" happens — tune freely.
INSTRUCTIONS = (
    "Voice: warm, natural, and engaging, like a knowledgeable friend giving you "
    "the morning download over coffee. "
    "Tone: conversational and relaxed, not a formal news anchor. "
    "Pacing: unhurried, with natural pauses between topics so key points can "
    "breathe. "
    "Emotion: genuine interest, with a little energy on the good news and a "
    "measured, clear delivery on the technical warnings. "
    "Avoid a flat, robotic, or monotone read."
)


_FORMATS = {".mp3": "mp3", ".wav": "wav", ".opus": "opus", ".flac": "flac"}


def synthesize_audio(
    text: str,
    out_path: Path,
    client: OpenAI | None = None,
    voice: str = VOICE,
    instructions: str = INSTRUCTIONS,
) -> Path:
    """Render `text` to audio at `out_path`. The response format follows the
    file extension (.mp3 for phone/podcast, .wav for local players like paplay).
    `instructions` steers delivery (tone/pacing/emotion). Returns the path."""
    fmt = _FORMATS.get(out_path.suffix.lower())
    if fmt is None:
        raise ValueError(
            f"Unsupported audio extension {out_path.suffix!r}; "
            f"use one of {sorted(_FORMATS)}"
        )
    if voice not in VOICES:
        raise ValueError(f"Unknown voice {voice!r}; choose from {VOICES}")

    client = client or OpenAI()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # `instructions` is optional — omit it entirely (don't send "") when empty,
    # so we can A/B the steered vs. unsteered delivery cleanly.
    kwargs = dict(model=MODEL, voice=voice, input=text, response_format=fmt)
    if instructions:
        kwargs["instructions"] = instructions

    with client.audio.speech.with_streaming_response.create(**kwargs) as response:
        response.stream_to_file(out_path)

    return out_path

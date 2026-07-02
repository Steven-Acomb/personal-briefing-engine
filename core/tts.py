"""Text-to-speech: turn a written brief (the source of truth) into an mp3.

Default backend is OpenAI TTS (cheap, good enough to validate the listening
experience). Swap for ElevenLabs later if voice quality becomes the bottleneck.
"""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI

# gpt-4o-mini-tts is cheap and current; "onyx"/"alloy"/"nova" are stock voices.
MODEL = "gpt-4o-mini-tts"
VOICE = "onyx"


_FORMATS = {".mp3": "mp3", ".wav": "wav", ".opus": "opus", ".flac": "flac"}


def synthesize_audio(
    text: str,
    out_path: Path,
    client: OpenAI | None = None,
    voice: str = VOICE,
) -> Path:
    """Render `text` to audio at `out_path`. The response format follows the
    file extension (.mp3 for phone/podcast, .wav for local players like paplay).
    Returns the path written."""
    fmt = _FORMATS.get(out_path.suffix.lower())
    if fmt is None:
        raise ValueError(
            f"Unsupported audio extension {out_path.suffix!r}; "
            f"use one of {sorted(_FORMATS)}"
        )

    client = client or OpenAI()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with client.audio.speech.with_streaming_response.create(
        model=MODEL,
        voice=voice,
        input=text,
        response_format=fmt,
    ) as response:
        response.stream_to_file(out_path)

    return out_path

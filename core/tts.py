"""Text-to-speech: turn a written brief (the source of truth) into audio.

Two backends behind one seam (`synthesize_audio`):

  * ElevenLabs (primary) — much more natural/expressive voices; the path toward
    the ChatGPT "Advanced Voice" (Ember) quality the owner wants. Paid, has a
    free trial tier. Requires ELEVENLABS_API_KEY.
  * OpenAI TTS (fallback) — cheap, always-available. When ElevenLabs isn't
    configured (or a call fails in "auto" mode), we fall back to OpenAI's
    `echo` voice with NO delivery instructions ("echo-plain"), the owner's
    chosen least-bad OpenAI option.

NOTE: ChatGPT's Ember voice itself is not available in ANY file-based TTS API
(it's OpenAI's Realtime speech-to-speech system). ElevenLabs is the realistic
way to get comparable quality here.

Backend selection (`backend="auto"`): use ElevenLabs if ELEVENLABS_API_KEY is
set and the `elevenlabs` package is importable; otherwise OpenAI echo-plain.
"""

from __future__ import annotations

import os
import wave
from pathlib import Path

# --------------------------------------------------------------------------- #
# OpenAI backend config
# --------------------------------------------------------------------------- #

OPENAI_MODEL = "gpt-4o-mini-tts"  # steerable (honors `instructions`)

# The 11 voices the OpenAI TTS API exposes.
OPENAI_VOICES = [
    "alloy", "ash", "ballad", "coral", "echo",
    "fable", "onyx", "nova", "sage", "shimmer", "verse",
]
VOICE = "echo"           # default/fallback OpenAI voice (owner's pick)
FALLBACK_VOICE = "echo"  # what "auto" falls back to (plain, no instructions)

# Delivery direction for the *steered* OpenAI path (audition/experiments only).
# The fallback path deliberately passes "" here (owner preferred plain).
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

# --------------------------------------------------------------------------- #
# ElevenLabs backend config (all env-overridable so no code edits to swap voice)
# --------------------------------------------------------------------------- #

# Default voice = "Brian" (warm American male narrator). Browse the ElevenLabs
# voice library and set ELEVENLABS_VOICE_ID in .env to the voice you like — the
# voice choice is the whole point of moving to ElevenLabs, so pick deliberately.
# Other premade male IDs: George JBFqnCBsd6RMkjVDRZzb, Adam pNInz6obpgDQGcFmaJgB.
DEFAULT_EL_VOICE_ID = "nPczCjzI2devNBz1zQrb"  # Brian
# eleven_multilingual_v2 = stable high quality. eleven_v3 = most expressive
# (best shot at Ember-like emotion, but newer/pricier). Override via env.
DEFAULT_EL_MODEL = "eleven_multilingual_v2"

_FORMATS = {".mp3": "mp3", ".wav": "wav"}


# --------------------------------------------------------------------------- #
# Backend resolution
# --------------------------------------------------------------------------- #


def _env(name: str) -> str | None:
    """Read an env var, treating blank OR comment-like values as unset.

    Guards against a common .env footgun: a trailing inline comment on an empty
    optional var (e.g. `ELEVENLABS_MODEL=  # optional`) gets parsed as the value.
    """
    v = os.getenv(name, "").strip()
    return None if (not v or v.startswith("#")) else v


def elevenlabs_available() -> bool:
    """True if ElevenLabs can be used (key set and package importable)."""
    if not _env("ELEVENLABS_API_KEY"):
        return False
    try:
        import elevenlabs  # noqa: F401
        return True
    except ImportError:
        return False


def _resolve_backend(backend: str) -> str:
    """Map 'auto' to a concrete backend; validate explicit choices."""
    if backend == "auto":
        return "elevenlabs" if elevenlabs_available() else "openai"
    if backend not in ("elevenlabs", "openai"):
        raise ValueError(f"Unknown backend {backend!r} (auto|elevenlabs|openai)")
    return backend


# --------------------------------------------------------------------------- #
# OpenAI backend
# --------------------------------------------------------------------------- #


def _synthesize_openai(
    text: str,
    out_path: Path,
    voice: str,
    instructions: str,
    client=None,
) -> Path:
    from openai import OpenAI  # lazy so ElevenLabs-only setups need no openai key

    fmt = _FORMATS.get(out_path.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported extension {out_path.suffix!r}; use .mp3/.wav")
    if voice not in OPENAI_VOICES:
        raise ValueError(f"Unknown OpenAI voice {voice!r}; choose from {OPENAI_VOICES}")

    client = client or OpenAI()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # `instructions` is optional — omit entirely (not "") when empty.
    kwargs = dict(model=OPENAI_MODEL, voice=voice, input=text, response_format=fmt)
    if instructions:
        kwargs["instructions"] = instructions

    with client.audio.speech.with_streaming_response.create(**kwargs) as response:
        response.stream_to_file(out_path)
    return out_path


# --------------------------------------------------------------------------- #
# ElevenLabs backend
# --------------------------------------------------------------------------- #


def _synthesize_elevenlabs(
    text: str,
    out_path: Path,
    voice_id: str,
    model: str,
    client=None,
) -> Path:
    from elevenlabs.client import ElevenLabs  # lazy import

    suffix = out_path.suffix.lower()
    if suffix == ".mp3":
        output_format = "mp3_44100_128"
    elif suffix == ".wav":
        output_format = "pcm_44100"  # wrapped into a WAV container below
    else:
        raise ValueError(f"Unsupported extension {suffix!r}; use .mp3/.wav")

    client = client or ElevenLabs(api_key=_env("ELEVENLABS_API_KEY"))
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model,
        output_format=output_format,
    )
    data = b"".join(audio)  # convert() yields byte chunks

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".wav":
        # pcm_44100 = 16-bit signed mono PCM; wrap in a WAV header.
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(data)
    else:
        out_path.write_bytes(data)
    return out_path


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def synthesize_audio(
    text: str,
    out_path: Path,
    *,
    backend: str = "auto",
    # OpenAI path knobs (used when backend resolves to openai)
    voice: str = VOICE,
    instructions: str = INSTRUCTIONS,
    openai_client=None,
    # ElevenLabs path knobs (env defaults if not passed)
    el_voice_id: str | None = None,
    el_model: str | None = None,
    el_client=None,
) -> tuple[Path, str]:
    """Render `text` to audio at `out_path`. Format follows the extension
    (.mp3 for phone, .wav for local players). Returns (path, backend_used).

    - backend="auto": ElevenLabs if configured, else OpenAI echo-plain.
    - backend="elevenlabs": force ElevenLabs (raises if unavailable).
    - backend="openai": force OpenAI with the given `voice`/`instructions`.
    """
    resolved = _resolve_backend(backend)

    if resolved == "elevenlabs":
        voice_id = el_voice_id or _env("ELEVENLABS_VOICE_ID") or DEFAULT_EL_VOICE_ID
        model = el_model or _env("ELEVENLABS_MODEL") or DEFAULT_EL_MODEL
        try:
            path = _synthesize_elevenlabs(text, out_path, voice_id, model, el_client)
            return path, "elevenlabs"
        except Exception as e:  # noqa: BLE001 — in auto mode we degrade gracefully
            if backend == "elevenlabs":
                raise
            print(f"[tts] ElevenLabs failed ({e}); falling back to OpenAI echo-plain.")
            path = _synthesize_openai(text, out_path, FALLBACK_VOICE, "", openai_client)
            return path, "openai-fallback"

    # OpenAI path. In "auto" mode this IS the fallback -> force echo-plain,
    # ignoring any steering args. When explicitly requested, honor voice/instructions.
    if backend == "auto":
        path = _synthesize_openai(text, out_path, FALLBACK_VOICE, "", openai_client)
        return path, "openai-fallback"
    path = _synthesize_openai(text, out_path, voice, instructions, openai_client)
    return path, "openai"

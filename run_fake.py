"""Step-2 runner: validate the consumption experience on FAKE data.

Pipeline (no real ingestion): fixtures -> synthesize (Claude) -> write text
brief -> TTS to mp3. Then actually read/listen to the output and iterate on the
synthesis_instruction. This is the cheapest place to tune the prompt.

Usage:
    python run_fake.py                 # text + audio for the daily-morning briefing
    python run_fake.py --no-audio      # skip TTS (only needs ANTHROPIC_API_KEY)
    python run_fake.py --voice ballad  # try a different TTS voice
    python run_fake.py --from briefs/daily-morning-XXXX.md --voice sage
                                       # re-voice an existing brief (no Claude call,
                                       # only needs OPENAI_API_KEY) — cheap A/B testing
    python run_fake.py --briefing NAME # a different briefing from briefings.toml
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from core.config import get_briefing
from core.fixtures import FAKE_ITEMS
from core.models import OutputMode

BRIEFS_DIR = Path(__file__).resolve().parent / "briefs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the brief on fake data.")
    parser.add_argument("--briefing", default="daily-morning")
    parser.add_argument("--no-audio", action="store_true", help="skip TTS")
    parser.add_argument(
        "--wav",
        action="store_true",
        help="emit .wav (playable locally with paplay) instead of .mp3",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="TTS voice to try (alloy, ash, ballad, coral, echo, fable, onyx, "
        "nova, sage, shimmer, verse). Default: ash. Filename is tagged with it.",
    )
    parser.add_argument(
        "--from",
        dest="from_text",
        default=None,
        metavar="PATH",
        help="re-voice an existing brief .md instead of synthesizing a new one "
        "(skips the Claude call — only needs OPENAI_API_KEY). Great for A/B'ing voices.",
    )
    parser.add_argument(
        "--no-instructions",
        action="store_true",
        help="omit the TTS delivery instructions (plain, unsteered read) — to "
        "A/B whether the instructions help. Output tagged '-plain'.",
    )
    args = parser.parse_args()

    load_dotenv()  # pull keys from .env

    briefing = get_briefing(args.briefing)

    if args.from_text:
        # Re-derive audio from an already-written brief. Text is source of truth.
        text_path = Path(args.from_text)
        text = text_path.read_text(encoding="utf-8")
        print(f"Re-voicing existing brief: {text_path}")
    else:
        from core.synthesize import synthesize  # lazy: --from needs no Anthropic key

        items = FAKE_ITEMS
        period = (
            min(i.timestamp for i in items),
            max(i.timestamp for i in items),
        )
        print(f"Synthesizing '{briefing.name}' from {len(items)} fake items...")
        text = synthesize(briefing, items, period=period)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        BRIEFS_DIR.mkdir(exist_ok=True)
        text_path = BRIEFS_DIR / f"{briefing.name}-{stamp}.md"
        text_path.write_text(text, encoding="utf-8")
        print(f"\n--- BRIEF ---\n{text}\n-------------\n")
        print(f"Text written: {text_path}")

    want_audio = OutputMode.AUDIO in briefing.output and not args.no_audio
    if want_audio:
        from core.tts import INSTRUCTIONS, VOICE, synthesize_audio  # lazy: --no-audio needs no OpenAI key

        voice = args.voice or VOICE
        instructions = "" if args.no_instructions else INSTRUCTIONS
        ext = ".wav" if args.wav else ".mp3"
        # Tag the filename with voice (and '-plain' when unsteered) so A/B
        # comparisons don't overwrite each other.
        tag = f"{voice}-plain" if args.no_instructions else voice
        audio_path = text_path.with_name(f"{text_path.stem}-{tag}{ext}")
        steer = "no instructions" if args.no_instructions else "steered"
        print(f"Generating audio (voice: {voice}, {steer})...")
        synthesize_audio(text, audio_path, voice=voice, instructions=instructions)
        print(f"Audio written: {audio_path}")
        if args.wav:
            print(f"\nListen locally:  paplay '{audio_path}'")
        else:
            print(f"\nListen: copy '{audio_path}' to your phone "
                  "(no mp3 player on this box; use --wav for local paplay)")
    else:
        print("(audio skipped)")


if __name__ == "__main__":
    main()

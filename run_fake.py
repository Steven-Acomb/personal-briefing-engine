"""Step-2 runner: validate the consumption experience on FAKE data.

Pipeline (no real ingestion): fixtures -> synthesize (Claude) -> write text
brief -> TTS to mp3. Then actually read/listen to the output and iterate on the
synthesis_instruction. This is the cheapest place to tune the prompt.

Usage:
    python run_fake.py                 # text + audio for the daily-morning briefing
    python run_fake.py --no-audio      # skip TTS (only needs ANTHROPIC_API_KEY)
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
from core.synthesize import synthesize

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
    args = parser.parse_args()

    load_dotenv()  # pull keys from .env

    briefing = get_briefing(args.briefing)
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
        from core.tts import synthesize_audio  # imported lazily so --no-audio needs no OpenAI key

        audio_path = text_path.with_suffix(".wav" if args.wav else ".mp3")
        print("Generating audio...")
        synthesize_audio(text, audio_path)
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

"""Pipeline orchestration: run one briefing end to end.

    gather items -> synthesize (Claude) -> write text -> TTS (optional) -> deliver

Text is the source of truth; audio is derived. Everything is a file (no DB —
see ROADMAP). `dry_run=True` skips the billable Claude/TTS calls so the wiring
(scheduling, delivery, file layout) can be verified for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.delivery import deliver
from core.fixtures import FAKE_ITEMS
from core.models import Briefing, IngestedItem, OutputMode

BRIEFS_DIR = Path(__file__).resolve().parent.parent / "briefs"


@dataclass
class BriefResult:
    briefing_name: str
    text_path: Path
    audio_path: Path | None
    delivered: list[Path]
    dry_run: bool


def gather_items(briefing: Briefing) -> list[IngestedItem]:
    """Collect the messages this briefing should cover.

    SEAM for step 4: today this returns the hand-made fake batch. Real adapters
    (Discord/Telegram/RSS) will replace this, honoring each SourceConfig and the
    briefing's lookback window. Kept deliberately dumb for now.
    """
    return FAKE_ITEMS


def run_briefing(
    briefing: Briefing,
    *,
    audio: bool = True,
    dry_run: bool = False,
    briefs_dir: Path = BRIEFS_DIR,
) -> BriefResult:
    """Run one briefing to completion and deliver it. Returns a BriefResult."""
    items = gather_items(briefing)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    briefs_dir.mkdir(parents=True, exist_ok=True)
    text_path = briefs_dir / f"{briefing.name}-{stamp}.md"

    # --- text (source of truth) ---
    if dry_run:
        text = (
            f"# DRY RUN — {briefing.name} @ {stamp}\n\n"
            f"(no Claude call) would synthesize {len(items)} items from sources "
            f"{sorted({i.source for i in items})}."
        )
    else:
        from core.synthesize import synthesize  # lazy: dry runs need no API key

        period = (min(i.timestamp for i in items), max(i.timestamp for i in items))
        text = synthesize(briefing, items, period=period)
    text_path.write_text(text, encoding="utf-8")

    # --- audio (derived) ---
    audio_path: Path | None = None
    want_audio = audio and OutputMode.AUDIO in briefing.output
    if want_audio and not dry_run:
        from core.tts import synthesize_audio  # lazy

        audio_path = text_path.with_suffix(".mp3")
        # Default backend/voice per ROADMAP ISSUE-1 (echo-plain). Scheduled runs
        # use the reliable default, not the audition knobs.
        audio_path, _ = synthesize_audio(text, audio_path)

    # --- delivery ---
    delivered = deliver(briefing.name, text_path, audio_path, briefing.delivery)

    return BriefResult(
        briefing_name=briefing.name,
        text_path=text_path,
        audio_path=audio_path,
        delivered=delivered,
        dry_run=dry_run,
    )

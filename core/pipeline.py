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

from core.config import load_sources
from core.delivery import deliver
from core.models import Briefing, IngestedItem, OutputMode, Platform

BRIEFS_DIR = Path(__file__).resolve().parent.parent / "briefs"


@dataclass
class BriefResult:
    briefing_name: str
    text_path: Path | None
    audio_path: Path | None
    delivered: list[Path]
    dry_run: bool
    skipped: bool = False


def gather_items(briefing: Briefing) -> list[IngestedItem]:
    """Collect the messages this briefing should cover, from its real sources.

    Dispatches per source platform to the right adapter, honoring the briefing's
    lookback window and each SourceConfig's keyword filter. A source whose adapter
    isn't built yet (Telegram/RSS) or that errors is logged and skipped — one bad
    source must not kill the whole brief.
    """
    sources = load_sources()
    since = datetime.now(timezone.utc) - briefing.lookback
    items: list[IngestedItem] = []

    for sc in briefing.sources:
        src = sources.get(sc.source_id)
        if src is None:
            print(f"[gather] unknown source_id {sc.source_id!r}; skipping")
            continue
        try:
            if src.platform is Platform.DISCORD:
                from adapters import discord as discord_adapter  # lazy

                fetched = discord_adapter.fetch(src, since)
            else:
                print(
                    f"[gather] no adapter for {src.platform.value} yet "
                    f"({src.display_name}); skipping"
                )
                continue
        except Exception as e:  # noqa: BLE001 — one source shouldn't kill the run
            print(f"[gather] {src.display_name}: fetch failed ({e}); skipping")
            continue

        if sc.keyword_filter:  # keep only messages mentioning a keyword
            kws = [k.lower() for k in sc.keyword_filter]
            fetched = [it for it in fetched if any(k in it.content.lower() for k in kws)]

        print(f"[gather] {src.display_name}: {len(fetched)} item(s)")
        items += fetched

    return items


def run_briefing(
    briefing: Briefing,
    *,
    audio: bool = True,
    dry_run: bool = False,
    briefs_dir: Path = BRIEFS_DIR,
) -> BriefResult:
    """Run one briefing to completion and deliver it. Returns a BriefResult."""
    items = gather_items(briefing)

    if not items and not dry_run:
        print(f"[pipeline] {briefing.name}: no items gathered — skipping brief.")
        return BriefResult(briefing.name, None, None, [], dry_run=False, skipped=True)

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

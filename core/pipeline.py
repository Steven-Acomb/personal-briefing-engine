"""Pipeline orchestration: run one briefing end to end.

    gather items -> synthesize (Claude) -> write text -> TTS (optional) -> deliver

Text/audio are files (source of truth in briefs/); SQLite (core.store) holds the
brief history + per-source watermark. `dry_run=True` skips the billable
Claude/TTS calls AND leaves the watermark untouched, so the wiring can be
verified for free without "consuming" messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core import obs, store
from core.config import load_sources
from core.delivery import deliver
from core.models import Briefing, IngestedItem, OutputMode, Platform

BRIEFS_DIR = Path(__file__).resolve().parent.parent / "briefs"


@dataclass
class GatherResult:
    """What a gather produced: the pooled items, plus a human-readable reason for
    each source that *errored* (distinct from a source that simply had nothing).
    The errors drive the failure marker so a broken source can't silently empty
    a brief (ROADMAP ISSUE-3)."""

    items: list[IngestedItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class BriefResult:
    briefing_name: str
    text_path: Path | None
    audio_path: Path | None
    delivered: list[Path]
    dry_run: bool
    skipped: bool = False
    failed: bool = False  # a source errored — brief (if any) is incomplete


def gather_items(
    briefing: Briefing, *, advance_watermark: bool = True
) -> GatherResult:
    """Collect the messages this briefing should cover, from its real sources.

    Incremental via the per-source watermark: each source is fetched newer than
    max(now - lookback, last-covered) — so a run only pulls messages it hasn't
    already covered, but never reaches back further than the lookback window
    (bounds a big gap). Dispatches per platform, honors keyword filters, and
    skips a source whose adapter isn't built yet or that errors.

    `advance_watermark=False` (dry runs) reads the watermark but doesn't move it,
    so a free wiring check doesn't "consume" messages a real run should cover.
    """
    sources = load_sources()
    now = datetime.now(timezone.utc)
    floor = now - briefing.lookback
    items: list[IngestedItem] = []
    errors: list[str] = []

    for sc in briefing.sources:
        src = sources.get(sc.source_id)
        if src is None:
            # A configured source that isn't in sources.toml is a silent gap —
            # surface it as an error, not a quiet skip.
            msg = f"unknown source_id {sc.source_id!r} (not in sources.toml)"
            obs.tee(f"[gather] {msg}", level=logging.ERROR)
            errors.append(msg)
            continue
        label = src.display_name or src.id  # display_name may be auto-derived at fetch

        watermark = store.get_watermark(briefing.name, sc.source_id)
        since = max(floor, watermark) if watermark else floor

        try:
            if src.platform is Platform.DISCORD:
                from adapters import discord as discord_adapter  # lazy

                fetched = discord_adapter.fetch(src, since)
            else:
                # No adapter yet is an expected gap, not a failure — skip quietly.
                obs.tee(
                    f"[gather] no adapter for {src.platform.value} yet "
                    f"({label}); skipping"
                )
                continue
        except Exception as e:  # noqa: BLE001 — one source shouldn't kill the run
            # A real failure (bad/expired token, 403/404, network). Record it so
            # the run is flagged instead of degrading to a hollow brief.
            msg = f"{label}: fetch failed ({e})"
            obs.tee(f"[gather] {msg}", level=logging.ERROR)
            errors.append(msg)
            continue

        if watermark:  # strictly after last-covered — don't re-summarize the boundary msg
            fetched = [it for it in fetched if it.timestamp > watermark]

        if sc.keyword_filter:  # keep only messages mentioning a keyword
            kws = [k.lower() for k in sc.keyword_filter]
            fetched = [it for it in fetched if any(k in it.content.lower() for k in kws)]

        if advance_watermark:
            newest = max((it.timestamp for it in fetched), default=None)
            store.set_watermark(briefing.name, sc.source_id, newest)

        # the real (possibly auto-derived) label is on the fetched items
        shown = fetched[0].source if fetched else label
        obs.tee(f"[gather] {shown}: {len(fetched)} item(s) since {since:%m-%d %H:%M}")
        items += fetched

    return GatherResult(items=items, errors=errors)


def run_briefing(
    briefing: Briefing,
    *,
    audio: bool = True,
    dry_run: bool = False,
    briefs_dir: Path = BRIEFS_DIR,
) -> BriefResult:
    """Run one briefing to completion and deliver it. Returns a BriefResult."""
    # Dry runs must not advance the watermark (they'd "consume" messages).
    gathered = gather_items(briefing, advance_watermark=not dry_run)
    items, errors = gathered.items, gathered.errors

    # A source that ERRORED (vs. legitimately empty) must be loud — otherwise an
    # expired token silently produces a hollow brief (ROADMAP ISSUE-3). Dry runs
    # log the error via gather but don't drop a marker file (it's a wiring check).
    if errors and not dry_run:
        marker = obs.write_failure_marker(briefing.name, errors)
        obs.tee(
            f"[pipeline] {briefing.name}: {len(errors)} source(s) FAILED — see "
            f"{marker.name} + logs/briefing.log",
            level=logging.ERROR,
        )
    elif not dry_run:
        # Fully clean run — drop any stale marker from a prior failure, even if
        # this run happened to gather nothing (the failure is resolved).
        obs.clear_failure_marker(briefing.name)

    if not items and not dry_run:
        # No items + a failure is a FAILED run (marker already written above);
        # no items + no errors is a benign quiet window.
        if errors:
            obs.tee(
                f"[pipeline] {briefing.name}: no items and source failure(s) — "
                "no brief produced.",
                level=logging.ERROR,
            )
            return BriefResult(
                briefing.name, None, None, [], dry_run=False, skipped=True, failed=True
            )
        obs.tee(f"[pipeline] {briefing.name}: no items gathered — skipping brief.")
        return BriefResult(briefing.name, None, None, [], dry_run=False, skipped=True)

    generated_at = datetime.now(timezone.utc)
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
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
        # Default voice is OpenAI echo, plain (see ROADMAP ISSUE-1).
        audio_path = synthesize_audio(text, audio_path)

    # --- delivery (dry runs must not clobber the real 'latest' pointer) ---
    delivered = (
        [] if dry_run
        else deliver(briefing.name, text_path, audio_path, briefing.delivery)
    )

    # --- record in history (not for dry runs) ---
    if not dry_run:
        store.record_brief(
            briefing.name,
            period_start=min(i.timestamp for i in items),
            period_end=max(i.timestamp for i in items),
            generated_at=generated_at,
            text_path=text_path,
            audio_path=audio_path,
            status="partial" if errors else "delivered",
        )

    return BriefResult(
        briefing_name=briefing.name,
        text_path=text_path,
        audio_path=audio_path,
        delivered=delivered,
        dry_run=dry_run,
        failed=bool(errors),
    )

"""Load config/*.toml into the ontology dataclasses.

Resolves each Briefing's SourceConfig entries against the Source registry so
the rest of the pipeline works with objects, not raw dicts.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from core.models import (
    Briefing,
    DeliveryTarget,
    OutputMode,
    Platform,
    Source,
    SourceConfig,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Base URL the podcast feed + enclosure links are built from. Points at the small
# feed/audio server (podcast_server.py). Locally that's localhost; for phone
# access it's the Tailscale HTTPS hostname — set via `podcast_base_url` in
# briefings.toml, never hardcoded (see HUMAN_TODO §8).
DEFAULT_PODCAST_BASE_URL = "http://localhost:8766"


def load_podcast_base_url(path: Path | None = None) -> str:
    """Top-level `podcast_base_url` from briefings.toml, or the local default."""
    path = path or CONFIG_DIR / "briefings.toml"
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        return DEFAULT_PODCAST_BASE_URL
    return str(raw.get("podcast_base_url") or DEFAULT_PODCAST_BASE_URL).rstrip("/")


def load_sources(path: Path | None = None) -> dict[str, Source]:
    """Load sources.toml, keyed by source id."""
    path = path or CONFIG_DIR / "sources.toml"
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    sources: dict[str, Source] = {}
    for s in raw.get("source", []):
        src = Source(
            id=s["id"],
            platform=Platform(s["platform"]),
            identifier=s["identifier"],
            display_name=s.get("display_name"),  # optional — adapter derives if unset
            credentials_ref=s.get("credentials_ref"),
            context=s.get("context", ""),  # optional interpretive context for synthesis
        )
        sources[src.id] = src
    return sources


def load_briefings(path: Path | None = None) -> list[Briefing]:
    """Load briefings.toml into Briefing objects."""
    path = path or CONFIG_DIR / "briefings.toml"
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    briefings: list[Briefing] = []
    for b in raw.get("briefing", []):
        sources = [
            SourceConfig(
                source_id=sc["source_id"],
                keyword_filter=sc.get("keyword_filter", []),
            )
            for sc in b.get("source", [])
        ]
        briefings.append(
            Briefing(
                name=b["name"],
                schedule=b["schedule"],
                lookback_window=b["lookback_window"],
                synthesis_instruction=b["synthesis_instruction"].strip(),
                sources=sources,
                output=[OutputMode(o) for o in b.get("output", ["text"])],
                delivery=[DeliveryTarget(d) for d in b.get("delivery", ["local"])],
            )
        )
    return briefings


def get_briefing(name: str) -> Briefing:
    """Load a single briefing by name; raises KeyError if not found."""
    for b in load_briefings():
        if b.name == name:
            return b
    raise KeyError(f"No briefing named {name!r} in briefings.toml")

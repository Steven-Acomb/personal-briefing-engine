"""Ontology for the personal briefing engine.

Four concepts (Source, Briefing, SourceConfig, Brief) plus the normalized
ingestion item (IngestedItem) that is the seam between adapters and synthesis.
See HANDOFF.md § Ontology. Pure data models — no I/O lives here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class Platform(str, Enum):
    """Where a Source ingests from. Add members as adapters are built."""

    DISCORD = "discord"
    TELEGRAM = "telegram"
    ARXIV = "arxiv"
    RSS = "rss"
    HN = "hn"


class OutputMode(str, Enum):
    TEXT = "text"
    AUDIO = "audio"


class DeliveryTarget(str, Enum):
    LOCAL = "local"
    EMAIL = "email"


class BriefStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    DELIVERED = "delivered"


# --------------------------------------------------------------------------- #
# Configuration models (loaded from config/*.toml)
# --------------------------------------------------------------------------- #


@dataclass
class Source:
    """A specific place to ingest from.

    Granularity is deliberate: Discord is channel-level (a server's channels
    vary wildly in relevance), Telegram is chat-level.

    `credentials_ref` is the NAME of an env var holding the secret, never the
    secret itself — see HANDOFF.md § Security.
    """

    id: str
    platform: Platform
    identifier: str  # channel_id / chat_id / feed_url / query
    display_name: str  # human label used in briefs, e.g. "telegram/chip-design"
    credentials_ref: str | None = None


@dataclass
class SourceConfig:
    """Join between a Source and a Briefing: per-briefing filtering of a source.

    One channel can feed multiple briefings; each briefing can filter it
    differently.
    """

    source_id: str
    channel_filter: list[str] = field(default_factory=list)  # optional sub-channels
    keyword_filter: list[str] = field(default_factory=list)


@dataclass
class Briefing:
    """A named, scheduled output definition. Many-to-many with Sources.

    `synthesis_instruction` is first-class — it's what to focus on, what to
    ignore, tone, and length. Expect heavy iteration here; it's where the real
    value (and cost) of tuning lives.
    """

    name: str
    schedule: str  # cron expr or named cadence (daily_morning, weekly_sunday)
    lookback_window: str  # "24h" | "7d" | ...
    synthesis_instruction: str
    sources: list[SourceConfig] = field(default_factory=list)
    output: list[OutputMode] = field(default_factory=lambda: [OutputMode.TEXT])
    delivery: list[DeliveryTarget] = field(default_factory=lambda: [DeliveryTarget.LOCAL])

    @property
    def lookback(self) -> timedelta:
        """Parse `lookback_window` ("24h", "7d", "90m") into a timedelta."""
        return parse_window(self.lookback_window)


# --------------------------------------------------------------------------- #
# Runtime models
# --------------------------------------------------------------------------- #


@dataclass
class IngestedItem:
    """The adapter seam: every adapter normalizes its platform's messages into
    this shape. The synthesizer only ever sees IngestedItems — never
    platform-specific structures.
    """

    source: str  # display_name of the originating Source
    content: str
    timestamp: datetime
    topic_tags: list[str] = field(default_factory=list)  # optional; may be set at synthesis
    meta: dict = field(default_factory=dict)  # {author, link_back, ...} for citations/links


@dataclass
class Brief:
    """One generated instance of a Briefing.

    `text_content` is the source of truth; `audio_path` is derived from it.
    """

    briefing_id: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    text_content: str  # markdown / TTS script — source of truth
    audio_path: str | None = None  # derived
    status: BriefStatus = BriefStatus.PENDING


# --------------------------------------------------------------------------- #
# Helpers (pure logic, no I/O)
# --------------------------------------------------------------------------- #

_WINDOW_UNITS = {
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}


def parse_window(window: str) -> timedelta:
    """Turn a lookback window string like "24h", "7d", "90m", "2w" into a
    timedelta. Raises ValueError on anything malformed.
    """
    match = re.fullmatch(r"\s*(\d+)\s*([mhdw])\s*", window.lower())
    if not match:
        raise ValueError(
            f"Bad lookback window {window!r}; expected e.g. '24h', '7d', '90m', '2w'"
        )
    count, unit = int(match.group(1)), match.group(2)
    return count * _WINDOW_UNITS[unit]

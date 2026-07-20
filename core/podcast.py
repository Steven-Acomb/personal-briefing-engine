"""Podcast feed generation — turn a briefing's recorded briefs into an RSS feed
an iOS podcast app can subscribe to.

**One feed per briefing** (each briefing is its own show), written to
`briefs/feeds/<briefing>.xml`. Built from the SQLite brief records (`core.store`),
not by globbing the folder, so the feed reflects real run history.

**Audio-only:** a podcast feed can only carry episodes with an enclosure, so
briefs without an `audio_path` (or whose mp3 is missing on disk) are skipped.

**GUIDs are the brief's stable SQLite row id with `isPermaLink=false`** so a
podcast app never duplicates an episode when the feed is regenerated.

Enclosure/feed URLs are built from a configurable base URL (`podcast_base_url` in
config/briefings.toml) pointing at `podcast_server.py`. For phone access that's
the Tailscale HTTPS hostname (HUMAN_TODO §8) — never hardcoded here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core import store
from core.config import load_podcast_base_url

ROOT = Path(__file__).resolve().parent.parent
BRIEFS_DIR = ROOT / "briefs"
FEEDS_DIR = BRIEFS_DIR / "feeds"
MAX_EPISODES = 20


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _episode_title(briefing_name: str, row) -> str:
    """e.g. 'group-chat-digest — Jul 19' (period end, falling back to generated)."""
    when = _dt(row["period_end"]) or _dt(row["generated_at"])
    # build the day without %-d / %#d (platform-specific) so it works on Windows
    return f"{briefing_name} — {when:%b} {when.day}" if when else briefing_name


def _description(row) -> str:
    """The brief's text is the source of truth — putting it in the episode notes
    gives read-or-listen in the podcast app."""
    path = row["text_path"]
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return "(brief text unavailable)"


def build_feed(
    briefing_name: str,
    *,
    base_url: str | None = None,
    briefs_dir: Path = BRIEFS_DIR,
    limit: int = MAX_EPISODES,
    db_path: Path | None = None,
) -> bytes:
    """Render this briefing's podcast RSS as bytes."""
    from feedgen.feed import FeedGenerator

    base = (base_url or load_podcast_base_url()).rstrip("/")
    kwargs = {"db_path": db_path} if db_path else {}
    rows = store.recent_briefs_with_audio(briefing_name, limit=limit, **kwargs)

    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title(briefing_name)
    fg.description(f"Personal briefing: {briefing_name}")
    fg.link(href=base, rel="alternate")  # RSS <link>
    fg.link(href=f"{base}/feed/{briefing_name}.xml", rel="self")
    fg.language("en")
    fg.podcast.itunes_author("Personal Briefing Engine")
    fg.podcast.itunes_block(True)  # private feed — keep it out of directories

    # feedgen prepends entries, so add oldest-first to end up newest-first.
    for row in reversed(rows):
        audio = Path(row["audio_path"])
        if not audio.is_absolute():
            audio = briefs_dir / audio.name
        if not audio.exists():
            continue  # enclosure must be servable
        fe = fg.add_entry()
        fe.guid(f"brief-{row['id']}", permalink=False)  # stable: never duplicates
        fe.title(_episode_title(briefing_name, row))
        fe.description(_description(row))
        published = _dt(row["generated_at"])
        if published:
            fe.published(published)
        fe.enclosure(f"{base}/audio/{audio.name}", str(audio.stat().st_size), "audio/mpeg")

    return fg.rss_str(pretty=True)


def write_feed(
    briefing_name: str,
    *,
    base_url: str | None = None,
    feeds_dir: Path = FEEDS_DIR,
    briefs_dir: Path = BRIEFS_DIR,
    db_path: Path | None = None,
) -> Path:
    """Regenerate and write `<feeds_dir>/<briefing>.xml`. Returns the path."""
    xml = build_feed(
        briefing_name, base_url=base_url, briefs_dir=briefs_dir, db_path=db_path
    )
    feeds_dir.mkdir(parents=True, exist_ok=True)
    out = feeds_dir / f"{briefing_name}.xml"
    out.write_bytes(xml)
    return out

"""RSS/Atom adapter — read recent feed entries into normalized IngestedItems.

Generic and public: one adapter over feedparser covers blogs, Substacks (append
`/feed`), trade press, podcasts, per-channel YouTube, Mastodon, Lobsters, and more
— all at once, all read-only, no auth, no cost.

Feed entries are INDEPENDENT items (not conversation), so a briefing that leans on
feeds should use `SourceConfig.keyword_filter` to pre-trim volume before synthesis
(the opposite of chat sources — see ROADMAP § Adapter roadmap). The fetch is HTTP
via requests (timeout + a real UA), then feedparser parses the bytes.

Standalone test (no auth, no cost):

    python -m adapters.rss <feed_url> --hours 48
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import feedparser
import requests

from core.models import IngestedItem, Platform, Source

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_MAX_CHARS = 2000  # cap each entry so full-article feeds don't bloat the prompt
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    """Feed summaries are usually HTML; the synthesizer/TTS want plain text."""
    s = _TAG_RE.sub(" ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _entry_time(entry) -> datetime | None:
    """Entry timestamp as tz-aware UTC (feedparser normalizes to UTC), or None."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _entry_text(entry) -> str:
    title = _strip_html(entry.get("title", ""))
    body = ""
    if entry.get("content"):  # full content when present, else the summary
        body = entry["content"][0].get("value", "")
    body = _strip_html(body or entry.get("summary", ""))
    text = f"{title}\n{body}".strip() if (title and body) else (title or body)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS].rstrip() + "…"
    return text


def fetch(source: Source, since: datetime) -> list[IngestedItem]:
    """Fetch feed entries from `source`'s URL published after `since` (tz-aware
    UTC). Returns normalized IngestedItems in chronological order. Entries without
    a parseable date are skipped (can't be placed in the window)."""
    if since.tzinfo is None:
        raise ValueError("`since` must be timezone-aware (UTC).")

    try:
        resp = requests.get(
            source.identifier, headers={"User-Agent": USER_AGENT}, timeout=20
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"RSS {source.identifier}: fetch failed ({e}).") from e

    parsed = feedparser.parse(resp.content)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        raise RuntimeError(
            f"RSS {source.identifier}: could not parse feed "
            f"({getattr(parsed, 'bozo_exception', 'unknown error')})."
        )

    feed_title = parsed.feed.get("title") if getattr(parsed, "feed", None) else None
    label = source.display_name or f"rss/{feed_title or source.identifier}"

    items: list[IngestedItem] = []
    for entry in parsed.entries:
        ts = _entry_time(entry)
        if ts is None or ts < since:
            continue
        text = _entry_text(entry)
        if not text:
            continue
        meta = {"author": entry.get("author") or feed_title or "unknown"}
        if entry.get("link"):
            meta["link_back"] = entry["link"]
        if entry.get("id"):
            meta["entry_id"] = entry["id"]
        items.append(IngestedItem(source=label, content=text, timestamp=ts, meta=meta))

    items.sort(key=lambda it: it.timestamp)  # chronological
    return items


# --------------------------------------------------------------------------- #
# Standalone test harness — validate a feed (read-only, no auth, no cost).
# --------------------------------------------------------------------------- #

def _main() -> None:
    import argparse
    import sys
    from datetime import timedelta

    try:  # non-ASCII entry titles vs. a Windows cp1252 console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="Fetch recent RSS/Atom entries.")
    parser.add_argument("feed_url")
    parser.add_argument("--hours", type=float, default=48.0)
    parser.add_argument("--name", default=None, help="display_name override")
    args = parser.parse_args()

    source = Source(
        id="cli-test", platform=Platform.RSS, identifier=args.feed_url,
        display_name=args.name,
    )
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    items = fetch(source, since)
    label = items[0].source if items else (args.name or args.feed_url)
    print(f"[{label}] fetched {len(items)} entr{'y' if len(items)==1 else 'ies'} "
          f"from the last {args.hours}h.\n")
    for it in items:
        snippet = it.content.replace("\n", " ")
        if len(snippet) > 100:
            snippet = snippet[:100] + "…"
        print(f"[{it.timestamp:%m-%d %H:%M}] {it.meta['author']}: {snippet}")


if __name__ == "__main__":
    _main()

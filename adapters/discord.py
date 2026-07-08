"""Discord adapter — read recent channel messages into normalized IngestedItems.

Approach: plain REST history pulls with the owner's **user token** (reads what
the account can already see). No gateway/websocket, no self-bot client — a
briefing only needs recent history, and periodic REST reads are the simplest and
lowest-footprint way to get it.

SECURITY (HANDOFF § Security): the user token is full account access. It is read
from an env var named by `Source.credentials_ref` (default DISCORD_USER_TOKEN),
never hard-coded, never logged, never placed in an IngestedItem or brief.

Standalone test (validate ingestion before wiring into the pipeline):

    python -m adapters.discord <channel_id> --hours 24
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import requests

from core.models import IngestedItem, Platform, Source

API = "https://discord.com/api/v10"
# Realistic UA — a user token paired with a bot-ish UA is the easy tell.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_MAX_PAGES = 10          # 10 * 100 = up to 1000 messages per fetch
_PAGE_DELAY_S = 0.6      # be gentle between paged requests


def _token(source: Source) -> str:
    ref = source.credentials_ref or "DISCORD_USER_TOKEN"
    token = os.getenv(ref)
    if not token:
        raise RuntimeError(
            f"Missing Discord user token: env var {ref!r} is not set (see .env)."
        )
    return token


def _label(source: Source, session: requests.Session, headers: dict) -> str:
    """The label used in briefs. Uses source.display_name if set; otherwise
    derives it from the channel name so a source needs only an identifier."""
    if source.display_name:
        return source.display_name
    try:
        r = session.get(
            f"{API}/channels/{source.identifier}", headers=headers, timeout=20
        )
        if r.ok:
            name = (r.json() or {}).get("name")
            if name:
                return f"discord/{name}"
    except requests.RequestException:
        pass
    return f"discord/{source.identifier}"  # fallback if the channel lookup fails


def fetch(
    source: Source,
    since: datetime,
    *,
    session: requests.Session | None = None,
    max_pages: int = _MAX_PAGES,
) -> list[IngestedItem]:
    """Fetch messages in `source`'s channel newer than `since` (tz-aware, UTC).

    Returns normalized IngestedItems in chronological order. Skips empty-content
    messages (attachment/embed-only) for v0.
    """
    if since.tzinfo is None:
        raise ValueError("`since` must be timezone-aware (UTC).")

    token = _token(source)
    sess = session or requests.Session()
    headers = {"Authorization": token, "User-Agent": USER_AGENT}
    label = _label(source, sess, headers)  # display_name, or derived from the channel
    url = f"{API}/channels/{source.identifier}/messages"

    items: list[IngestedItem] = []
    before: str | None = None

    for page in range(max_pages):
        params: dict[str, object] = {"limit": 100}
        if before:
            params["before"] = before

        resp = sess.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code == 401:
            raise RuntimeError("Discord 401: user token invalid or expired.")
        if resp.status_code == 403:
            raise RuntimeError(
                f"Discord 403: no access to channel {source.identifier} "
                "(wrong id, or the account can't see it)."
            )
        if resp.status_code == 404:
            raise RuntimeError(
                f"Discord 404: channel {source.identifier} not found. Usually this "
                "means you copied a SERVER id, not a channel id — or the id is a "
                "category / voice channel (no messages). Tip: open the channel in "
                "a browser; the URL is .../channels/<server_id>/<channel_id> — use "
                "the LAST number."
            )
        if resp.status_code == 429:
            retry = resp.json().get("retry_after", 5)
            raise RuntimeError(f"Discord 429 rate-limited; retry after {retry}s.")
        resp.raise_for_status()

        batch = resp.json()  # newest-first
        if not batch:
            break

        reached_cutoff = False
        for m in batch:
            ts = datetime.fromisoformat(m["timestamp"]).astimezone(timezone.utc)
            if ts < since:
                reached_cutoff = True
                continue
            content = (m.get("content") or "").strip()
            if not content:
                continue  # attachment/embed-only — skip for v0
            author = m.get("author") or {}
            items.append(
                IngestedItem(
                    source=label,
                    content=content,
                    timestamp=ts,
                    meta={
                        "author": author.get("global_name")
                        or author.get("username")
                        or "unknown",
                        "message_id": m["id"],
                        "link_back": (
                            f"https://discord.com/channels/{source.identifier}/{m['id']}"
                        ),
                    },
                )
            )

        before = batch[-1]["id"]
        if reached_cutoff or len(batch) < 100:
            break
        time.sleep(_PAGE_DELAY_S)

    items.reverse()  # chronological
    return items


# --------------------------------------------------------------------------- #
# Standalone test harness — validate real ingestion before pipeline wiring.
# --------------------------------------------------------------------------- #

def _main() -> None:
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="Fetch recent Discord messages.")
    parser.add_argument("channel_id")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument(
        "--name", default=None, help="display_name override (default: auto-derive)"
    )
    args = parser.parse_args()

    source = Source(
        id="cli-test",
        platform=Platform.DISCORD,
        identifier=args.channel_id,
        display_name=args.name,  # None -> derived from the channel
        credentials_ref="DISCORD_USER_TOKEN",
    )
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    items = fetch(source, since)
    print(f"Fetched {len(items)} message(s) from the last {args.hours}h.\n")
    for it in items:
        snippet = it.content.replace("\n", " ")
        if len(snippet) > 100:
            snippet = snippet[:100] + "…"
        print(f"[{it.timestamp:%m-%d %H:%M}] {it.meta['author']}: {snippet}")


if __name__ == "__main__":
    _main()

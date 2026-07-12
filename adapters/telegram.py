"""Telegram adapter — read recent messages from a chat into normalized IngestedItems.

Uses Telethon (MTProto) with the owner's OWN account: it reads the chats the
account is already in. Auth is API id/hash + a login-created `.session` file (NOT
a bot token), so it sees normal user chats. Like the Discord adapter, this is
account-level access to a personal account — see HANDOFF § Security. The
`.session` file is a live auth artifact and is gitignored.

Setup (one-time, interactive — see HUMAN_TODO.md §7):

    python -m adapters.telegram login          # phone + code -> creates the session
    python -m adapters.telegram list           # your chats: id / title / @username
    python -m adapters.telegram fetch <chat> --hours 24   # read-only validation

The pipeline only ever calls `fetch()` (a sync wrapper over the async client), so
the adapter seam matches Discord's. In a scheduled run an unauthorized/expired
session RAISES (surfacing via the FAILED marker) rather than prompting.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.models import IngestedItem, Platform, Source

_ROOT = Path(__file__).resolve().parent.parent
_MAX_MESSAGES = 3000  # bound a single fetch (newest-first; stops at `since` anyway)


def _creds() -> tuple[int, str, str]:
    """(api_id, api_hash, session_path) from env. Raises with guidance if unset."""
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session = os.getenv("TELEGRAM_SESSION") or "briefing"
    if not api_id or not api_hash:
        raise RuntimeError(
            "Missing Telegram credentials: set TELEGRAM_API_ID and TELEGRAM_API_HASH "
            "in .env (from https://my.telegram.org — see HUMAN_TODO.md §7)."
        )
    try:
        api_id_int = int(api_id)
    except ValueError as e:
        raise RuntimeError("TELEGRAM_API_ID must be the integer from my.telegram.org.") from e
    # absolute session path so it resolves the same from the CLI or the scheduled task
    return api_id_int, api_hash, str(_ROOT / session)


def _client():
    from telethon import TelegramClient  # lazy: only imported when telegram is used

    api_id, api_hash, session_path = _creds()
    return TelegramClient(session_path, api_id, api_hash)


def _peer(identifier: str):
    """A chat id (int) or a @username / username (str) that Telethon can resolve."""
    s = identifier.strip()
    if s.startswith("@"):
        return s
    try:
        return int(s)
    except ValueError:
        return s


def _sender_name(msg) -> str:
    s = getattr(msg, "sender", None)
    if s is None:
        return "unknown"
    return (
        getattr(s, "first_name", None)
        or getattr(s, "title", None)
        or getattr(s, "username", None)
        or "unknown"
    )


async def _fetch_async(source: Source, since: datetime) -> list[IngestedItem]:
    from telethon.errors import RPCError

    client = _client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Telegram session not authorized — run "
                "`python -m adapters.telegram login` (see HUMAN_TODO.md §7)."
            )
        try:
            entity = await client.get_entity(_peer(source.identifier))
        except (ValueError, TypeError, RPCError) as e:
            raise RuntimeError(
                f"Telegram: could not resolve chat {source.identifier!r} ({e}). "
                "Prefer @username if it has one; otherwise run "
                "`python -m adapters.telegram list` to find the id."
            ) from e

        label = source.display_name or f"telegram/{getattr(entity, 'title', source.identifier)}"
        username = getattr(entity, "username", None)

        items: list[IngestedItem] = []
        seen = 0
        async for msg in client.iter_messages(entity):  # newest-first
            seen += 1
            if seen > _MAX_MESSAGES:
                break
            ts = msg.date.astimezone(timezone.utc)
            if ts < since:
                break
            text = (msg.message or "").strip()
            if not text:
                continue  # media/service-only — skip for v0 (matches Discord)
            meta = {"author": _sender_name(msg), "message_id": msg.id}
            if username:
                meta["link_back"] = f"https://t.me/{username}/{msg.id}"
            items.append(IngestedItem(source=label, content=text, timestamp=ts, meta=meta))

        items.reverse()  # chronological
        return items
    finally:
        await client.disconnect()


def fetch(source: Source, since: datetime) -> list[IngestedItem]:
    """Fetch messages from `source`'s Telegram chat newer than `since` (tz-aware
    UTC). Sync wrapper over the async Telethon client, matching the adapter seam."""
    if since.tzinfo is None:
        raise ValueError("`since` must be timezone-aware (UTC).")
    return asyncio.run(_fetch_async(source, since))


# --------------------------------------------------------------------------- #
# CLI: login (one-time interactive) / list (find chat ids) / fetch (validate)
# --------------------------------------------------------------------------- #


async def _login() -> None:
    client = _client()
    # start() prompts for phone, the login code, and a 2FA password if set.
    await client.start()
    me = await client.get_me()
    uname = getattr(me, "username", None)
    print(f"Logged in as {getattr(me, 'first_name', '?')}"
          f"{f' (@{uname})' if uname else ''}. Session saved.")
    await client.disconnect()


async def _list_dialogs() -> None:
    client = _client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit("Not authorized — run: python -m adapters.telegram login")
        print(f"{'chat_id':>16}  {'username':22}  title")
        print(f"{'-'*16}  {'-'*22}  {'-'*20}")
        async for d in client.iter_dialogs():
            uname = f"@{d.entity.username}" if getattr(d.entity, "username", None) else "-"
            print(f"{d.id:>16}  {uname:22}  {d.name}")
    finally:
        await client.disconnect()


def _main() -> None:
    import argparse
    import sys

    from dotenv import load_dotenv

    # avoid Windows cp1252 console crashes on non-ASCII chat titles / messages
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — best-effort; older stdout without reconfigure
        pass

    load_dotenv()
    parser = argparse.ArgumentParser(description="Telegram adapter utilities.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="interactive login -> creates the .session file")
    sub.add_parser("list", help="list your chats (id / title / @username)")
    p_fetch = sub.add_parser("fetch", help="read recent messages from a chat (read-only)")
    p_fetch.add_argument("chat", help="chat id or @username")
    p_fetch.add_argument("--hours", type=float, default=24.0)
    args = parser.parse_args()

    if args.cmd == "login":
        asyncio.run(_login())
    elif args.cmd == "list":
        asyncio.run(_list_dialogs())
    elif args.cmd == "fetch":
        source = Source(id="cli-test", platform=Platform.TELEGRAM, identifier=args.chat)
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

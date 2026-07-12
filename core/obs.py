"""Observability: a durable run log + loud failure markers (ROADMAP ISSUE-3).

The problem this solves: a scheduled/headless run prints to stdout, which is
lost when detached — and a source error (e.g. an **expired Discord token**) is
caught by `gather_items` and the source skipped, so the run degrades to an
empty/thin brief **silently**. Nothing tells you a source broke.

This module adds two things, both OS-independent:

- **A rotating log file** (`logs/briefing.log`) that every run tees to, so a
  detached run leaves a trail even when nobody is watching stdout.
- **A failure marker** (`briefs/FAILED-<briefing>.txt`) written when a source
  *errors* (as opposed to legitimately having nothing), and cleared on the next
  fully-clean run — so an expired token surfaces as a file you'll notice instead
  of a quietly hollow digest.

Interactive UX is unchanged: `tee()` still prints to the console; it just also
writes to the log file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
BRIEFS_DIR = ROOT / "briefs"

_configured = False


def _configure() -> None:
    """Attach a rotating file handler to the 'briefing' logger, once. Console
    output stays on the existing print() calls, so this is file-only (no
    duplicate console lines, no changed interactive formatting)."""
    global _configured
    if _configured:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_DIR / "briefing.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger("briefing")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False  # don't double-emit through the root logger
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """A child of the 'briefing' logger, with the file handler ensured."""
    _configure()
    return logging.getLogger(f"briefing.{name}")


def tee(msg: str, *, level: int = logging.INFO, logger: str = "pipeline") -> None:
    """Print for the interactive console AND record to the rotating log file."""
    print(msg)
    get_logger(logger).log(level, msg)


def write_failure_marker(
    briefing_name: str, errors: list[str], *, briefs_dir: Path = BRIEFS_DIR
) -> Path:
    """Write a loud, human-readable marker naming which sources failed and why.
    Overwrites any prior marker so it always reflects the latest run."""
    briefs_dir.mkdir(parents=True, exist_ok=True)
    path = briefs_dir / f"FAILED-{briefing_name}.txt"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = (
        f"Briefing {briefing_name!r} had source failure(s) at {stamp} UTC.\n"
        f"The brief below (if any) is INCOMPLETE — a source was skipped.\n\n"
        + "\n".join(f"  - {e}" for e in errors)
        + "\n\nCommon cause: an expired DISCORD_USER_TOKEN — re-copy it into .env "
        "(see HUMAN_TODO.md §6). Full run log: logs/briefing.log\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def clear_failure_marker(
    briefing_name: str, *, briefs_dir: Path = BRIEFS_DIR
) -> None:
    """Remove a stale marker after a fully-clean run (no source errors)."""
    path = briefs_dir / f"FAILED-{briefing_name}.txt"
    if path.exists():
        path.unlink()

"""SQLite store for brief history + per-source run-state.

Hybrid model: the brief text/audio stay as readable files (source of truth in
briefs/); this DB holds the *metadata index* and the *run-state* — atomically,
with real queries. `sqlite3` is stdlib, so no dependency.

Two tables:
  brief         — one row per generated brief (history/index)
  source_state  — the "how far have I covered this source, for this briefing"
                  watermark, keyed by (briefing_id, source_id)

Timestamps are stored as ISO-8601 UTC strings.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "briefs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS brief (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    briefing_id   TEXT NOT NULL,
    period_start  TEXT,
    period_end    TEXT,
    generated_at  TEXT NOT NULL,
    text_path     TEXT,
    audio_path    TEXT,
    status        TEXT NOT NULL DEFAULT 'ready'
);
CREATE TABLE IF NOT EXISTS source_state (
    briefing_id     TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    last_covered_ts TEXT,
    last_run_at     TEXT,
    PRIMARY KEY (briefing_id, source_id)
);
"""


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def _parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


@contextmanager
def _connect(db_path: Path = DB_PATH):
    """Open a connection, ensure schema (idempotent), commit on success, close."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the DB + tables if they don't exist."""
    with _connect(db_path):
        pass


# --------------------------------------------------------------------------- #
# Brief history
# --------------------------------------------------------------------------- #


def record_brief(
    briefing_id: str,
    *,
    period_start: datetime | None,
    period_end: datetime | None,
    generated_at: datetime,
    text_path: Path | None,
    audio_path: Path | None,
    status: str = "delivered",
    db_path: Path = DB_PATH,
) -> int:
    """Insert a brief row; returns its id."""
    with _connect(db_path) as c:
        cur = c.execute(
            """INSERT INTO brief
               (briefing_id, period_start, period_end, generated_at,
                text_path, audio_path, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                briefing_id,
                _iso(period_start),
                _iso(period_end),
                _iso(generated_at),
                str(text_path) if text_path else None,
                str(audio_path) if audio_path else None,
                status,
            ),
        )
        return cur.lastrowid


def set_status(brief_id: int, status: str, db_path: Path = DB_PATH) -> None:
    with _connect(db_path) as c:
        c.execute("UPDATE brief SET status = ? WHERE id = ?", (status, brief_id))


def recent_briefs_with_audio(
    briefing_id: str, limit: int = 20, db_path: Path = DB_PATH
) -> list[sqlite3.Row]:
    """Most-recent briefs for a briefing that actually have audio — the source of
    truth for a podcast feed, which is audio-only (text-only briefs are skipped)."""
    with _connect(db_path) as c:
        return c.execute(
            "SELECT * FROM brief WHERE briefing_id = ? "
            "AND audio_path IS NOT NULL AND audio_path != '' "
            "ORDER BY generated_at DESC LIMIT ?",
            (briefing_id, limit),
        ).fetchall()


def recent_briefs(
    briefing_id: str | None = None, limit: int = 20, db_path: Path = DB_PATH
) -> list[sqlite3.Row]:
    """Most-recent briefs, optionally filtered to one briefing."""
    with _connect(db_path) as c:
        if briefing_id:
            rows = c.execute(
                "SELECT * FROM brief WHERE briefing_id = ? "
                "ORDER BY generated_at DESC LIMIT ?",
                (briefing_id, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM brief ORDER BY generated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return rows


# --------------------------------------------------------------------------- #
# Run-state (watermark): how far have we covered a source, for a briefing
# --------------------------------------------------------------------------- #


def get_watermark(
    briefing_id: str, source_id: str, db_path: Path = DB_PATH
) -> datetime | None:
    """The timestamp of the newest message already covered for (briefing, source),
    or None if never run."""
    with _connect(db_path) as c:
        row = c.execute(
            "SELECT last_covered_ts FROM source_state "
            "WHERE briefing_id = ? AND source_id = ?",
            (briefing_id, source_id),
        ).fetchone()
    return _parse(row["last_covered_ts"]) if row else None


def set_watermark(
    briefing_id: str,
    source_id: str,
    covered_ts: datetime | None,
    run_at: datetime | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Advance the watermark to `covered_ts` (never moves backward) and stamp the
    run time. Pass covered_ts=None to record a run that covered nothing (bumps
    last_run_at, leaves the watermark where it was)."""
    run_at = run_at or datetime.now(timezone.utc)
    with _connect(db_path) as c:
        row = c.execute(
            "SELECT last_covered_ts FROM source_state "
            "WHERE briefing_id = ? AND source_id = ?",
            (briefing_id, source_id),
        ).fetchone()
        existing = _parse(row["last_covered_ts"]) if row else None

        newest = existing
        if covered_ts is not None and (existing is None or covered_ts > existing):
            newest = covered_ts

        c.execute(
            """INSERT INTO source_state
                 (briefing_id, source_id, last_covered_ts, last_run_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(briefing_id, source_id) DO UPDATE SET
                 last_covered_ts = excluded.last_covered_ts,
                 last_run_at     = excluded.last_run_at""",
            (briefing_id, source_id, _iso(newest), _iso(run_at)),
        )

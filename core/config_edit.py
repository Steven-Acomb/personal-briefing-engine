"""Format-preserving WRITE path for config/*.toml (used by the web UI).

The pipeline READS config via `core.config` (tomllib -> dataclasses); that path
is untouched and stays the single reader. This module is the writer:

- Round-trips the TOML with **tomlkit**, so comments and formatting survive. On
  update it mutates fields in place (preserves per-entry comments); on create it
  appends a fresh table; on delete it removes one.
- Every write is **atomic + validated**: the mutated document is serialized to a
  temp file, parsed back through the real loader (`core.config`) plus cron /
  lookback checks, and only `os.replace`d into place if it loads. So the UI can
  never write something the pipeline can't read, and a concurrent reader (a cron
  `scheduler.py once`) sees old-or-new, never a partial or broken file.

Fidelity caveat (documented, accepted): inline comments attached to a *field you
change through the UI* may not survive; file-level comments and every untouched
entry's comments do.
"""

from __future__ import annotations

import os
from pathlib import Path

import tomlkit
from tomlkit import TOMLDocument

from core import config as cfg
from core.models import DeliveryTarget, OutputMode, Platform, parse_window

try:
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # pragma: no cover
    CronTrigger = None  # cron validation degrades to "accept" if APScheduler absent

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
SOURCES_PATH = CONFIG_DIR / "sources.toml"
BRIEFINGS_PATH = CONFIG_DIR / "briefings.toml"

VALID_PLATFORMS = [p.value for p in Platform]
VALID_OUTPUTS = [o.value for o in OutputMode]
VALID_DELIVERY = [d.value for d in DeliveryTarget]


class ConfigError(ValueError):
    """A validation failure meant to be surfaced back to the form."""


# --------------------------------------------------------------------------- #
# tomlkit helpers
# --------------------------------------------------------------------------- #


def _load_doc(path: Path) -> TOMLDocument:
    if path.exists():
        return tomlkit.parse(path.read_text(encoding="utf-8"))
    return tomlkit.document()


def _aot(doc: TOMLDocument, key: str):
    """Return the array-of-tables at `key`, creating it if absent."""
    arr = doc.get(key)
    if arr is None:
        arr = tomlkit.aot()
        doc[key] = arr
    return arr


def _find_index(arr, key: str, value: str) -> int | None:
    for i, tbl in enumerate(arr):
        if tbl.get(key) == value:
            return i
    return None


def _str_value(text: str):
    """A TOML string item: multiline triple-quoted if it spans lines (a basic
    string can't hold a literal newline), otherwise a plain quoted string."""
    if "\n" in text:
        return tomlkit.string("\n" + text.strip("\n") + "\n", multiline=True)
    return text


def _atomic_write(path: Path, doc: TOMLDocument, validate) -> None:
    """Serialize `doc` to a temp file, run `validate(temp_path)` (raises to
    reject), then atomically replace `path`. The original is untouched on error."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(tomlkit.dumps(doc), encoding="utf-8")
    try:
        validate(tmp)
    except ConfigError:
        tmp.unlink(missing_ok=True)
        raise
    except Exception as e:  # loader/parse failure on our own output
        tmp.unlink(missing_ok=True)
        raise ConfigError(f"Refusing to save — result would not load: {e}") from e
    os.replace(tmp, path)  # atomic on the same volume (incl. Windows)


# --------------------------------------------------------------------------- #
# Validators (run against the SERIALIZED temp file, the real safety net)
# --------------------------------------------------------------------------- #


def _validate_sources_file(path: Path) -> None:
    cfg.load_sources(path)  # exercises Platform enum etc.; raises on bad input


def _validate_briefings_file(path: Path) -> None:
    briefings = cfg.load_briefings(path)  # OutputMode/DeliveryTarget/parse fields
    for b in briefings:
        parse_window(b.lookback_window)  # raises ValueError on malformed window
        if CronTrigger is not None:
            CronTrigger.from_crontab(b.schedule)  # raises on bad cron


# --------------------------------------------------------------------------- #
# Field validation (run on form input, before we touch the document)
# --------------------------------------------------------------------------- #


def _req(fields: dict, name: str) -> str:
    val = (fields.get(name) or "").strip()
    if not val:
        raise ConfigError(f"{name} is required.")
    return val


# --------------------------------------------------------------------------- #
# Sources
# --------------------------------------------------------------------------- #


def upsert_source(fields: dict, *, original_id: str | None = None) -> None:
    """Create (original_id=None) or update a [[source]] entry, then atomic-write.

    `fields`: id, platform, identifier, display_name (optional), credentials_ref.
    """
    sid = _req(fields, "id")
    platform = _req(fields, "platform")
    identifier = _req(fields, "identifier")
    if platform not in VALID_PLATFORMS:
        raise ConfigError(f"platform must be one of {VALID_PLATFORMS}, got {platform!r}.")
    display_name = (fields.get("display_name") or "").strip()
    credentials_ref = (fields.get("credentials_ref") or "").strip()
    context = (fields.get("context") or "").strip()

    doc = _load_doc(SOURCES_PATH)
    arr = _aot(doc, "source")

    # duplicate-id guard: a *different* entry must not already own this id
    dup = _find_index(arr, "id", sid)
    if dup is not None and (original_id is None or arr[dup].get("id") != original_id):
        raise ConfigError(f"A source with id {sid!r} already exists.")

    if original_id is None:
        tbl = tomlkit.table()
        tbl["id"] = sid
        tbl["platform"] = platform
        tbl["identifier"] = identifier
        if display_name:
            tbl["display_name"] = display_name
        tbl["credentials_ref"] = credentials_ref
        if context:
            tbl["context"] = _str_value(context)
        arr.append(tbl)
    else:
        idx = _find_index(arr, "id", original_id)
        if idx is None:
            raise ConfigError(f"Source {original_id!r} not found.")
        tbl = arr[idx]  # mutate in place -> preserves this entry's comments
        tbl["id"] = sid
        tbl["platform"] = platform
        tbl["identifier"] = identifier
        if display_name:
            tbl["display_name"] = display_name
        elif "display_name" in tbl:
            del tbl["display_name"]
        tbl["credentials_ref"] = credentials_ref
        if context:
            tbl["context"] = _str_value(context)
        elif "context" in tbl:
            del tbl["context"]

    _atomic_write(SOURCES_PATH, doc, _validate_sources_file)


def delete_source(source_id: str) -> None:
    """Delete a [[source]] — BLOCKED if any briefing references it."""
    used_by = [
        b.name
        for b in cfg.load_briefings()
        if any(sc.source_id == source_id for sc in b.sources)
    ]
    if used_by:
        raise ConfigError(
            f"Source {source_id!r} is used by briefing(s) {', '.join(used_by)}; "
            "remove it there first."
        )
    doc = _load_doc(SOURCES_PATH)
    arr = _aot(doc, "source")
    idx = _find_index(arr, "id", source_id)
    if idx is None:
        raise ConfigError(f"Source {source_id!r} not found.")
    del arr[idx]
    _atomic_write(SOURCES_PATH, doc, _validate_sources_file)


# --------------------------------------------------------------------------- #
# Briefings
# --------------------------------------------------------------------------- #


def _build_source_configs(rows: list[dict]) -> "tomlkit.items.AoT":
    """Build the nested [[briefing.source]] array from form rows
    ({source_id, keyword_filter:[...]})."""
    known = set(cfg.load_sources().keys())
    aot = tomlkit.aot()
    for row in rows:
        sid = (row.get("source_id") or "").strip()
        if not sid:
            continue
        if sid not in known:
            raise ConfigError(
                f"source_id {sid!r} is not defined in sources.toml."
            )
        t = tomlkit.table()
        t["source_id"] = sid
        kw = [k.strip() for k in row.get("keyword_filter", []) if k.strip()]
        t["keyword_filter"] = kw
        aot.append(t)
    if not aot:
        raise ConfigError("A briefing needs at least one source.")
    return aot


def _apply_briefing_fields(tbl, fields: dict, source_rows: list[dict]) -> None:
    """Set scalar fields + nested sources on `tbl` (a tomlkit table)."""
    tbl["name"] = _req(fields, "name")
    tbl["schedule"] = _req(fields, "schedule")
    tbl["lookback_window"] = _req(fields, "lookback_window")

    outputs = [o for o in fields.get("output", []) if o in VALID_OUTPUTS]
    if not outputs:
        raise ConfigError(f"Select at least one output ({VALID_OUTPUTS}).")
    delivery = [d for d in fields.get("delivery", []) if d in VALID_DELIVERY]
    if not delivery:
        raise ConfigError(f"Select at least one delivery target ({VALID_DELIVERY}).")
    tbl["output"] = outputs
    tbl["delivery"] = delivery

    instruction = _req(fields, "synthesis_instruction")
    # multiline triple-quoted string, matching the hand-authored style
    tbl["synthesis_instruction"] = tomlkit.string(
        "\n" + instruction.strip("\n") + "\n", multiline=True
    )
    tbl["source"] = _build_source_configs(source_rows)


def upsert_briefing(
    fields: dict, source_rows: list[dict], *, original_name: str | None = None
) -> None:
    """Create (original_name=None) or update a [[briefing]] entry, atomic-write."""
    name = _req(fields, "name")
    # validate schedule/lookback early for a friendly message (safety net re-checks)
    parse_window(_req(fields, "lookback_window"))
    if CronTrigger is not None:
        try:
            CronTrigger.from_crontab(_req(fields, "schedule"))
        except Exception as e:
            raise ConfigError(f"Invalid cron schedule: {e}") from e

    doc = _load_doc(BRIEFINGS_PATH)
    arr = _aot(doc, "briefing")

    dup = _find_index(arr, "name", name)
    if dup is not None and (original_name is None or arr[dup].get("name") != original_name):
        raise ConfigError(f"A briefing named {name!r} already exists.")

    if original_name is None:
        tbl = tomlkit.table()
        _apply_briefing_fields(tbl, fields, source_rows)
        arr.append(tbl)
    else:
        idx = _find_index(arr, "name", original_name)
        if idx is None:
            raise ConfigError(f"Briefing {original_name!r} not found.")
        _apply_briefing_fields(arr[idx], fields, source_rows)

    _atomic_write(BRIEFINGS_PATH, doc, _validate_briefings_file)


def delete_briefing(name: str) -> None:
    doc = _load_doc(BRIEFINGS_PATH)
    arr = _aot(doc, "briefing")
    idx = _find_index(arr, "name", name)
    if idx is None:
        raise ConfigError(f"Briefing {name!r} not found.")
    del arr[idx]
    _atomic_write(BRIEFINGS_PATH, doc, _validate_briefings_file)

"""Delivery: get a finished brief to where the owner consumes it.

v0 target is a **local file drop**: the timestamped brief already lives in
briefs/; delivery additionally writes a stable `latest-<briefing>.*` pointer so
a predictable path always has the newest brief (easy to sync to a phone, open
in a browser, etc.). Email / web-page targets slot in behind the same seam later.
"""

from __future__ import annotations

from pathlib import Path
from shutil import copyfile

from core.models import DeliveryTarget

BRIEFS_DIR = Path(__file__).resolve().parent.parent / "briefs"


def deliver(
    briefing_name: str,
    text_path: Path,
    audio_path: Path | None,
    targets: list[DeliveryTarget],
    delivery_dir: Path | None = None,
) -> list[Path]:
    """Deliver a brief to each target. Returns the paths written/produced.

    LOCAL: copy the brief to `<delivery_dir>/latest-<briefing>.<ext>` so the
    newest is always at a stable location alongside the timestamped originals.
    """
    delivery_dir = delivery_dir or BRIEFS_DIR
    delivery_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for target in targets:
        if target is DeliveryTarget.LOCAL:
            latest_text = delivery_dir / f"latest-{briefing_name}{text_path.suffix}"
            copyfile(text_path, latest_text)
            written.append(latest_text)
            if audio_path is not None:
                latest_audio = delivery_dir / f"latest-{briefing_name}{audio_path.suffix}"
                copyfile(audio_path, latest_audio)
                written.append(latest_audio)
        else:
            # email / web page — not built yet (see ROADMAP / HANDOFF).
            raise NotImplementedError(f"Delivery target {target.value!r} not implemented yet")

    return written

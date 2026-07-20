"""Podcast feed + audio server — a tiny, stateless static file server.

Serves exactly two things so an iOS podcast app can subscribe to a briefing:

    GET /feed/<briefing>.xml    the generated podcast feed (briefs/feeds/)
    GET /audio/<file>.mp3       the episode audio (briefs/)

Deliberately separate from the authoring UI (`python -m web`, port 8765): this is
a different process on a different port with no config access, no write endpoints,
and no auth. **The tailnet is the security boundary** — it binds 127.0.0.1 only and
is fronted by `tailscale serve` for HTTPS access from the phone (HUMAN_TODO §8).

**Range requests matter:** podcast players scrub by requesting byte ranges, so
responses go through Flask's `send_file` with `conditional=True` (HTTP 206 partial
content). A plain `http.server` would NOT support this.

Run it and leave it running:

    python -m podcast_server            # http://127.0.0.1:8766
    python -m podcast_server --port N

How it stays running is your call (a terminal, a startup shortcut, whatever) —
this project deliberately ships no OS service installers or supervision. If it's
down, the phone's poll just fails and retries later.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask, abort, send_from_directory

ROOT = Path(__file__).resolve().parent
BRIEFS_DIR = ROOT / "briefs"
FEEDS_DIR = BRIEFS_DIR / "feeds"


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/feed/<briefing>.xml")
    def feed(briefing: str):
        """The briefing's podcast feed. `send_from_directory` rejects traversal,
        and the <string> converter won't match a '/'."""
        return send_from_directory(
            FEEDS_DIR, f"{briefing}.xml",
            mimetype="application/rss+xml", conditional=True,
        )

    @app.get("/audio/<path:filename>")
    def audio(filename: str):
        """Episode audio, with Range support so players can scrub (HTTP 206)."""
        if not filename.lower().endswith(".mp3"):
            abort(404)  # audio only; nothing else in briefs/ is servable
        return send_from_directory(
            BRIEFS_DIR, filename, mimetype="audio/mpeg", conditional=True,
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Podcast feed/audio server (localhost).")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    print(f"Podcast server on http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    print(f"  feed:  http://127.0.0.1:{args.port}/feed/<briefing>.xml")
    print(f"  audio: http://127.0.0.1:{args.port}/audio/<file>.mp3")
    # threaded so a player downloading an episode doesn't block the feed poll
    create_app().run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()

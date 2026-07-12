"""Run the localhost authoring/ops UI:

    python -m web            # http://127.0.0.1:8765
    python -m web --port N

Binds to 127.0.0.1 only — never exposed to the LAN or internet (it reads config
that references a Discord token by env-var name). Debug off (no Werkzeug console).
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Briefing engine web UI (localhost).")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    load_dotenv()  # so a future "Run Now" subprocess inherits the same env
    app = create_app()
    print(f"Authoring UI on http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()

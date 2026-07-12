"""Scheduler entrypoint (APScheduler).

Schedules each briefing by its cron `schedule` and runs the pipeline when it
fires. Cross-platform (works on Windows + Ubuntu) and self-contained — no OS
cron needed.

    python scheduler.py list                     # briefings + next fire times
    python scheduler.py once --briefing NAME      # run one now (BILLABLE unless --dry-run)
    python scheduler.py run                        # start the loop (fires on schedule; BILLABLE)

Add --dry-run to skip the Claude/TTS calls (free wiring check). Add --no-audio
to generate text only. `run` blocks forever and WILL make billable API calls at
each scheduled time — start it deliberately.
"""

from __future__ import annotations

import argparse
from datetime import datetime

from dotenv import load_dotenv

from core.config import load_briefings

try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError as e:  # pragma: no cover
    raise SystemExit("APScheduler not installed — run: pip install -e .") from e


def _trigger(cron_expr: str) -> CronTrigger:
    """Parse a 5-field cron string into an APScheduler trigger (local tz)."""
    return CronTrigger.from_crontab(cron_expr)


def cmd_list(args) -> None:
    briefings = load_briefings()
    if not briefings:
        print("No briefings defined in config/briefings.toml")
        return
    now = datetime.now().astimezone()
    for b in briefings:
        try:
            nxt = _trigger(b.schedule).get_next_fire_time(None, now)
            nxt_s = nxt.strftime("%Y-%m-%d %H:%M %Z") if nxt else "never"
        except ValueError as e:
            nxt_s = f"BAD CRON ({e})"
        outs = "+".join(o.value for o in b.output)
        print(f"{b.name:16} cron '{b.schedule}'  next: {nxt_s}  [{outs}]")


def _run_one(briefing, *, dry_run: bool, audio: bool) -> None:
    from core.pipeline import run_briefing  # lazy so `list` needs no pipeline deps

    tag = " [DRY RUN]" if dry_run else ""
    print(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}] running '{briefing.name}'{tag}")
    result = run_briefing(briefing, audio=audio, dry_run=dry_run)
    if result.skipped:
        if result.failed:
            print("  ⚠ source failure(s) — see briefs/FAILED-"
                  f"{briefing.name}.txt and logs/briefing.log")
        else:
            print("  (no items gathered — no brief produced)")
        return
    print(f"  text:      {result.text_path}")
    if result.audio_path:
        print(f"  audio:     {result.audio_path}")
    print(f"  delivered: {[str(p) for p in result.delivered]}")
    if result.failed:
        print("  ⚠ INCOMPLETE — a source errored; see briefs/FAILED-"
              f"{briefing.name}.txt and logs/briefing.log")


def cmd_once(args) -> None:
    briefings = {b.name: b for b in load_briefings()}
    if args.briefing not in briefings:
        raise SystemExit(f"No briefing named {args.briefing!r}. Have: {list(briefings)}")
    _run_one(briefings[args.briefing], dry_run=args.dry_run, audio=not args.no_audio)


def cmd_history(args) -> None:
    from core import store

    rows = store.recent_briefs(args.briefing, limit=args.limit)
    if not rows:
        print("No briefs recorded yet.")
        return
    for r in rows:
        print(
            f"{r['generated_at']}  {r['briefing_id']:16} {r['status']:10} "
            f"{r['text_path']}"
        )


def cmd_run(args) -> None:
    briefings = load_briefings()
    scheduler = BlockingScheduler()
    for b in briefings:
        scheduler.add_job(
            _run_one,
            trigger=_trigger(b.schedule),
            args=[b],
            kwargs={"dry_run": args.dry_run, "audio": not args.no_audio},
            id=b.name,
            name=b.name,
        )
    mode = "DRY RUN (no API calls)" if args.dry_run else "LIVE — will make billable API calls"
    print(f"Scheduler starting [{mode}]. {len(briefings)} briefing(s). Ctrl-C to stop.")
    cmd_list(args)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Briefing scheduler (APScheduler).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="show briefings and next fire times")
    p_list.set_defaults(func=cmd_list)

    p_once = sub.add_parser("once", help="run one briefing immediately")
    p_once.add_argument("--briefing", required=True)
    p_once.add_argument("--dry-run", action="store_true")
    p_once.add_argument("--no-audio", action="store_true")
    p_once.set_defaults(func=cmd_once)

    p_run = sub.add_parser("run", help="start the scheduling loop (blocks)")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--no-audio", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_hist = sub.add_parser("history", help="show recorded brief history (SQLite)")
    p_hist.add_argument("--briefing", default=None)
    p_hist.add_argument("--limit", type=int, default=20)
    p_hist.set_defaults(func=cmd_history)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

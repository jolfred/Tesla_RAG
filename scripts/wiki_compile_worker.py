#!/usr/bin/env python3
"""Keep the resumable Wiki compiler running during Jolf's daytime window."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.wiki.ingest import connect  # noqa: E402
from backend.wiki.ingest_runner import compile_wiki  # noqa: E402

MOSCOW = ZoneInfo("Europe/Moscow")


class WorkerStopped(BaseException):
    pass


def stop_worker(_signum, _frame):
    raise WorkerStopped()


def progress(db: Path) -> dict:
    con = connect(db)
    try:
        posts = dict(con.execute("SELECT state,count(*) FROM posts GROUP BY state"))
        facts = dict(con.execute("SELECT state,count(*) FROM facts GROUP BY state"))
        proposals = dict(con.execute("SELECT state,count(*) FROM proposals GROUP BY state"))
        return {"posts": posts, "facts": facts, "proposals": proposals}
    finally:
        con.close()


def record(run_dir: Path, state: str, **extra) -> None:
    payload = {"state": state, "updated_at": dt.datetime.now(MOSCOW).isoformat(),
               "worker_pid": os.getpid(), **extra}
    path = run_dir / "continuation-state.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def wait_until(deadline: dt.datetime) -> None:
    # Wall time includes suspend: an expired cooldown ends promptly after wakeup.
    while (remaining := (deadline - dt.datetime.now(MOSCOW)).total_seconds()) > 0:
        time.sleep(min(30, remaining))


def run(args) -> None:
    policy = {"primary_provider": "free OpenCode CLI", "codex_fallback": args.codex_fallback,
              "codex_minimum_remaining_percent": 10, "batch_size": 10,
              "char_budget": 16000, "work_hours": "08:00–23:00 Europe/Moscow"}
    delay = 900
    # Retain a cooldown across a restart; a reboot must not hammer a limited provider.
    try:
        previous = json.loads((args.run_dir / "continuation-state.json").read_text(encoding="utf-8"))
        deadline = dt.datetime.fromisoformat(previous["next_retry_at"])
        if previous.get("state") == "waiting_for_provider" and deadline.tzinfo is not None:
            record(args.run_dir, "waiting_for_provider", **policy, next_retry_at=deadline.isoformat())
            wait_until(deadline)
    except (OSError, ValueError, KeyError, TypeError):
        pass

    while True:
        now = dt.datetime.now(MOSCOW)
        if not 8 <= now.hour < 23:
            morning = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now.hour >= 23:
                morning += dt.timedelta(days=1)
            record(args.run_dir, "outside_work_hours", **policy, next_retry_at=morning.isoformat())
            wait_until(morning)
            continue

        counts = progress(args.db)
        if not counts["posts"].get("queued", 0) and not counts["facts"].get("extracted", 0):
            record(args.run_dir, "automatic_queue_finished", **policy, progress=counts,
                   note="Review items still require editorial work; this is not certification of Wiki accuracy.")
            return

        record(args.run_dir, "compiling", **policy, progress=counts)
        try:
            result = compile_wiki(
                args.db, args.wiki, args.run_dir,
                ROOT / "schema/prompts/wiki_extract_en.md", ROOT / "schema/prompts/wiki_merge_en.md",
                max_posts=10, batch_size=10, char_budget=16000,
                do_apply=True, codex_fallback=args.codex_fallback,
            )
        except RuntimeError as exc:
            message = str(exc)
            if "all free OpenCode models failed" in message:
                # No invented quota percentage for free providers: retry actual failures slowly.
                deadline = dt.datetime.now(MOSCOW) + dt.timedelta(seconds=delay)
                record(args.run_dir, "waiting_for_provider", **policy, reason=message,
                       next_retry_at=deadline.isoformat(), retry_delay_seconds=delay, progress=progress(args.db))
                wait_until(deadline)
                delay = min(delay * 2, 3600)
                continue
            if "another compiler is already using this ledger" in message:
                record(args.run_dir, "waiting_for_existing_compiler", **policy)
                time.sleep(60)
                continue
            raise
        except (ValueError, TypeError, KeyError) as exc:
            # A damaged response or ledger is not a quota failure. Preserve it for review.
            record(args.run_dir, "needs_review", **policy, reason=f"{type(exc).__name__}: {exc}",
                   progress=progress(args.db))
            traceback.print_exc()
            return
        delay = 900
        record(args.run_dir, "batch_finished", **policy, result=result, progress=progress(args.db))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "storage/wiki/_ingest/ledger.sqlite")
    parser.add_argument("--wiki", type=Path, default=ROOT / "storage/wiki")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--codex-fallback", action="store_true",
                        help="allow guarded Luna Low/Medium after all free models fail")
    parser.add_argument("--execute", action="store_true", help="explicitly permit compilation and provider calls")
    args = parser.parse_args()
    if not args.execute:
        parser.error("pass --execute to start the background compiler")
    args.run_dir.mkdir(parents=True, exist_ok=True)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    with args.db.with_suffix(args.db.suffix + ".worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "another Wiki worker is already using this ledger\n")
        try:
            run(args)
        except WorkerStopped:
            record(args.run_dir, "stopped", note="Persisted ledger and proposals will resume on the next start.")
        except Exception as exc:
            record(args.run_dir, "worker_error", reason=f"{type(exc).__name__}: {exc}")
            raise


if __name__ == "__main__":
    main()

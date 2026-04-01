#!/usr/bin/env python3
"""Single entry point for the mindpattern pipeline.

Replaces run-all-users.sh, run-user-research.sh, and all other shell scripts.
Handles: PATH setup, concurrency guard, caffeinate, structured logging,
user iteration, and Slack summary.

Usage:
    python3 run.py                      # Run for all active users
    python3 run.py --user ramsay        # Run for a specific user
    python3 run.py --date 2026-03-14    # Run for a specific date
    python3 run.py --dry-run            # Skip actual claude calls
"""

import argparse
import fcntl
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── PATH setup for launchd (minimal PATH by default) ──────────────────
os.environ["PATH"] = (
    f"/usr/local/bin:/opt/homebrew/bin:{os.environ.get('PATH', '')}"
)

PROJECT_ROOT = Path(__file__).parent.resolve()
os.chdir(PROJECT_ROOT)

# Ensure our packages are importable
sys.path.insert(0, str(PROJECT_ROOT))

LOCK_FILE = "/tmp/mindpattern-pipeline.lock"


def setup_logging(date_str: str) -> None:
    """Set up dual logging: human-readable to stderr + JSONL to file."""
    log_dir = PROJECT_ROOT / "reports"
    log_dir.mkdir(exist_ok=True)

    # Human-readable handler (stderr, captured by launchd)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    ))

    # JSONL handler (for machine parsing)
    jsonl_path = log_dir / f"pipeline-{date_str}.jsonl"
    file_handler = logging.FileHandler(str(jsonl_path))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record):
        return json.dumps({
            "ts": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        })


def load_active_users() -> list[dict]:
    """Load active users from users.json."""
    users_path = PROJECT_ROOT / "users.json"
    with open(users_path) as f:
        data = json.load(f)
    return [u for u in data.get("users", []) if u.get("active", True)]


def acquire_lock() -> int:
    """Acquire exclusive lock. Returns fd or exits if another instance is running."""
    fd = os.open(LOCK_FILE, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        logging.getLogger(__name__).error("Another instance is already running")
        sys.exit(0)


def send_slack_summary(message: str) -> None:
    """Send pipeline summary to Slack #mindpattern-approvals."""
    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "slack-bot-token", "-w"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning("No Slack token in Keychain for summary")
            return

        token = result.stdout.strip()
        import json
        import urllib.request
        payload = json.dumps({
            "channel": "C0ALSRHAATH",
            "text": message,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        logger.error(f"Failed to send Slack summary: {e}")


def main():
    parser = argparse.ArgumentParser(description="mindpattern pipeline runner")
    parser.add_argument("--user", help="Run for a specific user only")
    parser.add_argument("--date", help="Date to run for (YYYY-MM-DD, default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual claude calls")
    parser.add_argument("--skip-social", action="store_true", help="Skip social + engagement phases")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    setup_logging(date_str)
    logger = logging.getLogger("mindpattern")

    # ── Concurrency guard ──────────────────────────────────────────────
    lock_fd = acquire_lock()

    # ── Caffeinate (keep Mac awake) ────────────────────────────────────
    caffeinate = subprocess.Popen(
        ["caffeinate", "-i", "-s", "-w", str(os.getpid())],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    pipeline_start = time.monotonic()
    exit_code = 0

    try:
        # ── Load users ─────────────────────────────────────────────────
        if args.user:
            users = [{"id": args.user}]
        else:
            users = load_active_users()

        logger.info(f"Pipeline start: {date_str}, {len(users)} user(s)")

        for user in users:
            user_id = user["id"]
            user_start = time.monotonic()
            logger.info(f"Running pipeline for {user_id}")

            try:
                from orchestrator.runner import ResearchPipeline

                pipeline = ResearchPipeline(user_id, date_str)
                result = pipeline.run()

                if result != 0:
                    exit_code = 1
                    logger.error(f"Pipeline failed for {user_id}")

                user_duration = int((time.monotonic() - user_start) * 1000)
                logger.info(f"User {user_id} completed in {user_duration}ms")

                pipeline.close()

            except Exception as e:
                exit_code = 1
                logger.error(f"Pipeline crashed for {user_id}: {e}", exc_info=True)

        total_duration = int((time.monotonic() - pipeline_start))
        logger.info(f"Pipeline finished: {total_duration}s, exit={exit_code}")

        # ── Slack summary ─────────────────────────────────────────────
        if not args.dry_run:
            try:
                from memory import get_stats, open_db
                with open_db(user_id=users[0]["id"]) as db:
                    stats = get_stats(db)
                summary = (
                    f"{stats['findings']} findings | "
                    f"{total_duration}s | "
                    f"exit={exit_code}"
                )
                send_slack_summary(summary)
            except Exception as e:
                logging.getLogger(__name__).debug(f"Failed to send Slack summary: {e}")

    finally:
        # ── Cleanup ────────────────────────────────────────────────────
        caffeinate.terminate()
        os.close(lock_fd)
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

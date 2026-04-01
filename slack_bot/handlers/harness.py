"""Slack handler for the #mp-harness channel.

Commands:
  status   — Show harness state (running/idle), last run, open ticket count
  tickets  — List open tickets with priority and age
  skip <id> — Mark a ticket as held (harness skips it)
  urgent <id> — Bump a ticket to P1
  hold     — Pause the next scheduled harness run
  resume   — Unpause harness scheduling
  run      — Trigger an immediate harness run in background
"""

import json
import logging
import subprocess
from pathlib import Path

from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
HOLD_SENTINEL = Path("/tmp/mindpattern-harness.hold")
LOCK_FILE = Path("/tmp/mindpattern-harness.lock")


class HarnessHandler(BaseHandler):
    """Handle messages in the #mp-harness channel."""

    def handle(self, event: dict) -> None:
        text = event.get("text", "").strip().lower()
        thread_ts = event.get("ts")

        if text.startswith("status"):
            self._cmd_status(thread_ts)
        elif text.startswith("tickets"):
            self._cmd_tickets(thread_ts)
        elif text.startswith("skip "):
            ticket_id = text.split(maxsplit=1)[1].strip()
            self._cmd_skip(ticket_id, thread_ts)
        elif text.startswith("urgent "):
            ticket_id = text.split(maxsplit=1)[1].strip()
            self._cmd_urgent(ticket_id, thread_ts)
        elif text == "hold":
            self._cmd_hold(thread_ts)
        elif text == "resume":
            self._cmd_resume(thread_ts)
        elif text == "run":
            self._cmd_run(thread_ts)
        else:
            self.reply(
                "Commands: `status`, `tickets`, `skip <id>`, `urgent <id>`, `hold`, `resume`, `run`",
                thread_ts,
            )

    def _cmd_status(self, thread_ts: str) -> None:
        running = LOCK_FILE.exists()
        on_hold = HOLD_SENTINEL.exists()

        from harness.tickets import list_tickets
        open_tickets = list_tickets(status="open")
        in_progress = list_tickets(status="in_progress")

        state = "running" if running else ("on hold" if on_hold else "idle")
        msg = f"*Harness Status:* {state}\n"
        msg += f"Open tickets: {len(open_tickets)}\n"
        msg += f"In progress: {len(in_progress)}\n"

        # Last run log
        import glob
        logs = sorted(glob.glob(str(PROJECT_ROOT / "reports" / "harness-*.log")))
        if logs:
            last_log = Path(logs[-1])
            last_line = last_log.read_text().strip().split("\n")[-1]
            msg += f"Last run: `{last_log.name}` — {last_line}"

        self.reply(msg, thread_ts)

    def _cmd_tickets(self, thread_ts: str) -> None:
        from harness.tickets import list_tickets
        tickets = list_tickets(status="open")

        if not tickets:
            self.reply("No open tickets.", thread_ts)
            return

        lines = ["*Open Tickets:*"]
        for t in sorted(tickets, key=lambda x: x.get("priority", "P3")):
            tid = t.get("id", "?")
            title = t.get("title", "?")
            priority = t.get("priority", "?")
            source = t.get("source", "?")
            lines.append(f"`[{priority}]` `{tid}` — {title} (_{source}_)")

        self.reply("\n".join(lines), thread_ts)

    def _cmd_skip(self, ticket_id: str, thread_ts: str) -> None:
        from harness.tickets import find_ticket_by_id, mark_held
        path = find_ticket_by_id(ticket_id)
        if path:
            mark_held(str(path))
            self.reply(f"Ticket `{ticket_id}` marked as held.", thread_ts)
        else:
            self.reply(f"Ticket `{ticket_id}` not found.", thread_ts)

    def _cmd_urgent(self, ticket_id: str, thread_ts: str) -> None:
        from harness.tickets import find_ticket_by_id, bump_priority
        path = find_ticket_by_id(ticket_id)
        if path:
            bump_priority(str(path), "P1")
            self.reply(f"Ticket `{ticket_id}` bumped to P1.", thread_ts)
        else:
            self.reply(f"Ticket `{ticket_id}` not found.", thread_ts)

    def _cmd_hold(self, thread_ts: str) -> None:
        HOLD_SENTINEL.touch()
        self.reply("Harness paused. Next scheduled run will be skipped. Use `resume` to unpause.", thread_ts)

    def _cmd_resume(self, thread_ts: str) -> None:
        if HOLD_SENTINEL.exists():
            HOLD_SENTINEL.unlink()
            self.reply("Harness resumed. Next scheduled run will proceed.", thread_ts)
        else:
            self.reply("Harness was not on hold.", thread_ts)

    def _cmd_run(self, thread_ts: str) -> None:
        self.reply("Starting harness run in background...", thread_ts)
        subprocess.Popen(
            ["bash", str(PROJECT_ROOT / "harness" / "run.sh")],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

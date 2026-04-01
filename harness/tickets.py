"""Ticket management utilities for the MindPattern autonomous harness.

Tickets are JSON files in harness/tickets/. This module provides
functions to query, update, and manage the ticket lifecycle.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TICKET_DIR = PROJECT_ROOT / "harness" / "tickets"
FEEDBACK_FILE = PROJECT_ROOT / "harness" / "feedback.json"
CONFIG_FILE = PROJECT_ROOT / "harness" / "config.json"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {"ticket_decay_days": 7}


def _load_ticket(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load ticket {path}: {e}")
        return None


def _save_ticket(path: Path, ticket: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ticket, indent=2) + "\n")
    tmp.rename(path)


def pick_next(ticket_dir: str | None = None) -> str | None:
    """Return the path to the highest-priority open ticket, or None.

    Skips expired tickets (past expires_at) and held tickets.
    Priority order: P1 > P2 > P3, then oldest first.
    """
    tdir = Path(ticket_dir) if ticket_dir else TICKET_DIR
    now = datetime.now(timezone.utc)
    candidates = []

    for f in tdir.glob("*.json"):
        ticket = _load_ticket(f)
        if not ticket:
            continue
        if ticket.get("status") != "open":
            continue

        # Check expiry
        expires = ticket.get("expires_at")
        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if now > exp_dt:
                    continue
            except ValueError:
                pass

        priority = ticket.get("priority", "P3")
        created = ticket.get("created_at", "")
        priority_rank = {"P1": 0, "P2": 1, "P3": 2}.get(priority, 3)
        candidates.append((priority_rank, created, str(f)))

    if not candidates:
        return None

    candidates.sort()
    return candidates[0][2]


def mark_in_progress(ticket_path: str) -> None:
    path = Path(ticket_path)
    ticket = _load_ticket(path)
    if ticket:
        ticket["status"] = "in_progress"
        _save_ticket(path, ticket)


def mark_done(ticket_path: str, pr_url: str | None = None) -> None:
    path = Path(ticket_path)
    ticket = _load_ticket(path)
    if ticket:
        ticket["status"] = "done"
        if pr_url:
            ticket["pr_url"] = pr_url
        ticket["completed_at"] = datetime.now(timezone.utc).isoformat()
        _save_ticket(path, ticket)


def mark_failed(ticket_path: str, reason: str) -> None:
    path = Path(ticket_path)
    ticket = _load_ticket(path)
    if ticket:
        ticket["status"] = "failed"
        ticket.setdefault("feedback_history", []).append({
            "type": "failure",
            "reason": reason[:2000],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        _save_ticket(path, ticket)


def mark_held(ticket_path: str) -> None:
    path = Path(ticket_path)
    ticket = _load_ticket(path)
    if ticket:
        ticket["status"] = "held"
        _save_ticket(path, ticket)


def bump_priority(ticket_path: str, priority: str = "P1") -> None:
    path = Path(ticket_path)
    ticket = _load_ticket(path)
    if ticket:
        ticket["priority"] = priority
        _save_ticket(path, ticket)


def decay_stale(ticket_dir: str | None = None) -> int:
    """Archive tickets past their expires_at. Returns count archived."""
    tdir = Path(ticket_dir) if ticket_dir else TICKET_DIR
    archive = tdir / "archive"
    now = datetime.now(timezone.utc)
    count = 0

    for f in tdir.glob("*.json"):
        ticket = _load_ticket(f)
        if not ticket:
            continue
        if ticket.get("status") not in ("open", "failed"):
            continue

        expires = ticket.get("expires_at")
        if not expires:
            continue
        try:
            exp_dt = datetime.fromisoformat(expires)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if now > exp_dt:
                archive.mkdir(exist_ok=True)
                f.rename(archive / f.name)
                count += 1
        except ValueError:
            pass

    return count


def list_tickets(ticket_dir: str | None = None, status: str | None = None) -> list[dict]:
    """List tickets, optionally filtered by status."""
    tdir = Path(ticket_dir) if ticket_dir else TICKET_DIR
    results = []
    for f in sorted(tdir.glob("*.json")):
        ticket = _load_ticket(f)
        if not ticket:
            continue
        if status and ticket.get("status") != status:
            continue
        ticket["_path"] = str(f)
        results.append(ticket)
    return results


def find_ticket_by_id(ticket_id: str, ticket_dir: str | None = None) -> Path | None:
    """Find a ticket file by its ID field."""
    tdir = Path(ticket_dir) if ticket_dir else TICKET_DIR
    for f in tdir.glob("*.json"):
        ticket = _load_ticket(f)
        if ticket and ticket.get("id") == ticket_id:
            return f
    return None


def record_pr_outcome(ticket_id: str, pr_number: int, outcome: str,
                      pr_url: str = "", close_reason: str = "") -> None:
    """Append a PR outcome to feedback.json for the scout to learn from."""
    feedback = []
    if FEEDBACK_FILE.exists():
        try:
            feedback = json.loads(FEEDBACK_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            feedback = []

    entry = {
        "ticket_id": ticket_id,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if close_reason:
        entry["close_reason"] = close_reason

    feedback.append(entry)

    tmp = FEEDBACK_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(feedback, indent=2) + "\n")
    tmp.rename(FEEDBACK_FILE)


# CLI interface for use from run.sh
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m harness.tickets <command> [args]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "pick":
        result = pick_next()
        if result:
            print(result)
        else:
            sys.exit(1)

    elif cmd == "list":
        status_filter = sys.argv[2] if len(sys.argv) > 2 else None
        for t in list_tickets(status=status_filter):
            print(f"[{t.get('priority','?')}] {t.get('status','?'):12s} {t.get('id','?'):20s} {t.get('title','?')}")

    elif cmd == "decay":
        count = decay_stale()
        print(f"Archived {count} stale tickets")

    elif cmd == "mark-failed" and len(sys.argv) >= 4:
        mark_failed(sys.argv[2], sys.argv[3])

    elif cmd == "mark-done" and len(sys.argv) >= 3:
        pr = sys.argv[3] if len(sys.argv) > 3 else None
        mark_done(sys.argv[2], pr)

    elif cmd == "mark-held" and len(sys.argv) >= 3:
        mark_held(sys.argv[2])

    elif cmd == "bump" and len(sys.argv) >= 3:
        priority = sys.argv[3] if len(sys.argv) > 3 else "P1"
        bump_priority(sys.argv[2], priority)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

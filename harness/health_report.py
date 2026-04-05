"""Daily health report for the harness — posts to Slack.

Deterministic: no LLM, just data aggregation from tickets, issues, feedback, and logs.

CLI:
    python3 -m harness.health_report           # print to stdout
    python3 -m harness.health_report --slack    # post to Slack
"""

import json
import logging
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .issues import read_issues, ISSUES_PATH
from .tickets import list_tickets, FEEDBACK_FILE, TICKET_DIR

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REPORTS_DIR = PROJECT_ROOT / "reports"


def _count_issues_since(hours: int = 24) -> tuple[int, list[str]]:
    """Count issues logged in the last N hours. Returns (count, titles)."""
    if not ISSUES_PATH.exists():
        return 0, []

    content = ISSUES_PATH.read_text()
    cutoff = datetime.now() - timedelta(hours=hours)
    titles = []

    for line in content.split("\n"):
        if line.startswith("### "):
            # Parse "### 2026-04-02 06:26 — title"
            parts = line[4:].split(" — ", 1)
            if len(parts) == 2:
                try:
                    ts = datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M")
                    if ts >= cutoff:
                        titles.append(parts[1].strip())
                except ValueError:
                    pass

    return len(titles), titles


def _get_pipeline_status() -> dict:
    """Check if today's pipeline ran successfully."""
    today = datetime.now().strftime("%Y-%m-%d")
    marker = Path(f"/tmp/mindpattern-ran-{today}")
    stderr_log = REPORTS_DIR / "launchd-stderr.log"

    status = "unknown"
    if marker.exists():
        status = "success"
    elif stderr_log.exists():
        content = stderr_log.read_text()
        # Check if today's run crashed
        if f"Pipeline start: {today}" in content:
            if "ERROR" in content.split(f"Pipeline start: {today}")[-1]:
                status = "crashed"
            else:
                status = "running"
        else:
            status = "not_started"
    else:
        status = "not_started"

    return {"status": status, "date": today}


def _get_pr_stats() -> dict:
    """Get PR outcomes from feedback.json."""
    if not FEEDBACK_FILE.exists():
        return {"total": 0, "merged": 0, "closed": 0, "rejected": 0}

    try:
        feedback = json.loads(FEEDBACK_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "merged": 0, "closed": 0, "rejected": 0}

    outcomes = Counter(f.get("outcome", "unknown") for f in feedback)
    return {
        "total": len(feedback),
        "merged": outcomes.get("merged", 0),
        "closed": outcomes.get("closed", 0),
        "rejected": outcomes.get("rejected", 0),
    }


def _get_harness_run_stats() -> dict:
    """Parse today's harness log for run stats."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = REPORTS_DIR / f"harness-{today}.log"

    if not log_path.exists():
        return {"ran_today": False}

    content = log_path.read_text()
    stats = {"ran_today": True, "processed": 0, "prs": 0, "failed": 0}

    for line in content.split("\n"):
        if "HARNESS COMPLETE" in line:
            # Parse: processed=3 PRs=4 failed=0 remaining=33
            for part in line.split("|"):
                part = part.strip()
                if part.startswith("processed="):
                    stats["processed"] = int(part.split("=")[1])
                elif part.startswith("PRs="):
                    stats["prs"] = int(part.split("=")[1])
                elif part.startswith("failed="):
                    stats["failed"] = int(part.split("=")[1])

    return stats


def generate_report() -> str:
    """Generate the daily health report as a Slack-formatted string."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # Ticket stats
    all_tickets = list_tickets()
    by_status = Counter(t.get("status") for t in all_tickets)
    open_tickets = [t for t in all_tickets if t.get("status") == "open"]
    by_priority = Counter(t.get("priority") for t in open_tickets)
    by_type = Counter(t.get("type") for t in open_tickets)

    # Issues in last 24h
    issue_count, issue_titles = _count_issues_since(24)

    # Pipeline status
    pipeline = _get_pipeline_status()

    # Harness run stats
    harness = _get_harness_run_stats()

    # PR stats
    pr_stats = _get_pr_stats()

    # Success rate
    total_processed = by_status.get("done", 0) + by_status.get("failed", 0)
    success_rate = (by_status.get("done", 0) / total_processed * 100) if total_processed > 0 else 0

    # Stale tickets (created > 3 days ago, still open)
    stale_cutoff = now - timedelta(days=3)
    stale = []
    for t in open_tickets:
        created = t.get("created_at", "")
        if created:
            try:
                created_dt = datetime.fromisoformat(created)
                if created_dt.tzinfo:
                    created_dt = created_dt.replace(tzinfo=None)
                if created_dt < stale_cutoff:
                    stale.append(t)
            except ValueError:
                pass

    # Build report
    pipeline_emoji = {"success": ":white_check_mark:", "crashed": ":x:", "running": ":hourglass_flowing_sand:", "not_started": ":zzz:"}.get(pipeline["status"], ":question:")

    lines = [
        f":clipboard: *MindPattern Daily Health Report* — {today}",
        "",
        f"*Pipeline*: {pipeline_emoji} {pipeline['status']}",
    ]

    if harness["ran_today"]:
        lines.append(f"*Harness*: processed {harness['processed']}, {harness['prs']} PRs, {harness['failed']} failed")
    else:
        lines.append("*Harness*: did not run today")

    lines += [
        "",
        "*Ticket Backlog*",
        f"  :red_circle: P1: {by_priority.get('P1', 0)}  :large_orange_circle: P2: {by_priority.get('P2', 0)}  :white_circle: P3: {by_priority.get('P3', 0)}  — {len(open_tickets)} open total",
        f"  Types: {by_type.get('bug', 0)} bugs, {by_type.get('improvement', 0)} improvements, {by_type.get('feature', 0)} features, {by_type.get('research', 0)} research",
        f"  Lifetime: {by_status.get('done', 0)} done, {by_status.get('failed', 0)} failed — {success_rate:.0f}% success rate",
    ]

    if stale:
        lines.append(f"  :warning: {len(stale)} stale tickets (open > 3 days)")
        for t in stale[:3]:
            lines.append(f"    `{t.get('id')}` {t.get('title', '?')[:50]}")
        if len(stale) > 3:
            lines.append(f"    ...and {len(stale) - 3} more")

    if issue_count > 0:
        lines += ["", f"*Issues (last 24h)*: {issue_count}"]
        for title in issue_titles[:5]:
            lines.append(f"  :rotating_light: {title[:80]}")

    if pr_stats["total"] > 0:
        lines += [
            "",
            f"*PR Outcomes*: {pr_stats['merged']} merged, {pr_stats['rejected']} rejected, {pr_stats['closed']} closed",
        ]

    return "\n".join(lines)


def post_to_slack(report: str) -> bool:
    """Post the health report to the harness Slack channel."""
    try:
        tok = subprocess.run(
            ["security", "find-generic-password", "-s", "slack-bot-token", "-a", "mindpattern", "-w"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()

        cfg_raw = subprocess.run(
            ["security", "find-generic-password", "-s", "slack-channel-config", "-a", "mindpattern", "-w"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()

        cfg = json.loads(cfg_raw)
        channel = cfg.get("harness", "")

        if not tok or not channel:
            logger.warning("Missing Slack token or channel config")
            return False

        from slack_sdk import WebClient
        client = WebClient(token=tok)
        client.chat_postMessage(channel=channel, text=report)
        return True

    except Exception as e:
        logger.warning(f"Failed to post health report to Slack: {e}")
        return False


if __name__ == "__main__":
    report = generate_report()

    if "--slack" in sys.argv:
        print(report)
        if post_to_slack(report):
            print("\nPosted to Slack.")
        else:
            print("\nFailed to post to Slack.")
    else:
        print(report)

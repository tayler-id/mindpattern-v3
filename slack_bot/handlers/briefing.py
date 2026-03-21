"""#mp-briefing handler: morning digest after pipeline run.

Posts a summary to #mp-briefing when the pipeline completes.
Also responds to status queries ("status", "how did it go", etc.).
"""

import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class BriefingHandler(BaseHandler):
    """Handle messages in #mp-briefing and post pipeline summaries."""

    def handle(self, event: dict) -> None:
        text = event.get("text", "").strip().lower()
        ts = event.get("ts", "")

        if text in ("status", "how did it go", "summary", "briefing", "?", "help"):
            self._post_status(ts)
        elif text == "yesterday":
            yesterday = (datetime.now() - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
            self._post_status(ts, date_str=yesterday)

    def _post_status(self, ts: str, date_str: str | None = None) -> None:
        """Query pipeline data and post a status summary."""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        db_path = PROJECT_ROOT / "data" / "ramsay" / "memory.db"
        if not db_path.exists():
            self.reply("No database found.", thread_ts=ts)
            return

        try:
            db = sqlite3.connect(str(db_path))
            db.row_factory = sqlite3.Row

            # Findings count
            findings = db.execute(
                "SELECT COUNT(*) as cnt FROM findings WHERE run_date = ?", (date_str,)
            ).fetchone()
            findings_count = findings["cnt"] if findings else 0

            # Agent count
            agents = db.execute(
                "SELECT COUNT(DISTINCT agent) as cnt FROM findings WHERE run_date = ?", (date_str,)
            ).fetchone()
            agent_count = agents["cnt"] if agents else 0

            # Social posts
            posts = db.execute(
                "SELECT platform, content FROM social_posts WHERE date = ? AND posted = 1", (date_str,)
            ).fetchall()

            # Engagement
            engagements = db.execute(
                "SELECT COUNT(*) as cnt FROM engagements WHERE date(created_at) = ?", (date_str,)
            ).fetchall()
            engagement_count = engagements[0]["cnt"] if engagements else 0

            db.close()

            # Format the briefing
            lines = [f"*Pipeline briefing for {date_str}*\n"]

            if findings_count > 0:
                lines.append(f"Research: {findings_count} findings from {agent_count} agents")
            else:
                lines.append("Research: No findings (pipeline may not have run)")

            if posts:
                platforms = [p["platform"] for p in posts]
                lines.append(f"Social: Posted to {', '.join(platforms)}")
            else:
                lines.append("Social: No posts")

            if engagement_count > 0:
                lines.append(f"Engagement: {engagement_count} interactions")

            # Check newsletter
            report_path = PROJECT_ROOT / "reports" / "ramsay" / f"{date_str}.md"
            if report_path.exists():
                lines.append("Newsletter: Sent")
            else:
                lines.append("Newsletter: Not generated")

            self.reply("\n".join(lines), thread_ts=ts)

        except Exception as e:
            logger.error(f"Failed to generate briefing: {e}")
            self.reply(f"Failed to pull status: {e}", thread_ts=ts)

    def post_pipeline_summary(self, results: dict) -> None:
        """Called by the pipeline runner after completion to post a briefing.

        This is called programmatically, not from a Slack event.
        """
        lines = ["*Pipeline run complete*\n"]

        findings = results.get("findings_count", 0)
        if findings:
            lines.append(f"Research: {findings} findings")

        newsletter = results.get("newsletter_generated", False)
        if newsletter:
            lines.append("Newsletter: Sent")

        social = results.get("social", {})
        platforms = social.get("platforms_posted", [])
        if platforms:
            lines.append(f"Social: Posted to {', '.join(platforms)}")

        verdict = social.get("expeditor_verdict", "")
        if verdict:
            lines.append(f"Expeditor: {verdict}")

        self.reply("\n".join(lines))

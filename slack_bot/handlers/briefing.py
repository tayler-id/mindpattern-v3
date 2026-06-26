"""#mp-briefing handler: morning digest after pipeline run.

Posts a summary to #mp-briefing when the pipeline completes.
Also responds to status queries ("status", "how did it go", etc.).
"""

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from slack_bot import heartbeat
from slack_bot.handlers.base import BaseHandler
from slack_bot.registry import get_bot_doctor_report

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class BriefingHandler(BaseHandler):
    """Handle messages in #mp-briefing and post pipeline summaries."""

    def handle(self, event: dict) -> None:
        text = event.get("text", "").strip().lower()
        ts = event.get("ts", "")

        if text in ("doctor", "bot doctor", "bot status"):
            self._post_bot_doctor(ts)
        elif text in ("status", "how did it go", "summary", "briefing", "?", "help"):
            self._post_status(ts)
        elif text == "yesterday":
            yesterday = (datetime.now() - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
            self._post_status(ts, date_str=yesterday)

    def _post_bot_doctor(self, ts: str) -> None:
        """Post safe bot wiring health without IDs, tokens, or message bodies."""
        report = get_bot_doctor_report(self.owner_user_id)
        expected_count = len(report.get("expected_names", []))
        registered_names = report.get("registered_names", [])
        missing_names = report.get("missing_names", [])
        failed_names = report.get("failed_names", [])
        token_sources = report.get("token_sources", {})

        lines = ["*Slack bot doctor*\n"]
        lines.append(
            "Registered handlers "
            f"({report.get('registered_count', 0)}/{expected_count}): "
            f"{', '.join(registered_names) if registered_names else 'none'}"
        )
        lines.append(f"Configured channels: {report.get('configured_count', 0)}")
        if missing_names:
            lines.append(f"Missing channel config: {', '.join(missing_names)}")
        if failed_names:
            lines.append(f"Failed handlers: {', '.join(failed_names)}")
        lines.append(
            f"Owner: {'configured' if report.get('owner_configured') else 'missing'}"
        )
        lines.append(f"Bot token: {token_sources.get('bot_token', 'unknown')}")
        lines.append(f"App token: {token_sources.get('app_token', 'unknown')}")
        lines.append(f"Heartbeat: {self._heartbeat_status()}")

        self.reply("\n".join(lines), thread_ts=ts)

    def _heartbeat_status(self) -> str:
        """Return heartbeat freshness without exposing host paths."""
        try:
            mtime = heartbeat.heartbeat_path().stat().st_mtime
        except FileNotFoundError:
            return "missing"
        age = max(0, int(time.time() - mtime))
        state = "stale" if heartbeat.is_stale() else "fresh"
        return f"{state} ({age}s old)"

    def _format_social_state(self, social: dict) -> str | None:
        """Format social status without including draft/post bodies."""
        if not social:
            return None

        platforms_posted = social.get("platforms_posted") or []
        if platforms_posted:
            return f"Social: Posted to {', '.join(platforms_posted)}"

        manual_copy = social.get("manual_copy") or [
            p for p in social.get("posts", [])
            if p.get("manual_only") or p.get("status") == "manual_only"
        ]
        if manual_copy:
            platforms = list(dict.fromkeys(
                p.get("platform", "unknown") for p in manual_copy
            ))
            return f"Social: Manual-copy drafts for {', '.join(platforms)}"

        if social.get("skipped"):
            return f"Social: Skipped - {social.get('reason', 'unknown reason')}"

        errors = social.get("errors") or []
        if errors:
            return f"Social: Error - {errors[0]}"

        if social.get("kill_day"):
            return "Social: Kill day"

        if social.get("publish_mode") == "manual_only":
            return "Social: Manual-only, no approved drafts"

        return "Social: No posts"

    def _latest_source_health_state(self, date_str: str) -> dict | None:
        """Load the latest preflight source-health trace for the requested day."""
        traces_path = PROJECT_ROOT / "data" / "ramsay" / "traces.db"
        if not traces_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(traces_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT payload FROM events WHERE event_type = ? "
                "ORDER BY id DESC LIMIT 20",
                ("preflight_complete",),
            ).fetchall()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to read source health from traces: {e}")
            return None

        for row in rows:
            try:
                payload = json.loads(row["payload"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue

            payload_date = payload.get("run_date")
            if payload_date and payload_date != date_str:
                continue

            if payload.get("source_health_summary") or payload.get("source_health"):
                return {
                    "summary": payload.get("source_health_summary") or {},
                    "health": payload.get("source_health") or {},
                }

        return None

    def _format_source_health_state(self, state: dict | None) -> list[str]:
        """Format source health without raw stderr or per-item content."""
        if not state:
            return []

        summary = state.get("summary") or {}
        health = state.get("health") or {}
        lines = []

        responsive = summary.get("responsive_source_count")
        expected = summary.get("expected_source_count")
        if responsive is not None and expected is not None:
            lines.append(f"Sources: {responsive}/{expected} responsive")

        unavailable = summary.get("unavailable_sources") or []
        if unavailable:
            lines.append(f"Unavailable: {', '.join(unavailable)}")

        degraded = summary.get("degraded_sources") or []
        if degraded:
            parts = []
            for source in degraded:
                status = (health.get(source) or {}).get("status", "failed")
                parts.append(f"{source} ({status})")
            lines.append(f"Degraded: {', '.join(parts)}")

        return lines

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

            lines.extend(
                self._format_source_health_state(
                    self._latest_source_health_state(date_str)
                )
            )

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
        social_line = self._format_social_state(social)
        if social_line:
            lines.append(social_line)

        lines.extend(self._format_source_health_state({
            "summary": results.get("source_health_summary") or {},
            "health": results.get("source_health") or {},
        }))

        verdict = social.get("expeditor_verdict", "")
        if verdict:
            lines.append(f"Expeditor: {verdict}")

        self.reply("\n".join(lines))

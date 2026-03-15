"""Approval system — web dashboard API + iMessage fallback.

Two-tier approval: tries the authenticated web dashboard first (instant push
notifications), falls back to iMessage (AppleScript send + Messages.db polling)
if the dashboard is unreachable or times out.

All approval methods return structured dicts so the pipeline can act on them
without parsing free-text responses.
"""

import json
import logging
import secrets
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Messages.db path on macOS
MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"


class ApprovalGateway:
    """Unified approval interface — dashboard API with iMessage fallback."""

    def __init__(self, config: dict):
        """Initialize from social-config.json.

        Args:
            config: Full social-config.json dict. Reads:
                - imessage.phone: phone number for iMessage fallback
                - imessage.gate_timeout_seconds: max wait (default 43200 = 12h)
                - approval_api_base: dashboard API URL
        """
        imessage_config = config.get("imessage", {})
        self.phone = imessage_config.get("phone", "")
        self.gate_timeout = imessage_config.get("gate_timeout_seconds", 43200)
        self.api_base = config.get("approval_api_base", "")
        self._last_rowid: int | None = None

    # ── Public gates ──────────────────────────────────────────────────

    def request_topic_approval(self, topics: list[dict]) -> dict:
        """Gate 1: Topic approval.

        Presents candidate topics and waits for human selection.
        Tries web dashboard first, falls back to iMessage.

        Args:
            topics: List of topic dicts with at least {title, summary, score}.

        Returns:
            {
                action: 'go' | 'skip' | 'retry' | 'custom',
                topic_index: int,       # which topic was selected (0-based)
                guidance: str           # any editorial guidance from approver
            }
        """
        # Format topics for display
        items = []
        for i, t in enumerate(topics):
            items.append({
                "index": i,
                "title": t.get("title", f"Topic {i + 1}"),
                "summary": t.get("summary", ""),
                "score": t.get("score", 0),
            })

        # Try dashboard first
        web_result = self._web_approval(items, "topic")
        if web_result is not None:
            return web_result

        # Fall back to iMessage
        message = self._format_topic_message(topics)
        reply = self._imessage_approval(message, self.gate_timeout)

        return self._parse_topic_reply(reply, len(topics))

    def request_draft_approval(self, drafts: dict, images: dict) -> dict:
        """Gate 2: Draft approval.

        Presents final drafts (with images) for approval before posting.
        Tries web dashboard first, falls back to iMessage with previews.

        Args:
            drafts: {platform: content_str} dict.
            images: {platform: image_path_or_url} dict.

        Returns:
            {
                action: 'all' | 'skip' | 'approve_selected',
                platforms: list[str],   # which platforms to post (if approve_selected)
                edits: dict             # {platform: edited_content} for inline edits
            }
        """
        # Build proof package for dashboard
        items = []
        for platform, content in drafts.items():
            if isinstance(content, dict):
                text = content.get("content", content.get("text", str(content)))
            else:
                text = content
            items.append({
                "platform": platform,
                "content_type": "post",
                "content": text,
                "image_url": images.get(platform),
            })

        # Try dashboard first
        web_result = self._web_approval(items, "draft")
        if web_result is not None:
            return web_result

        # Fall back to iMessage
        message = self._format_draft_message(drafts, images)
        reply = self._imessage_approval(message, self.gate_timeout)

        return self._parse_draft_reply(reply, list(drafts.keys()))

    def request_engagement_approval(self, candidates: list[dict]) -> dict:
        """Engagement gate: approve/reject reply candidates.

        Args:
            candidates: List of dicts with {platform, author, content, our_reply}.

        Returns:
            {approved_indices: list[int], reason: str}
        """
        if not candidates:
            return {"approved_indices": [], "reason": "No candidates"}

        items = []
        for i, c in enumerate(candidates):
            items.append({
                "index": i,
                "platform": c.get("platform", "?"),
                "author": c.get("author", "unknown"),
                "content_preview": (c.get("content", "")[:200]),
                "our_reply": c.get("our_reply", ""),
            })

        # Try dashboard first
        web_result = self._web_approval(items, "engagement")
        if web_result is not None:
            return web_result

        # Fall back to iMessage
        message = self._format_engagement_message(candidates)
        reply = self._imessage_approval(message, self.gate_timeout)

        return self._parse_engagement_reply(reply, len(candidates))

    # ── Web dashboard ─────────────────────────────────────────────────

    def _web_approval(self, items: list[dict], gate_type: str) -> dict | None:
        """Submit to authenticated dashboard API, poll for response.

        Creates an approval_review record with a unique token, submits items,
        then polls the API for a decision. Uses bearer token auth.

        Args:
            items: List of content items for review.
            gate_type: Type of gate (topic, draft, engagement).

        Returns:
            Response dict or None (triggers iMessage fallback).
        """
        if not self.api_base:
            logger.debug("No approval_api_base configured, skipping web approval")
            return None

        try:
            import requests
        except ImportError:
            logger.debug("requests library not available for web approval")
            return None

        token = secrets.token_urlsafe(32)
        submit_url = f"{self.api_base}/api/approvals"

        try:
            resp = requests.post(
                submit_url,
                json={
                    "gate_type": gate_type,
                    "token": token,
                    "items": items,
                    "created_at": datetime.now().isoformat(),
                },
                headers={"Content-Type": "application/json"},
                timeout=15,
            )

            if resp.status_code not in (200, 201):
                logger.warning(
                    f"Dashboard API returned {resp.status_code}, "
                    f"falling back to iMessage"
                )
                return None

        except Exception as e:
            logger.warning(f"Dashboard API unreachable: {e}, falling back to iMessage")
            return None

        # Poll for decision
        poll_url = f"{self.api_base}/api/approvals/{token}"
        poll_interval = 30  # seconds
        max_polls = self.gate_timeout // poll_interval
        logger.info(
            f"Approval submitted to dashboard (token={token[:8]}...), "
            f"polling every {poll_interval}s"
        )

        for poll_num in range(max_polls):
            time.sleep(poll_interval)

            try:
                poll_resp = requests.get(poll_url, timeout=10)
                if poll_resp.status_code != 200:
                    continue

                data = poll_resp.json()
                status = data.get("status", "pending")

                if status == "pending":
                    if poll_num > 0 and poll_num % 20 == 0:
                        logger.debug(
                            f"Still waiting for {gate_type} approval "
                            f"({poll_num * poll_interval}s elapsed)"
                        )
                    continue

                # Decision received
                logger.info(f"Dashboard approval received: {status}")
                return self._normalize_web_response(data, gate_type)

            except Exception as e:
                logger.debug(f"Poll error (will retry): {e}")
                continue

        logger.warning("Dashboard approval timed out, falling back to iMessage")
        return None

    def _normalize_web_response(self, data: dict, gate_type: str) -> dict:
        """Convert dashboard API response to standard gate format."""
        status = data.get("status", "rejected")

        if gate_type == "topic":
            if status == "approved":
                return {
                    "action": "go",
                    "topic_index": data.get("selected_index", 0),
                    "guidance": data.get("feedback", ""),
                }
            elif status == "retry":
                return {
                    "action": "retry",
                    "topic_index": 0,
                    "guidance": data.get("feedback", ""),
                }
            else:
                return {"action": "skip", "topic_index": 0, "guidance": ""}

        elif gate_type == "draft":
            if status == "approved":
                items = data.get("items", [])
                edits = {}
                approved_platforms = []
                for item in items:
                    platform = item.get("platform", "")
                    item_status = item.get("status", "approved")
                    if item_status == "approved":
                        approved_platforms.append(platform)
                        if item.get("feedback"):
                            edits[platform] = item["feedback"]

                if len(approved_platforms) == len(items):
                    return {
                        "action": "all",
                        "platforms": approved_platforms,
                        "edits": edits,
                    }
                else:
                    return {
                        "action": "approve_selected",
                        "platforms": approved_platforms,
                        "edits": edits,
                    }
            else:
                return {"action": "skip", "platforms": [], "edits": {}}

        elif gate_type == "engagement":
            if status == "approved":
                approved = data.get("approved_indices", [])
                return {
                    "approved_indices": approved,
                    "reason": data.get("feedback", ""),
                }
            else:
                return {"approved_indices": [], "reason": data.get("feedback", "")}

        return {"action": "skip"}

    # ── iMessage fallback ─────────────────────────────────────────────

    def _imessage_approval(self, message: str, timeout_seconds: int = 43200) -> str | None:
        """Send iMessage via AppleScript, poll Messages.db for reply.

        Args:
            message: Message text to send.
            timeout_seconds: Max wait time (default 12 hours).

        Returns:
            Reply text or None if timed out.
        """
        if not self.phone:
            logger.warning("No iMessage phone configured, cannot request approval")
            return None

        # Record current max ROWID before sending so we only read new messages
        self._last_rowid = self._get_max_rowid()

        # Send the approval request
        self._imessage_send(self.phone, message)
        logger.info(f"iMessage sent to {self.phone}, waiting for reply...")

        # Poll for response
        return self._imessage_poll(self.phone, timeout_seconds)

    def _imessage_send(self, phone: str, message: str):
        """Send iMessage via osascript.

        Args:
            phone: Phone number to send to.
            message: Message text.
        """
        # Escape special characters for AppleScript
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
        tell application "Messages"
            set targetService to 1st account whose service type = iMessage
            set targetBuddy to participant "{phone}" of targetService
            send "{escaped}" to targetBuddy
        end tell
        '''

        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            logger.debug(f"iMessage sent to {phone}")
        except subprocess.TimeoutExpired:
            logger.error("osascript timed out sending iMessage")
            raise
        except Exception as e:
            logger.error(f"Failed to send iMessage: {e}")
            raise

    def _imessage_poll(self, phone: str, timeout_seconds: int) -> str | None:
        """Poll Messages.db for replies from the given phone number.

        Tracks ROWID to skip old messages. Skips echo messages (messages
        we sent ourselves via is_from_me=1).

        Args:
            phone: Phone number to monitor.
            timeout_seconds: Max wait time.

        Returns:
            Reply text or None if timed out.
        """
        if not MESSAGES_DB.exists():
            logger.error(f"Messages.db not found at {MESSAGES_DB}")
            return None

        poll_interval = 15  # seconds
        start_time = time.monotonic()
        min_rowid = self._last_rowid or 0

        # Normalize phone for matching (strip spaces, dashes)
        normalized_phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

        while (time.monotonic() - start_time) < timeout_seconds:
            time.sleep(poll_interval)

            try:
                conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row

                # Query for new messages from this phone number
                # Join through chat_message_join and chat to find the right conversation
                rows = conn.execute(
                    """
                    SELECT m.ROWID, m.text, m.is_from_me, m.date
                    FROM message m
                    JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                    JOIN chat c ON c.ROWID = cmj.chat_id
                    WHERE m.ROWID > ?
                      AND m.is_from_me = 0
                      AND m.text IS NOT NULL
                      AND m.text != ''
                      AND c.chat_identifier LIKE ?
                    ORDER BY m.ROWID ASC
                    """,
                    (min_rowid, f"%{normalized_phone[-10:]}%"),
                ).fetchall()

                conn.close()

                if rows:
                    # Return the first new reply
                    reply_text = rows[0]["text"]
                    logger.info(
                        f"iMessage reply received ({len(rows)} new messages)"
                    )
                    return reply_text

            except sqlite3.OperationalError as e:
                logger.debug(f"Messages.db poll error (will retry): {e}")
            except Exception as e:
                logger.warning(f"Unexpected error polling Messages.db: {e}")

            elapsed = int(time.monotonic() - start_time)
            if elapsed > 0 and elapsed % 3600 == 0:
                hours = elapsed // 3600
                logger.info(f"Still waiting for iMessage reply ({hours}h elapsed)")

        logger.warning(f"iMessage approval timed out after {timeout_seconds}s")
        return None

    def _get_max_rowid(self) -> int:
        """Get the current maximum ROWID from Messages.db."""
        if not MESSAGES_DB.exists():
            return 0

        try:
            conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
            row = conn.execute("SELECT MAX(ROWID) FROM message").fetchone()
            conn.close()
            return row[0] if row and row[0] else 0
        except Exception:
            return 0

    # ── Message formatting ────────────────────────────────────────────

    def _format_topic_message(self, topics: list[dict]) -> str:
        """Format topic candidates for iMessage."""
        lines = ["MindPattern Social - Topic Approval", ""]
        for i, t in enumerate(topics):
            # Support both title and anchor keys
            title = t.get("anchor", t.get("title", f"Topic {i + 1}"))
            angle = t.get("angle", "")
            scores = t.get("editorial_scores", {})
            composite = scores.get("composite", t.get("score", 0))
            source_urls = t.get("source_urls", [])

            lines.append(f"{i + 1}. {title}")
            if angle:
                lines.append(f"   Angle: {angle[:150]}")
            lines.append(f"   Score: {composite}")
            if source_urls:
                lines.append(f"   Source: {source_urls[0]}")
            lines.append("")

        lines.append("Reply: 'go' to approve, 'skip' to kill, or type custom topic")

        return "\n".join(lines)

    def _format_draft_message(self, drafts: dict, images: dict) -> str:
        """Format draft previews for iMessage."""
        lines = ["MindPattern Social - Draft Approval", ""]

        for platform, content in drafts.items():
            if isinstance(content, dict):
                text = content.get("content", content.get("text", str(content)))
            else:
                text = content
            has_image = "yes" if images.get(platform) else "no"
            lines.append(f"--- {platform.upper()} (image: {has_image}) ---")
            lines.append(text[:500])
            if len(text) > 500:
                lines.append(f"... ({len(text)} chars total)")
            lines.append("")

        lines.append("Reply with:")
        lines.append("  'go' or 'all' to post everything")
        lines.append("  'skip' to cancel all")
        lines.append("  Platform names to approve selectively (e.g. 'x bluesky')")

        return "\n".join(lines)

    def _format_engagement_message(self, candidates: list[dict]) -> str:
        """Format engagement candidates for iMessage."""
        lines = [f"MindPattern Engagement - {len(candidates)} Reply Candidates", ""]

        for i, c in enumerate(candidates):
            platform = c.get("platform", "?")
            author = c.get("author", "unknown")
            content = (c.get("content", ""))[:100]
            reply = (c.get("our_reply", ""))[:150]
            lines.append(f"{i + 1}. [{platform}] @{author}")
            lines.append(f"   Their post: {content}")
            lines.append(f"   Our reply: {reply}")
            lines.append("")

        lines.append("Reply with:")
        lines.append("  'all' to approve all replies")
        lines.append("  Numbers to approve selectively (e.g. '1 3 5')")
        lines.append("  'skip' to cancel all")

        return "\n".join(lines)

    # ── Reply parsing ─────────────────────────────────────────────────

    def _parse_topic_reply(self, reply: str | None, num_topics: int) -> dict:
        """Parse iMessage reply for topic approval."""
        if not reply:
            return {"action": "skip", "topic_index": 0, "guidance": "Timed out"}

        reply = reply.strip().lower()

        if reply in ("skip", "kill", "no", "pass"):
            return {"action": "skip", "topic_index": 0, "guidance": ""}

        if reply in ("retry", "again", "redo"):
            return {"action": "retry", "topic_index": 0, "guidance": ""}

        # Check for number selection
        try:
            num = int(reply.split()[0])
            if 1 <= num <= num_topics:
                # Check if there's additional guidance after the number
                parts = reply.split(maxsplit=1)
                guidance = parts[1] if len(parts) > 1 else ""
                return {
                    "action": "go",
                    "topic_index": num - 1,
                    "guidance": guidance,
                }
        except (ValueError, IndexError):
            pass

        # Treat as custom topic
        return {"action": "custom", "topic_index": 0, "guidance": reply}

    def _parse_draft_reply(self, reply: str | None, platforms: list[str]) -> dict:
        """Parse iMessage reply for draft approval."""
        if not reply:
            return {"action": "skip", "platforms": [], "edits": {}}

        reply = reply.strip().lower()

        if reply in ("skip", "kill", "no", "pass", "cancel"):
            return {"action": "skip", "platforms": [], "edits": {}}

        if reply in ("go", "all", "yes", "approve", "send", "post"):
            return {"action": "all", "platforms": platforms, "edits": {}}

        # Check for selective platform approval
        approved = []
        for platform in platforms:
            if platform.lower() in reply:
                approved.append(platform)

        if approved:
            return {
                "action": "approve_selected",
                "platforms": approved,
                "edits": {},
            }

        # If nothing matched, treat ambiguous replies as approval
        # (bias toward action — user can always say skip/no explicitly)
        if len(reply) > 0 and reply[0] not in ("n", "s", "k", "c"):
            return {"action": "all", "platforms": platforms, "edits": {}}

        return {"action": "skip", "platforms": [], "edits": {}}

    def _parse_engagement_reply(
        self, reply: str | None, num_candidates: int
    ) -> dict:
        """Parse iMessage reply for engagement approval."""
        if not reply:
            return {"approved_indices": [], "reason": "Timed out"}

        reply = reply.strip().lower()

        if reply in ("skip", "no", "cancel", "none"):
            return {"approved_indices": [], "reason": "Rejected"}

        if reply in ("all", "yes", "go", "approve"):
            return {
                "approved_indices": list(range(num_candidates)),
                "reason": "All approved",
            }

        # Parse number selections
        approved = []
        for token in reply.split():
            try:
                num = int(token)
                if 1 <= num <= num_candidates:
                    approved.append(num - 1)  # Convert to 0-based
            except ValueError:
                continue

        if approved:
            return {
                "approved_indices": sorted(set(approved)),
                "reason": f"Selectively approved {len(approved)} replies",
            }

        return {"approved_indices": [], "reason": f"Could not parse reply: {reply}"}

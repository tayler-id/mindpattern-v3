"""Approval system — Slack only.

Posts approval requests to Slack #mindpattern-approvals channel and polls
for threaded replies. If Slack is unavailable, logs an error and returns
a timeout/skip result.

All approval methods return structured dicts so the pipeline can act on them
without parsing free-text responses.
"""

import json
import logging
import secrets
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

# Slack config
SLACK_CHANNEL = "C0ALSRHAATH"  # #mindpattern-approvals
SLACK_KEYCHAIN_KEY = "slack-bot-token"

# Safety cap: approval polls must terminate even if no explicit timeout
# is configured.  Prevents indefinite pipeline blocks (see 2026-04-01-006).
DEFAULT_MAX_TIMEOUT = 4 * 3600  # 4 hours in seconds


class ApprovalGateway:
    """Unified approval interface — Slack only."""

    def __init__(self, config: dict):
        """Initialize from social-config.json.

        Args:
            config: Full social-config.json dict. Reads:
                - gate_timeout_seconds: max wait (None = wait forever)
                - approval_api_base: dashboard API URL
        """
        self.gate_timeout = config.get("gate_timeout_seconds", None)
        self.api_base = config.get("approval_api_base", "")
        self.thread_ts = None  # Shared thread for all gates in one pipeline run

    # ── Public gates ──────────────────────────────────────────────────

    def notify(self, message: str) -> None:
        """Post a notification to the approvals channel (no reply expected)."""
        token = self._get_slack_token()
        if not token:
            logger.warning("No Slack token — skipping notification")
            return
        self._slack_post(token, message, thread_ts=self.thread_ts)

    def request_topic_approval(self, topics: list[dict]) -> dict:
        """Gate 1: Topic approval.

        Presents candidate topics and waits for human selection via Slack.

        Args:
            topics: List of topic dicts with at least {title, summary, score}.

        Returns:
            {
                action: 'go' | 'skip' | 'retry' | 'custom',
                topic_index: int,       # which topic was selected (0-based)
                guidance: str           # any editorial guidance from approver
            }
        """
        message = self._format_topic_message(topics)
        reply = self._slack_approval(message, self.gate_timeout)
        return self._parse_topic_reply(reply, len(topics))

    def request_draft_approval(self, drafts: dict, images: dict) -> dict:
        """Gate 2: Draft approval.

        Presents final drafts (with images) for approval before posting via Slack.

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
        message = self._format_draft_message(drafts, images)
        reply = self._slack_approval(message, self.gate_timeout)
        return self._parse_draft_reply(reply, list(drafts.keys()))

    def request_engagement_approval(self, candidates: list[dict]) -> dict:
        """Engagement gate: approve/reject reply candidates via Slack.

        Args:
            candidates: List of dicts with {platform, author, content, our_reply}.

        Returns:
            {approved_indices: list[int], reason: str}
        """
        if not candidates:
            return {"approved_indices": [], "reason": "No candidates"}

        message = self._format_engagement_message(candidates)
        reply = self._slack_approval(message, self.gate_timeout)
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
            Response dict or None if dashboard is unavailable.
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
                    f"Dashboard API returned {resp.status_code}"
                )
                return None

        except Exception as e:
            logger.warning(f"Dashboard API unreachable: {e}")
            return None

        # Poll for decision
        poll_url = f"{self.api_base}/api/approvals/{token}"
        poll_interval = 30  # seconds
        logger.info(
            f"Approval submitted to dashboard (token={token[:8]}...), "
            f"polling every {poll_interval}s"
        )

        poll_num = 0
        effective_timeout = self.gate_timeout if self.gate_timeout is not None else DEFAULT_MAX_TIMEOUT
        start_time = time.monotonic()

        while True:
            time.sleep(poll_interval)

            # Safety cap — prevent indefinite blocking
            if (time.monotonic() - start_time) >= effective_timeout:
                logger.warning(
                    f"Web approval timed out after {effective_timeout}s "
                    f"for {gate_type} gate — returning None to unblock pipeline"
                )
                return None

            try:
                poll_resp = requests.get(poll_url, timeout=10)
                if poll_resp.status_code != 200:
                    poll_num += 1
                    continue

                data = poll_resp.json()
                status = data.get("status", "pending")

                if status == "pending":
                    if poll_num > 0 and poll_num % 20 == 0:
                        logger.debug(
                            f"Still waiting for {gate_type} approval "
                            f"({poll_num * poll_interval}s elapsed)"
                        )
                    poll_num += 1
                    continue

                # Decision received
                logger.info(f"Dashboard approval received: {status}")
                return self._normalize_web_response(data, gate_type)

            except Exception as e:
                logger.debug(f"Poll error (will retry): {e}")
                poll_num += 1
                continue

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

    # ── Slack approval (primary) ─────────────────────────────────────

    def _get_slack_token(self) -> str | None:
        """Get Slack bot token from macOS Keychain."""
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", SLACK_KEYCHAIN_KEY, "-w"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Keychain Slack token lookup failed: {e}")
        return None

    def _slack_post(self, token: str, text: str, thread_ts: str | None = None) -> dict | None:
        """Post a message to the Slack approvals channel.

        Returns the Slack API response dict with 'ts' (message timestamp) on success.
        """
        payload = {
            "channel": SLACK_CHANNEL,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode())
                if result.get("ok"):
                    return result
                logger.warning(f"Slack post failed: {result.get('error')}")
                return None
        except Exception as e:
            logger.warning(f"Slack post error: {e}")
            return None

    def _slack_poll_replies(self, token: str, after_ts: str, timeout_seconds: int | None = None) -> str | None:
        """Poll Slack channel for any reply after a specific message.

        Accepts both threaded replies AND new channel messages posted after
        the bot's message. Ignores bot messages (only human replies count).

        Args:
            token: Slack bot token.
            after_ts: Timestamp of the bot's message to look for replies after.
            timeout_seconds: Max wait time. None means wait forever.

        Returns:
            First human reply text, or None if timed out.
        """
        poll_interval = 10
        start_time = time.monotonic()
        # Use the shared thread parent for fetching thread replies,
        # but only accept replies with ts > after_ts
        thread_parent = self.thread_ts or after_ts

        while True:
            time.sleep(poll_interval)

            try:
                # Check for threaded replies first
                params = urllib.parse.urlencode({
                    "channel": SLACK_CHANNEL,
                    "ts": thread_parent,
                    "limit": 20,
                })
                req = urllib.request.Request(
                    f"https://slack.com/api/conversations.replies?{params}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode())

                if result.get("ok"):
                    messages = result.get("messages", [])
                    # Only consider replies posted AFTER our specific message
                    replies = [
                        m for m in messages[1:]
                        if m.get("text") and not m.get("bot_id")
                        and m.get("ts", "0") > after_ts
                    ]
                    if replies:
                        reply_text = replies[0]["text"]
                        logger.info(f"Slack threaded reply: {reply_text[:50]}")
                        return reply_text

                # Also check for new channel messages after our post
                params = urllib.parse.urlencode({
                    "channel": SLACK_CHANNEL,
                    "oldest": after_ts,
                    "limit": 10,
                })
                req = urllib.request.Request(
                    f"https://slack.com/api/conversations.history?{params}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read().decode())

                if result.get("ok"):
                    messages = result.get("messages", [])
                    # Find human messages posted AFTER our bot message
                    for m in messages:
                        if m.get("ts", "0") > after_ts and not m.get("bot_id") and m.get("text"):
                            reply_text = m["text"]
                            logger.info(f"Slack channel reply: {reply_text[:50]}")
                            return reply_text

            except Exception as e:
                logger.debug(f"Slack poll error (will retry): {e}")

            elapsed = int(time.monotonic() - start_time)
            if elapsed > 0 and elapsed % 3600 == 0:
                hours = elapsed // 3600
                logger.info(f"Still waiting for Slack reply ({hours}h elapsed)")

            # Explicit timeout
            if timeout_seconds is not None and (time.monotonic() - start_time) >= timeout_seconds:
                logger.warning(f"Slack approval timed out after {timeout_seconds}s")
                return None

            # Safety cap — prevents indefinite blocking when no timeout configured
            if timeout_seconds is None and (time.monotonic() - start_time) >= DEFAULT_MAX_TIMEOUT:
                logger.warning(
                    f"Slack approval hit default max timeout "
                    f"({DEFAULT_MAX_TIMEOUT}s) — returning None to unblock pipeline"
                )
                return None

    def _slack_approval(self, message: str, timeout_seconds: int | None = None) -> str | None:
        """Send approval request to Slack, poll for threaded reply.

        All gates in a single pipeline run share one thread. Gate 1 creates
        the parent message; Gate 2+ reply in that thread so the full
        conversation stays in one place.
        """
        token = self._get_slack_token()
        if not token:
            logger.error("No Slack token in Keychain — cannot request approval")
            return None

        # Post in existing thread if we have one (Gate 2+ replies to Gate 1)
        result = self._slack_post(token, message, thread_ts=self.thread_ts)
        if not result:
            logger.error("Slack post failed — cannot request approval")
            return None

        msg_ts = result.get("message", {}).get("ts") or result.get("ts")
        if not msg_ts:
            logger.error("No thread_ts from Slack — cannot poll for reply")
            return None

        # Save the parent thread_ts from the first gate
        if self.thread_ts is None:
            self.thread_ts = msg_ts

        # Poll for replies after THIS message, not the thread parent.
        # Otherwise Gate 2 picks up Gate 1's reply immediately.
        logger.info(f"Slack approval posted to #mindpattern-approvals, waiting for reply...")
        return self._slack_poll_replies(token, msg_ts, timeout_seconds)

    # ── Message formatting ────────────────────────────────────────────

    def _format_topic_message(self, topics: list[dict]) -> str:
        """Format topic candidates for Slack approval message."""
        lines = ["MindPattern Social - Topic Approval", ""]
        for i, t in enumerate(topics):
            # Support both title and anchor keys
            anchor = t.get("anchor", t.get("title", f"Topic {i + 1}"))
            angle = t.get("angle", "")
            scores = t.get("editorial_scores", {})
            composite = scores.get("composite", t.get("score", 0))
            source_urls = t.get("source_urls", [])
            reasoning = t.get("reasoning", "")

            lines.append(f"{i + 1}. {anchor}")
            if angle:
                lines.append(f"   Angle: {angle[:200]}")
            lines.append(f"   Score: {composite}")
            if source_urls:
                sources_str = ", ".join(source_urls[:3])
                lines.append(f"   Sources: {sources_str}")
            if reasoning:
                lines.append(f"   Reasoning: {reasoning[:200]}")
            lines.append("")

        lines.append("Reply GO to approve, SKIP to kill, or type a custom topic")

        return "\n".join(lines)

    def _format_draft_message(self, drafts: dict, images: dict) -> str:
        """Format draft previews for Slack approval message."""
        lines = ["MindPattern Social - Draft Approval", ""]

        for platform, content in drafts.items():
            if isinstance(content, dict):
                text = content.get("content", content.get("text", str(content)))
            else:
                text = content
            has_image = "yes" if images.get(platform) else "no"
            lines.append(f"--- {platform.upper()} (image: {has_image}) ---")
            truncated = text[:500]
            lines.append(truncated)
            if len(text) > 500:
                lines.append(f"... ({len(text)} chars total)")
            lines.append("")

        lines.append("Reply ALL to post all, SKIP to reject, or name platforms (e.g. 'bluesky linkedin')")

        return "\n".join(lines)

    def _format_engagement_message(self, candidates: list[dict]) -> str:
        """Format engagement candidates for Slack approval message."""
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
        """Parse reply for topic approval."""
        if not reply:
            return {"action": "skip", "topic_index": 0, "guidance": "Timed out"}

        original = reply.strip()
        lower = original.lower()

        if lower in ("skip", "kill", "no", "pass"):
            return {"action": "skip", "topic_index": 0, "guidance": ""}

        if lower in ("go", "yes", "approve", "ok", "approved"):
            return {"action": "go", "topic_index": 0, "guidance": ""}

        if lower in ("retry", "again", "redo"):
            return {"action": "retry", "topic_index": 0, "guidance": ""}

        # Check for number selection
        try:
            num = int(lower.split()[0])
            if 1 <= num <= num_topics:
                parts = original.split(maxsplit=1)
                guidance = parts[1] if len(parts) > 1 else ""
                return {
                    "action": "go",
                    "topic_index": num - 1,
                    "guidance": guidance,
                }
        except (ValueError, IndexError):
            pass

        # Anything else = custom topic (preserve original case)
        return {"action": "custom", "topic_index": 0, "guidance": original}

    def _parse_draft_reply(self, reply: str | None, platforms: list[str]) -> dict:
        """Parse reply for draft approval."""
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
        """Parse reply for engagement approval."""
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

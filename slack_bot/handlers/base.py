"""Base handler for all Slack channel handlers.

Every channel handler inherits from BaseHandler and gets:
- reply(text, thread_ts): post a message (optionally threaded)
- react(emoji, ts): add a reaction to a message
- get_thread_replies(thread_ts): fetch replies in a thread
- wait_for_reply(thread_ts, timeout): poll for human reply in thread

Subclasses implement handle(event) which is called when a message
arrives in their registered channel.
"""

import logging
import re
import subprocess
import time
from urllib.parse import urlparse

from slack_sdk import WebClient

logger = logging.getLogger(__name__)

# Matches http/https URLs in message text
URL_PATTERN = re.compile(r"https?://[^\s>]+")


class BaseHandler:
    """Base class for all channel handlers."""

    def __init__(self, client: WebClient, channel_id: str, owner_user_id: str):
        self.client = client
        self.channel_id = channel_id
        self.owner_user_id = owner_user_id

    def handle(self, event: dict) -> None:
        """Process an incoming message event. Override in subclasses."""
        raise NotImplementedError

    # ── Slack helpers ──────────────────────────────────────────────

    def reply(self, text: str, thread_ts: str | None = None) -> dict | None:
        """Post a message to this handler's channel, optionally in a thread."""
        try:
            return self.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.error(f"Failed to post message to {self.channel_id}: {e}")
            return None

    def react(self, emoji: str, ts: str) -> None:
        """Add an emoji reaction to a message."""
        try:
            self.client.reactions_add(
                channel=self.channel_id, name=emoji, timestamp=ts,
            )
        except Exception as e:
            logger.debug(f"Failed to add reaction {emoji}: {e}")

    def get_thread_replies(self, thread_ts: str) -> list[dict]:
        """Fetch all replies in a thread, excluding bot messages."""
        try:
            resp = self.client.conversations_replies(
                channel=self.channel_id, ts=thread_ts,
            )
        except Exception as e:
            logger.error(f"Failed to fetch thread replies for {thread_ts}: {e}")
            return []
        messages = resp.get("messages", [])
        # Filter out bot messages and the original post
        return [
            m for m in messages
            if m.get("ts") != thread_ts and not m.get("bot_id")
        ]

    def wait_for_reply(
        self, thread_ts: str, timeout: int = 300, poll_interval: int = 5
    ) -> str | None:
        """Poll for a human reply in a thread. Returns reply text or None on timeout.

        Args:
            thread_ts: Thread timestamp to poll.
            timeout: Max wait in seconds. Defaults to 300 (5 min).
            poll_interval: Seconds between polls.
        """
        start = time.monotonic()
        seen_ts = set()
        while True:
            time.sleep(poll_interval)
            replies = self.get_thread_replies(thread_ts)
            for r in replies:
                if r["ts"] not in seen_ts:
                    seen_ts.add(r["ts"])
                    user = r.get("user", "")
                    if user == self.owner_user_id:
                        return r.get("text", "").strip()
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return None

    # ── URL helpers ────────────────────────────────────────────────

    @staticmethod
    def extract_urls(text: str) -> list[str]:
        """Extract URLs from message text. Handles Slack's <url> formatting."""
        # Slack wraps URLs in angle brackets: <https://example.com>
        # Sometimes with display text: <https://example.com|example.com>
        urls = []
        for match in re.finditer(r"<(https?://[^|>]+)(?:\|[^>]*)?>", text):
            urls.append(match.group(1))
        # Also catch bare URLs not in angle brackets
        for match in URL_PATTERN.finditer(text):
            url = match.group(0)
            if url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Check if a string is a valid HTTP(S) URL."""
        try:
            result = urlparse(url)
            return result.scheme in ("http", "https") and bool(result.netloc)
        except Exception:
            return False

    @staticmethod
    def read_url(url: str, timeout: int = 30) -> str | None:
        """Read a URL's content using Jina Reader. Returns markdown or None."""
        try:
            proc = subprocess.run(
                ["curl", "-sL", f"https://r.jina.ai/{url}"],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"Jina Reader timed out for {url}")
            return None
        except Exception as e:
            logger.error(f"Failed to read URL {url}: {e}")
            return None

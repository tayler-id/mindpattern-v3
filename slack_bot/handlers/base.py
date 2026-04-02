"""Base handler for all Slack channel handlers.

Every channel handler inherits from BaseHandler and gets:
- reply(text, thread_ts): post a message (optionally threaded)
- react(emoji, ts): add a reaction to a message
- get_thread_replies(thread_ts): fetch replies in a thread
- wait_for_reply(thread_ts, timeout): poll for human reply in thread

Subclasses implement handle(event) which is called when a message
arrives in their registered channel.
"""

import json
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

    def reply(self, text: str, thread_ts: str | None = None) -> dict:
        """Post a message to this handler's channel, optionally in a thread."""
        return self.client.chat_postMessage(
            channel=self.channel_id,
            text=text,
            thread_ts=thread_ts,
        )

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
        resp = self.client.conversations_replies(
            channel=self.channel_id, ts=thread_ts,
        )
        messages = resp.get("messages", [])
        # Filter out bot messages and the original post
        return [
            m for m in messages
            if m.get("ts") != thread_ts and not m.get("bot_id")
        ]

    def wait_for_reply(
        self, thread_ts: str, timeout: int | None = None, poll_interval: int = 5
    ) -> str | None:
        """Poll for a human reply in a thread. Returns reply text or None on timeout.

        Args:
            thread_ts: Thread timestamp to poll.
            timeout: Max wait in seconds. None means wait forever.
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
    def _is_jina_error(text: str) -> bool:
        """Detect Jina Reader error responses (JSON with error code)."""
        stripped = text.strip()
        if not stripped.startswith("{"):
            return False
        try:
            data = json.loads(stripped)
            return isinstance(data.get("code"), int) and data.get("code") >= 400
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def _read_url_direct(url: str, timeout: int = 30) -> str | None:
        """Fallback: scrape URL directly with a browser user-agent."""
        try:
            proc = subprocess.run(
                [
                    "curl", "-sL",
                    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "-H", "Accept: text/html",
                    url,
                ],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                # Strip HTML tags for a rough plaintext extraction
                import re as _re
                html = proc.stdout
                # Remove script/style blocks
                html = _re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=_re.DOTALL | _re.IGNORECASE)
                # Remove tags
                text = _re.sub(r"<[^>]+>", " ", html)
                # Collapse whitespace
                text = _re.sub(r"\s+", " ", text).strip()
                if len(text) > 200:
                    return text
            return None
        except Exception as e:
            logger.warning(f"Direct URL fetch failed for {url}: {e}")
            return None

    @classmethod
    def read_url(cls, url: str, timeout: int = 30) -> str | None:
        """Read a URL's content using Jina Reader, with direct fallback."""
        # Try Jina Reader first
        try:
            proc = subprocess.run(
                ["curl", "-sL", f"https://r.jina.ai/{url}"],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                if not cls._is_jina_error(proc.stdout):
                    return proc.stdout.strip()
                logger.warning(f"Jina Reader blocked for {url}, trying direct fetch")
        except subprocess.TimeoutExpired:
            logger.warning(f"Jina Reader timed out for {url}, trying direct fetch")
        except Exception as e:
            logger.warning(f"Jina Reader failed for {url}: {e}, trying direct fetch")

        # Fallback: direct scrape
        return cls._read_url_direct(url, timeout=timeout)

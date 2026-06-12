"""MindPattern Slack bot — Socket Mode daemon.

Listens to messages across registered channels and routes them
to the appropriate handler. Runs as a long-lived launchd daemon
alongside the daily pipeline.

Usage:
    python3 -m slack_bot.bot

Environment / Keychain:
    slack-bot-token   — Bot User OAuth Token (xoxb-...)
    slack-app-token   — App-Level Token (xapp-...) for Socket Mode
    slack-channel-config — JSON mapping channel names to IDs
"""

import logging
import os
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from slack_bot import heartbeat
from slack_bot.registry import _keychain_get, build_handlers

# Slack redelivers events on slow acks and reconnects — remember recently
# seen event ids for this long so a redelivery is processed exactly once.
EVENT_DEDUP_TTL_SECONDS = 300

logger = logging.getLogger("slack_bot")

# Mutex to prevent Claude CLI collisions with the daily pipeline
MUTEX_PATH = Path("/tmp/mindpattern-bot.mutex")
PIPELINE_LOCK = Path("/tmp/mindpattern-pipeline.lock")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _setup_logging():
    """Configure structured logging for the bot daemon."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    )
    logging.getLogger("slack_bot").setLevel(logging.INFO)
    logging.getLogger("slack_bot").addHandler(handler)
    # Quiet the slack_sdk logger
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)


def _get_owner_user_id(client: WebClient) -> str:
    """Get the bot installer's user ID (the owner)."""
    # The bot token's auth.test gives us the bot user ID, not the installer.
    # We store the owner's Slack user ID in Keychain.
    owner_id = _keychain_get("slack-owner-user-id")
    if owner_id:
        return owner_id

    # Fallback: environment variable
    owner_id = os.environ.get("MP_SLACK_OWNER_USER_ID", "")
    if owner_id:
        return owner_id

    logger.error(
        "No owner user ID configured — the bot FAILS CLOSED and will refuse "
        "all commands. Set 'slack-owner-user-id' in Keychain or "
        "MP_SLACK_OWNER_USER_ID in the environment."
    )
    return ""


def _acquire_mutex() -> bool:
    """Check if the daily pipeline is running. Returns True if safe to proceed."""
    if PIPELINE_LOCK.exists():
        try:
            pid = int(PIPELINE_LOCK.read_text().strip())
            # Check if the PID is still running
            os.kill(pid, 0)
            return False  # Pipeline is actively running
        except (ValueError, OSError):
            pass  # Stale lock or process not running
    return True


class MindPatternBot:
    """Socket Mode bot that routes messages to channel handlers."""

    def __init__(self):
        _setup_logging()

        # Load tokens
        bot_token = _keychain_get("slack-bot-token")
        app_token = _keychain_get("slack-app-token")

        if not bot_token:
            logger.error("No slack-bot-token found in Keychain")
            sys.exit(1)
        if not app_token:
            logger.error("No slack-app-token found in Keychain")
            sys.exit(1)

        self.web_client = WebClient(token=bot_token)
        self.socket_client = SocketModeClient(
            app_token=app_token,
            web_client=self.web_client,
            auto_reconnect_enabled=True,
            ping_interval=30,
        )

        # Get bot's own user ID (to ignore its own messages)
        auth = self.web_client.auth_test()
        self.bot_user_id = auth["user_id"]
        logger.info(f"Bot user ID: {self.bot_user_id}")

        # Get owner user ID (to filter messages)
        self.owner_user_id = _get_owner_user_id(self.web_client)
        if self.owner_user_id:
            logger.info(f"Owner user ID: {self.owner_user_id}")

        # Build handlers
        self.handlers = build_handlers(self.web_client, self.owner_user_id)
        logger.info(f"Loaded {len(self.handlers)} channel handlers")

        if not self.handlers:
            logger.error("No handlers loaded — check channel config")
            sys.exit(1)

        # Redelivered-event dedup: event id -> monotonic time first seen
        self._seen_events: dict[str, float] = {}

        # Handlers run long pipelines (claude -p calls). Dispatch on a
        # dedicated executor so they never block the Socket Mode pool.
        self._handler_executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="mp-handler"
        )

    def _handle_event(self, client: SocketModeClient, req: SocketModeRequest):
        """Route incoming Socket Mode events to handlers."""
        # Acknowledge immediately
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        logger.debug(f"Socket Mode event: type={req.type}")

        if req.type != "events_api":
            return

        event = req.payload.get("event", {})
        event_type = event.get("type")
        channel = event.get("channel", "")
        logger.info(f"Event received: type={event_type}, channel={channel}, user={event.get('user', '?')}, subtype={event.get('subtype', 'none')}")

        # Only handle message events (not message_changed, etc.)
        if event_type != "message" or event.get("subtype"):
            return

        # Dedup: Slack redelivers events on slow acks and reconnects.
        if self._is_duplicate_event(req, event):
            return

        # Thread replies are consumed by handlers' wait_for_reply() polling
        # (approvals, follow-ups). Routing them to handle() would start a
        # second pipeline on the approval text itself.
        if event.get("thread_ts") and event.get("thread_ts") != event.get("ts"):
            return

        # Ignore bot's own messages
        if event.get("user") == self.bot_user_id or event.get("bot_id"):
            return

        # Security: fail closed — no owner configured means no commands.
        if not self.owner_user_id:
            logger.warning("Refusing command: no owner user ID configured")
            return
        user = event.get("user", "")
        if user != self.owner_user_id:
            logger.debug(f"Ignoring message from non-owner user {user}")
            return

        # Route to the correct handler based on channel
        channel = event.get("channel", "")
        handler = self.handlers.get(channel)
        if not handler:
            return  # Message is in a channel we don't handle

        # Dispatch off the socket thread (claude -p calls run for minutes)
        self._handler_executor.submit(self._run_handler, handler, channel, event)

    def _is_duplicate_event(self, req: SocketModeRequest, event: dict) -> bool:
        """TTL-set dedup keyed by Slack's event id (channel:ts fallback)."""
        event_id = req.payload.get("event_id") or (
            f"{event.get('channel', '')}:{event.get('event_ts') or event.get('ts', '')}"
        )
        now = time.monotonic()
        self._seen_events = {
            k: v for k, v in self._seen_events.items()
            if now - v < EVENT_DEDUP_TTL_SECONDS
        }
        if event_id in self._seen_events:
            logger.info(f"Skipping duplicate event delivery: {event_id}")
            return True
        self._seen_events[event_id] = now
        return False

    def _run_handler(self, handler, channel: str, event: dict):
        """Execute a handler on the dispatch executor with error reporting."""
        try:
            handler.handle(event)
        except Exception as e:
            logger.error(f"Handler error in {channel}: {e}", exc_info=True)
            try:
                handler.reply(
                    f"Something went wrong: {e}",
                    thread_ts=event.get("thread_ts") or event.get("ts"),
                )
            except Exception:
                pass

    def run(self):
        """Start the Socket Mode connection and listen for events."""
        self.socket_client.socket_mode_request_listeners.append(self._handle_event)

        # Touch BEFORE connecting: the heartbeat file persists on the Fly
        # volume, so a stale leftover from before a restart must not 503
        # the machine into a restart loop while we reconnect.
        heartbeat.touch()

        logger.info("Connecting to Slack via Socket Mode...")
        self.socket_client.connect()
        logger.info("Connected. Listening for messages.")
        heartbeat.touch()

        # Keep the process alive; heartbeat ONLY while the socket is
        # actually connected, so a silently dead connection goes stale
        # and /healthz fails the Fly health check (2026-06-11 outage).
        try:
            while True:
                time.sleep(heartbeat.TOUCH_INTERVAL_SECONDS)
                if self.socket_client.is_connected():
                    heartbeat.touch()
                else:
                    logger.warning(
                        "Socket Mode disconnected — heartbeat withheld "
                        "(healthz will go stale and Fly will restart)"
                    )
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.socket_client.close()


def main():
    """Entry point for the Slack bot daemon."""
    # Handle SIGTERM gracefully (launchd sends this on stop)
    signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))

    bot = MindPatternBot()
    bot.run()


if __name__ == "__main__":
    main()

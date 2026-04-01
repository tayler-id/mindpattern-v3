"""#mp-approvals handler: pipeline approval gate proxy.

The daily pipeline posts approval requests to #mp-approvals.
This handler doesn't need to do anything special — the pipeline's
existing _slack_approval() already posts and polls this channel.

This handler exists so the bot acknowledges messages in this channel
rather than ignoring them silently.
"""

import logging

from slack_bot.handlers.base import BaseHandler

logger = logging.getLogger(__name__)


class ApprovalsHandler(BaseHandler):
    """Handle messages in #mp-approvals."""

    def handle(self, event: dict) -> None:
        """Acknowledge messages in the approvals channel.

        The pipeline's _slack_approval() handles the actual polling.
        This handler just provides help text if the user messages
        outside of an active approval flow.
        """
        text = event.get("text", "").strip().lower()
        ts = event.get("ts", "")
        thread_ts = event.get("thread_ts")

        # If this is a threaded reply, it's probably a response to a
        # pipeline approval request — let the pipeline's poll pick it up.
        if thread_ts:
            return

        # Top-level message in the channel — provide help
        if text in ("help", "?", "status"):
            self.reply(
                "This channel is for pipeline approval gates.\n"
                "When the daily pipeline runs, it posts topic and draft "
                "approvals here. Reply in the thread to approve/reject.\n\n"
                "Commands: GO / SKIP / 1-5 (topic number) / ALL / platform names",
                thread_ts=ts,
            )

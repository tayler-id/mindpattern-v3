"""Idempotency receipts + the outbound kill switch.

Every irreversible external action (email send, social post, follow) must
claim a receipt BEFORE acting. A crash-and-resume then cannot repeat the
action: the second claim returns False and the caller skips.

Action-key scheme (date-scoped, content-scoped where it matters):
    newsletter:{date}
    broadcast:{date}:{email}
    post:{platform}:{date}:{sha1(content)[:12]}
    follow:{platform}:{handle}

MP_DISABLE_OUTBOUND=1 is the global kill switch: every outbound path calls
outbound_allowed() first. It must work even when config files don't.
"""

import hashlib
import logging
import os
import sqlite3

from core.time import now_utc

logger = logging.getLogger(__name__)


def outbound_allowed() -> bool:
    """False when the global kill switch is set."""
    if os.environ.get("MP_DISABLE_OUTBOUND") == "1":
        logger.warning("outbound action blocked: MP_DISABLE_OUTBOUND=1")
        return False
    return True


def content_key(content: str) -> str:
    """Stable short hash for content-scoped action keys."""
    return hashlib.sha1(content.encode()).hexdigest()[:12]


def claim(conn: sqlite3.Connection, action_key: str) -> bool:
    """Claim an action. True exactly once per key; False on repeat."""
    with conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO receipts (action_key, created_at) VALUES (?, ?)",
            (action_key, now_utc()),
        )
    claimed = cur.rowcount == 1
    if not claimed:
        logger.info("receipt already claimed, skipping: %s", action_key)
    return claimed


def release(conn: sqlite3.Connection, action_key: str) -> None:
    """Manual override: drop a receipt so the action can run again."""
    with conn:
        conn.execute("DELETE FROM receipts WHERE action_key = ?", (action_key,))

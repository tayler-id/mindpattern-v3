"""Bot liveness heartbeat — written by the bot, read by /healthz.

The 2026-06-11 outage root cause: the Socket Mode connection died while the
process stayed alive, so Fly saw a healthy machine and never restarted it.
The bot now touches a heartbeat file every 30s ONLY while the socket is
connected; /healthz returns 503 when the file goes stale, which fails the
Fly health check and triggers a machine restart.

This module must stay import-light (no slack_sdk) — the dashboard imports it.
"""

import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

STALE_AFTER_SECONDS = 120
TOUCH_INTERVAL_SECONDS = 30


def heartbeat_path() -> Path:
    """Resolve the heartbeat file path (env override > Fly volume > repo)."""
    env = os.environ.get("MP_BOT_HEARTBEAT_PATH")
    if env:
        return Path(env)
    if Path("/data").is_dir():  # Fly volume
        return Path("/data/bot-heartbeat")
    return PROJECT_ROOT / "data" / "bot-heartbeat"


def touch() -> None:
    """Update the heartbeat mtime."""
    path = heartbeat_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def is_stale(stale_after: float = STALE_AFTER_SECONDS) -> bool:
    """True when the heartbeat file is missing or older than stale_after."""
    try:
        mtime = heartbeat_path().stat().st_mtime
    except FileNotFoundError:
        return True
    return (time.time() - mtime) > stale_after

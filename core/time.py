"""One timestamp format for the whole system.

v3 stored timestamps in four incompatible formats (audit: mirror date
attribution bugs, unsortable ORDER BY). Every new write goes through here:
UTC, space-separated ISO ("YYYY-MM-DD HH:MM:SS") — the same format SQLite's
datetime('now') emits, so new rows sort correctly alongside existing ones.
"""

from datetime import datetime, timezone

FORMAT = "%Y-%m-%d %H:%M:%S"


def now_utc() -> str:
    """Current UTC timestamp, e.g. '2026-06-11 17:30:05'."""
    return datetime.now(timezone.utc).strftime(FORMAT)


def today_utc() -> str:
    """Current UTC date, e.g. '2026-06-11'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

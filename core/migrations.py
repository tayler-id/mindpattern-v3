"""Schema migrations via PRAGMA user_version.

v3 evolved its schema with CREATE TABLE IF NOT EXISTS only — columns could
never be added and drift was masked by `except OperationalError: pass`.
Every schema change is now a numbered entry here; `migrate()` applies the
ones a database hasn't seen, each in its own transaction.

Version 1 is a baseline stamp: existing memory.db schemas (created by
memory.db._init_schema) and fresh test databases both start from there.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)

MIGRATIONS: list[tuple[int, str]] = [
    (1, "SELECT 1"),  # baseline stamp — schema owned by memory.db._init_schema
    (2, """
        CREATE TABLE IF NOT EXISTS receipts (
            action_key TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """),
]


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply all unapplied migrations. Returns the resulting version."""
    version = current_version(conn)
    for target, sql in MIGRATIONS:
        if target <= version:
            continue
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {target}")
        logger.info("migrated schema to user_version=%d", target)
        version = target
    return version

"""SQLite connection discipline.

One way to open a database: WAL mode, foreign keys on, busy timeout, Row
factory. Transactions use the connection's native context manager —
``with conn:`` commits on success and rolls back on exception, which is the
fix for v3's orphan-row class of bugs (a failed multi-statement write left
uncommitted rows that the next unrelated commit silently persisted).
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database with the project-standard pragmas."""
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def open_db(path: str | Path):
    """Context-managed connection: always closed, never leaked."""
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()

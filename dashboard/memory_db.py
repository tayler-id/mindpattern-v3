import sqlite3
from pathlib import Path
from typing import Optional

MEMORY_DB_PATH = Path(__file__).parent.parent / "data" / "ramsay" / "memory.db"


def get_memory_db() -> Optional[sqlite3.Connection]:
    if not MEMORY_DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(MEMORY_DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

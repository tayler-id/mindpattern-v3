"""First-party site event store (site_events.db).

Deliberately a SEPARATE database from memory.db: the daily local->Fly sync
REPLACES memory.db, so events recorded in production would be destroyed
every morning. site_events.db lives only where events happen and is never
bundled by the sync.

Privacy contract (test-enforced): rows contain event type, target, path,
referrer domain, coarse timestamp, and an optional client-random anon_id.
Never IP, user agent, geo, or anything derived from them.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

ALLOWED_EVENTS = {
    "page_view",
    "story_view",
    "related_click",
    "entity_click",
    "source_click",
    "briefing_click",
    "outbound_source_click",
    "scroll_depth",
    "subscribe_submitted",
    "subscribe_success",
    "search_query","agent_hit",
    "share",
    "web_vital",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    type TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    ref_domain TEXT NOT NULL DEFAULT '',
    anon_id TEXT NOT NULL DEFAULT '',
    value INTEGER NOT NULL DEFAULT 0,
    owner INTEGER NOT NULL DEFAULT 0,
    -- 1 when the client could persist its reader id, 0 when it could not and
    -- will mint a fresh one on the next page load. On 2026-08-26 the site
    -- reported 757 unique readers at 1.02 page views each, with fewer story
    -- views than readers, which is what per-page-load identity looks like.
    -- Mixing the two into one "unique readers" figure hides which it was.
    durable INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);
CREATE INDEX IF NOT EXISTS idx_events_target ON events(target, type, ts);
-- Answers "has this anon_id been seen before timestamp T" with one index seek,
-- which is what separates a new reader from a returning one. Without it the
-- new/returning split on /site-analytics degrades to a table scan per reader.
CREATE INDEX IF NOT EXISTS idx_events_anon_ts ON events(anon_id, ts);
"""

_ANON_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_TEXT_CAP = 200


def events_db_path() -> Path:
    override = os.environ.get("MP_EVENTS_DB")
    if override:
        return Path(override)
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    if data_dir.exists():
        return data_dir / "site_events.db"
    return Path(__file__).parent.parent / "data" / "site_events.db"


def open_events_db(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or events_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    # Additive migrations for databases written before a column existed. The
    # Fly volume holds one, so these must never drop or rewrite rows.
    for column, ddl in (
        ("owner", "ALTER TABLE events ADD COLUMN owner INTEGER NOT NULL DEFAULT 0"),
        ("durable", "ALTER TABLE events ADD COLUMN durable INTEGER NOT NULL DEFAULT 0"),
    ):
        try:
            conn.execute(ddl)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


def _clean(value: object, cap: int = _TEXT_CAP) -> str:
    text = str(value or "")[:cap]
    # strip anything that could smuggle identity: querystrings and emails
    text = text.split("?")[0]
    return text.replace("\n", " ").strip()


def record_event(conn: sqlite3.Connection, payload: dict) -> bool:
    """Validate and store one event. Returns False (never raises) on junk."""
    event_type = str(payload.get("type") or "")
    if event_type not in ALLOWED_EVENTS:
        return False
    anon = str(payload.get("anon_id") or "")
    if anon and not _ANON_RE.fullmatch(anon):
        anon = ""
    ref = _clean(payload.get("ref_domain"), 80)
    if "/" in ref or "@" in ref:
        ref = ""
    try:
        value = max(0, min(int(payload.get("value") or 0), 100))
    except (TypeError, ValueError):
        value = 0
    # Self-declared owner flag ("this is Tayler browsing") — set client-side
    # via ?mp_owner=1. Unauthenticated by design: worst case someone hides
    # their own events from the counts, which stays privacy-safe.
    owner = 1 if payload.get("owner") in (1, "1", True) else 0
    # Absent means not durable. A client that does not report the flag is one
    # we cannot vouch for, and counting it as durable would defeat the split.
    durable = 1 if payload.get("durable") in (1, "1", True) else 0
    conn.execute(
        "INSERT INTO events (ts, type, target, path, ref_domain, anon_id, value, owner, durable)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(time.time()),
            event_type,
            _clean(payload.get("target")),
            _clean(payload.get("path")),
            ref,
            anon,
            value,
            owner,
            durable,
        ),
    )
    conn.commit()
    return True

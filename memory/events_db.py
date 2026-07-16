"""First-party site event store (site_events.db).

Deliberately a SEPARATE database from memory.db: the daily local->Fly sync
REPLACES memory.db, so events recorded in production would be destroyed
every morning. site_events.db lives only where events happen and is never
bundled by the sync.

Privacy contract (test-enforced): rows contain event type, target, path,
referrer domain, coarse timestamp, an optional client-random anon_id, and —
for campaign-permitted event types only — normalized safe campaign/channel
ids captured client-side from utm tags (pilot spec section 11). Never IP,
user agent, geo, raw query strings, or anything derived from them.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path

ALLOWED_EVENTS = {
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
}

#: Event types that may carry campaign attribution (pilot spec section 11:
#: story, source-click, subscribe, and share events). Campaign fields on any
#: other type are dropped server-side regardless of what the client sent.
CAMPAIGN_EVENTS = {
    "story_view",
    "source_click",
    "outbound_source_click",
    "subscribe_submitted",
    "subscribe_success",
    "share",
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
    campaign_id TEXT NOT NULL DEFAULT '',
    source_channel TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);
CREATE INDEX IF NOT EXISTS idx_events_target ON events(target, type, ts);
"""

# Additive migrations for databases created before each column existed.
# The campaign index lives here (NOT in _SCHEMA) so it is only created
# after the columns exist on older databases.
_MIGRATIONS = (
    "ALTER TABLE events ADD COLUMN owner INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE events ADD COLUMN campaign_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE events ADD COLUMN source_channel TEXT NOT NULL DEFAULT ''",
)

_ANON_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Normalized safe ids — never a raw query-string value. Campaign ids are
# CampaignOS SHA-256 ids (64 hex chars) but the rule is the general safe set.
_CAMPAIGN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_CHANNEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
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
    for statement in _MIGRATIONS:
        try:  # additive migration for databases created before the column
            conn.execute(statement)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_campaign ON events(campaign_id, ts)"
    )
    conn.commit()
    return conn


def _clean(value: object, cap: int = _TEXT_CAP) -> str:
    text = str(value or "")[:cap]
    # strip anything that could smuggle identity: querystrings and emails
    text = text.split("?")[0]
    return text.replace("\n", " ").strip()


def _campaign_field(value: object, pattern: re.Pattern) -> str:
    """Normalize one campaign attribution field to a safe id, else ''."""
    text = str(value or "").strip().lower()
    return text if pattern.fullmatch(text) else ""


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
    # Campaign attribution (pilot spec section 11): normalized safe ids on
    # permitted event types only, never a raw query-string value. Anything
    # invalid — and any campaign field on a non-permitted type — stores ''.
    campaign_id = ""
    source_channel = ""
    if event_type in CAMPAIGN_EVENTS:
        campaign_id = _campaign_field(payload.get("campaign_id"), _CAMPAIGN_ID_RE)
        source_channel = _campaign_field(payload.get("source_channel"), _CHANNEL_RE)
    conn.execute(
        "INSERT INTO events (ts, type, target, path, ref_domain, anon_id, value,"
        " owner, campaign_id, source_channel)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            int(time.time()),
            event_type,
            _clean(payload.get("target")),
            _clean(payload.get("path")),
            ref,
            anon,
            value,
            owner,
            campaign_id,
            source_channel,
        ),
    )
    conn.commit()
    return True

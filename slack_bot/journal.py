"""Fly→Mac event journal — bot-side writer.

Outbound actions taken on Fly (phone posts, approvals, reactions) are
invisible to the Mac pipeline's memory.db: sync only flows Mac→Fly. The bot
appends each event as one JSON line here; the pipeline's INIT phase pulls
the file and ingests it so dedup, rate caps, and receipts see phone
activity (audit HIGH posts.py:304).

Import-light by design (no slack_sdk) — the ingest side imports this for
the path convention.
"""

import json
import os
import uuid
from pathlib import Path

from core.time import now_utc

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def journal_path() -> Path:
    """Resolve the journal file path (env override > Fly volume > repo)."""
    env = os.environ.get("MP_JOURNAL_PATH")
    if env:
        return Path(env)
    if Path("/data").is_dir():  # Fly volume
        return Path("/data/journal.jsonl")
    return PROJECT_ROOT / "data" / "journal.jsonl"


def append(event: dict) -> dict:
    """Append one event line. Returns the full entry as written."""
    entry = {"id": uuid.uuid4().hex, "ts": now_utc(), **event}
    path = journal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

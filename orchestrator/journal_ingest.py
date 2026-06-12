"""Fly→Mac journal ingestion — pipeline-side reader (M0 task 15).

The Slack bot on Fly journals outbound events (phone posts) to
/data/journal.jsonl. At INIT the pipeline pulls that file and ingests new
entries into memory.db so dedup, rate caps, and receipts see phone
activity. A line-count offset is tracked per user; receipts make
re-ingestion idempotent even if the offset resets.
"""

import json
import logging
from pathlib import Path

import memory
from core import receipts

from .sync import _fly_ssh

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
REMOTE_JOURNAL = "/data/journal.jsonl"


def _offset_path(user_id: str) -> Path:
    return PROJECT_ROOT / "data" / user_id / "journal.offset"


def _read_offset(user_id: str) -> int:
    try:
        return int(_offset_path(user_id).read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def _write_offset(user_id: str, offset: int) -> None:
    path = _offset_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset))


def ingest_lines(db, user_id: str, lines: list[str]) -> dict:
    """Ingest journal lines into memory.db. Idempotent via receipts.

    Posts are recorded into social_posts (posted=True) + engagements so
    rate caps and dedup count them; the same post:{...} receipt key the
    pipeline claims before posting makes ingestion collision-safe in both
    directions (a phone post blocks a same-content pipeline post and vice
    versa).
    """
    result = {"ingested": 0, "skipped": 0, "malformed": 0}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            result["malformed"] += 1
            continue

        if entry.get("type") != "post":
            # Approvals/reactions are journaled for the record; nothing to
            # ingest for them yet.
            result["skipped"] += 1
            continue

        platform = entry.get("platform", "")
        content = entry.get("content", "")
        date = entry.get("date") or str(entry.get("ts", ""))[:10]
        if not platform or not content or not date:
            result["malformed"] += 1
            continue

        receipt_key = f"post:{platform}:{date}:{receipts.content_key(content)}"
        if not receipts.claim(db, receipt_key):
            result["skipped"] += 1  # already ingested or already posted
            continue

        memory.store_post(
            db, date=date, platform=platform, content=content, posted=True,
        )
        memory.store_engagement(
            db, user_id=user_id, platform=platform,
            engagement_type="post", status="posted",
        )
        result["ingested"] += 1

    return result


def pull_and_ingest(db, user_id: str, *, app_name: str = "mindpattern") -> dict:
    """Pull the Fly journal and ingest entries past the stored offset."""
    fetched = _fly_ssh(app_name, f"cat {REMOTE_JOURNAL} 2>/dev/null || true")
    if not fetched.get("success"):
        return {"error": fetched.get("error", "journal fetch failed")}

    all_lines = fetched.get("output", "").splitlines()
    offset = _read_offset(user_id)
    if offset > len(all_lines):
        # Journal rotated/truncated on Fly — re-read from the start;
        # receipts make the re-ingest a no-op for known entries.
        logger.info(
            f"Journal offset {offset} > {len(all_lines)} lines — resetting"
        )
        offset = 0

    new_lines = all_lines[offset:]
    result = ingest_lines(db, user_id, new_lines)
    result["new_lines"] = len(new_lines)
    _write_offset(user_id, len(all_lines))

    if result.get("ingested"):
        logger.info(
            f"Journal ingest: {result['ingested']} phone event(s) into memory.db"
        )
    return result

# preflight/rss.py
"""Preflight: RSS feed items via tools/rss-fetch.py."""

import logging
import subprocess
from pathlib import Path

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    """Transform rss-fetch.py output item to preflight entry."""
    return make_entry(
        source="rss",
        source_name=raw.get("source", ""),
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=raw.get("published", ""),
        content_preview=raw.get("summary", ""),
    )


def fetch(feeds_file: Path, hours: int = 48) -> list[dict]:
    """Fetch RSS items and return as preflight entries."""
    cmd = [
        "python3", str(TOOLS_DIR / "rss-fetch.py"),
        "--feeds-file", str(feeds_file),
        "--hours", str(hours),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.warning("rss-fetch.py timed out after 120s")
        return []
    except Exception as e:
        logger.error(f"rss-fetch.py failed: {e}")
        return []

    if proc.stderr:
        for line in proc.stderr.strip().split("\n"):
            if line.strip():
                logger.debug(f"rss-fetch stderr: {line}")

    items = parse_ndjson(proc.stdout)
    return [_transform(item) for item in items]

"""Preflight: arXiv papers via tools/arxiv-fetch.py."""

import logging
import subprocess

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    authors = ", ".join(raw.get("authors", [])[:3])
    cats = ", ".join(raw.get("categories", []))
    preview = raw.get("summary", "")
    if authors:
        preview = f"[{authors}] [{cats}] {preview}"
    return make_entry(
        source="arxiv",
        source_name="arXiv",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=raw.get("published", ""),
        content_preview=preview,
    )


def fetch(categories: str = "cs.AI,cs.LG,cs.CL", days: int = 2, max_results: int = 30) -> list[dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "arxiv-fetch.py"),
        "--categories", categories,
        "--days", str(days),
        "--max", str(max_results),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"arxiv-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]

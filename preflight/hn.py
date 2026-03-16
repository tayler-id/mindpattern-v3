"""Preflight: Hacker News stories via tools/hn-fetch.py."""

import logging
import subprocess

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    pts = raw.get("points", 0)
    cmts = raw.get("comments", 0)
    return make_entry(
        source="hn",
        source_name="Hacker News",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=raw.get("time", ""),
        content_preview=f"{pts} points, {cmts} comments on HN. Query: {raw.get('query', '')}",
        metrics={"points": pts, "comments": cmts},
    )


def fetch(queries: str = "AI,LLM,agents,vibe coding,MCP", hours: int = 48, min_points: int = 10) -> list[dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "hn-fetch.py"),
        "--queries", queries,
        "--hours", str(hours),
        "--min-points", str(min_points),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"hn-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]

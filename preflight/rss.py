# preflight/rss.py
"""Preflight: RSS feed items via tools/rss-fetch.py."""

import logging
import json
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


def _parse_stderr_diagnostics(stderr: str) -> list[dict]:
    """Parse structured rss-fetch stderr lines, preserving raw fallback."""
    diagnostics = []
    for line in stderr.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                diagnostics.append(parsed)
                continue
        except json.JSONDecodeError:
            pass
        diagnostics.append({"error": line, "tool": "rss-fetch"})
    return diagnostics


def _summarize_diagnostics(feed_errors: list[dict]) -> str:
    """Return a compact reason string naming bad feeds/URLs when possible."""
    if not feed_errors:
        return ""
    parts = []
    for error in feed_errors[:3]:
        message = error.get("error", "rss error")
        context = error.get("context")
        parts.append(f"{message} ({context})" if context else message)
    if len(feed_errors) > 3:
        parts.append(f"{len(feed_errors) - 3} more")
    return "; ".join(parts)


def fetch_with_diagnostics(feeds_file: Path, hours: int = 48) -> tuple[list[dict], dict]:
    """Fetch RSS items and return entries plus source-health diagnostics."""
    cmd = [
        "python3", str(TOOLS_DIR / "rss-fetch.py"),
        "--feeds-file", str(feeds_file),
        "--hours", str(hours),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.warning("rss-fetch.py timed out after 120s")
        return [], {
            "status": "timeout",
            "reason": "rss-fetch.py timed out after 120s",
            "feed_errors": [],
        }
    except Exception as e:
        logger.error(f"rss-fetch.py failed: {e}")
        return [], {
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
            "feed_errors": [],
        }

    feed_errors = _parse_stderr_diagnostics(proc.stderr or "")
    if proc.stderr:
        for error in feed_errors:
            logger.debug(f"rss-fetch stderr: {error}")

    items = parse_ndjson(proc.stdout)
    transformed = [_transform(item) for item in items]
    reason = _summarize_diagnostics(feed_errors)

    if proc.returncode == 0:
        status = "ok" if transformed else "empty"
        reason = "" if transformed else "no items"
    elif proc.returncode == 1:
        status = "partial" if transformed else "failed"
        reason = reason or "rss-fetch.py reported partial failure"
    else:
        status = "failed"
        reason = reason or f"rss-fetch.py exited {proc.returncode}"

    return transformed, {
        "status": status,
        "reason": reason,
        "feed_errors": feed_errors,
    }


def fetch(feeds_file: Path, hours: int = 48) -> list[dict]:
    """Fetch RSS items and return as preflight entries."""
    items, _diagnostics = fetch_with_diagnostics(feeds_file=feeds_file, hours=hours)
    return items

"""Preflight: Hacker News stories via tools/hn-fetch.py."""

import json
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


def _parse_stderr_diagnostics(stderr: str) -> list[dict]:
    """Parse structured hn-fetch stderr lines, preserving raw fallback."""
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
        diagnostics.append({"error": line, "tool": "hn-fetch"})
    return diagnostics


def _summarize_errors(errors: list[dict]) -> str:
    if not errors:
        return ""
    parts = []
    for error in errors[:3]:
        message = error.get("error", "hn error")
        context = error.get("context")
        parts.append(f"{message} ({context})" if context else message)
    if len(errors) > 3:
        parts.append(f"{len(errors) - 3} more")
    return "; ".join(parts)


def fetch_with_diagnostics(
    queries: str = "AI,LLM,agents,vibe coding,MCP",
    hours: int = 48,
    min_points: int = 10,
) -> tuple[list[dict], dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "hn-fetch.py"),
        "--queries", queries,
        "--hours", str(hours),
        "--min-points", str(min_points),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as e:
        logger.error(f"hn-fetch.py failed: {e}")
        return [], {
            "status": "timeout",
            "reason": "hn-fetch.py timed out after 60s",
            "queries": queries,
            "hours": hours,
            "min_points": min_points,
            "errors": [],
        }
    except Exception as e:
        logger.error(f"hn-fetch.py failed: {e}")
        return [], {
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
            "queries": queries,
            "hours": hours,
            "min_points": min_points,
            "errors": [],
        }

    errors = _parse_stderr_diagnostics(proc.stderr or "")
    items = [_transform(item) for item in parse_ndjson(proc.stdout)]
    reason = _summarize_errors(errors)

    if proc.returncode == 0:
        status = "ok" if items else "empty"
        reason = "" if items else (
            f"no HN items for queries={queries}, hours={hours}, "
            f"min_points={min_points}"
        )
    elif proc.returncode == 1:
        status = "partial" if items else "failed"
        reason = reason or "hn-fetch.py reported partial failure"
    else:
        status = "failed"
        reason = reason or f"hn-fetch.py exited {proc.returncode}"

    return items, {
        "status": status,
        "reason": reason,
        "queries": queries,
        "hours": hours,
        "min_points": min_points,
        "errors": errors,
    }


def fetch(queries: str = "AI,LLM,agents,vibe coding,MCP", hours: int = 48, min_points: int = 10) -> list[dict]:
    items, _diagnostics = fetch_with_diagnostics(
        queries=queries,
        hours=hours,
        min_points=min_points,
    )
    return items

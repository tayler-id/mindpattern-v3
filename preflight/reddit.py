"""Preflight: Reddit posts via tools/reddit-fetch.py."""

import json
import logging
import subprocess
from datetime import datetime, timezone

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = (
    "MachineLearning,LocalLLaMA,artificial,singularity,"
    "ChatGPT,ClaudeAI,SaaS,fintech,startups,programming"
)


def _transform(raw: dict) -> dict:
    created = raw.get("created_utc")
    published = ""
    if created:
        try:
            published = datetime.fromtimestamp(int(created), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            pass

    return make_entry(
        source="reddit",
        source_name=f"r/{raw.get('subreddit', '')}",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=published,
        content_preview=raw.get("selftext", "")[:500],
        metrics={"score": raw.get("score", 0), "comments": raw.get("comments", 0)},
    )


def _parse_stderr_diagnostics(stderr: str) -> list[dict]:
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
        diagnostics.append({"error": line, "tool": "reddit-fetch"})
    return diagnostics


def _summarize_errors(errors: list[dict]) -> str:
    if not errors:
        return ""
    parts = []
    for error in errors[:3]:
        message = error.get("error", "reddit error")
        context = error.get("context")
        parts.append(f"{message} ({context})" if context else message)
    if len(errors) > 3:
        parts.append(f"{len(errors) - 3} more")
    return "; ".join(parts)


def fetch_with_diagnostics(
    subreddits: str | None = None,
    min_score: int = 50,
) -> tuple[list[dict], dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "reddit-fetch.py"),
        "--subreddits", subreddits or DEFAULT_SUBREDDITS,
        "--min-score", str(min_score),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.error("reddit-fetch.py timed out after 120s")
        return [], {
            "status": "timeout",
            "reason": "reddit-fetch.py timed out after 120s",
            "subreddits": subreddits or DEFAULT_SUBREDDITS,
            "errors": [],
        }
    except FileNotFoundError as e:
        logger.error(f"reddit-fetch.py dependency missing: {e}")
        return [], {
            "status": "unavailable",
            "reason": f"reddit-fetch.py unavailable: {e}",
            "subreddits": subreddits or DEFAULT_SUBREDDITS,
            "errors": [{"error": str(e), "tool": "reddit-fetch"}],
        }
    except Exception as e:
        logger.error(f"reddit-fetch.py failed: {e}")
        return [], {
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
            "subreddits": subreddits or DEFAULT_SUBREDDITS,
            "errors": [],
        }

    errors = _parse_stderr_diagnostics(proc.stderr or "")
    items = [_transform(item) for item in parse_ndjson(proc.stdout)]
    reason = _summarize_errors(errors)

    if proc.returncode == 0:
        status = "ok" if items else "empty"
        reason = "" if items else "no reddit items"
    elif proc.returncode == 1:
        status = "partial" if items else "failed"
        reason = reason or "reddit-fetch.py reported partial failure"
    elif proc.returncode == 2 and not items:
        status = "unavailable"
        reason = reason or "reddit backend unavailable"
    else:
        status = "failed"
        reason = reason or f"reddit-fetch.py exited {proc.returncode}"

    return items, {
        "status": status,
        "reason": reason,
        "subreddits": subreddits or DEFAULT_SUBREDDITS,
        "errors": errors,
    }


def fetch(subreddits: str | None = None, min_score: int = 50) -> list[dict]:
    items, _diagnostics = fetch_with_diagnostics(
        subreddits=subreddits,
        min_score=min_score,
    )
    return items

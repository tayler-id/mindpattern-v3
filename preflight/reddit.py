"""Preflight: Reddit posts via tools/reddit-fetch.py."""

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


def fetch(subreddits: str | None = None, min_score: int = 50) -> list[dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "reddit-fetch.py"),
        "--subreddits", subreddits or DEFAULT_SUBREDDITS,
        "--min-score", str(min_score),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"reddit-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]

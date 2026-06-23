"""Preflight: Twitter/X posts via xreach or twitter-cli search."""

import json
import logging
import shutil
import subprocess
from datetime import datetime

from . import make_entry

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    "AI agents coding",
    "Claude Anthropic",
    "vibe coding",
    "SaaS disruption AI",
    "fintech AI 2026",
]


def _search_command(query: str, count: int) -> list[str] | None:
    """Return the best installed Twitter/X search command."""
    if shutil.which("xreach"):
        return ["xreach", "search", query, "--count", str(count), "--json"]
    if shutil.which("twitter"):
        return [
            "twitter",
            "search",
            query,
            "-n",
            str(count),
            "--json",
            "--exclude",
            "retweets",
            "--exclude",
            "replies",
        ]
    return None


def _extract_items(data) -> list[dict]:
    """Normalize supported CLI JSON shapes into tweet dictionaries."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        return []

    if data.get("ok") is False:
        error = data.get("error") or {}
        logger.warning("twitter-cli search unavailable: %s", error.get("code", "unknown"))
        return []

    items = data.get("items") or data.get("tweets") or []
    return [item for item in items if isinstance(item, dict)]


def _parse_twitter_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""


def _published_at(raw: dict) -> str:
    created_iso = raw.get("createdAtISO")
    if isinstance(created_iso, str) and created_iso:
        return created_iso
    return _parse_twitter_date(raw.get("createdAt", ""))


def _metrics(raw: dict) -> dict:
    nested = raw.get("metrics") or {}
    return {
        "likes": raw.get("likeCount", nested.get("likes", 0)),
        "retweets": raw.get("retweetCount", nested.get("retweets", 0)),
        "views": raw.get("viewCount", nested.get("views", 0)),
    }


def _transform(raw: dict, query: str = "") -> dict:
    tweet_id = raw.get("id", "")
    return make_entry(
        source="twitter",
        source_name=f"x.com (query: {query})",
        title=raw.get("text", "")[:120],
        url=f"https://x.com/i/status/{tweet_id}",
        published=_published_at(raw),
        content_preview=raw.get("text", ""),
        metrics=_metrics(raw),
    )


def fetch(queries: list[str] | None = None, count: int = 10) -> list[dict]:
    queries = queries or DEFAULT_QUERIES
    all_items = []
    seen_ids = set()

    if not _search_command("", 1):
        logger.error("No Twitter/X search CLI found — install Agent Reach twitter channel")
        return []

    for query in queries:
        cmd = _search_command(query, count)
        if cmd is None:
            return []

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"Twitter/X search failed for '{query}': {proc.stderr[:200]}")
                continue

            data = json.loads(proc.stdout)
            for item in _extract_items(data):
                tid = item.get("id", "")
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
                if item.get("isRetweet") or item.get("isReply"):
                    continue
                all_items.append(_transform(item, query=query))

        except subprocess.TimeoutExpired:
            logger.warning(f"Twitter/X search timed out for '{query}'")
        except json.JSONDecodeError:
            logger.warning(f"Twitter/X search returned invalid JSON for '{query}'")
        except FileNotFoundError:
            logger.error("Twitter/X search CLI disappeared from PATH")
            return []
        except Exception as e:
            logger.error(f"Twitter/X search failed for '{query}': {e}")

    return all_items

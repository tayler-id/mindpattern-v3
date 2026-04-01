"""Preflight: Twitter/X posts via xreach search."""

import json
import logging
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


def _parse_twitter_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""


def _transform(raw: dict, query: str = "") -> dict:
    tweet_id = raw.get("id", "")
    return make_entry(
        source="twitter",
        source_name=f"x.com (query: {query})",
        title=raw.get("text", "")[:120],
        url=f"https://x.com/i/status/{tweet_id}",
        published=_parse_twitter_date(raw.get("createdAt", "")),
        content_preview=raw.get("text", ""),
        metrics={
            "likes": raw.get("likeCount", 0),
            "retweets": raw.get("retweetCount", 0),
            "views": raw.get("viewCount", 0),
        },
    )


def fetch(queries: list[str] | None = None, count: int = 10) -> list[dict]:
    queries = queries or DEFAULT_QUERIES
    all_items = []
    seen_ids = set()

    for query in queries:
        cmd = ["xreach", "search", query, "--count", str(count), "--json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"xreach search failed for '{query}': {proc.stderr[:200]}")
                continue

            data = json.loads(proc.stdout)
            for item in data.get("items", []):
                tid = item.get("id", "")
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
                if item.get("isRetweet") or item.get("isReply"):
                    continue
                all_items.append(_transform(item, query=query))

        except subprocess.TimeoutExpired:
            logger.warning(f"xreach search timed out for '{query}'")
        except json.JSONDecodeError:
            logger.warning(f"xreach returned invalid JSON for '{query}'")
        except FileNotFoundError:
            logger.error("xreach not found — install with: pip install xreach")
            return []
        except Exception as e:
            logger.error(f"xreach failed for '{query}': {e}")

    return all_items

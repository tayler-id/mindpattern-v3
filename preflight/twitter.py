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


def _feed_command(count: int) -> list[str] | None:
    """Return a stable Twitter/X fallback command when query search breaks."""
    if shutil.which("twitter"):
        return ["twitter", "feed", "-n", str(count), "--json"]
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

    items = data.get("items") or data.get("tweets") or data.get("data") or []
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
    source_name = "x.com (feed fallback)" if query == "feed fallback" else f"x.com (query: {query})"
    return make_entry(
        source="twitter",
        source_name=source_name,
        title=raw.get("text", "")[:120],
        url=f"https://x.com/i/status/{tweet_id}",
        published=_published_at(raw),
        content_preview=raw.get("text", ""),
        metrics=_metrics(raw),
    )


def _stderr_snippet(stderr: str, limit: int = 300) -> str:
    """Return a safe one-line stderr snippet."""
    return (stderr or "").strip().replace("\n", " ")[:limit]


def _output_snippet(stdout: str, stderr: str, limit: int = 300) -> str:
    """Prefer stderr, but include stdout JSON errors when CLIs print there."""
    combined = " ".join(part for part in (_stderr_snippet(stderr), _stderr_snippet(stdout)) if part)
    return combined[:limit]


def _append_command_items(
    *,
    cmd: list[str],
    query: str,
    all_items: list[dict],
    seen_ids: set,
    failures: list[dict],
    timeout: int = 30,
) -> int:
    """Run a Twitter command and append unique, non-retweet items."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            snippet = _output_snippet(proc.stdout, proc.stderr)
            logger.warning(f"Twitter/X command failed for '{query}': {snippet[:200]}")
            failures.append({
                "backend": cmd[0],
                "query": query,
                "exit_code": proc.returncode,
                "stderr": snippet,
            })
            return 0

        data = json.loads(proc.stdout)
        added = 0
        for item in _extract_items(data):
            tid = item.get("id", "")
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            if item.get("isRetweet") or item.get("isReply"):
                continue
            all_items.append(_transform(item, query=query))
            added += 1
        return added

    except subprocess.TimeoutExpired:
        logger.warning(f"Twitter/X command timed out for '{query}'")
        failures.append({
            "backend": cmd[0],
            "query": query,
            "exit_code": None,
            "stderr": "timeout after 30s",
        })
    except json.JSONDecodeError:
        logger.warning(f"Twitter/X command returned invalid JSON for '{query}'")
        failures.append({
            "backend": cmd[0],
            "query": query,
            "exit_code": 0,
            "stderr": "invalid JSON",
        })
    except FileNotFoundError:
        logger.error("Twitter/X CLI disappeared from PATH")
        failures.append({
            "backend": cmd[0],
            "query": query,
            "exit_code": None,
            "stderr": "CLI disappeared from PATH",
        })
    except Exception as e:
        logger.error(f"Twitter/X command failed for '{query}': {e}")
        failures.append({
            "backend": cmd[0],
            "query": query,
            "exit_code": None,
            "stderr": str(e)[:300],
        })
    return 0


def fetch_with_diagnostics(
    queries: list[str] | None = None,
    count: int = 10,
) -> tuple[list[dict], dict]:
    """Fetch Twitter/X items plus backend/query diagnostics."""
    queries = queries or DEFAULT_QUERIES
    all_items = []
    seen_ids = set()
    failures = []
    fallbacks = []

    if not _search_command("", 1):
        logger.error("No Twitter/X search CLI found — install Agent Reach twitter channel")
        return [], {
            "status": "missing",
            "reason": "No Twitter/X search CLI found",
            "queries": queries,
            "failures": [{
                "backend": "none",
                "query": "",
                "exit_code": None,
                "stderr": "install Agent Reach twitter channel",
            }],
        }

    for query in queries:
        cmd = _search_command(query, count)
        if cmd is None:
            failures.append({
                "backend": "none",
                "query": query,
                "exit_code": None,
                "stderr": "No Twitter/X search CLI found",
            })
            continue

        _append_command_items(
            cmd=cmd,
            query=query,
            all_items=all_items,
            seen_ids=seen_ids,
            failures=failures,
        )

    if not all_items and failures:
        feed_count = min(max(count * len(queries), count), 20)
        cmd = _feed_command(feed_count)
        if cmd:
            before = len(all_items)
            _append_command_items(
                cmd=cmd,
                query="feed fallback",
                all_items=all_items,
                seen_ids=seen_ids,
                failures=failures,
            )
            added = len(all_items) - before
            if added:
                fallbacks.append({
                    "backend": cmd[0],
                    "mode": "feed",
                    "count": added,
                    "reason": "search failed",
                })

    if all_items and failures:
        status = "partial"
        first = failures[0]
        reason = f"{first['backend']} exit {first['exit_code']} for {first['query']}: {first['stderr']}"
    elif all_items:
        status = "ok"
        reason = ""
    elif failures:
        status = "failed"
        first = failures[0]
        reason = f"{first['backend']} exit {first['exit_code']} for {first['query']}: {first['stderr']}"
    else:
        status = "empty"
        reason = f"no items for queries: {', '.join(queries)}"

    return all_items, {
        "status": status,
        "reason": reason,
        "queries": queries,
        "failures": failures,
        "fallbacks": fallbacks,
    }


def fetch(queries: list[str] | None = None, count: int = 10) -> list[dict]:
    items, _diagnostics = fetch_with_diagnostics(queries=queries, count=count)
    return items

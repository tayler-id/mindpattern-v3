"""
hn-fetch.py — Hacker News story fetcher using Algolia HN API.

Usage:
    python3 hn-fetch.py [--queries AI,LLM,agents] [--hours 24] [--min-points 50]

Outputs one JSON object per line to stdout (newline-delimited JSON).
Errors are printed to stderr as structured JSON. Exit codes: 0=success, 1=partial, 2=total failure.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple


TOOL_NAME = "hn-fetch"
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]
DEFAULT_TIMEOUT = 15


def _log_error(message: str, context: Optional[str] = None) -> None:
    """Print structured JSON error to stderr."""
    err = {"error": message, "tool": TOOL_NAME}
    if context:
        err["context"] = context
    print(json.dumps(err), file=sys.stderr)


def _fetch_with_retry(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """Fetch URL with retry + exponential backoff for transient HTTP errors."""
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, headers=headers)
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code in RETRYABLE_CODES and attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[attempt]
                _log_error(
                    f"HTTP {e.code} (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying in {delay}s",
                    context=url,
                )
                time.sleep(delay)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[attempt]
                _log_error(
                    f"Network error (attempt {attempt + 1}/{MAX_RETRIES + 1}): {e}, retrying in {delay}s",
                    context=url,
                )
                time.sleep(delay)
                continue
            raise

    raise last_exc  # type: ignore[misc]


def fetch_query(query: str, hours: int, min_points: int) -> Tuple[List[dict], bool]:
    """Fetch HN stories for a query. Returns (results, had_error)."""
    cutoff_unix = int(datetime.now(timezone.utc).timestamp()) - hours * 3600
    params = urllib.parse.urlencode({
        "query": query,
        "tags": "story",
        "numericFilters": f"points>={min_points},created_at_i>{cutoff_unix}",
        "hitsPerPage": 50,
    })
    url = f"https://hn.algolia.com/api/v1/search?{params}"

    try:
        body = _fetch_with_retry(
            url,
            headers={"User-Agent": "daily-research-agent/1.0"},
            timeout=DEFAULT_TIMEOUT,
        )
        data = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        _log_error(f"HTTP {e.code} for query '{query}': {e.reason}", context=url)
        return [], True
    except Exception as e:
        _log_error(f"Failed to fetch query '{query}': {e}", context=url)
        return [], True

    hits = data.get("hits", [])
    results = []
    for hit in hits:
        object_id = hit.get("objectID", "")
        url_val = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        results.append({
            "title": hit.get("title", ""),
            "url": url_val,
            "hn_url": f"https://news.ycombinator.com/item?id={object_id}",
            "points": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "time": hit.get("created_at", ""),
            "author": hit.get("author", ""),
            "query": query,
            "_object_id": object_id,
        })
    return results, False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Hacker News stories via Algolia API")
    parser.add_argument("--queries", default="AI,LLM,agents",
                        help="Comma-separated search queries (default: AI,LLM,agents)")
    parser.add_argument("--hours", type=int, default=24,
                        help="Look back this many hours (default: 24)")
    parser.add_argument("--min-points", type=int, default=50,
                        help="Minimum points threshold (default: 50)")
    args = parser.parse_args()

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    seen_ids: Set[str] = set()
    total_queries = len(queries)
    failed_queries = 0

    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(0.5)

        try:
            hits, had_error = fetch_query(query, args.hours, args.min_points)
            if had_error:
                failed_queries += 1
        except Exception as e:
            _log_error(f"Unexpected error for query '{query}': {e}")
            failed_queries += 1
            continue

        for hit in hits:
            oid = hit.pop("_object_id", "")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            print(json.dumps(hit))

    if failed_queries == total_queries:
        _log_error(f"All {total_queries} queries failed")
        sys.exit(2)
    elif failed_queries > 0:
        _log_error(f"{failed_queries}/{total_queries} queries failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

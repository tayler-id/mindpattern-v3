"""
github-fetch.py — GitHub repository fetcher using the Search API (unauthenticated).

Usage:
    python3 github-fetch.py [--topics llm,ai-agent,rag,mcp] [--days 7] [--min-stars 50]

Outputs one JSON object per line to stdout (newline-delimited JSON).
Errors are printed to stderr as structured JSON. Exit codes: 0=success, 1=partial, 2=total failure.

Note: Unauthenticated rate limit is 10 requests/min; a 2-second sleep between
topic requests is included to stay within limits.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Set, Tuple


TOOL_NAME = "github-fetch"
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]
DEFAULT_TIMEOUT = 15

HEADERS = {
    "User-Agent": "daily-research-agent/1.0",
    "Accept": "application/vnd.github.v3+json",
}


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


def fetch_topic(topic: str, since_date: str, min_stars: int) -> Tuple[List[dict], bool]:
    """Fetch GitHub repos for a topic. Returns (results, had_error)."""
    query = f"topic:{topic} stars:>={min_stars} pushed:>{since_date}"
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": 20,
    })
    url = f"https://api.github.com/search/repositories?{params}"

    try:
        body = _fetch_with_retry(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        data = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass
        _log_error(f"HTTP {e.code} for topic '{topic}': {e.reason}. {error_body}", context=url)
        return [], True
    except Exception as e:
        _log_error(f"Failed to fetch topic '{topic}': {e}", context=url)
        return [], True

    results = []
    for repo in data.get("items", []):
        results.append({
            "name": repo.get("full_name", ""),
            "description": repo.get("description") or "",
            "url": repo.get("html_url", ""),
            "stars": repo.get("stargazers_count", 0),
            "language": repo.get("language") or "",
            "topics": repo.get("topics", []),
            "created_at": repo.get("created_at", ""),
            "pushed_at": repo.get("pushed_at", ""),
            "query_topic": topic,
            "_repo_id": repo.get("id"),
        })
    return results, False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GitHub repos via Search API")
    parser.add_argument("--topics", default="llm,ai-agent,rag,mcp",
                        help="Comma-separated GitHub topics (default: llm,ai-agent,rag,mcp)")
    parser.add_argument("--days", type=int, default=7,
                        help="Filter repos pushed within this many days (default: 7)")
    parser.add_argument("--min-stars", type=int, default=50,
                        help="Minimum star count (default: 50)")
    args = parser.parse_args()

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    since_date = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    seen_ids: Set[int] = set()
    total_topics = len(topics)
    failed_topics = 0

    for i, topic in enumerate(topics):
        if i > 0:
            time.sleep(2)

        try:
            repos, had_error = fetch_topic(topic, since_date, args.min_stars)
            if had_error:
                failed_topics += 1
        except Exception as e:
            _log_error(f"Unexpected error for topic '{topic}': {e}")
            failed_topics += 1
            continue

        for repo in repos:
            rid = repo.pop("_repo_id", None)
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            print(json.dumps(repo))

    if failed_topics == total_topics:
        _log_error(f"All {total_topics} topics failed")
        sys.exit(2)
    elif failed_topics > 0:
        _log_error(f"{failed_topics}/{total_topics} topics failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

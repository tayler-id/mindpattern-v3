"""
reddit-fetch.py — Reddit top posts fetcher using the public JSON API (no auth).

Usage:
    python3 reddit-fetch.py [--subreddits MachineLearning,LocalLLaMA,artificial]
                            [--period day] [--min-score 100]

Outputs one JSON object per line to stdout (newline-delimited JSON).
Errors are printed to stderr as structured JSON. Exit codes: 0=success, 1=partial, 2=total failure.

Note: Reddit requires a User-Agent header or returns 429 Too Many Requests.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import List, Optional, Tuple


TOOL_NAME = "reddit-fetch"
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]
DEFAULT_TIMEOUT = 15

HEADERS = {
    "User-Agent": "daily-research-agent/1.0",
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


def fetch_subreddit(subreddit: str, period: str, min_score: int) -> Tuple[List[dict], bool]:
    """Fetch top posts from a subreddit. Returns (results, had_error)."""
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t={period}&limit=50"

    try:
        body = _fetch_with_retry(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        data = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        _log_error(f"HTTP {e.code} for r/{subreddit}: {e.reason}", context=url)
        return [], True
    except Exception as e:
        _log_error(f"Failed to fetch r/{subreddit}: {e}", context=url)
        return [], True

    posts = data.get("data", {}).get("children", [])
    results = []

    for post in posts:
        post_data = post.get("data", {})
        score = post_data.get("score", 0)

        if score < min_score:
            continue

        selftext = (post_data.get("selftext") or "").strip()
        selftext = selftext[:200]

        permalink = post_data.get("permalink", "")
        reddit_url = f"https://reddit.com{permalink}" if permalink else ""

        results.append({
            "subreddit": post_data.get("subreddit", subreddit),
            "title": post_data.get("title", ""),
            "url": post_data.get("url", ""),
            "reddit_url": reddit_url,
            "score": score,
            "comments": post_data.get("num_comments", 0),
            "author": post_data.get("author", ""),
            "created_utc": post_data.get("created_utc", 0),
            "selftext": selftext,
        })

    return results, False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch top Reddit posts via public JSON API")
    parser.add_argument("--subreddits", default="MachineLearning,LocalLLaMA,artificial",
                        help="Comma-separated subreddit names (default: MachineLearning,LocalLLaMA,artificial)")
    parser.add_argument("--period", default="day",
                        choices=["hour", "day", "week", "month"],
                        help="Time period for top posts (default: day)")
    parser.add_argument("--min-score", type=int, default=100,
                        help="Minimum post score (upvotes) to include (default: 100)")
    args = parser.parse_args()

    subreddits = [s.strip() for s in args.subreddits.split(",") if s.strip()]
    total_subs = len(subreddits)
    failed_subs = 0

    for i, subreddit in enumerate(subreddits):
        if i > 0:
            time.sleep(2)

        try:
            posts, had_error = fetch_subreddit(subreddit, args.period, args.min_score)
            if had_error:
                failed_subs += 1
        except Exception as e:
            _log_error(f"Unexpected error for r/{subreddit}: {e}")
            failed_subs += 1
            continue

        for post in posts:
            print(json.dumps(post))

    if failed_subs == total_subs:
        _log_error(f"All {total_subs} subreddits failed")
        sys.exit(2)
    elif failed_subs > 0:
        _log_error(f"{failed_subs}/{total_subs} subreddits failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

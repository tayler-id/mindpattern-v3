"""
rss-fetch.py — RSS/Atom feed fetcher using feedparser.

Usage:
    python3 rss-fetch.py --feeds-file feeds.json [--hours 48]

feeds.json must be a JSON array of {"name": "...", "url": "..."} objects.

Outputs one JSON object per line to stdout (newline-delimited JSON).
Errors are printed to stderr as structured JSON. Exit codes: 0=success, 1=partial, 2=total failure.
"""

import argparse
import json
import socket
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

try:
    import feedparser
except ImportError:
    print(json.dumps({"error": "feedparser is required: pip install feedparser", "tool": "rss-fetch"}), file=sys.stderr)
    sys.exit(2)


TOOL_NAME = "rss-fetch"


def _log_error(message: str, context: Optional[str] = None) -> None:
    """Print structured JSON error to stderr."""
    err = {"error": message, "tool": TOOL_NAME}
    if context:
        err["context"] = context
    print(json.dumps(err), file=sys.stderr)


def struct_time_to_datetime(st) -> Optional[datetime]:
    """Convert a time.struct_time (as returned by feedparser) to a UTC-aware datetime."""
    if st is None:
        return None
    try:
        import calendar
        ts = calendar.timegm(st)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def strip_html_basic(text: str) -> str:
    """Very basic HTML tag stripping without external libraries."""
    import re
    return re.sub(r"<[^>]+>", "", text or "")


def process_feed(feed_def: dict, cutoff: datetime) -> Tuple[List[dict], bool]:
    """Process a single feed. Returns (results, had_error)."""
    name = feed_def.get("name", "")
    url = feed_def.get("url", "")
    results = []

    try:
        parsed = feedparser.parse(url)
    except Exception as e:
        _log_error(f"Error parsing feed '{name}' ({url}): {e}", context=url)
        return [], True

    if parsed.get("bozo") and parsed.get("bozo_exception"):
        exc = parsed["bozo_exception"]
        _log_error(f"Warning for feed '{name}': {exc}", context=url)

    for entry in parsed.get("entries", []):
        pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        pub_dt = struct_time_to_datetime(pub_struct)

        if pub_dt is not None and pub_dt < cutoff:
            continue

        if pub_dt is not None:
            published_str = pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            published_str = ""

        raw_summary = entry.get("summary", "") or ""
        summary = strip_html_basic(raw_summary).strip()
        summary = summary[:300]

        results.append({
            "source": name,
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", ""),
            "published": published_str,
            "summary": summary,
        })

    return results, False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch articles from RSS/Atom feeds")
    parser.add_argument("--feeds-file", required=True,
                        help="Path to JSON file containing list of {name, url} feed definitions")
    parser.add_argument("--hours", type=int, default=48,
                        help="Skip entries older than this many hours (default: 48)")
    args = parser.parse_args()

    try:
        with open(args.feeds_file, "r", encoding="utf-8") as f:
            feeds = json.load(f)
    except FileNotFoundError:
        _log_error(f"Feeds file not found: {args.feeds_file}")
        sys.exit(2)
    except json.JSONDecodeError as e:
        _log_error(f"Invalid JSON in feeds file: {e}")
        sys.exit(2)

    if not isinstance(feeds, list):
        _log_error("Feeds file must contain a JSON array")
        sys.exit(2)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    total_feeds = len(feeds)
    failed_feeds = 0

    # Prevent feedparser from hanging indefinitely on unresponsive servers
    socket.setdefaulttimeout(30)

    for feed_def in feeds:
        if not isinstance(feed_def, dict) or "url" not in feed_def:
            _log_error(f"Skipping invalid feed entry: {feed_def}")
            failed_feeds += 1
            continue

        try:
            entries, had_error = process_feed(feed_def, cutoff)
            if had_error:
                failed_feeds += 1
        except Exception as e:
            _log_error(f"Unexpected error for feed '{feed_def.get('name', '')}': {e}")
            failed_feeds += 1
            continue

        for entry in entries:
            print(json.dumps(entry))

    if total_feeds > 0 and failed_feeds == total_feeds:
        _log_error(f"All {total_feeds} feeds failed")
        sys.exit(2)
    elif failed_feeds > 0:
        _log_error(f"{failed_feeds}/{total_feeds} feeds failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

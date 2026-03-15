"""
arxiv-fetch.py — arXiv paper fetcher using the export API (no auth required).

Usage:
    python3 arxiv-fetch.py [--categories cs.AI,cs.LG,cs.CL] [--days 2] [--max 20]

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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import List, Optional


TOOL_NAME = "arxiv-fetch"
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
BACKOFF_DELAYS = [1, 2, 4]
DEFAULT_TIMEOUT = 15
ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"


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


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse an ISO-8601 datetime string (e.g. 2024-01-15T12:00:00Z) into a UTC datetime."""
    dt_str = dt_str.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(dt_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def fetch_arxiv(categories: List[str], days: int, max_results: int) -> List[dict]:
    cat_query = " OR ".join(f"cat:{c}" for c in categories)
    params = urllib.parse.urlencode({
        "search_query": cat_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"https://export.arxiv.org/api/query?{params}"

    body = _fetch_with_retry(
        url,
        headers={"User-Agent": "daily-research-agent/1.0"},
        timeout=DEFAULT_TIMEOUT,
    )
    raw = body.decode("utf-8")

    root = ET.fromstring(raw)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        published_el = entry.find(f"{{{ATOM_NS}}}published")
        published_str = published_el.text.strip() if published_el is not None else ""
        published_dt = parse_datetime(published_str) if published_str else None

        if published_dt and published_dt < cutoff:
            continue

        id_el = entry.find(f"{{{ATOM_NS}}}id")
        id_url = id_el.text.strip() if id_el is not None else ""
        arxiv_id = id_url.rstrip("/").split("/")[-1]
        base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

        title_el = entry.find(f"{{{ATOM_NS}}}title")
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""

        summary_el = entry.find(f"{{{ATOM_NS}}}summary")
        raw_summary = (summary_el.text or "").replace("\n", " ").strip() if summary_el is not None else ""
        summary = raw_summary[:500]

        authors = []
        for author_el in entry.findall(f"{{{ATOM_NS}}}author"):
            name_el = author_el.find(f"{{{ATOM_NS}}}name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())
            if len(authors) >= 3:
                break

        categories_out = []
        for cat_el in entry.findall(f"{{{ATOM_NS}}}category"):
            term = cat_el.get("term", "")
            if term:
                categories_out.append(term)

        results.append({
            "id": base_id,
            "title": title,
            "summary": summary,
            "url": f"https://arxiv.org/abs/{base_id}",
            "pdf_url": f"https://arxiv.org/pdf/{base_id}",
            "published": published_str,
            "authors": authors,
            "categories": categories_out,
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch arXiv papers via export API")
    parser.add_argument("--categories", default="cs.AI,cs.LG,cs.CL",
                        help="Comma-separated arXiv categories (default: cs.AI,cs.LG,cs.CL)")
    parser.add_argument("--days", type=int, default=2,
                        help="Only include papers published within this many days (default: 2)")
    parser.add_argument("--max", type=int, default=20,
                        help="Maximum number of results to fetch (default: 20)")
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    try:
        papers = fetch_arxiv(categories, args.days, args.max)
    except urllib.error.HTTPError as e:
        _log_error(f"HTTP {e.code}: {e.reason}")
        sys.exit(2)
    except Exception as e:
        _log_error(f"Failed to fetch arXiv papers: {e}")
        sys.exit(2)

    if not papers:
        _log_error("No papers found matching criteria (this may be expected)")

    for paper in papers:
        print(json.dumps(paper))


if __name__ == "__main__":
    main()

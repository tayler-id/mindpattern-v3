"""Preflight data collection for research agents.

Gathers structured data from 8 sources BEFORE agents run.
Each source module exports a `fetch() -> list[dict]` function
that returns items in the standard preflight entry schema.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR = PROJECT_ROOT / "tools"


def make_entry(
    *,
    source: str,
    source_name: str,
    title: str,
    url: str,
    published: str = "",
    content_preview: str = "",
    metrics: dict | None = None,
    already_covered: bool = False,
    match_info: dict | None = None,
) -> dict:
    """Create a standardized preflight entry dict."""
    return {
        "source": source,
        "source_name": source_name,
        "title": title,
        "url": url,
        "published": published,
        "content_preview": content_preview[:500],
        "metrics": metrics or {},
        "already_covered": already_covered,
        "match_info": match_info,
    }


def parse_ndjson(text: str) -> list[dict]:
    """Parse newline-delimited JSON from tool stdout."""
    import json
    items = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items

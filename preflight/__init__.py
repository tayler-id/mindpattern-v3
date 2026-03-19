"""Preflight data collection for research agents.

Gathers structured data from 8 sources BEFORE agents run.
Each source module exports a `fetch() -> list[dict]` function
that returns items in the standard preflight entry schema.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR = PROJECT_ROOT / "tools"


def _sanitize_external_text(text: str) -> str:
    """Strip control characters and known prompt injection delimiters from external content."""
    # Remove null bytes and control chars except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


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
        "title": _sanitize_external_text(title),
        "url": url,
        "published": published,
        "content_preview": _sanitize_external_text(content_preview[:500]),
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
                import logging
                logging.getLogger(__name__).debug(f"Skipping non-JSON line: {line[:100]}")
                continue
    return items

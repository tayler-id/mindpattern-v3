"""Preflight: GitHub trending repos via tools/github-fetch.py."""

import logging
import subprocess

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    desc = raw.get("description", "") or ""
    lang = raw.get("language", "")
    topics = ", ".join(raw.get("topics", [])[:5])
    preview = f"[{lang}] {desc}"
    if topics:
        preview += f" Topics: {topics}"
    return make_entry(
        source="github",
        source_name=raw.get("name", ""),
        title=f"{raw.get('name', '')}: {desc[:100]}",
        url=raw.get("url", ""),
        published=raw.get("pushed_at", ""),
        content_preview=preview,
        metrics={"stars": raw.get("stars", 0)},
    )


def fetch(
    topics: str = "llm,ai-agent,rag,mcp,ai-coding,vibe-coding,ai-sdk,llm-framework",
    days: int = 7,
    min_stars: int = 25,
) -> list[dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "github-fetch.py"),
        "--topics", topics,
        "--days", str(days),
        "--min-stars", str(min_stars),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"github-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]

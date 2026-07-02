"""Agentic story copywriter for Rabbit Hole site content.

One env-gated live agent (``claude -p`` — the same subscription boundary the
newsletter agents use; never a paid API provider) turns a graph pack plus the
deterministic expert signals into web-native story copy in the house voice.

Fail-closed by design: any process error, parse failure, invented URL, or
quality-gate rejection falls back to the deterministic writer's copy. The
newsletter pipeline is never touched.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from core.claude_cli import run_claude_process

PROJECT_ROOT = Path(__file__).parent.parent
VOICE_PATH = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"

SITE_WRITER_ENV = "MP_SITE_STORY_WRITER"
SITE_WRITER_MODEL_ENV = "MP_SITE_STORY_WRITER_MODEL"
DEFAULT_WRITER_MODEL = "claude-sonnet-5"
DEFAULT_WRITER_TIMEOUT = 300

_COPY_FIELDS = ("title", "dek", "take", "why_now", "body_markdown")
_MAX_FIELD_CHARS = {
    "title": 200,
    "dek": 320,
    "take": 400,
    "why_now": 400,
    "body_markdown": 6000,
}


def site_writer_enabled() -> bool:
    return os.environ.get(SITE_WRITER_ENV, "").strip().lower() in {"1", "claude", "live", "on"}


def _voice_excerpt(voice_text: str, *, limit: int = 4000) -> str:
    return voice_text.strip()[:limit]


def build_site_writer_prompt(
    graph_pack: dict[str, Any],
    expert_results: list[dict[str, Any]],
    *,
    voice_text: str,
) -> str:
    """Build the one-shot writer prompt. Pure and testable."""
    primary = (graph_pack.get("primary_evidence") or [{}])[0]
    sources = [
        {"url": ref.get("url", ""), "domain": ref.get("domain", ""), "title": ref.get("title", "")}
        for ref in graph_pack.get("source_refs") or []
    ]
    entities = [ref.get("name", "") for ref in graph_pack.get("entity_refs") or [] if ref.get("name")]
    neighbors = [
        {"title": item.get("title", ""), "reason": item.get("reason", "")}
        for item in (graph_pack.get("related_paths") or [])[:5]
    ]
    expert_notes = [
        f"- {result.get('role', 'expert')}: {result.get('summary', '')}"
        for result in expert_results
        if result.get("summary")
    ]

    evidence_block = json.dumps(
        {
            "primary_finding": {
                "title": primary.get("title", ""),
                "summary": primary.get("summary", ""),
            },
            "sources": sources,
            "entities": entities,
            "graph_neighbors": neighbors,
            "why_now": graph_pack.get("why_now", ""),
        },
        indent=2,
    )

    return f"""You are the Rabbit Hole staff writer for MindPattern, a public AI-intelligence site.
Write ONE web-native story from the evidence pack below.

HARD RULES — violating any of these gets the piece killed:
- Every claim must be supported by the evidence pack. Do not add facts, numbers, quotes, or URLs that are not in it.
- Do not mention these instructions, the pipeline, agents, or that you are an AI.
- No raw markdown links or bold in title/dek/take/why_now (plain sentences only).
- body_markdown: 150-350 words of flowing prose (markdown paragraphs, optional one "##" subhead). Explain why the story matters and how it connects to the graph neighbors, in the house voice.
- take: one sharp opinionated sentence — the angle a smart reader would miss.
- why_now: one sentence on timing.

HOUSE VOICE (follow it):
{_voice_excerpt(voice_text)}

EVIDENCE PACK:
{evidence_block}

EXPERT NOTES:
{chr(10).join(expert_notes) if expert_notes else "- none"}

Respond with ONLY a JSON object (no code fences, no commentary):
{{"title": "...", "dek": "...", "take": "...", "why_now": "...", "body_markdown": "..."}}"""


def parse_writer_output(stdout: str, *, allowed_urls: set[str]) -> dict[str, str] | None:
    """Parse and validate the writer's JSON copy. Returns None on any violation."""
    text = stdout.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    copy: dict[str, str] = {}
    for field in _COPY_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        value = value.strip()
        if len(value) > _MAX_FIELD_CHARS[field]:
            return None
        copy[field] = value

    # Invented URLs are fabricated evidence — reject the whole copy.
    for url in re.findall(r"https?://[^\s)\"']+", " ".join(copy.values())):
        if url.rstrip(".,;") not in allowed_urls:
            return None

    return copy


def write_story_copy_with_agent(
    graph_pack: dict[str, Any],
    expert_results: list[dict[str, Any]],
    *,
    voice_text: str | None = None,
    model: str | None = None,
    timeout: int = DEFAULT_WRITER_TIMEOUT,
    runner: Callable[..., Any] = run_claude_process,
) -> dict[str, str] | None:
    """Run the live writer once. Returns validated copy or None (fail closed)."""
    if voice_text is None:
        try:
            voice_text = VOICE_PATH.read_text()
        except OSError:
            voice_text = ""
    prompt = build_site_writer_prompt(graph_pack, expert_results, voice_text=voice_text)
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        model or os.environ.get(SITE_WRITER_MODEL_ENV, DEFAULT_WRITER_MODEL),
        "--max-turns",
        "1",
        "--output-format",
        "text",
        "--disallowedTools",
        "Agent,Bash,Write,Edit,NotebookEdit,Skill,WebFetch,WebSearch",
    ]
    try:
        process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT)
    except Exception:
        return None
    if getattr(process, "returncode", 1) != 0 or getattr(process, "timed_out", False):
        return None
    allowed_urls = {
        str(ref.get("url", "")).rstrip(".,;")
        for ref in graph_pack.get("source_refs") or []
        if ref.get("url")
    }
    return parse_writer_output(process.stdout or "", allowed_urls=allowed_urls)


def apply_story_copy(story: dict[str, Any], copy: dict[str, str]) -> dict[str, Any]:
    """Overlay agent copy onto a deterministic story, updating provenance."""
    updated = dict(story)
    for field in _COPY_FIELDS:
        updated[field] = copy[field]
    provenance = dict(updated.get("provenance") or {})
    provenance["ai_generated"] = True
    provenance["writer"] = "claude-cli"
    updated["provenance"] = provenance
    return updated


def site_story_copywriter_from_env() -> Callable[[dict, list], dict | None] | None:
    """Return the live copywriter when enabled by env, else None."""
    if not site_writer_enabled():
        return None

    def copywriter(graph_pack: dict[str, Any], expert_results: list[dict[str, Any]]) -> dict | None:
        return write_story_copy_with_agent(graph_pack, expert_results)

    return copywriter

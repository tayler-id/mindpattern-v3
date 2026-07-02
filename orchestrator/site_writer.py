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
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from core.claude_cli import run_claude_process

PROJECT_ROOT = Path(__file__).parent.parent
VOICE_PATH = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"
SOUL_PATH = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "soul.md"
WRITER_SYSTEM_PROMPT = PROJECT_ROOT / "agents" / "site-story-writer.md"

# Mirror of the voice guide's banned list. Copy that slips one of these (or an
# em dash) past the writer is rejected mechanically, not just by prompt.
BANNED_WORDS = {
    "delve", "tapestry", "multifaceted", "testament", "realm", "landscape",
    "nuanced", "pivotal", "robust", "seamless", "comprehensive", "leverage",
    "utilize", "foster", "embark", "illuminate", "elucidate", "meticulous",
    "meticulously", "unwavering", "unprecedented", "transformative",
    "groundbreaking", "cutting-edge", "revolutionary", "innovative",
    "intricate", "profound", "vibrant", "whimsical", "quintessential",
    "enigma", "labyrinth", "gossamer", "virtuoso", "beacon", "crucible",
    "underscore", "spearheaded", "transcended", "reverberate", "symphony",
}


def violates_voice_guide(text: str) -> str | None:
    """Return the first mechanical voice violation in ``text``, else None."""
    if "\u2014" in text or "—" in text:
        return "em_dash"
    lowered = text.lower()
    for word in BANNED_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return f"banned_word:{word}"
    return None

SITE_WRITER_ENV = "MP_SITE_STORY_WRITER"
SITE_WRITER_MODEL_ENV = "MP_SITE_STORY_WRITER_MODEL"
DEFAULT_WRITER_MODEL = "claude-sonnet-5"
DEFAULT_WRITER_TIMEOUT = 300

_COPY_FIELDS = ("title", "dek", "take", "why_now", "body_markdown")
_MAX_FIELD_CHARS = {
    "title": 90,
    "dek": 200,
    "take": 400,
    "why_now": 400,
    "body_markdown": 6000,
}


def site_writer_enabled() -> bool:
    return os.environ.get(SITE_WRITER_ENV, "").strip().lower() in {"1", "claude", "live", "on"}


def _voice_excerpt(voice_text: str, *, limit: int = 12000) -> str:
    return voice_text.strip()[:limit]


def load_writer_rules() -> str:
    try:
        return (PROJECT_ROOT / "docs" / "specs" / "site-writer-rules.md").read_text()
    except OSError:
        return ""


def evidence_block_for_pack(graph_pack: dict[str, Any]) -> str:
    """The single evidence JSON both the writer and the critic are shown."""
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
    return json.dumps(
        {
            "as_of_date": graph_pack.get("date", ""),
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


def build_site_writer_prompt(
    graph_pack: dict[str, Any],
    expert_results: list[dict[str, Any]],
    *,
    voice_text: str,
    rules_text: str | None = None,
) -> str:
    """Build the one-shot writer prompt. Pure and testable."""
    expert_notes = [
        f"- {result.get('role', 'expert')}: {result.get('summary', '')}"
        for result in expert_results
        if result.get("summary")
    ]

    evidence_block = evidence_block_for_pack(graph_pack)

    rules = rules_text if rules_text is not None else load_writer_rules()
    return f"""Write one Rabbit Hole site story from the evidence pack below.

## Writer's Rules (structure and craft; follow exactly)
{rules}

## Voice Guide
{_voice_excerpt(voice_text)}

## Evidence Pack
{evidence_block}

## Expert Notes
{chr(10).join(expert_notes) if expert_notes else "- none"}

Follow the output contract from your instructions. JSON only."""


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

    # Invented URLs are fabricated evidence: reject the whole copy.
    for url in re.findall(r"https?://[^\s)\"']+", " ".join(copy.values())):
        if url.rstrip(".,;") not in allowed_urls:
            return None

    # Voice violations (em dashes, banned words) fail closed too.
    if violates_voice_guide(" ".join(copy.values())):
        return None

    return copy


def diagnose_writer_output(stdout: str, *, allowed_urls: set[str]) -> str:
    text = stdout.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return "no_json"
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "bad_json"
    if not isinstance(payload, dict):
        return "not_object"
    for field in _COPY_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"missing:{field}"
        if len(value.strip()) > _MAX_FIELD_CHARS[field]:
            return f"too_long:{field}:{len(value.strip())}"
    joined = " ".join(str(payload.get(f, "")) for f in _COPY_FIELDS)
    for url in re.findall(r"https?://[^\s)\"']+", joined):
        if url.rstrip(".,;") not in allowed_urls:
            return f"invented_url:{url[:60]}"
    violation = violates_voice_guide(joined)
    if violation:
        return f"voice:{violation}"
    return "unknown"


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
        "8",
        "--output-format",
        "text",
        "--append-system-prompt-file",
        str(WRITER_SYSTEM_PROMPT),
        "--disallowedTools",
        "Agent,Bash,Write,Edit,NotebookEdit,Skill,WebFetch,WebSearch",
    ]
    candidate = graph_pack.get("candidate_id", "story")
    process = None
    for attempt in (1, 2):
        try:
            process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT)
        except Exception as exc:
            logger.warning("site_writer %s: process exception %s", candidate, exc)
            return None
        if getattr(process, "returncode", 1) == 0 and not getattr(process, "timed_out", False):
            break
        logger.warning(
            "site_writer %s attempt %d: exit=%s timed_out=%s stderr=%.300s stdout=%.200s",
            candidate,
            attempt,
            getattr(process, "returncode", None),
            getattr(process, "timed_out", None),
            getattr(process, "stderr", ""),
            getattr(process, "stdout", ""),
        )
    if process is None or getattr(process, "returncode", 1) != 0 or getattr(process, "timed_out", False):
        return None
    allowed_urls = {
        str(ref.get("url", "")).rstrip(".,;")
        for ref in graph_pack.get("source_refs") or []
        if ref.get("url")
    }
    copy = parse_writer_output(process.stdout or "", allowed_urls=allowed_urls)
    if copy is None:
        logger.warning(
            "site_writer %s: output rejected (%s) stdout=%.300s",
            candidate,
            diagnose_writer_output(process.stdout or "", allowed_urls=allowed_urls),
            (process.stdout or "").strip()[:300],
        )
    return copy


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

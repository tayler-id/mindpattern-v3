"""Editorial critic + revision harness for Rabbit Hole site stories.

The writer drafts, the critic judges the draft against the writer's-rules spec
(docs/specs/site-writer-rules.md) and the voice guide, and the writer gets one
revision with the critic's notes. Anything that still fails the critic or the
mechanical voice validator falls back to deterministic copy. Same ``claude -p``
subscription boundary as the newsletter; fails closed everywhere.
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
from orchestrator.site_writer import (
    DEFAULT_WRITER_TIMEOUT,
    PROJECT_ROOT,
    build_site_writer_prompt,
    parse_writer_output,
    violates_voice_guide,
    write_story_copy_with_agent,
)

RULES_SPEC_PATH = PROJECT_ROOT / "docs" / "specs" / "site-writer-rules.md"
CRITIC_SYSTEM_PROMPT = PROJECT_ROOT / "agents" / "site-story-critic.md"

SITE_CRITIC_ENV = "MP_SITE_STORY_CRITIC"
SITE_CRITIC_MODEL_ENV = "MP_SITE_STORY_CRITIC_MODEL"
DEFAULT_CRITIC_MODEL = "claude-sonnet-5"

PASS_SCORE = 8


def critic_enabled() -> bool:
    """Critic defaults ON whenever the writer runs; MP_SITE_STORY_CRITIC=off disables."""
    return os.environ.get(SITE_CRITIC_ENV, "on").strip().lower() not in {"0", "off", "false"}


def load_rules_spec() -> str:
    try:
        return RULES_SPEC_PATH.read_text()
    except OSError:
        return ""


def build_critic_prompt(copy: dict[str, str], graph_pack: dict[str, Any], *, rules_text: str) -> str:
    evidence = json.dumps(
        {
            "primary_finding": (graph_pack.get("primary_evidence") or [{}])[0],
            "sources": graph_pack.get("source_refs") or [],
        },
        indent=2,
        default=str,
    )
    draft = json.dumps(copy, indent=2)
    return f"""Judge this Rabbit Hole story draft against the writer's rules.

## Writer's Rules
{rules_text}

## Evidence Pack (ground truth; anything beyond it is fabrication)
{evidence}

## Draft
{draft}

Respond with ONLY a JSON object:
{{"score": 0-10, "verdict": "pass" | "revise", "issues": ["specific, fixable note", ...]}}
Score 8+ means publishable as-is. List every rule violation you find; be concrete
(quote the offending phrase). Fabricated facts or numbers are an automatic 0."""


def parse_critic_output(stdout: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", stdout.strip(), re.DOTALL)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        score = float(payload.get("score", -1))
    except (TypeError, ValueError):
        return None
    if not 0 <= score <= 10:
        return None
    issues = [str(item) for item in payload.get("issues") or [] if str(item).strip()]
    return {
        "score": score,
        "verdict": "pass" if str(payload.get("verdict")) == "pass" and score >= PASS_SCORE else "revise",
        "issues": issues,
    }


def run_critic(
    copy: dict[str, str],
    graph_pack: dict[str, Any],
    *,
    rules_text: str | None = None,
    timeout: int = DEFAULT_WRITER_TIMEOUT,
    runner: Callable[..., Any] = run_claude_process,
) -> dict[str, Any] | None:
    """One critic pass. Returns verdict dict or None on any failure."""
    prompt = build_critic_prompt(copy, graph_pack, rules_text=rules_text or load_rules_spec())
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        os.environ.get(SITE_CRITIC_MODEL_ENV, DEFAULT_CRITIC_MODEL),
        "--max-turns",
        "8",
        "--output-format",
        "text",
        "--append-system-prompt-file",
        str(CRITIC_SYSTEM_PROMPT),
        "--disallowedTools",
        "Agent,Bash,Write,Edit,NotebookEdit,Skill,WebFetch,WebSearch",
    ]
    try:
        process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT)
    except Exception:
        return None
    if getattr(process, "returncode", 1) != 0 or getattr(process, "timed_out", False):
        return None
    return parse_critic_output(process.stdout or "")


def build_revision_prompt(
    graph_pack: dict[str, Any],
    copy: dict[str, str],
    issues: list[str],
    *,
    voice_text: str,
) -> str:
    base = build_site_writer_prompt(graph_pack, [], voice_text=voice_text)
    notes = "\n".join(f"- {issue}" for issue in issues[:8])
    draft = json.dumps(copy, indent=2)
    return f"""{base}

## Your previous draft
{draft}

## Editor's notes (fix every one)
{notes}

Rewrite the story fixing every note. Keep what already works. JSON only."""


def write_story_with_review(
    graph_pack: dict[str, Any],
    expert_results: list[dict[str, Any]],
    *,
    voice_text: str | None = None,
    rules_text: str | None = None,
    timeout: int = DEFAULT_WRITER_TIMEOUT,
    runner: Callable[..., Any] = run_claude_process,
) -> dict[str, str] | None:
    """Writer -> critic -> one revision -> critic. Fail closed to None."""
    if voice_text is None:
        from orchestrator.site_writer import VOICE_PATH

        try:
            voice_text = VOICE_PATH.read_text()
        except OSError:
            voice_text = ""
    rules = rules_text if rules_text is not None else load_rules_spec()

    draft = write_story_copy_with_agent(
        graph_pack, expert_results, voice_text=voice_text, timeout=timeout, runner=runner
    )
    if draft is None:
        return None
    if not critic_enabled():
        return draft

    candidate_id = graph_pack.get("candidate_id", "story")
    verdict = run_critic(draft, graph_pack, rules_text=rules, timeout=timeout, runner=runner)
    if verdict is None:
        # Critic unavailable: the mechanically validated draft is still better
        # than template copy, so publish it rather than fail the whole story.
        logger.warning("site_critic %s: critic unavailable, publishing draft", candidate_id)
        return draft
    if verdict["verdict"] == "pass":
        return draft
    logger.warning(
        "site_critic %s: score=%s issues=%s",
        candidate_id,
        verdict["score"],
        "; ".join(verdict["issues"][:4])[:400],
    )
    # Fabrication (score 0) goes back to the writer with the critic's notes,
    # like any desk: the editor names the unsupported claim, the writer cuts
    # it. The fabricating draft itself is never a publishable fallback.
    draft_is_usable = verdict["score"] >= 5
    prompt = build_revision_prompt(graph_pack, draft, verdict["issues"], voice_text=voice_text)
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        os.environ.get("MP_SITE_STORY_WRITER_MODEL", "claude-sonnet-5"),
        "--max-turns",
        "8",
        "--output-format",
        "text",
        "--append-system-prompt-file",
        str(PROJECT_ROOT / "agents" / "site-story-writer.md"),
        "--disallowedTools",
        "Agent,Bash,Write,Edit,NotebookEdit,Skill,WebFetch,WebSearch",
    ]
    candidate = graph_pack.get("candidate_id", "story")
    try:
        process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT)
    except Exception as exc:
        logger.warning("site_critic %s: revision exception %s", candidate, exc)
        return draft if draft_is_usable else None
    if getattr(process, "returncode", 1) != 0 or getattr(process, "timed_out", False):
        logger.warning(
            "site_critic %s: revision exit=%s stderr=%.200s",
            candidate,
            getattr(process, "returncode", None),
            getattr(process, "stderr", ""),
        )
        return draft if draft_is_usable else None
    allowed_urls = {
        str(ref.get("url", "")).rstrip(".,;")
        for ref in graph_pack.get("source_refs") or []
        if ref.get("url")
    }
    revised = parse_writer_output(process.stdout or "", allowed_urls=allowed_urls)
    if revised is None:
        logger.warning("site_critic %s: revision output rejected", candidate)
        return draft if draft_is_usable else None

    final_verdict = run_critic(revised, graph_pack, rules_text=rules, timeout=timeout, runner=runner)
    if final_verdict is None or final_verdict["verdict"] == "pass":
        return revised
    logger.warning(
        "site_critic %s: post-revision score=%s issues=%s",
        candidate,
        final_verdict["score"],
        "; ".join(final_verdict["issues"][:3])[:300],
    )
    # Still failing after one revision: keep the better-scored version if
    # either is usable, else fail closed to deterministic copy.
    if final_verdict["score"] >= 5 or draft_is_usable:
        return revised if final_verdict["score"] >= verdict["score"] else draft
    return None


def reviewed_copywriter_from_env() -> Callable[[dict, list], dict | None] | None:
    """Copywriter with the critic loop, gated by MP_SITE_STORY_WRITER."""
    from orchestrator.site_writer import site_writer_enabled

    if not site_writer_enabled():
        return None

    def copywriter(graph_pack: dict[str, Any], expert_results: list[dict[str, Any]]) -> dict | None:
        return write_story_with_review(graph_pack, expert_results)

    return copywriter

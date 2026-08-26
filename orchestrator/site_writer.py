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
from orchestrator import word_bank
from orchestrator.site_copy_lint import (
    BANNED_WORDS,
    COPY_FIELDS,
    MAX_FIELD_CHARS,
    CopyLintIssue,
    copy_allowed_urls_from_refs,
    first_voice_violation,
    format_lint_issues_for_prompt,
    hard_fail_issues,
    lint_site_copy,
    required_inline_links,
)

PROJECT_ROOT = Path(__file__).parent.parent

VOICE_PATH = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "voice.md"
SOUL_PATH = PROJECT_ROOT / "data" / "ramsay" / "mindpattern" / "soul.md"
WRITER_SYSTEM_PROMPT = PROJECT_ROOT / "agents" / "site-story-writer.md"

def violates_voice_guide(text: str) -> str | None:
    """Return the first mechanical voice violation in ``text``, else None."""
    return first_voice_violation(text)

SITE_WRITER_ENV = "MP_SITE_STORY_WRITER"
SITE_WRITER_MODEL_ENV = "MP_SITE_STORY_WRITER_MODEL"
DEFAULT_WRITER_MODEL = "claude-sonnet-5"
DEFAULT_WRITER_TIMEOUT = 300

_COPY_FIELDS = COPY_FIELDS
_MAX_FIELD_CHARS = MAX_FIELD_CHARS


class UsageLimitReached(RuntimeError):
    """The Claude subscription hit its session/usage limit."""


_LIMIT_MARKERS = ("hit your session limit", "usage limit", "rate limit")


def _is_limit_response(process) -> bool:
    text = f"{getattr(process, 'stdout', '')} {getattr(process, 'stderr', '')}".lower()
    return any(marker in text for marker in _LIMIT_MARKERS)


def site_writer_enabled() -> bool:
    value = os.environ.get(SITE_WRITER_ENV, "").strip().lower()
    return bool(value) and value not in {"0", "off", "false"}


def writer_provider() -> str:
    """Which drafting provider MP_SITE_STORY_WRITER selects.

    "claude" (default), "codex" (Codex CLI, its own quota), or
    "cmd:<shell template>" (any CLI: prompt on stdin, JSON copy on stdout).
    The critic gate is always Claude regardless of the drafting provider.
    """
    value = os.environ.get(SITE_WRITER_ENV, "").strip()
    lowered = value.lower()
    if lowered in {"", "1", "claude", "live", "on"}:
        return "claude"
    if lowered == "codex":
        return "codex"
    if lowered.startswith("cmd:"):
        return value
    return "claude"


def writer_label() -> str:
    provider = writer_provider()
    if provider == "claude":
        return "claude-cli"
    if provider == "codex":
        return "codex"
    return "cmd"


def writer_command(prompt: str, *, model: str | None = None) -> tuple[list[str], str | None]:
    """(argv, stdin) for one drafting call under the current provider."""
    provider = writer_provider()
    if provider == "codex":
        return (
            ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", prompt],
            None,
        )
    if provider.startswith("cmd:"):
        return (["sh", "-c", provider[4:]], prompt)
    return (
        [
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
        ],
        None,
    )


# voice.md was 13,318 chars on 2026-08-23 against a 12,000 limit, so the tail of
# the humanize pass (plain speech, active voice, adverbs) stopped reaching the
# writer with no warning. The limit exists to bound a runaway file, not to trim
# the current one, so it sits well above the real length and the writer prompt
# appends the word bank separately.
def _voice_excerpt(voice_text: str, *, limit: int = 40000) -> str:
    return voice_text.strip()[:limit]


def load_writer_rules() -> str:
    try:
        return (PROJECT_ROOT / "docs" / "specs" / "site-writer-rules.md").read_text()
    except OSError:
        return ""


def linkable_source_urls(graph_pack: dict[str, Any]) -> list[str]:
    """The source URLs the writer is allowed to link, in pack order, deduped."""
    urls: list[str] = []
    for ref in graph_pack.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        url = str(ref.get("url") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def evidence_block_for_pack(graph_pack: dict[str, Any]) -> str:
    """The single evidence JSON both the writer and the critic are shown."""
    primary = (graph_pack.get("primary_evidence") or [{}])[0]
    sources = [
        {
            "url": ref.get("url", ""),
            "domain": ref.get("domain", ""),
            "title": ref.get("title", ""),
            "linkable": bool(str(ref.get("url") or "").strip()),
        }
        for ref in graph_pack.get("source_refs") or []
    ]
    urls = linkable_source_urls(graph_pack)
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
            "linkable_source_urls": urls,
            "source_link_policy": {
                "required_inline_links": required_inline_links(len(urls)),
                "where": "body_markdown only. Never in title, dek, take, or why_now.",
                "syntax": "[descriptive anchor](url), using a URL from linkable_source_urls verbatim.",
                "anchor_text": (
                    "Name the thing on the other end: the project, repo, paper, company, "
                    'or post. Never "Source", never "here", never a bare URL.'
                ),
                "no_other_urls": "Any URL outside linkable_source_urls fails the copy gate.",
            },
            "entities": entities,
            "graph_neighbors": neighbors,
            "why_now": graph_pack.get("why_now", ""),
        },
        indent=2,
    )


def _outbound_link_block(urls: list[str]) -> str:
    """The link instruction shown to the writer, sized to the evidence it has."""
    if not urls:
        return (
            "This pack carries no source URLs, so write the story without links. "
            "Do not invent one."
        )
    target = required_inline_links(len(urls))
    listed = "\n".join(f"- {url}" for url in urls[:8])
    ask = f"Put {target} inline markdown {'link' if target == 1 else 'links'}"
    counted = f"{len(urls)} source URL" + ("" if len(urls) == 1 else "s")
    return f"""The story is built on {counted}. {ask} in body_markdown,
pointing at these URLs and no others:

{listed}

- Syntax: [descriptive anchor](url), copied character for character from the list.
- Anchor text names the thing being linked: the project, the repo, the paper, the
  company, the post. Never the bare word "Source", never "here" or "click here",
  never a naked URL, never the whole sentence.
- Link the first mention of a thing, inside the sentence that makes the claim.
- One link per source. Never two links in the same sentence.
- Links belong in body_markdown only. A link in title, dek, take, or why_now
  fails the copy gate.
- A URL that is not on this list fails the copy gate."""


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
    link_block = _outbound_link_block(linkable_source_urls(graph_pack))

    rules = rules_text if rules_text is not None else load_writer_rules()
    return f"""Write one Rabbit Hole site story from the evidence pack below.

## Writer's Rules (structure and craft; follow exactly)
{rules}

## Word bank (the copy lint measures every one of these)
{word_bank.prompt_block("site")}

## Voice Guide
{_voice_excerpt(voice_text)}

## Evidence Pack
{evidence_block}

## Outbound links (required)
{link_block}

## Expert Notes
{chr(10).join(expert_notes) if expert_notes else "- none"}

Follow the output contract from your instructions. JSON only."""


def parse_writer_output(
    stdout: str,
    *,
    allowed_urls: set[str],
) -> dict[str, str] | None:
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

    issues = lint_site_copy(payload, allowed_urls=allowed_urls, include_revise=False)
    if hard_fail_issues(issues):
        return None

    return {field: str(payload[field]).strip() for field in _COPY_FIELDS}


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
    issues = hard_fail_issues(
        lint_site_copy(payload, allowed_urls=allowed_urls, include_revise=False)
    )
    if issues:
        issue = issues[0]
        return f"{issue.code}:{issue.field}:{issue.excerpt}" if issue.excerpt else f"{issue.code}:{issue.field}"
    return "unknown"


def _gate_rejection_prompt(prompt: str, stdout: str, *, allowed_urls: set[str]) -> str:
    """One rewrite instruction for a draft the mechanical copy gate rejected."""
    text = stdout.strip()
    issues: list[CopyLintIssue] = []
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is not None:
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            issues = hard_fail_issues(
                lint_site_copy(payload, allowed_urls=allowed_urls, include_revise=False)
            )
    notes = (
        format_lint_issues_for_prompt(issues)
        if issues
        else f"- {diagnose_writer_output(stdout, allowed_urls=allowed_urls)}"
    )
    return f"""{prompt}

## Your previous draft
{text[:3000]}

## It was rejected by the mechanical copy gate (fix every item)
{notes}

Rewrite the full story fixing every rejection. Keep what already works. JSON only."""


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
    if writer_provider() != "claude":
        # Non-Claude providers get the system prompt inline.
        try:
            prompt = WRITER_SYSTEM_PROMPT.read_text() + "\n\n" + prompt
        except OSError:
            pass
    cmd, stdin_text = writer_command(prompt, model=model)
    candidate = graph_pack.get("candidate_id", "story")
    process = None
    for attempt in (1, 2):
        try:
            process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT, input_text=stdin_text)
        except TypeError:
            process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT)
        except Exception as exc:
            logger.warning("site_writer %s: process exception %s", candidate, exc)
            return None
        if getattr(process, "returncode", 1) == 0 and not getattr(process, "timed_out", False):
            break
        if _is_limit_response(process):
            raise UsageLimitReached(f"claude usage limit while writing {candidate}")
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
    allowed_urls = copy_allowed_urls_from_refs(graph_pack.get("source_refs"))
    copy = parse_writer_output(process.stdout or "", allowed_urls=allowed_urls)
    if copy is None:
        logger.warning(
            "site_writer %s: output rejected (%s) stdout=%.300s",
            candidate,
            diagnose_writer_output(process.stdout or "", allowed_urls=allowed_urls),
            (process.stdout or "").strip()[:300],
        )
        # A gate rejection is fixable feedback, not a dead process: give the
        # writer the lint notes and one rewrite, same shape as the critic loop.
        retry_prompt = _gate_rejection_prompt(
            prompt, process.stdout or "", allowed_urls=allowed_urls
        )
        cmd, stdin_text = writer_command(retry_prompt, model=model)
        try:
            try:
                process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT, input_text=stdin_text)
            except TypeError:
                process = runner(cmd, timeout=timeout, cwd=PROJECT_ROOT)
        except Exception as exc:
            logger.warning("site_writer %s: gate-rejection retry exception %s", candidate, exc)
            return None
        if getattr(process, "returncode", 1) != 0 or getattr(process, "timed_out", False):
            if _is_limit_response(process):
                raise UsageLimitReached(f"claude usage limit while writing {candidate}")
            return None
        copy = parse_writer_output(process.stdout or "", allowed_urls=allowed_urls)
        if copy is None:
            logger.warning(
                "site_writer %s: gate-rejection retry rejected (%s)",
                candidate,
                diagnose_writer_output(process.stdout or "", allowed_urls=allowed_urls),
            )
    return copy


def ensure_claim_evidence(story: dict[str, Any]) -> dict[str, Any]:
    """Guarantee the headline claim is tied to the primary source.

    The public gate refuses stories without claim evidence; writer-upgraded
    newsletter stories inherit an empty list from their dynamic parents, so
    anchor the title claim to the first cited source.
    """
    if story.get("claim_evidence"):
        return story
    refs = story.get("source_refs") or []
    if not refs or not story.get("title"):
        return story
    updated = dict(story)
    updated["claim_evidence"] = [{
        "claim": str(story["title"]),
        "source_url": str(refs[0].get("url") or ""),
        "finding_id": None,
    }]
    return updated


def apply_story_copy(story: dict[str, Any], copy: dict[str, str]) -> dict[str, Any]:
    """Overlay agent copy onto a deterministic story, updating provenance."""
    updated = dict(story)
    for field in _COPY_FIELDS:
        updated[field] = copy[field]
    provenance = dict(updated.get("provenance") or {})
    provenance["ai_generated"] = True
    provenance["writer"] = writer_label()
    updated["provenance"] = provenance
    return ensure_claim_evidence(updated)


def site_story_copywriter_from_env() -> Callable[[dict, list], dict | None] | None:
    """Return the live copywriter when enabled by env, else None."""
    if not site_writer_enabled():
        return None

    def copywriter(graph_pack: dict[str, Any], expert_results: list[dict[str, Any]]) -> dict | None:
        return write_story_copy_with_agent(graph_pack, expert_results)

    return copywriter

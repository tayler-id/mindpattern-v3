"""LLM-driven identity file evolution for the EVOLVE phase.

After each pipeline run, an LLM reviews the current identity files (soul.md,
user.md, voice.md) plus recent editorial decisions, and proposes a JSON diff
describing incremental updates. This module builds the prompt, parses the
LLM output, validates the diff, and applies it via vault.py primitives.

The EVOLVE phase is the only writer of identity files at runtime. All writes
go through vault.atomic_write so Obsidian never sees partial content.
"""

import json
import re
from pathlib import Path

from memory import vault

# Only these keys are allowed in the evolution diff.
ALLOWED_KEYS = {"soul", "user", "voice", "decisions"}

# Maps diff keys to their vault filenames.
FILE_MAP = {
    "soul": "soul.md",
    "user": "user.md",
    "voice": "voice.md",
    "decisions": "decisions.md",
}

# Valid action values.
VALID_ACTIONS = {"update", "none", "append"}

# Maximum characters per content field.
# Decisions entries include topic, gate outcomes, scores, and pattern notes,
# which regularly exceed 500 chars. 3000 is generous but still bounded.
MAX_CONTENT_LENGTH = 3000

# Patterns that must not appear in LLM-produced content written to vault files.
# Prevents YAML frontmatter injection, Obsidian wikilink/templater injection, and HTML.
_UNSAFE_PATTERNS = re.compile(
    r"^---\s*$"         # YAML frontmatter delimiter
    r"|<%%|%%>"          # Obsidian templater directives
    r"|<script|<iframe"  # HTML injection
    , re.MULTILINE | re.IGNORECASE
)
# Section names must be safe heading text only.
_SAFE_SECTION_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _-]{0,63}$")


def _sanitize_vault_content(text: str) -> str:
    """Strip Obsidian-active patterns from LLM-produced content."""
    # Strip YAML frontmatter blocks
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, flags=re.DOTALL)
    # Neutralize wikilinks: [[target]] -> \[\[target\]\]
    text = text.replace("[[", r"\[\[").replace("]]", r"\]\]")
    # Neutralize templater directives
    text = text.replace("<%", r"\<%").replace("%>", r"\%>")
    # Strip HTML tags
    text = re.sub(r"<(script|iframe|object|embed)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text


# ── Prompt builder ──────────────────────────────────────────────────────────


def build_evolve_prompt(vault_dir: Path, pipeline_results: dict) -> str:
    """Build a prompt that instructs an LLM to produce a JSON evolution diff.

    Reads the current identity files from *vault_dir* and the last 7 entries
    from decisions.md, then combines them with *pipeline_results* into a
    single prompt string.

    Args:
        vault_dir: Path to the Obsidian vault directory.
        pipeline_results: Dict with keys like ``topic``, ``gate1_outcome``,
            ``gate2_outcome``, ``corrections``, ``expeditor_feedback``.

    Returns:
        A prompt string ready to pass to ``run_claude_prompt()``.
    """
    vault_dir = Path(vault_dir)

    soul_content = vault.read_source_file(vault_dir / "soul.md")
    user_content = vault.read_source_file(vault_dir / "user.md")
    voice_content = vault.read_source_file(vault_dir / "voice.md")

    decisions_path = vault_dir / "decisions.md"
    recent_decisions = vault.get_recent_entries(decisions_path, n=7)
    decisions_text = "\n\n---\n\n".join(recent_decisions) if recent_decisions else "(no recent decisions)"

    # Build structured sections for social and newsletter results
    social = pipeline_results.get("social", {})
    social_section = ""
    if social and social.get("topic"):
        social_section = f"""
## Social Pipeline Results
- Topic: {social.get('topic', 'none')} (score: {social.get('topic_score', 'N/A')})
- Gate 1: {social.get('gate1_outcome', 'unknown')}{' — ' + social['gate1_guidance'] if social.get('gate1_guidance') else ''}
- Gate 2: {social.get('gate2_outcome', 'unknown')}{' (edits: ' + ', '.join(social['gate2_edits']) + ')' if social.get('gate2_edits') else ''}
- Expeditor: {social.get('expeditor_verdict', 'unknown')}
- Posted to: {', '.join(social.get('platforms_posted', [])) or 'none'}
"""

    newsletter_eval = pipeline_results.get("newsletter_eval", {})
    newsletter_section = ""
    if newsletter_eval:
        newsletter_section = f"""
## Newsletter Quality Scores
- Overall: {newsletter_eval.get('overall', 'N/A')}
- Coverage: {newsletter_eval.get('coverage', 'N/A')}
- Dedup: {newsletter_eval.get('dedup', 'N/A')}
- Sources: {newsletter_eval.get('sources', 'N/A')}
"""

    core_results = f"""
## Core Pipeline Results
- Date: {pipeline_results.get('date', 'unknown')}
- Findings: {pipeline_results.get('findings_count', 0)}
- Newsletter generated: {pipeline_results.get('newsletter_generated', False)}
"""

    return f"""\
You are the EVOLVE phase of the MindPattern pipeline. Your job is to review
the current identity files and this run's results, then propose small,
incremental updates to keep the identity files accurate and useful.

## Current Identity Files

### soul.md
{soul_content}

### user.md
{user_content}

### voice.md
{voice_content}

### Recent Decisions (last 7 entries from decisions.md)
{decisions_text}

{core_results}
{social_section}
{newsletter_section}

## Instructions

Based on the run results, decide whether any identity files need updating.
Most runs should produce NO changes to soul/user/voice — only update when
there is a genuine lesson, preference shift, or pattern worth recording.

However, you MUST ALWAYS append to decisions.md with a detailed entry including:
- Topic selected/killed + score + reasoning
- Gate 1 outcome (approved/rejected/custom + any user guidance)
- Gate 2 outcome (approved/rejected/edits made)
- Expeditor verdict
- Newsletter quality scores
- Pattern observations (e.g. "3rd security topic rejected this week")

Output a single JSON object with these rules:
- Keys: only "soul", "user", "voice", "decisions" are allowed.
- Each value is an object with:
  - "action": one of "update", "append", or "none"
  - "section": (required for "update") the ## section heading to update
  - "content": (required for "update" and "append") the new text (max 3000 chars)
- "append" is only valid for "decisions" — it adds a new dated entry.
- "update" replaces the body of the named ## section in the target file.
- "none" means no change needed for that file.
- Omitting a key is equivalent to "none".

Output ONLY the JSON object. No explanation before or after.

JSON:"""


# ── LLM output parser ──────────────────────────────────────────────────────


def parse_llm_output(raw_output: str) -> dict | None:
    """Extract a JSON dict from raw LLM output.

    Handles:
    - Clean JSON (the full string is valid JSON)
    - JSON inside markdown code fences (```json ... ``` or ``` ... ```)
    - JSON embedded in surrounding prose (first { ... last })

    Args:
        raw_output: Raw text from the LLM.

    Returns:
        Parsed dict, or None if no valid JSON could be extracted.
    """
    if not raw_output or not raw_output.strip():
        return None

    text = raw_output.strip()

    # 1. Try the whole string as JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try extracting from markdown code fences.
    fence_pattern = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Try extracting the first { ... } block.
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ── Diff applier ────────────────────────────────────────────────────────────


def apply_evolution_diff(vault_dir: Path, diff_json: dict) -> dict:
    """Validate and apply an evolution diff to the vault files.

    Args:
        vault_dir: Path to the Obsidian vault directory.
        diff_json: Parsed JSON diff from the LLM. Expected schema::

            {
                "soul":      {"action": "update|none|append", "section": "...", "content": "..."},
                "user":      {"action": "update|none|append", "section": "...", "content": "..."},
                "voice":     {"action": "update|none|append", "section": "...", "content": "..."},
                "decisions": {"action": "update|none|append", "content": "..."},
            }

    Returns:
        ``{"changes_made": [...], "errors": [...]}``
    """
    vault_dir = Path(vault_dir)
    changes_made: list[str] = []
    errors: list[str] = []

    if not isinstance(diff_json, dict):
        return {"changes_made": [], "errors": ["diff_json must be a dict"]}

    for key, spec in diff_json.items():
        # Reject unknown keys.
        if key not in ALLOWED_KEYS:
            errors.append(f"Unknown key '{key}' — only {sorted(ALLOWED_KEYS)} are allowed")
            continue

        # Each value must be a dict.
        if not isinstance(spec, dict):
            errors.append(f"Value for '{key}' must be a dict, got {type(spec).__name__}")
            continue

        action = spec.get("action")
        if action is None:
            errors.append(f"Missing 'action' for key '{key}'")
            continue

        if action not in VALID_ACTIONS:
            errors.append(f"Invalid action '{action}' for key '{key}' — must be one of {sorted(VALID_ACTIONS)}")
            continue

        # action == "none" — skip.
        if action == "none":
            continue

        # action == "append" — only valid for decisions.
        if action == "append":
            if key != "decisions":
                errors.append(f"action='append' is only valid for 'decisions', not '{key}'")
                continue

            content = _sanitize_vault_content(spec.get("content", ""))
            if not content:
                errors.append(f"Missing 'content' for append on '{key}'")
                continue

            if len(content) > MAX_CONTENT_LENGTH:
                errors.append(
                    f"Content for '{key}' is {len(content)} chars, exceeds max {MAX_CONTENT_LENGTH}"
                )
                continue

            path = vault_dir / FILE_MAP[key]
            try:
                vault.append_entry(path, content)
                changes_made.append(f"Appended entry to {FILE_MAP[key]}")
            except Exception as exc:
                errors.append(f"Failed to append to {FILE_MAP[key]}: {exc}")

        # action == "update"
        elif action == "update":
            section = spec.get("section", "")
            if not section:
                errors.append(f"Missing 'section' for update on '{key}'")
                continue
            # LLMs sometimes include the markdown heading prefix ("## ").
            # Strip it so the regex validates the heading text only.
            section = re.sub(r"^#{1,6}\s+", "", section).strip()
            if not _SAFE_SECTION_NAME.match(section):
                errors.append(f"Invalid section name '{section}' for key '{key}'")
                continue

            content = _sanitize_vault_content(spec.get("content", ""))
            if not content:
                errors.append(f"Missing 'content' for update on '{key}'")
                continue

            if len(content) > MAX_CONTENT_LENGTH:
                errors.append(
                    f"Content for '{key}' is {len(content)} chars, exceeds max {MAX_CONTENT_LENGTH}"
                )
                continue

            path = vault_dir / FILE_MAP[key]
            try:
                vault.update_section(path, section, content)
                changes_made.append(f"Updated section '{section}' in {FILE_MAP[key]}")
            except Exception as exc:
                errors.append(f"Failed to update '{section}' in {FILE_MAP[key]}: {exc}")

    return {"changes_made": changes_made, "errors": errors}

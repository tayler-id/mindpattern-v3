"""Self-optimization analyzer — trace-driven skill improvement.

Reads agent trace logs, compares behavior vs skill instructions,
identifies deviations, and produces a JSON diff of skill file changes.
"""

import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def build_analyzer_prompt(
    trace_dir: Path,
    skill_files: list[Path],
    date_str: str,
    metrics: dict,
    regression_data: list[dict],
) -> str:
    """Assemble the analyzer prompt with traces, skills, metrics, and regression data."""

    # Collect trace logs for today only
    traces_section = ""
    traced_agents = set()
    if trace_dir.exists():
        for agent_dir in sorted(trace_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            trace_file = agent_dir / f"{date_str}.md"
            if trace_file.exists():
                content = trace_file.read_text()
                traces_section += f"\n### TRACE LOG: {agent_dir.name}\n\n{content}\n\n---\n"
                traced_agents.add(agent_dir.name)

    if not traces_section:
        traces_section = "\nNo trace logs found for today.\n"

    # Collect skill files
    skills_section = ""
    for sf in sorted(skill_files):
        if sf.exists():
            content = sf.read_text()
            rel_path = sf.name
            try:
                rel_path = str(sf.relative_to(sf.parent.parent.parent))
            except ValueError:
                try:
                    rel_path = str(sf.relative_to(sf.parent.parent))
                except ValueError:
                    rel_path = sf.name
            skills_section += f"\n### SKILL FILE: {rel_path}\n\n{content}\n\n---\n"

    # Metrics
    metrics_section = ""
    if metrics:
        metrics_section = f"\n## Pipeline Metrics\n\n```json\n{json.dumps(metrics, indent=2)}\n```\n"

    # Regression data
    regression_section = ""
    if regression_data:
        regression_section = "\n## REGRESSION WARNINGS\n\nPrevious ANALYZE edits caused quality drops:\n\n"
        regression_section += "| File | Quality Before | Quality After | Drop |\n|---|---|---|---|\n"
        for r in regression_data:
            regression_section += (
                f"| {r.get('file', '?')} | {r.get('quality_before', '?')} "
                f"| {r.get('quality_after', '?')} | {r.get('regression_pct', 0):.1%} |\n"
            )
        regression_section += "\nConsider REVERTING these changes or fixing the underlying issue.\n"

    # Traced agents list for validation
    traced_list = ", ".join(sorted(traced_agents)) if traced_agents else "none"

    prompt = f"""You are analyzing agent execution traces to improve agent skill files.

## Your Task

Compare each agent's SKILL FILE (what it should do) against its TRACE LOG (what it actually did).
Identify deviations and output a JSON diff to fix the skill files for next run.

## Rules

1. Only propose changes for agents that have a trace log from today. Agents with traces: {traced_list}
2. If a REGRESSION WARNING exists for a file, consider reverting or fixing that change.
3. Be specific in your reasons — cite exact tool calls or behaviors from the trace.
4. Prefer minimal targeted edits over full rewrites.
5. If an agent performed well (followed instructions, good findings), put it in no_changes.

## Deviation Categories to Check

- **Tool usage**: Did the agent use tools in the order the skill specified? (e.g., Exa before WebSearch)
- **Phase compliance**: Did it do Phase 1 (evaluate preflight) before Phase 2 (explore)?
- **Quality**: Did it read sources deeply (Jina/WebFetch) or rely on search snippets?
- **Output**: Valid JSON on first try? Findings match focus areas?
- **Cross-agent**: Multiple agents making the same mistake = systemic issue.

{regression_section}
{metrics_section}

## Agent Trace Logs
{traces_section}

## Agent Skill Files
{skills_section}

## Output Format

Output ONLY valid JSON:

```json
{{
  "changes": [
    {{
      "file": "relative/path/to/skill.md",
      "reason": "Specific deviation observed in trace",
      "diff": {{
        "section": "## Section Name",
        "action": "replace|append",
        "content": "New section content"
      }}
    }}
  ],
  "reversions": [
    {{
      "file": "relative/path/to/skill.md",
      "reason": "Previous change caused regression",
      "revert_to_hash": "git_hash"
    }}
  ],
  "no_changes": [
    "relative/path/to/skill.md"
  ]
}}
```

Use full relative paths from project root for all files (e.g., "verticals/ai-tech/agents/hn-researcher.md", "agents/eic.md").
"""
    return prompt


def parse_analyzer_output(raw_output: str) -> dict | None:
    """Extract JSON diff from analyzer LLM output.

    Same extraction pattern as identity_evolve.parse_llm_output().
    """
    if not raw_output or not raw_output.strip():
        return None

    text = raw_output.strip()

    # 1. Try direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "changes" in parsed:
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict) and "changes" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Try first { ... last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            parsed = json.loads(text[first_brace:last_brace + 1])
            if isinstance(parsed, dict) and "changes" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _find_and_replace_section(content: str, section_name: str, new_body: str) -> str:
    """Replace the body of a ## section in markdown, preserving other sections.

    If multiple sections share the same heading, the first is replaced with
    *new_body* and all subsequent duplicates are silently removed.
    """
    lines = content.split("\n")
    result = []
    in_target = False
    replaced = False

    # Normalize section name for matching
    target = section_name.lstrip("#").strip().lower()

    for line in lines:
        if line.startswith("## "):
            heading = line.lstrip("#").strip().lower()
            if heading == target:
                if not replaced:
                    # First occurrence: keep heading + new body
                    result.append(line)
                    result.append(new_body.rstrip())
                    result.append("")
                    replaced = True
                # Whether first or duplicate, skip old body
                in_target = True
                continue
            else:
                in_target = False

        if not in_target:
            result.append(line)

    # If section not found, append it
    if not replaced:
        result.append("")
        result.append(f"## {section_name.lstrip('#').strip()}")
        result.append(new_body.rstrip())
        result.append("")

    return "\n".join(result)


def _section_already_contains(section_lines: list[str], new_content: str, threshold: float = 0.8) -> bool:
    """Return True if >threshold of *new_content* lines already exist in *section_lines*."""
    new_lines = [l.strip() for l in new_content.strip().splitlines() if l.strip()]
    if not new_lines:
        return True  # nothing to add

    existing = {l.strip() for l in section_lines if l.strip()}
    matches = sum(1 for l in new_lines if l in existing)
    return (matches / len(new_lines)) >= threshold


def _append_to_section(content: str, section_name: str, new_content: str) -> str:
    """Append content to the end of a ## section in markdown.

    Skips the append if >80% of the new lines already exist in the target
    section (prevents duplicate accumulation).
    """
    lines = content.split("\n")
    result = []
    target = section_name.lstrip("#").strip().lower()
    in_target = False
    appended = False
    section_body: list[str] = []  # collect body lines of the target section

    for line in lines:
        if line.startswith("## "):
            heading = line.lstrip("#").strip().lower()
            if in_target and not appended:
                # We were in the target section and hit the next section
                if not _section_already_contains(section_body, new_content):
                    result.append(new_content.rstrip())
                    result.append("")
                else:
                    logger.debug("Skipping append to '%s': content already present", section_name)
                appended = True
                section_body = []
            in_target = (heading == target)

        if in_target:
            section_body.append(line)

        result.append(line)

    # If we were in the target section at end of file
    if in_target and not appended:
        if not _section_already_contains(section_body, new_content):
            result.append(new_content.rstrip())
            result.append("")
        else:
            logger.debug("Skipping append to '%s': content already present", section_name)

    return "\n".join(result)


def _dedup_sections(content: str) -> str:
    """Remove duplicate ## sections from markdown content.

    Keeps the first occurrence of each heading and drops subsequent duplicates.
    """
    lines = content.split("\n")
    result: list[str] = []
    seen_headings: set[str] = set()
    skipping = False

    for line in lines:
        if line.startswith("## "):
            heading = line.lstrip("#").strip().lower()
            if heading in seen_headings:
                # Duplicate heading — skip it and its body
                skipping = True
                continue
            else:
                seen_headings.add(heading)
                skipping = False

        if not skipping:
            result.append(line)

    return "\n".join(result)


# Known vertical directory names for path normalization
_VERTICAL_NAMES = frozenset([
    "ai-tech",
])

# Prefixes to try when a file path doesn't resolve
_PATH_PREFIXES = [
    "verticals/",
    "agents/",
]


def _normalize_path(file_path: str, project_root: Path) -> str:
    """Try to fix LLM-generated paths that are missing directory prefixes.

    If the literal path doesn't exist on disk, attempt common corrections:
    1. If path starts with a known vertical name (e.g. 'ai-tech/'), prepend 'verticals/'.
    2. Try each entry in _PATH_PREFIXES.
    """
    resolved = project_root / file_path
    if resolved.exists():
        return file_path

    # Check if path starts with a known vertical name
    first_segment = file_path.split("/")[0] if "/" in file_path else ""
    if first_segment in _VERTICAL_NAMES:
        candidate = f"verticals/{file_path}"
        if (project_root / candidate).exists():
            logger.info("Path normalized: %s -> %s", file_path, candidate)
            return candidate

    # Brute-force prefix search
    for prefix in _PATH_PREFIXES:
        if file_path.startswith(prefix):
            continue  # already has this prefix
        candidate = f"{prefix}{file_path}"
        if (project_root / candidate).exists():
            logger.info("Path normalized: %s -> %s", file_path, candidate)
            return candidate

    # Return original — caller will report file-not-found
    return file_path


def apply_analyzer_changes(
    changes: dict,
    project_root: Path,
    traced_files: set[str] | None = None,
    prompt_tracker=None,
) -> dict:
    """Apply JSON diff changes to skill files.

    Args:
        changes: Parsed JSON diff from analyzer.
        project_root: Project root for resolving relative paths.
        traced_files: Set of agent names that had traces today. If provided,
                     changes for agents without traces are rejected.
        prompt_tracker: PromptTracker instance for recording hashes.

    Returns:
        Dict with applied, skipped, reverted, errors counts.
    """
    from memory.vault import atomic_write

    result = {"applied": 0, "skipped": 0, "reverted": 0, "errors": []}

    # Apply changes
    for change in changes.get("changes", []):
        # Normalize path before resolving (fixes LLM-generated short paths)
        normalized = _normalize_path(change["file"], project_root)
        file_path = (project_root / normalized).resolve()
        if not file_path.is_relative_to(project_root.resolve()):
            result["errors"].append(f"Path traversal rejected: {change['file']}")
            continue
        diff = change.get("diff", {})
        reason = change.get("reason", "")

        # Validate: reject if no trace for this agent
        if traced_files is not None:
            # Extract agent name from file path
            agent_name = file_path.stem
            if agent_name not in traced_files:
                logger.info(f"Skipping {change['file']}: no trace for {agent_name}")
                result["skipped"] += 1
                continue

        if not file_path.exists():
            result["errors"].append(f"File not found: {change['file']}")
            continue

        try:
            # Record hash before change
            if prompt_tracker:
                prompt_tracker.record_version(str(change["file"]))

            content = file_path.read_text()
            section = diff.get("section", "").lstrip("#").strip()
            action = diff.get("action", "replace")
            new_content = diff.get("content", "")

            if action == "replace":
                content = _find_and_replace_section(content, section, new_content)
            elif action == "append":
                content = _append_to_section(content, section, new_content)
            else:
                result["errors"].append(f"Unknown action '{action}' for {change['file']}")
                continue

            # Final dedup pass — removes any duplicate sections
            content = _dedup_sections(content)

            atomic_write(file_path, content)

            # Record hash after change
            if prompt_tracker:
                prompt_tracker.record_version(str(change["file"]))

            logger.info(f"ANALYZE: Updated {change['file']} ({action} {section}): {reason}")
            result["applied"] += 1

        except Exception as e:
            logger.error(f"ANALYZE: Failed to update {change['file']}: {e}")
            result["errors"].append(f"{change['file']}: {e}")

    # Apply reversions
    for reversion in changes.get("reversions", []):
        file_path = project_root / reversion["file"]
        git_hash = reversion.get("revert_to_hash", "")
        reason = reversion.get("reason", "")

        if not git_hash or not re.fullmatch(r"[0-9a-f]{7,40}", git_hash):
            result["errors"].append(f"Invalid or missing hash for reversion: {reversion['file']}")
            continue

        rev_path = (project_root / reversion["file"]).resolve()
        if not rev_path.is_relative_to(project_root.resolve()):
            result["errors"].append(f"Path traversal rejected: {reversion['file']}")
            continue

        try:
            # Get file content at previous hash
            proc = subprocess.run(
                ["git", "show", f"{git_hash}:{reversion['file']}"],
                capture_output=True, text=True, timeout=10,
                cwd=str(project_root),
            )
            if proc.returncode != 0:
                result["errors"].append(f"git show failed for {reversion['file']}: {proc.stderr}")
                continue

            if prompt_tracker:
                prompt_tracker.record_version(str(reversion["file"]))

            atomic_write(file_path, proc.stdout)

            if prompt_tracker:
                prompt_tracker.record_version(str(reversion["file"]))

            logger.info(f"ANALYZE: Reverted {reversion['file']} to {git_hash[:8]}: {reason}")
            result["reverted"] += 1

        except Exception as e:
            logger.error(f"ANALYZE: Failed to revert {reversion['file']}: {e}")
            result["errors"].append(f"revert {reversion['file']}: {e}")

    return result

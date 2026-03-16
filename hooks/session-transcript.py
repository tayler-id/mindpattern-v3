#!/usr/bin/env python3
"""Claude Code SessionEnd hook: capture agent transcripts into Obsidian vault.

Fires for every `claude -p` subprocess in the mindpattern pipeline. Reads the
JSONL transcript, extracts reasoning / tool calls / outputs, and writes a
structured markdown file to:

    data/ramsay/mindpattern/agents/{agent-name}/{date}.md

Environment variables (set by orchestrator/agents.py before each subprocess):
    MINDPATTERN_AGENT  — agent identifier (e.g. "news-researcher", "eic")
    MINDPATTERN_DATE   — pipeline date YYYY-MM-DD (falls back to today)
    MINDPATTERN_VAULT  — vault root path (falls back to cwd-based default)

Stdin JSON from Claude Code:
    {"session_id": "...", "transcript_path": "...", "cwd": "...", ...}

This hook is standalone — no imports from the mindpattern codebase so it works
reliably in Claude Code's subprocess context.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


# ── Stdin ────────────────────────────────────────────────────────────────────


def read_stdin() -> dict:
    """Read and parse the JSON blob Claude Code sends on stdin."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw)
    except Exception:
        return {}


# ── Transcript parsing ───────────────────────────────────────────────────────


def parse_transcript(jsonl_path: str) -> list[dict]:
    """Parse a Claude Code .jsonl transcript into a list of message dicts."""
    path = Path(jsonl_path)
    if not path.exists():
        return []

    messages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def extract_agent_log(messages: list[dict]) -> dict:
    """Extract structured data from transcript messages.

    Returns a dict with:
        - reasoning: list of assistant text blocks
        - tool_calls: list of {tool, input_preview, output_preview}
        - user_prompts: list of user message texts
        - duration_estimate: rough time span from first to last timestamp
    """
    reasoning = []
    tool_calls = []
    tool_results = []
    user_prompts = []
    timestamps = []

    for msg in messages:
        ts = msg.get("timestamp")
        if ts:
            timestamps.append(ts)

        msg_type = msg.get("type", "")

        # User messages (the prompt sent to the agent)
        if msg_type == "user":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                text = content.strip()
                # Skip system/internal messages
                if any(text.startswith(p) for p in [
                    "<system-reminder", "<teammate-message",
                    "<command-message", "<observed_from",
                ]):
                    continue
                user_prompts.append(text)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and not text.startswith("<"):
                            user_prompts.append(text)
                    elif isinstance(block, dict) and block.get("type") == "tool_result":
                        result_text = block.get("content", "")
                        if isinstance(result_text, str) and result_text.strip():
                            tool_results.append(_truncate(result_text.strip(), 300))

        # Assistant messages (reasoning, decisions)
        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                reasoning.append(content.strip())
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                reasoning.append(text)
                        elif block.get("type") == "thinking":
                            # Claude's internal reasoning between tool calls
                            text = block.get("thinking", "").strip()
                            if text:
                                reasoning.append(text)
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "tool": block.get("name", "unknown"),
                                "input_preview": _truncate(
                                    json.dumps(block.get("input", {})), 200
                                ),
                            })

        # Tool results
        elif msg_type == "tool_result":
            # Tool results are embedded in user messages as tool_result content
            pass

    duration = ""
    if len(timestamps) >= 2:
        try:
            t0 = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            delta = t1 - t0
            minutes = int(delta.total_seconds() / 60)
            seconds = int(delta.total_seconds() % 60)
            duration = f"{minutes}m {seconds}s"
        except Exception:
            pass

    return {
        "reasoning": reasoning,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "user_prompts": user_prompts,
        "duration": duration,
    }


def _truncate(text: str, max_len: int = 200) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# ── Markdown formatting ─────────────────────────────────────────────────────


def format_agent_log(
    agent_name: str,
    date_str: str,
    log_data: dict,
) -> str:
    """Format extracted log data as Obsidian-compatible markdown."""
    lines = []

    # YAML frontmatter
    lines.append("---")
    lines.append("type: agent-log")
    lines.append(f"agent: {agent_name}")
    lines.append(f"date: {date_str}")
    lines.append(f"duration: {log_data['duration'] or 'unknown'}")
    lines.append(f"tool_calls: {len(log_data['tool_calls'])}")
    lines.append(f"reasoning_blocks: {len(log_data['reasoning'])}")
    lines.append(f"tool_results: {len(log_data.get('tool_results', []))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {agent_name} — {date_str}")
    lines.append("")
    lines.append(f"Daily log: [[daily/{date_str}]]")
    lines.append("")

    # Tool calls (skip prompt — it's just the agent schema + SOUL, not useful)
    if log_data["tool_calls"]:
        lines.append("## Tool Calls")
        lines.append("")
        for tc in log_data["tool_calls"]:
            tool = tc['tool']
            preview = tc['input_preview']
            # Flag subagent dispatches
            if tool == "Agent":
                lines.append(f"- **Subagent dispatched**: `{_truncate(preview, 150)}`")
            else:
                lines.append(f"- **{tool}**: `{_truncate(preview, 150)}`")
        lines.append("")

    # Tool results (summaries) — what the agent actually found
    if log_data.get("tool_results"):
        lines.append("## Research Results")
        lines.append("")
        for i, tr in enumerate(log_data["tool_results"]):
            # Clean up tool results for readability
            clean = tr.replace("\\n", " ").strip()
            if len(clean) > 500:
                clean = clean[:500] + "..."
            lines.append(f"### Result {i + 1}")
            lines.append("")
            lines.append(clean)
            lines.append("")

    # Output — the agent's final response (findings JSON, etc.)
    if log_data["reasoning"]:
        lines.append("## Output")
        lines.append("")
        for block in log_data["reasoning"]:
            # Try to detect JSON output and format it
            stripped = block.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                if len(stripped) > 2000:
                    lines.append("```json")
                    lines.append(stripped[:2000] + "...")
                    lines.append("```")
                else:
                    lines.append("```json")
                    lines.append(stripped)
                    lines.append("```")
            else:
                if len(block) > 1000:
                    lines.append(block[:1000] + "...")
                else:
                    lines.append(block)
            lines.append("")

    return "\n".join(lines)


# ── Atomic write ─────────────────────────────────────────────────────────────


def atomic_write(path: Path, content: str) -> None:
    """Write content atomically (tmp + rename) with LF line endings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(content.encode("utf-8"))
        os.rename(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    # Check if this is a mindpattern pipeline agent
    agent_name = os.environ.get("MINDPATTERN_AGENT")
    if not agent_name:
        return  # Not a pipeline agent, skip silently

    # Read hook input
    hook_input = read_stdin()
    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        return

    # Determine date and vault path
    date_str = os.environ.get("MINDPATTERN_DATE", datetime.now().strftime("%Y-%m-%d"))
    vault_dir = os.environ.get("MINDPATTERN_VAULT")
    if not vault_dir:
        cwd = hook_input.get("cwd", "")
        if cwd:
            vault_dir = os.path.join(cwd, "data", "ramsay", "mindpattern")
        else:
            return  # Can't determine vault path

    vault_path = Path(vault_dir)

    # Parse transcript
    messages = parse_transcript(transcript_path)
    if not messages:
        return

    # Extract and format
    log_data = extract_agent_log(messages)
    markdown = format_agent_log(agent_name, date_str, log_data)

    # Write to agent folder
    output_path = vault_path / "agents" / agent_name / f"{date_str}.md"
    atomic_write(output_path, markdown)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never block session end
        pass

#!/usr/bin/env python3
"""Claude Code SessionEnd hook: capture interactive conversations into knowledge base.

Fires at the end of every interactive Claude Code session. Parses the transcript,
extracts decisions, files touched, and concepts discussed, then writes a structured
session page to:

    data/ramsay/mindpattern/knowledge/sessions/{date}-{slug}.md

The next COMPILE run picks up session files and promotes insights into concept pages.

Unlike session-transcript.py (which handles pipeline agent subprocesses), this hook
captures human-AI conversations where architectural decisions, debugging insights,
and project context are discussed.

Stdin JSON from Claude Code:
    {"session_id": "...", "transcript_path": "...", "cwd": "...", ...}

This hook is standalone — minimal imports so it works reliably in Claude Code's
subprocess context. Does not call the LLM (that would be slow + fragile in a hook).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Transcript parsing (shared logic with session-transcript.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Session data extraction
# ---------------------------------------------------------------------------

# Patterns that indicate decisions in assistant text
DECISION_PATTERNS = [
    re.compile(r"(?:I )?decided? to (.+?)(?:\.|$)", re.IGNORECASE),
    re.compile(r"(?:I )?chose (.+?)(?:\.|$)", re.IGNORECASE),
    re.compile(r"the (?:right|best) (?:approach|choice|call) is (.+?)(?:\.|$)", re.IGNORECASE),
    re.compile(r"going with (.+?) because", re.IGNORECASE),
    re.compile(r"(?:we|I)'ll use (.+?) (?:instead|rather|because)", re.IGNORECASE),
]


def extract_session_data(messages: list[dict]) -> dict:
    """Extract structured session data from transcript messages.

    Returns dict with:
        - user_messages: list of user text messages
        - assistant_texts: list of assistant text blocks
        - decisions: list of decision sentences
        - files_touched: list of file paths from Write/Edit tool calls
        - tool_counts: dict of tool_name -> count
        - duration: time span string
        - thinking: list of thinking blocks
    """
    user_messages = []
    assistant_texts = []
    decisions = []
    files_touched = []
    tool_counts = {}
    thinking = []
    timestamps = []

    for msg in messages:
        ts = msg.get("timestamp")
        if ts:
            timestamps.append(ts)

        msg_type = msg.get("type", "")
        content = msg.get("message", {}).get("content", "")

        if msg_type == "user":
            if isinstance(content, str) and content.strip():
                text = content.strip()
                # Skip system messages
                if not any(text.startswith(p) for p in [
                    "<system-reminder", "<teammate-message",
                    "<command-message", "<observed_from",
                ]):
                    user_messages.append(text)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text and not text.startswith("<"):
                            user_messages.append(text)

        elif msg_type == "assistant":
            if isinstance(content, str) and content.strip():
                assistant_texts.append(content.strip())
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            assistant_texts.append(text)

                    elif block.get("type") == "thinking":
                        text = block.get("thinking", "").strip()
                        if text:
                            thinking.append(text)

                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                        inp = block.get("input", {})
                        file_path = inp.get("file_path", inp.get("path", ""))
                        if file_path and tool_name in ("Write", "Edit", "Read"):
                            # Extract just the filename for readability
                            basename = Path(file_path).name
                            if basename not in files_touched:
                                files_touched.append(basename)

    # Extract decisions from assistant text
    for text in assistant_texts:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            for pattern in DECISION_PATTERNS:
                match = pattern.search(sentence)
                if match:
                    decisions.append(sentence.strip())
                    break

    # Compute duration
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
        "user_messages": user_messages,
        "assistant_texts": assistant_texts,
        "decisions": decisions,
        "files_touched": files_touched,
        "tool_counts": tool_counts,
        "thinking": thinking,
        "duration": duration,
    }


# ---------------------------------------------------------------------------
# Session title inference
# ---------------------------------------------------------------------------

def infer_session_title(user_messages: list[str]) -> str:
    """Infer a short session title from the user's first message."""
    if not user_messages:
        return "untitled-session"

    first = user_messages[0].strip()

    # Remove common prefixes
    for prefix in ["can you ", "please ", "let's ", "i want to ", "i need to "]:
        if first.lower().startswith(prefix):
            first = first[len(prefix):]

    # Take first meaningful chunk (up to 60 chars, word-aligned)
    words = first.split()
    title = ""
    for word in words:
        candidate = f"{title} {word}".strip() if title else word
        if len(candidate) > 60:
            break
        title = candidate

    if not title:
        title = "untitled-session"

    # Slugify
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")

    return slug[:80] if slug else "untitled-session"


# ---------------------------------------------------------------------------
# Session page formatting
# ---------------------------------------------------------------------------

def format_session_page(session_data: dict, date_str: str) -> str:
    """Format extracted session data as an Obsidian-compatible markdown page."""
    title = infer_session_title(session_data["user_messages"])
    duration = session_data.get("duration", "unknown")
    files = session_data.get("files_touched", [])
    decisions = session_data.get("decisions", [])
    tool_counts = session_data.get("tool_counts", {})
    total_tools = sum(tool_counts.values())

    lines = [
        "---",
        "type: session",
        f"date: {date_str}",
        f"title: {title}",
        f"duration: {duration}",
        f"files_touched: {len(files)}",
        f"tool_calls: {total_tools}",
        f"decisions: {len(decisions)}",
        "---",
        "",
        f"# Session: {title}",
        "",
        f"Date: [[daily/{date_str}]] | Duration: {duration} | "
        f"Tools: {total_tools} | Files: {len(files)}",
        "",
    ]

    # What was done (from user messages)
    lines.append("## What Was Done")
    lines.append("")
    if session_data["user_messages"]:
        for msg in session_data["user_messages"][:10]:  # Cap at 10
            truncated = msg[:200] + "..." if len(msg) > 200 else msg
            lines.append(f"- {truncated}")
    else:
        lines.append("No user messages captured.")
    lines.append("")

    # Decisions
    lines.append("## Decisions")
    lines.append("")
    if decisions:
        for d in decisions:
            truncated = d[:300] + "..." if len(d) > 300 else d
            lines.append(f"- {truncated}")
    else:
        lines.append("No explicit decisions captured.")
    lines.append("")

    # Files touched
    lines.append("## Files Touched")
    lines.append("")
    if files:
        for f in files:
            lines.append(f"- `{f}`")
    else:
        lines.append("No files modified.")
    lines.append("")

    # Tool usage summary
    if tool_counts:
        lines.append("## Tool Usage")
        lines.append("")
        for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {tool}: {count}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_session_file(
    sessions_dir: Path,
    content: str,
    date_str: str,
    slug: str,
) -> Path:
    """Write a session page to the sessions directory.

    Uses atomic write (tmp + rename). Appends a counter suffix if the
    file already exists to avoid overwriting.
    """
    sessions_dir = Path(sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{date_str}-{slug}"
    path = sessions_dir / f"{base_name}.md"

    # If file exists, add counter suffix
    counter = 1
    while path.exists():
        counter += 1
        path = sessions_dir / f"{base_name}-{counter}.md"

    # Atomic write
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_bytes(content.encode("utf-8"))
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise

    return path


# ---------------------------------------------------------------------------
# Main hook entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Skip if this is a pipeline agent (handled by session-transcript.py)
    if os.environ.get("MINDPATTERN_AGENT"):
        return

    # Read hook input from stdin
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except Exception:
        return

    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        return

    # Determine vault path
    cwd = hook_input.get("cwd", "")
    vault_dir = os.environ.get("MINDPATTERN_VAULT")
    if not vault_dir:
        if cwd:
            vault_dir = os.path.join(cwd, "data", "ramsay", "mindpattern")
        else:
            return

    vault_path = Path(vault_dir)

    # Only capture sessions in the mindpattern project
    if not vault_path.exists():
        return

    # Parse transcript
    messages = parse_transcript(transcript_path)
    if not messages:
        return

    # Minimum session length — skip trivial interactions
    user_count = sum(1 for m in messages if m.get("type") == "user")
    if user_count < 2:
        return

    # Extract and format
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    session_data = extract_session_data(messages)
    title_slug = infer_session_title(session_data["user_messages"])
    markdown = format_session_page(session_data, date_str)

    # Write session file
    sessions_dir = vault_path / "knowledge" / "sessions"
    path = write_session_file(sessions_dir, markdown, date_str, title_slug)

    # Update sessions index
    _update_sessions_index(sessions_dir)

    print(f"session-capture: saved {path.name}", file=sys.stderr)


def _update_sessions_index(sessions_dir: Path) -> None:
    """Regenerate _index.md for the sessions directory."""
    session_files = sorted(sessions_dir.glob("*.md"), reverse=True)
    session_files = [f for f in session_files if f.name != "_index.md"]

    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "---",
        "type: index",
        f"last_updated: {today}",
        f"session_count: {len(session_files)}",
        "---",
        "",
        "# Sessions",
        "",
        f"{len(session_files)} captured conversations.",
        "",
    ]

    for f in session_files[:50]:  # Cap index at 50 most recent
        name = f.stem
        lines.append(f"- [[sessions/{name}]]")

    lines.append("")

    index_path = sessions_dir / "_index.md"
    content = "\n".join(lines)
    content = content.replace("\r\n", "\n")
    tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    try:
        tmp.write_bytes(content.encode("utf-8"))
        os.replace(tmp, index_path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"session-capture hook error: {e}", file=sys.stderr)

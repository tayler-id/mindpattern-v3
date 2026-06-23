#!/usr/bin/env python3
"""Claude Code SessionEnd hook: capture conversation and spawn flush.

Extracts conversation context from the transcript, writes it to a temp file,
then spawns flush.py as a background process. The hook itself does no API calls
and must complete in <10s.

Stdin JSON from Claude Code:
    {"session_id": "...", "transcript_path": "...", "cwd": "...", ...}
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Recursion guard
if os.environ.get("CLAUDE_INVOKED_BY") or os.environ.get("MINDPATTERN_AGENT"):
    sys.exit(0)

MAX_CONTEXT_CHARS = 15000
MAX_TURNS = 30
MIN_TURNS = 2


def _extract_context(messages: list[dict]) -> str:
    """Extract conversation context as markdown from transcript messages."""
    turns = []

    for msg in messages:
        msg_type = msg.get("type", "")
        content = msg.get("message", {}).get("content", "")

        if msg_type == "user":
            text = ""
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                text = "\n".join(parts).strip()

            # Skip system messages
            if text and not any(text.startswith(p) for p in [
                "<system-reminder", "<teammate-message",
                "<command-message", "<observed_from",
            ]):
                turns.append(f"**User**: {text}")

        elif msg_type == "assistant":
            text = ""
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            parts.append(f"[Thinking: {block.get('thinking', '')[:200]}]")
                        elif block.get("type") == "tool_use":
                            tool = block.get("name", "")
                            inp = block.get("input", {})
                            fp = inp.get("file_path", inp.get("command", ""))
                            if fp:
                                parts.append(f"[Tool: {tool} → {str(fp)[:100]}]")
                            else:
                                parts.append(f"[Tool: {tool}]")
                text = "\n".join(parts).strip()

            if text:
                turns.append(f"**Assistant**: {text}")

    # Keep last N turns
    turns = turns[-MAX_TURNS:]

    context = "\n\n".join(turns)

    # Truncate with boundary awareness
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[-MAX_CONTEXT_CHARS:]
        boundary = context.find("\n**")
        if boundary > 0:
            context = context[boundary + 1:]

    return context


def _check_dedup(session_id: str, state_dir: Path) -> bool:
    """Return True if this session was recently flushed (skip it)."""
    last_flush_path = state_dir / "last-flush.json"
    try:
        if last_flush_path.exists():
            state = json.loads(last_flush_path.read_text())
            if (state.get("session_id") == session_id
                    and time.time() - state.get("timestamp", 0) < 60):
                return True
    except Exception:
        pass
    return False


def _write_dedup(session_id: str, state_dir: Path) -> None:
    """Record this flush to prevent duplicates."""
    state_dir.mkdir(parents=True, exist_ok=True)
    last_flush_path = state_dir / "last-flush.json"
    try:
        last_flush_path.write_text(json.dumps({
            "session_id": session_id,
            "timestamp": time.time(),
        }))
    except Exception:
        pass


def main() -> None:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except Exception:
        return

    session_id = hook_input.get("session_id", "")
    transcript_path = hook_input.get("transcript_path")
    cwd = hook_input.get("cwd", "")

    if not transcript_path or not cwd:
        return

    # Only capture in the mindpattern project
    vault_dir = Path(cwd) / "data" / "ramsay" / "mindpattern"
    if not vault_dir.exists():
        return

    state_dir = Path(cwd) / "knowledge" / "state"

    # Dedup check
    if _check_dedup(session_id, state_dir):
        return

    # Parse transcript
    transcript_file = Path(transcript_path)
    if not transcript_file.exists():
        return

    messages = []
    for line in transcript_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Check minimum turns
    user_turns = sum(1 for m in messages if m.get("type") == "user")
    if user_turns < MIN_TURNS:
        return

    # Extract context
    context = _extract_context(messages)
    if not context.strip():
        return

    # Write context to temp file for flush.py
    state_dir.mkdir(parents=True, exist_ok=True)
    context_file = state_dir / f"context-{session_id}-{int(time.time())}.md"
    context_file.write_text(context, encoding="utf-8")

    # Record dedup
    _write_dedup(session_id, state_dir)

    # Spawn flush.py as background process
    flush_script = Path(cwd) / "knowledge" / "flush.py"
    if not flush_script.exists():
        return

    env = os.environ.copy()
    env["CLAUDE_INVOKED_BY"] = "session-end-hook"
    env["MINDPATTERN_VAULT"] = str(vault_dir)

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen(
        [sys.executable, str(flush_script), str(context_file)],
        stdout=subprocess.DEVNULL,
        stderr=open(str(state_dir / "flush.log"), "a"),
        env=env,
        **kwargs,
    )

    print(f"session-end: spawned flush for {context_file.name}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"session-end hook error: {e}", file=sys.stderr)

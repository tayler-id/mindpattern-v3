#!/usr/bin/env python3
"""Post-tool hook: audit trail for harness agent actions.

Logs every tool call made by harness agents to harness/audit.jsonl.
This is deterministic logging — no LLM involved, just append to a file.

Stdin: {"tool_name": "...", "tool_input": {...}, "tool_result": "...", "session_id": "..."}
Stdout: (empty — post hooks don't block)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return

    # Only log if we're in a harness context
    cwd = event.get("cwd", os.getcwd())
    if "worktree" not in cwd and "harness" not in cwd:
        return

    # Find project root
    project_root = Path(cwd)
    while project_root.parent != project_root:
        if (project_root / "harness").exists():
            break
        project_root = project_root.parent

    audit_file = project_root / "harness" / "audit.jsonl"

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": event.get("tool_name", "unknown"),
        "session": event.get("session_id", "unknown"),
        "cwd": cwd,
    }

    # Log command for Bash, file path for Read/Write/Edit
    tool_input = event.get("tool_input", {})
    if event.get("tool_name") == "Bash":
        entry["command"] = tool_input.get("command", "")[:200]
    elif event.get("tool_name") in ("Read", "Write", "Edit"):
        entry["file"] = tool_input.get("file_path", "")

    try:
        with open(audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Non-fatal — don't block the agent


if __name__ == "__main__":
    main()

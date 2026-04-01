#!/usr/bin/env python3
"""Pre-tool hook: block git commit if deterministic gates fail.

Fires on every Bash tool call. If the command is a git commit inside
a harness worktree, runs the deterministic gates first. If any gate
fails, blocks the commit with a clear error message.

Stdin: {"tool_name": "Bash", "tool_input": {"command": "..."}, "session_id": "..."}
Stdout: {"decision": "allow"} or {"decision": "block", "reason": "..."}
"""

import json
import os
import re
import sys
from pathlib import Path


def main():
    try:
        event = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({"decision": "allow"}))
        return

    command = event.get("tool_input", {}).get("command", "")

    # Only gate git commits in harness worktrees
    if "git commit" not in command:
        print(json.dumps({"decision": "allow"}))
        return

    cwd = event.get("cwd", os.getcwd())
    if "harness" not in cwd and "worktree" not in cwd:
        print(json.dumps({"decision": "allow"}))
        return

    # Find the ticket file for this worktree
    # Convention: harness worktree branches are named harness/<ticket-id>
    # or worktree-agent-<hash>
    project_root = Path(cwd)
    while project_root.parent != project_root:
        if (project_root / "harness" / "tickets").exists():
            break
        project_root = project_root.parent

    # Run syntax check on staged files
    import subprocess
    result = subprocess.run(
        "git diff --cached --name-only --diff-filter=ACM",
        shell=True, capture_output=True, text=True, cwd=cwd,
    )
    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    # Gate 1: Syntax validation
    import ast
    for f in changed_files:
        if not f.endswith(".py"):
            continue
        full = Path(cwd) / f
        if not full.exists():
            continue
        try:
            ast.parse(full.read_text())
        except SyntaxError as e:
            print(json.dumps({
                "decision": "block",
                "reason": f"HARNESS GATE: Syntax error in {f}:{e.lineno}: {e.msg}",
            }))
            return

    # Gate 2: No hardcoded secrets
    secret_patterns = [
        r'(?i)(api_key|secret_key|private_key|password|token)\s*=\s*["\'][^"\']{8,}',
        r'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+',
    ]
    for f in changed_files:
        if not f.endswith(".py"):
            continue
        full = Path(cwd) / f
        if not full.exists():
            continue
        content = full.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            for pattern in secret_patterns:
                if re.search(pattern, line):
                    print(json.dumps({
                        "decision": "block",
                        "reason": f"HARNESS GATE: Possible hardcoded secret in {f}:{i}",
                    }))
                    return

    # Gate 3: No debug statements
    debug_patterns = [r'^\s*import\s+pdb', r'^\s*breakpoint\(\)', r'^\s*import\s+ipdb']
    for f in changed_files:
        if not f.endswith(".py"):
            continue
        full = Path(cwd) / f
        if not full.exists():
            continue
        content = full.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            for pattern in debug_patterns:
                if re.search(pattern, line):
                    print(json.dumps({
                        "decision": "block",
                        "reason": f"HARNESS GATE: Debug statement in {f}:{i}",
                    }))
                    return

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()

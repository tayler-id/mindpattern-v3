#!/usr/bin/env python3
"""Claude Code SessionStart hook: inject knowledge base context.

Loads the knowledge index so Claude knows what's in the brain at the
start of every conversation. Pure file I/O, no API calls, must be <1s.

Stdin JSON from Claude Code:
    {"session_id": "...", "cwd": "...", ...}

Stdout JSON response:
    {"additionalContext": "..."}  (injected into conversation context)
"""

import json
import os
import sys
from pathlib import Path

# Recursion guard: skip if this is a subprocess spawned by our own hooks
if os.environ.get("CLAUDE_INVOKED_BY") or os.environ.get("MINDPATTERN_AGENT"):
    sys.exit(0)

MAX_CONTEXT_CHARS = 20000


def main() -> None:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except Exception:
        return

    cwd = hook_input.get("cwd", "")
    if not cwd:
        return

    vault_dir = Path(cwd) / "data" / "ramsay" / "mindpattern"
    knowledge_dir = vault_dir / "knowledge"
    index_path = knowledge_dir / "index.md"

    if not index_path.exists():
        return

    parts = []

    # Load the knowledge index
    index_content = index_path.read_text(encoding="utf-8")
    parts.append("## Knowledge Base (compiled research + conversations)\n")
    parts.append(index_content)

    # Load today's daily research log if it exists
    from datetime import datetime, timezone
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    daily_path = vault_dir / "daily" / f"{today}.md"
    if daily_path.exists():
        daily_content = daily_path.read_text(encoding="utf-8")
        # Truncate if needed
        if len(daily_content) > 5000:
            daily_content = daily_content[:5000] + "\n\n... (truncated)"
        parts.append(f"\n## Today's Research ({today})\n")
        parts.append(daily_content)

    context = "\n".join(parts)

    # Truncate total context
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS]
        boundary = context.rfind("\n")
        if boundary > MAX_CONTEXT_CHARS * 0.8:
            context = context[:boundary]

    # Output as JSON for Claude Code to consume
    print(json.dumps({"additionalContext": context}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never block session start

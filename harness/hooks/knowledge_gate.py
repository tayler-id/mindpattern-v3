"""
PostToolUse hook: enforce knowledge graph integrity after edits.

Runs after every Write/Edit tool call. If a .py file in the project was modified:
1. Validates all [[wiki-links]] resolve (file + section level)
2. Reports enhanced validation failures (sections, index, code refs)
3. Detects when code changes are significant but knowledge docs weren't updated

Warning-only — does not block. The evolve() calls will fix most issues.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path("/Users/taylerramsay/Projects/mindpattern-v3")
KNOWLEDGE_DIR = PROJECT_ROOT / "harness" / "knowledge"


def _count_diff_lines(cwd: str) -> tuple[int, int]:
    """Count changed lines in code vs knowledge files from git diff.

    Returns (code_lines, knowledge_lines).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--numstat", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0, 0

    code_lines = 0
    knowledge_lines = 0

    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added = int(parts[0]) if parts[0] != "-" else 0
        deleted = int(parts[1]) if parts[1] != "-" else 0
        path = parts[2]
        total = added + deleted

        if "knowledge/" in path and path.endswith(".md"):
            knowledge_lines += total
        elif path.endswith(".py"):
            code_lines += total

    return code_lines, knowledge_lines


def main():
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "{}")
    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")

    if tool_name not in ("Write", "Edit"):
        return

    try:
        data = json.loads(tool_input)
    except json.JSONDecodeError:
        return

    file_path = data.get("file_path", "")
    if not file_path.endswith(".py"):
        return

    if "/tests/" in file_path or "/harness/knowledge" in file_path:
        return

    # Run full knowledge graph validation
    sys.path.insert(0, str(PROJECT_ROOT))
    from harness.knowledge_graph import check

    result = check()

    # Report broken links (backward compat)
    if result["broken"]:
        broken_list = "\n".join(f"  {b['source']} -> [[{b['link']}]]" for b in result["broken"][:5])
        print(f"WARNING: Knowledge graph has {len(result['broken'])} broken links:\n{broken_list}", file=sys.stderr)

    # Report enhanced validation failures
    for name, r in result.get("results", {}).items():
        if not r.get("pass") and r.get("failures"):
            for f in r["failures"][:3]:
                print(f"WARNING: [{name}] {f}", file=sys.stderr)

    # Sync enforcement: detect underdocumented code changes
    cwd = os.environ.get("CLAUDE_CWD", os.getcwd())
    code_lines, knowledge_lines = _count_diff_lines(cwd)

    if code_lines >= 5 and knowledge_lines < 50:
        if knowledge_lines < code_lines * 0.05:
            print(
                f"WARNING: {code_lines} lines of code changed but only "
                f"{knowledge_lines} lines of knowledge docs updated. "
                f"Consider updating harness/knowledge/ files.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()

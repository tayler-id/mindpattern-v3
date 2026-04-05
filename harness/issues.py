"""Shared issue log — append-only log that every component writes to.

The harness reads this before every fix attempt. Pipeline writes on crash.
Harness writes on fix failure. Humans can write manually.

CLI:
    python3 -m harness.issues log "component" "short title" "details"
    python3 -m harness.issues read
    python3 -m harness.issues read --limit 5
"""

import sys
from datetime import datetime
from pathlib import Path

ISSUES_PATH = Path(__file__).parent / "ISSUES.md"


def log_issue(source: str, title: str, details: str) -> str:
    """Append an issue to ISSUES.md. Returns the entry that was added."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### {now} — {title}\n\n- **Source**: {source}\n- **Details**: {details}\n"

    content = ISSUES_PATH.read_text() if ISSUES_PATH.exists() else "# Shared Issue Log\n\n## Issues\n"

    # Insert after "## Issues" header (newest first)
    marker = "## Issues\n"
    if marker in content:
        content = content.replace(marker, marker + entry, 1)
    else:
        content += f"\n## Issues\n{entry}"

    ISSUES_PATH.write_text(content)
    return entry.strip()


def read_issues(limit: int = 0) -> str:
    """Read ISSUES.md content. If limit > 0, return only that many entries."""
    if not ISSUES_PATH.exists():
        return ""
    content = ISSUES_PATH.read_text()
    if limit <= 0:
        return content

    lines = content.split("\n")
    result = []
    count = 0
    for line in lines:
        if line.startswith("### "):
            count += 1
            if count > limit:
                break
        result.append(line)
    return "\n".join(result)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "log" and len(sys.argv) >= 5:
        entry = log_issue(sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"Logged: {entry}")
    elif cmd == "read":
        limit = 0
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            limit = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 0
        print(read_issues(limit))
    else:
        print("Usage:")
        print('  python3 -m harness.issues log "source" "title" "details"')
        print("  python3 -m harness.issues read [--limit N]")

#!/usr/bin/env python3
"""Flush: background worker that summarizes a conversation context into the daily log.

Spawned by session-end or pre-compact hooks. Receives a context file path as argument.
Uses `claude -p` to extract what's worth saving, then appends to the daily conversation log.

Usage:
    python3 knowledge/flush.py /path/to/context-file.md

The context file is deleted after successful processing.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Set up logging to flush.log
LOG_DIR = Path(__file__).resolve().parent / "state"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "flush.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("flush")

# Recursion guard
if os.environ.get("CLAUDE_INVOKED_BY") == "flush":
    logger.info("Recursion guard triggered, exiting")
    sys.exit(0)

FLUSH_PROMPT = """\
You are a knowledge extraction assistant. Given a conversation between a user and
an AI coding assistant, extract what's worth saving to a knowledge base.

Focus on:
- **Decisions made** — architectural choices, trade-offs, approaches chosen and why
- **Lessons learned** — what worked, what didn't, debugging insights
- **Concepts discussed** — technical topics explored in depth
- **Action items** — things to do next, open questions

Skip:
- Routine tool calls and file reads (unless the result revealed something important)
- Greetings, confirmations, "yes do it" messages
- Transient debugging (one-off errors that were immediately fixed)

## Conversation

{context}

## Output Format

Write a structured markdown summary. Use this exact format:

### Context
1-2 sentences: what was the session about?

### Key Exchanges
Bullet list of the most important back-and-forth moments. Include the decision or insight, not the full conversation.

### Decisions
Bullet list of decisions made and WHY (the reasoning matters more than the choice).

### Lessons
Bullet list of things learned — debugging insights, patterns discovered, gotchas encountered.

### Action Items
Bullet list of remaining work or open questions.

Be concise. Each section should have 2-5 bullets max. If a section has nothing worth saving, write "None." Do not add sections beyond those listed.
"""


def _run_claude_extract(context: str) -> str | None:
    """Use claude -p to extract knowledge from conversation context."""
    prompt = FLUSH_PROMPT.format(context=context)

    env = os.environ.copy()
    env["CLAUDE_INVOKED_BY"] = "flush"

    cmd = [
        "claude", "-p", prompt,
        "--model", "claude-sonnet-4-6",
        "--max-turns", "1",
        "--output-format", "text",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        logger.warning("Claude extract failed: exit=%d stderr=%s",
                       result.returncode, result.stderr[:200])
        return None
    except subprocess.TimeoutExpired:
        logger.warning("Claude extract timed out after 120s")
        return None
    except Exception as e:
        logger.warning("Claude extract error: %s", e)
        return None


def _append_to_daily_log(vault_dir: Path, date_str: str, summary: str) -> Path:
    """Append a session summary to the daily conversation log."""
    conversations_dir = vault_dir / "knowledge" / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    log_path = conversations_dir / f"{date_str}.md"

    timestamp = datetime.now(tz=timezone.utc).strftime("%H:%M UTC")

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
    else:
        existing = (
            f"---\n"
            f"type: conversation-log\n"
            f"date: {date_str}\n"
            f"---\n\n"
            f"# Conversations — {date_str}\n"
        )

    entry = f"\n\n---\n\n## {timestamp}\n\n{summary}"
    content = existing + entry

    # Atomic write
    tmp = log_path.with_suffix(".md.tmp")
    try:
        tmp.write_bytes(content.encode("utf-8"))
        os.replace(tmp, log_path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise

    return log_path


def main() -> None:
    if len(sys.argv) < 2:
        logger.error("Usage: flush.py <context-file>")
        sys.exit(1)

    context_file = Path(sys.argv[1])
    if not context_file.exists():
        logger.error("Context file not found: %s", context_file)
        sys.exit(1)

    context = context_file.read_text(encoding="utf-8")
    if not context.strip():
        logger.info("Empty context, skipping")
        context_file.unlink(missing_ok=True)
        return

    logger.info("Processing context: %s (%d chars)", context_file.name, len(context))

    # Determine vault directory
    vault_dir = os.environ.get("MINDPATTERN_VAULT")
    if vault_dir:
        vault_path = Path(vault_dir)
    else:
        # Try to find it relative to this script
        vault_path = Path(__file__).resolve().parent.parent / "data" / "ramsay" / "mindpattern"

    if not vault_path.exists():
        logger.error("Vault not found: %s", vault_path)
        context_file.unlink(missing_ok=True)
        return

    # Extract knowledge via Claude
    summary = _run_claude_extract(context)
    if not summary:
        logger.warning("No summary produced, keeping context file for retry")
        return

    # Append to daily conversation log
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    log_path = _append_to_daily_log(vault_path, date_str, summary)
    logger.info("Appended to %s", log_path.name)

    # Clean up context file
    context_file.unlink(missing_ok=True)
    logger.info("Flush complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error("Flush failed: %s", e, exc_info=True)

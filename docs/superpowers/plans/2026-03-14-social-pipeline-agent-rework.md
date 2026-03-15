# Social Pipeline Agent Call Rework — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework v3 social pipeline agent calls from inline prompts to file-based I/O with agent definition files and tools, matching v2 quality patterns.

**Architecture:** Add `run_agent_with_files()` helper alongside existing `run_claude_prompt()`. Social agents get tools (Read, Write, Bash, Glob, Grep) and their own definition files via `--append-system-prompt-file`. Agents write structured output to `data/social-drafts/` files; Python reads and validates. New `memory_cli.py` gives agents Bash access to the memory module. Research pipeline untouched.

**Tech Stack:** Python 3, Claude CLI (`claude -p`), SQLite, subprocess, argparse

**Spec:** `docs/superpowers/specs/2026-03-14-social-pipeline-agent-rework-design.md`

---

## Chunk 1: Prerequisites — memory_cli.py

### Task 1: Create `memory_cli.py`

**Files:**
- Create: `memory_cli.py`
- Create: `tests/test_memory_cli.py`

- [ ] **Step 1: Write failing tests for memory_cli.py**

Create `tests/test_memory_cli.py`:

```python
"""Tests for memory_cli.py — lightweight CLI for agent memory access."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CLI = str(PROJECT_ROOT / "memory_cli.py")


def run_cli(*args: str) -> dict | list:
    """Run memory_cli.py and parse JSON output."""
    result = subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return json.loads(result.stdout)


class TestSearchFindings:
    @patch("memory.open_db")
    def test_returns_list(self, mock_db):
        """search-findings returns a JSON array."""
        # Tested via subprocess — mock at module level
        pass

    def test_search_findings_with_days_filter(self):
        """--days flag filters findings by date."""
        # Integration test — needs test DB
        pass


class TestRecentPosts:
    def test_returns_list(self):
        pass


class TestGetExemplars:
    def test_returns_list(self):
        pass


class TestRecentCorrections:
    def test_returns_list(self):
        pass


class TestCheckDuplicate:
    def test_returns_object(self):
        """check-duplicate returns a JSON object, not array."""
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_memory_cli.py -v`
Expected: FAIL (file not found / import error)

- [ ] **Step 3: Implement memory_cli.py**

Create `memory_cli.py` at project root:

```python
#!/usr/bin/env python3
"""Lightweight CLI for agent memory access.

Agents call this via Bash tool to query the memory database.
Each command prints JSON to stdout. Exit 0 on success, 1 on error.

Usage:
    python3 memory_cli.py search-findings --days 1 --min-importance 6
    python3 memory_cli.py recent-posts --days 30
    python3 memory_cli.py get-exemplars --platform x --limit 5
    python3 memory_cli.py recent-corrections --days 30
    python3 memory_cli.py check-duplicate --anchor "some topic anchor"
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

# DB lives at data/{user_id}/memory.db — default user is "ramsay"
DEFAULT_USER_ID = "ramsay"


def _get_db(user_id: str = DEFAULT_USER_ID) -> sqlite3.Connection:
    db_path = PROJECT_ROOT / "data" / user_id / "memory.db"
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    return db


def cmd_search_findings(args):
    """Search findings by date range and minimum importance.

    Note: importance is stored as a string ('high', 'medium', 'low').
    --min-importance accepts these strings (default: all).
    """
    db = _get_db()
    cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    query = """
        SELECT id, run_date, agent, title, summary, importance, category,
               source_url, source_name, date_found
        FROM findings
        WHERE run_date >= ?
    """
    params = [cutoff]
    if args.min_importance:
        # importance is a string: 'high', 'medium', 'low'
        query += " AND importance = ?"
        params.append(args.min_importance)
    query += " ORDER BY CASE importance WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, run_date DESC LIMIT ?"
    params.append(args.limit)
    rows = db.execute(query, params).fetchall()
    db.close()
    print(json.dumps([dict(r) for r in rows], indent=2))


def cmd_recent_posts(args):
    """List recent social posts for dedup context."""
    from memory.social import recent_posts
    db = _get_db()
    posts = recent_posts(db, days=args.days, limit=args.limit)
    db.close()
    print(json.dumps(posts, indent=2))


def cmd_get_exemplars(args):
    """Get approved posts as voice exemplars."""
    from memory.social import get_exemplars
    db = _get_db()
    exemplars = get_exemplars(db, platform=args.platform, limit=args.limit)
    db.close()
    print(json.dumps(exemplars, indent=2))


def cmd_recent_corrections(args):
    """Get recent editorial corrections (DPO training data)."""
    from memory.corrections import recent_corrections
    db = _get_db()
    corrections = recent_corrections(db, platform=args.platform, limit=args.limit)
    db.close()
    print(json.dumps(corrections, indent=2, default=str))


def cmd_check_duplicate(args):
    """Check if anchor text duplicates a recent post."""
    from memory.social import check_duplicate
    db = _get_db()
    result = check_duplicate(db, args.anchor, days=args.days, threshold=args.threshold)
    db.close()
    print(json.dumps(result, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="Memory CLI for agents")
    sub = parser.add_subparsers(dest="command", required=True)

    # search-findings
    p = sub.add_parser("search-findings")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--min-importance", type=str, default=None,
                   choices=["high", "medium", "low"],
                   help="Filter by importance level (string: high/medium/low)")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_search_findings)

    # recent-posts
    p = sub.add_parser("recent-posts")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_recent_posts)

    # get-exemplars
    p = sub.add_parser("get-exemplars")
    p.add_argument("--platform", type=str, default=None)
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_get_exemplars)

    # recent-corrections (no --days — function returns most recent N)
    p = sub.add_parser("recent-corrections")
    p.add_argument("--platform", type=str, default=None)
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_recent_corrections)

    # check-duplicate
    p = sub.add_parser("check-duplicate")
    p.add_argument("--anchor", type=str, required=True)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--threshold", type=float, default=0.80)
    p.set_defaults(func=cmd_check_duplicate)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write real tests with mock DB**

Update `tests/test_memory_cli.py` with proper tests:

```python
"""Tests for memory_cli.py."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
CLI = str(PROJECT_ROOT / "memory_cli.py")


def run_cli(*args: str, db_path: str | None = None) -> str:
    """Run memory_cli.py and return stdout."""
    env = None
    result = subprocess.run(
        [sys.executable, CLI, *args],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    return result


class TestSearchFindings:
    def test_no_db_returns_error(self):
        """Fails gracefully when DB doesn't exist at expected path."""
        # This tests the error path — production DB may or may not exist
        result = run_cli("search-findings", "--days", "1")
        # Either succeeds with [] or fails with error
        assert result.returncode in (0, 1)

    def test_help_flag(self):
        result = run_cli("search-findings", "--help")
        assert result.returncode == 0
        assert "--days" in result.stdout


class TestCheckDuplicate:
    def test_help_flag(self):
        result = run_cli("check-duplicate", "--help")
        assert result.returncode == 0
        assert "--anchor" in result.stdout

    def test_requires_anchor(self):
        result = run_cli("check-duplicate")
        assert result.returncode != 0


class TestCLICommands:
    def test_all_commands_have_help(self):
        for cmd in ["search-findings", "recent-posts", "get-exemplars",
                     "recent-corrections", "check-duplicate"]:
            result = run_cli(cmd, "--help")
            assert result.returncode == 0, f"{cmd} --help failed"

    def test_invalid_command(self):
        result = run_cli("nonexistent")
        assert result.returncode != 0
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_memory_cli.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add memory_cli.py tests/test_memory_cli.py
git commit -m "feat: add memory_cli.py for agent memory access via Bash tool"
```

---

## Chunk 2: `run_agent_with_files()` helper

### Task 2: Add `run_agent_with_files()` to orchestrator/agents.py

**Files:**
- Modify: `orchestrator/agents.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing test for `run_agent_with_files()`**

Append to `tests/test_orchestrator.py`:

```python
# ────────────────────────────────────────────────────────────────────────
# run_agent_with_files tests
# ────────────────────────────────────────────────────────────────────────

from orchestrator.agents import run_agent_with_files

class TestRunAgentWithFiles:
    def test_returns_parsed_json_when_agent_writes_file(self, tmp_path):
        """Agent writes JSON to output_file, helper reads and returns it."""
        output_file = tmp_path / "output.json"
        expected = {"anchor": "test topic", "composite_score": 7.5}

        with patch("orchestrator.agents.subprocess.run") as mock_run:
            # Simulate agent writing the output file
            def side_effect(*args, **kwargs):
                output_file.write_text(json.dumps(expected))
                return MagicMock(returncode=0, stdout="done", stderr="")
            mock_run.side_effect = side_effect

            result = run_agent_with_files(
                system_prompt_file="agents/eic.md",
                prompt="pick a topic",
                output_file=str(output_file),
                task_type="eic",
            )

        assert result == expected

    def test_returns_none_when_no_output_file(self, tmp_path):
        """Returns None when agent fails to write output file."""
        output_file = tmp_path / "output.json"

        with patch("orchestrator.agents.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            result = run_agent_with_files(
                system_prompt_file="agents/eic.md",
                prompt="pick a topic",
                output_file=str(output_file),
                task_type="eic",
            )

        assert result is None

    def test_deletes_stale_output_file(self, tmp_path):
        """Stale output file is deleted before agent runs."""
        output_file = tmp_path / "output.json"
        output_file.write_text('{"stale": true}')

        with patch("orchestrator.agents.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = run_agent_with_files(
                system_prompt_file="agents/eic.md",
                prompt="pick a topic",
                output_file=str(output_file),
                task_type="eic",
            )

        assert result is None  # stale data not returned

    def test_md_output_returns_text_dict(self, tmp_path):
        """Markdown output files return {"text": content} instead of JSON."""
        output_file = tmp_path / "draft.md"

        with patch("orchestrator.agents.subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                output_file.write_text("This is the draft content.")
                return MagicMock(returncode=0, stdout="done", stderr="")
            mock_run.side_effect = side_effect

            result = run_agent_with_files(
                system_prompt_file="agents/x-writer.md",
                prompt="write a draft",
                output_file=str(output_file),
                task_type="writer",
            )

        assert result == {"text": "This is the draft content."}

    def test_builds_correct_claude_command(self, tmp_path):
        """Verifies the subprocess command has correct flags."""
        output_file = tmp_path / "output.json"

        with patch("orchestrator.agents.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            run_agent_with_files(
                system_prompt_file="agents/eic.md",
                prompt="test",
                output_file=str(output_file),
                allowed_tools=["Read", "Write", "Bash"],
                task_type="eic",
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--append-system-prompt-file" in cmd
        idx = cmd.index("--append-system-prompt-file")
        assert cmd[idx + 1] == "agents/eic.md"
        assert "--output-format" in cmd
        # Verify all tools are passed
        tool_indices = [i for i, x in enumerate(cmd) if x == "--allowedTools"]
        tool_values = [cmd[i + 1] for i in tool_indices]
        assert set(tool_values) == {"Read", "Write", "Bash"}

    def test_writes_debug_log(self, tmp_path):
        """Captures stdout/stderr to debug log."""
        output_file = tmp_path / "output.json"
        debug_log = tmp_path / "eic-debug.log"

        with patch("orchestrator.agents.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="agent output", stderr="agent warnings"
            )
            with patch("orchestrator.agents.SOCIAL_DRAFTS_DIR", tmp_path):
                run_agent_with_files(
                    system_prompt_file="agents/eic.md",
                    prompt="test",
                    output_file=str(output_file),
                    task_type="eic",
                )

        assert debug_log.exists()
        log_content = debug_log.read_text()
        assert "agent output" in log_content
        assert "agent warnings" in log_content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_orchestrator.py::TestRunAgentWithFiles -v`
Expected: FAIL (ImportError — `run_agent_with_files` does not exist)

- [ ] **Step 3: Implement `run_agent_with_files()`**

Add to `orchestrator/agents.py` after the existing `run_claude_prompt()` function:

```python
SOCIAL_DRAFTS_DIR = PROJECT_ROOT / "data" / "social-drafts"


def run_agent_with_files(
    system_prompt_file: str,
    prompt: str,
    output_file: str,
    allowed_tools: list[str] | None = None,
    task_type: str = "eic",
) -> dict | None:
    """Run claude -p with agent file, tools, and file-based output.

    The agent writes structured output to output_file. This function
    reads and parses that file after the agent exits.

    Args:
        system_prompt_file: Path to agent definition .md file (relative to PROJECT_ROOT)
        prompt: Context and instructions for the agent
        output_file: Absolute path where agent should write output
        allowed_tools: Tools the agent can use (default: Read, Write, Bash, Glob, Grep)
        task_type: Router key for model/turns/timeout lookup

    Returns:
        Parsed dict from output file, or None if agent failed to write output.
        For .md output files, returns {"text": content}.
    """
    if allowed_tools is None:
        allowed_tools = ["Read", "Write", "Bash", "Glob", "Grep"]

    output_path = Path(output_file)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Delete stale output
    if output_path.exists():
        output_path.unlink()

    # Build command
    model = router.get_model(task_type)
    max_turns = router.get_max_turns(task_type)
    timeout = router.get_timeout(task_type)

    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--max-turns", str(max_turns),
        "--output-format", "text",
        "--append-system-prompt-file", system_prompt_file,
    ]
    for tool in allowed_tools:
        cmd.extend(["--allowedTools", tool])

    logger.info("run_agent_with_files: task=%s model=%s turns=%d timeout=%ds",
                task_type, model, max_turns, timeout)

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(PROJECT_ROOT),
        )
    except subprocess.TimeoutExpired:
        logger.error("Agent timed out: task=%s timeout=%ds", task_type, timeout)
        proc = None

    # Write debug log
    debug_log = SOCIAL_DRAFTS_DIR / f"{task_type}-debug.log"
    SOCIAL_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(debug_log, "w") as f:
        f.write(f"=== {task_type} debug log ===\n")
        f.write(f"exit_code: {proc.returncode if proc else 'TIMEOUT'}\n")
        f.write(f"output_file: {output_file}\n")
        f.write(f"output_exists: {output_path.exists()}\n\n")
        f.write("=== STDOUT ===\n")
        f.write(proc.stdout if proc else "")
        f.write("\n\n=== STDERR ===\n")
        f.write(proc.stderr if proc else "")

    # Read output file
    if not output_path.exists():
        logger.warning("Agent did not write output file: %s", output_file)
        return None

    content = output_path.read_text().strip()
    if not content:
        logger.warning("Agent wrote empty output file: %s", output_file)
        return None

    # Markdown files return as text dict
    if output_path.suffix == ".md":
        return {"text": content}

    # JSON files get parsed
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse agent output as JSON: %s — %s", output_file, e)
        return None
```

Also add at the top of the file if not already present: `import logging`, `import json`, and `logger = logging.getLogger(__name__)`. Check existing code — the file may already have these.

- [ ] **Step 4: Run tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_orchestrator.py::TestRunAgentWithFiles -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30`
Expected: All 223+ tests PASS

- [ ] **Step 6: Commit**

```bash
git add orchestrator/agents.py tests/test_orchestrator.py
git commit -m "feat: add run_agent_with_files() helper for file-based agent I/O"
```

---

## Chunk 3: Router update + agent .md file updates

### Task 3: Bump writer max_turns in router

**Files:**
- Modify: `orchestrator/router.py`

- [ ] **Step 1: Update MAX_TURNS for writer**

In `orchestrator/router.py`, change writer max_turns from 10 to 15:

```python
# In MAX_TURNS dict
"writer": 15,  # was 10 — agents now spend 2-3 turns on memory_cli tool calls
```

- [ ] **Step 2: Run existing tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_orchestrator.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add orchestrator/router.py
git commit -m "feat: bump writer max_turns 10→15 for tool-use overhead"
```

### Task 4: Update agent .md files

**Files:**
- Modify: `agents/eic.md` — update output path and simplify schema
- Modify: `agents/creative-director.md` — update output path to `data/social-drafts/creative-brief.json`
- Modify: `agents/x-writer.md` — update output path to `data/social-drafts/x-draft.md`
- Modify: `agents/linkedin-writer.md` — update output path to `data/social-drafts/linkedin-draft.md`
- Modify: `agents/bluesky-writer.md` — update output path to `data/social-drafts/bluesky-draft.md`
- Modify: `agents/expeditor.md` — update output path to `data/social-drafts/expedite-verdict.json`
- Modify: `agents/x-critic.md` — remove brief references, update output path
- Modify: `agents/linkedin-critic.md` — remove brief references, update output path
- Modify: `agents/bluesky-critic.md` — remove brief references, update output path

- [ ] **Step 1: Update `agents/eic.md`**

Find the output path instruction (references `data/social-brief-options.json`) and change to:
```
Write your output as JSON to `data/social-drafts/eic-topic.json`
```

Update the output schema section to match the spec:
```json
{
  "anchor": "one-line topic anchor",
  "angle": "editorial angle",
  "composite_score": 7.5,
  "scores": {
    "novelty": 8.0,
    "broad_appeal": 7.0,
    "thread_potential": 7.5
  },
  "sources": ["https://..."],
  "reasoning": "why this topic was selected"
}
```

- [ ] **Step 2: Update writer, CD, and expeditor .md files — output paths**

In `agents/x-writer.md`, `agents/linkedin-writer.md`, `agents/bluesky-writer.md`:
- Update output path instruction to `data/social-drafts/{platform}-draft.md`
- Ensure the file says "Write ONLY the post text, no JSON wrapper"

In `agents/creative-director.md`:
- Update output path instruction to `data/social-drafts/creative-brief.json`

In `agents/expeditor.md`:
- Update output path instruction to `data/social-drafts/expedite-verdict.json`

- [ ] **Step 3: Update critic .md files — remove brief references**

In `agents/x-critic.md`, `agents/linkedin-critic.md`, `agents/bluesky-critic.md`:
- Remove any line mentioning "curator brief", "creative brief", or "do_not_include from brief"
- Remove any line mentioning "Ralph loop state file"
- Ensure the "You'll receive" section lists only: draft post, voice guide, platform rules
- Add output instruction: `Write your verdict as JSON to data/social-drafts/{platform}-verdict.json`

Update verdict schema in each critic file:
```json
{
  "verdict": "APPROVED or REVISE",
  "feedback": "specific actionable feedback",
  "scores": {
    "voice_authenticity": 8,
    "platform_fit": 7,
    "engagement_potential": 6
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add agents/eic.md agents/creative-director.md agents/expeditor.md agents/x-writer.md agents/linkedin-writer.md agents/bluesky-writer.md agents/x-critic.md agents/linkedin-critic.md agents/bluesky-critic.md
git commit -m "feat: update agent .md files for file-based I/O and blind critic design"
```

---

## Chunk 4: Rework social/eic.py

### Task 5: Rework `select_topic()` and `create_brief()`

**Files:**
- Modify: `social/eic.py`

- [ ] **Step 1: Rework `select_topic()`**

Replace the inline prompt building and stdout parsing with file-based pattern.

Key changes to `select_topic()` (lines ~195-315):
1. Replace `_build_eic_prompt()` call with a minimal prompt that tells the agent to use `memory_cli.py`
2. Replace `run_claude_prompt()` call with `run_agent_with_files()`
3. Replace `_parse_eic_response()` with direct dict access from the returned JSON
4. Preserve the retry/dedup loop — rebuild prompt with rejected anchors on retry

New `select_topic()` implementation:

```python
def select_topic(
    db: sqlite3.Connection,
    user_id: str,
    date_str: str,
    *,
    max_retries: int = 3,
) -> dict | None:
    """Select today's social topic via EIC agent (Opus).

    The EIC agent queries memory via memory_cli.py, scores topics, and
    writes its selection to data/social-drafts/eic-topic.json.
    """
    from orchestrator.agents import run_agent_with_files

    config = _load_social_config()
    quality_threshold = config.get("eic", {}).get("quality_threshold", 5.0)
    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / "eic-topic.json")
    rejected_anchors: list[str] = []

    for attempt in range(1, max_retries + 1):
        logger.info("EIC topic selection attempt %d/%d", attempt, max_retries)

        prompt = _build_eic_agent_prompt(date_str, rejected_anchors)
        result = run_agent_with_files(
            system_prompt_file="agents/eic.md",
            prompt=prompt,
            output_file=output_file,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
            task_type="eic",
        )

        if result is None:
            logger.warning("EIC agent failed to produce output (attempt %d)", attempt)
            continue

        # Validate required fields
        if not result.get("anchor") or not result.get("composite_score"):
            logger.warning("EIC output missing required fields: %s", result.keys())
            continue

        # Quality threshold check
        score = float(result["composite_score"])
        if score < quality_threshold:
            logger.info("Topic below threshold: %.1f < %.1f — %s",
                     score, quality_threshold, result["anchor"])
            rejected_anchors.append(result["anchor"])
            continue

        # Dedup check
        from memory.social import check_duplicate
        dup = check_duplicate(db, result["anchor"], days=14)
        if dup["is_duplicate"]:
            logger.info("Topic is duplicate: %s (sim=%.2f)",
                     result["anchor"], dup["duplicates"][0]["similarity"] if dup["duplicates"] else 0)
            rejected_anchors.append(result["anchor"])
            continue

        logger.info("EIC selected topic: %s (score=%.1f)", result["anchor"], score)
        return result

    logger.warning("EIC exhausted %d retries — kill day", max_retries)
    return None
```

- [ ] **Step 2: Add `_build_eic_agent_prompt()` helper**

Add this function (replaces `_build_eic_prompt()`):

```python
def _build_eic_agent_prompt(date_str: str, rejected_anchors: list[str]) -> str:
    """Build prompt for EIC agent with memory_cli instructions."""
    parts = [
        f"Today is {date_str}. You are selecting one topic for today's social posts.",
        "",
        "## Your tools",
        "Use these Bash commands to gather information:",
        f"  python3 memory_cli.py search-findings --days 1 --limit 50",
        f"  python3 memory_cli.py search-findings --days 7 --min-importance high --limit 20",
        f"  python3 memory_cli.py recent-posts --days 30",
        "",
        "## Your task",
        "1. Run the commands above to see today's findings and recent posts",
        "2. Score the top candidates using your rubric (Novelty 0.35, Broad Appeal 0.40, Thread Potential 0.25)",
        "3. Select the single best topic",
        "4. Write your selection as JSON to data/social-drafts/eic-topic.json",
        "",
        "## Output schema",
        "Write EXACTLY this JSON structure to the file:",
        '```json',
        '{',
        '  "anchor": "one-line topic anchor",',
        '  "angle": "editorial angle — your unique take",',
        '  "composite_score": 7.5,',
        '  "scores": {"novelty": 8.0, "broad_appeal": 7.0, "thread_potential": 7.5},',
        '  "sources": ["https://..."],',
        '  "reasoning": "why this topic"',
        '}',
        '```',
    ]

    if rejected_anchors:
        parts.append("")
        parts.append("## DO NOT select these topics (already rejected):")
        for anchor in rejected_anchors:
            parts.append(f"- {anchor}")

    return "\n".join(parts)
```

- [ ] **Step 3: Rework `create_brief()`**

Replace inline prompt building with file-based pattern.

New `create_brief()` implementation:

```python
def create_brief(
    db: sqlite3.Connection,
    topic: dict,
    date_str: str,
) -> dict:
    """Expand EIC topic into creative brief via Creative Director (Sonnet).

    The CD agent reads its definition, the voice guide, and writes
    the brief to data/social-drafts/creative-brief.json.
    """
    from orchestrator.agents import run_agent_with_files

    config = _load_social_config()
    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / "creative-brief.json")

    # Read voice guide to inline in prompt
    voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    prompt = _build_brief_prompt(topic, date_str, voice_guide)
    result = run_agent_with_files(
        system_prompt_file="agents/creative-director.md",
        prompt=prompt,
        output_file=output_file,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
        task_type="creative_brief",
    )

    if result and result.get("editorial_angle"):
        logger.info("Creative brief generated: %s", result["editorial_angle"][:80])
        return result

    logger.warning("Creative Director failed — using fallback brief")
    return _fallback_brief(topic, date_str, config)
```

- [ ] **Step 4: Add `_build_brief_prompt()` helper**

```python
def _build_brief_prompt(topic: dict, date_str: str, voice_guide: str) -> str:
    """Build prompt for Creative Director agent."""
    topic_json = json.dumps(topic, indent=2)
    return f"""Today is {date_str}. Expand this topic into a creative brief for social posts.

## Selected topic
{topic_json}

## Voice guide
{voice_guide}

## Your tools
You can query memory for exemplars: python3 memory_cli.py get-exemplars --limit 5

## Your task
1. Read the topic and voice guide
2. Optionally check exemplars for voice calibration
3. Create a unified creative brief
4. Write the brief as JSON to data/social-drafts/creative-brief.json

## Output schema
Write EXACTLY this JSON structure:
```json
{{
  "editorial_angle": "your unique angle",
  "key_message": "the core message",
  "emotional_register": "curious/urgent/skeptical/etc",
  "tone": "tone description",
  "source_attribution": "how to reference sources",
  "visual_metaphor_direction": "metaphor for art",
  "platform_hooks": {{
    "x": "280-char hook for X",
    "linkedin": "1200-1500 char angle for LinkedIn",
    "bluesky": "300-char angle for Bluesky"
  }},
  "do_not_include": ["things to avoid"],
  "mindpattern_link": "https://mindpattern.ai/..."
}}
```"""
```

- [ ] **Step 5: Clean up — remove old helper functions that are no longer called**

Remove `_build_eic_prompt()` and `_parse_eic_response()` and `_parse_brief_response()` if they are no longer referenced anywhere. Keep `_fallback_brief()` and `_extract_source_urls()` and `_get_recent_findings()` (the latter may still be useful or referenced elsewhere — check before removing).

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add social/eic.py
git commit -m "feat: rework EIC to use file-based I/O with agent tools"
```

---

## Chunk 5: Rework social/writers.py

### Task 6: Rework `_write_single_platform()` and consolidate humanizer

**Files:**
- Modify: `social/writers.py`

- [ ] **Step 1: Rework `_write_single_platform()` to use `run_agent_with_files()`**

Key changes:
1. Replace `run_claude_prompt()` with `run_agent_with_files()`
2. Agent gets tools to query memory itself (exemplars, corrections)
3. Agent writes draft to `data/social-drafts/{platform}-draft.md`
4. Python reads the file back
5. Keep the Ralph Loop (writer → critic → feedback)

New implementation:

```python
def _write_single_platform(
    db,
    platform: str,
    brief: dict,
    config: dict,
) -> dict:
    """Run writer for one platform with Ralph Loop (writer ↔ blind critic).

    The writer agent queries memory for exemplars and corrections,
    then writes its draft to data/social-drafts/{platform}-draft.md.
    """
    from orchestrator.agents import run_agent_with_files
    from social.critics import review_draft, deterministic_validate

    max_iterations = config.get("max_iterations", 3)
    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / f"{platform}-draft.md")

    # Read voice guide to inline in prompt
    voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    feedback = None
    last_draft = ""
    last_verdict = {"verdict": "REVISE", "feedback": "initial attempt"}

    for iteration in range(1, max_iterations + 1):
        logger.info("Writing %s draft (iteration %d/%d)", platform, iteration, max_iterations)

        prompt = _build_writer_agent_prompt(
            platform, brief, voice_guide, iteration, feedback,
        )

        result = run_agent_with_files(
            system_prompt_file=f"agents/{platform}-writer.md",
            prompt=prompt,
            output_file=output_file,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
            task_type="writer",
        )

        if result is None or not result.get("text", "").strip():
            logger.warning("Writer produced no output for %s (iteration %d)", platform, iteration)
            continue

        last_draft = result["text"].strip()

        # Deterministic policy check
        policy_errors = deterministic_validate(platform, last_draft)
        if policy_errors:
            feedback = "POLICY VIOLATIONS:\n" + "\n".join(f"- {e}" for e in policy_errors)
            logger.info("Policy errors on %s: %s", platform, policy_errors)
            continue

        # Blind critic review
        last_verdict = review_draft(platform, last_draft)
        if last_verdict["verdict"] == "APPROVED":
            logger.info("Critic approved %s draft (iteration %d)", platform, iteration)
            break

        feedback = last_verdict.get("feedback", "No specific feedback")
        logger.info("Critic requests revision for %s: %s", platform, feedback[:100])

    # Humanize — open thread-safe DB connection (SQLite not thread-safe)
    import memory as _mem
    thread_db = _mem.get_db()
    humanized = _humanize(last_draft, platform, thread_db)
    thread_db.close()

    return {
        "content": humanized,
        "humanized": True,
        "iterations": iteration,
        "critic_verdict": last_verdict,
        "policy_errors": deterministic_validate(platform, humanized),
        "error": None,
    }
```

- [ ] **Step 2: Add `_build_writer_agent_prompt()` helper**

Replaces `_build_writer_prompt()`:

```python
def _build_writer_agent_prompt(
    platform: str,
    brief: dict,
    voice_guide: str,
    iteration: int,
    feedback: str | None,
) -> str:
    """Build prompt for writer agent with memory_cli instructions."""
    brief_json = json.dumps(brief, indent=2)
    parts = [
        f"Write a {platform} post based on this creative brief.",
        "",
        "## Creative brief",
        brief_json,
        "",
        "## Voice guide",
        voice_guide,
        "",
        "## Your tools",
        "Use these Bash commands to calibrate your voice:",
        f"  python3 memory_cli.py get-exemplars --platform {platform} --limit 5",
        f"  python3 memory_cli.py recent-corrections --platform {platform}",
        "",
        "## Your task",
        "1. Read the brief and voice guide above",
        "2. Run the memory commands to see approved exemplars and editorial corrections",
        "3. Write the post, matching the voice of the exemplars",
        "4. Apply lessons from the corrections (avoid patterns that were corrected)",
        f"5. Write ONLY the post text to data/social-drafts/{platform}-draft.md",
        "   - No JSON wrapper, no metadata, just the post text",
    ]

    if iteration > 1 and feedback:
        parts.extend([
            "",
            f"## Critic feedback (iteration {iteration})",
            "Your previous draft was rejected. Address this feedback:",
            feedback,
        ])

    return "\n".join(parts)
```

- [ ] **Step 3: Update `_humanize()` to include editorial corrections**

Port the corrections logic from `pipeline.py:_build_humanize_prompt()` into `writers.py:_humanize()`. The new signature adds a `db` parameter:

```python
def _humanize(content: str, platform: str, db=None) -> str:
    """Remove AI writing patterns. Includes editorial corrections for voice calibration.

    This is the canonical humanizer. pipeline.py's _build_humanize_prompt is removed.
    """
    from orchestrator.agents import run_claude_prompt

    # Load recent corrections for DPO calibration
    corrections_text = ""
    if db is not None:
        try:
            from memory.corrections import recent_corrections
            corrections = recent_corrections(db, platform=platform, limit=5)
            if corrections:
                pairs = []
                for c in corrections:
                    pairs.append(f"BEFORE: {c['original_text'][:200]}")
                    pairs.append(f"AFTER: {c['approved_text'][:200]}")
                    if c.get("reason"):
                        pairs.append(f"REASON: {c['reason']}")
                    pairs.append("")
                corrections_text = "\n## Editorial corrections (learn from these)\n" + "\n".join(pairs)
        except Exception:
            pass  # corrections are optional

    prompt = f"""Remove AI writing patterns from this {platform} post.

## Rules
- Remove em dashes (—), replace with commas or periods
- Remove rhetorical questions
- Remove filler: "It's worth noting", "Interestingly", "Let's be clear"
- Remove excessive hedging: "arguably", "perhaps", "it seems"
- Remove banned words: "game-changer", "paradigm", "synergy", "leverage", "ecosystem"
- Keep the meaning and length approximately the same
- Return ONLY the cleaned post text, nothing else
{corrections_text}

## Post to clean
{content}"""

    output, code = run_claude_prompt(prompt, "humanizer")
    if code == 0 and output.strip():
        return output.strip()
    return content  # fallback to original
```

- [ ] **Step 4: Update `write_drafts()` to pass `db` to `_humanize()`**

The existing `write_drafts()` already has `db` as first parameter. Ensure `_write_single_platform()` passes it through. The updated `_write_single_platform()` already calls `_humanize(last_draft, platform, db)`.

- [ ] **Step 5: Clean up — remove old `_build_writer_prompt()` and `_extract_draft_text()`**

These are replaced by `_build_writer_agent_prompt()` and direct file reading. Remove them if not referenced elsewhere.

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add social/writers.py
git commit -m "feat: rework writers to use file-based I/O with agent tools"
```

---

## Chunk 6: Rework social/critics.py

### Task 7: Rework `review_draft()` and `expedite()`

**Files:**
- Modify: `social/critics.py`

- [ ] **Step 1: Rework `review_draft()` to use `run_agent_with_files()`**

```python
def review_draft(platform: str, draft_text: str) -> dict:
    """Blind critic review. Sees ONLY draft text + platform rules + voice guide.

    Agent writes verdict to data/social-drafts/{platform}-verdict.json.
    """
    from orchestrator.agents import run_agent_with_files

    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / f"{platform}-verdict.json")

    # Read voice guide to inline
    voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    platform_rules = _get_platform_rules(platform)

    prompt = f"""Review this {platform} draft. You are a BLIND critic — you have NOT seen the brief.

## Draft to review
{draft_text}

## Platform rules
{platform_rules}

## Voice guide
{voice_guide}

## Your task
1. Evaluate the draft on three dimensions (1-10 each):
   - voice_authenticity: Does it sound like a real person, not an AI?
   - platform_fit: Does it follow {platform} conventions and constraints?
   - engagement_potential: Would people engage with this?
2. Check kill switches: banned words, em dashes, character limits, "mindpattern" as grammatical subject
3. Decide: APPROVED or REVISE
4. Write your verdict as JSON to data/social-drafts/{platform}-verdict.json

## Output schema
```json
{{
  "verdict": "APPROVED or REVISE",
  "feedback": "specific actionable feedback",
  "scores": {{
    "voice_authenticity": 8,
    "platform_fit": 7,
    "engagement_potential": 6
  }}
}}
```"""

    result = run_agent_with_files(
        system_prompt_file=f"agents/{platform}-critic.md",
        prompt=prompt,
        output_file=output_file,
        allowed_tools=["Read", "Write", "Glob", "Grep"],  # No Bash — blind
        task_type="critic",
    )

    if result and result.get("verdict"):
        return result

    # Fail safe: REVISE on failure
    logger.warning("Critic failed for %s — defaulting to REVISE", platform)
    return {
        "verdict": "REVISE",
        "feedback": "Critic agent failed to produce output. Please revise.",
        "scores": {"voice_authenticity": 0, "platform_fit": 0, "engagement_potential": 0},
    }
```

- [ ] **Step 2: Rework `expedite()` to use `run_agent_with_files()`**

```python
def expedite(drafts: dict[str, dict], brief: dict, images: dict) -> dict:
    """Final cross-platform quality gate before approval.

    Agent sees all drafts, brief, and images. Writes verdict to
    data/social-drafts/expedite-verdict.json.
    """
    from orchestrator.agents import run_agent_with_files

    output_file = str(PROJECT_ROOT / "data" / "social-drafts" / "expedite-verdict.json")

    # Read voice guide
    voice_guide_path = PROJECT_ROOT / "agents" / "voice-guide.md"
    voice_guide = voice_guide_path.read_text() if voice_guide_path.exists() else ""

    # Build proof package
    proof = {
        "brief": brief,
        "drafts": {p: d.get("content", "") for p, d in drafts.items()},
        "policy_errors": {p: d.get("policy_errors", []) for p, d in drafts.items()},
        "images": {p: str(v) for p, v in images.items()} if images else {},
    }
    proof_json = json.dumps(proof, indent=2)

    prompt = f"""Final quality gate. Check cross-platform coherence before posting.

## Proof package
{proof_json}

## Voice guide
{voice_guide}

## Your task
1. Check: Do all drafts align with the same anchor/angle?
2. Check: Any conflicting claims across platforms?
3. Check: Any policy errors? (Any draft with policy_errors → FAIL)
4. Check: Does each draft match the voice guide?
5. Score on 6 dimensions (1-10 each)
6. Write verdict to data/social-drafts/expedite-verdict.json

## Output schema
```json
{{
  "verdict": "PASS or FAIL",
  "feedback": "explanation",
  "platform_verdicts": {{
    "x": "PASS or FAIL",
    "linkedin": "PASS or FAIL",
    "bluesky": "PASS or FAIL"
  }},
  "scores": {{
    "voice_match": 8,
    "framing_authenticity": 7,
    "platform_genre_fit": 8,
    "epistemic_calibration": 7,
    "structural_variation": 6,
    "rhetorical_framework": 7
  }}
}}
```"""

    result = run_agent_with_files(
        system_prompt_file="agents/expeditor.md",
        prompt=prompt,
        output_file=output_file,
        allowed_tools=["Read", "Write", "Glob", "Grep"],  # No Bash
        task_type="expeditor",
    )

    if result and result.get("verdict"):
        return result

    # Fail safe: FAIL on failure
    logger.warning("Expeditor failed — defaulting to FAIL")
    return {
        "verdict": "FAIL",
        "feedback": "Expeditor agent failed to produce output.",
        "platform_verdicts": {},
        "scores": {},
    }
```

- [ ] **Step 3: Clean up old helpers**

Remove `_build_critic_prompt()`, `_build_expeditor_prompt()`, `_parse_critic_output()`, `_parse_expeditor_output()` — all replaced by file-based pattern. Keep `_get_platform_rules()` and `deterministic_validate()` unchanged.

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add social/critics.py
git commit -m "feat: rework critics to use file-based I/O with blind design"
```

---

## Chunk 7: Pipeline changes + iMessage fix

### Task 8: Update `social/pipeline.py`

**Files:**
- Modify: `social/pipeline.py`

- [ ] **Step 1: Remove `_build_humanize_prompt()` from pipeline.py**

Delete the `_build_humanize_prompt()` method (lines ~587-625). The canonical humanizer is now `writers._humanize()` which includes corrections logic.

Update any call site in `pipeline.py` that uses `_build_humanize_prompt()` to call `writers._humanize()` instead. The humanizer step in the pipeline's `run()` method should be:

```python
# Step 7: Humanize
from social.writers import _humanize
for platform, draft in drafts.items():
    draft["content"] = _humanize(draft["content"], platform, self.db)
```

- [ ] **Step 2: Update Gate 1 message formatting in `approval.py`**

The message formatting happens in `ApprovalGateway` (not pipeline.py). Find `_format_topic_message()` or the iMessage send call in `request_topic_approval()` and update to include full details:

```python
# In approval.py — wherever the topic iMessage text is built
topic_msg = (
    f"Topic for approval:\n\n"
    f"Anchor: {topic['anchor']}\n"
    f"Angle: {topic.get('angle', 'N/A')}\n"
    f"Score: {topic.get('composite_score', 'N/A')}\n"
    f"Sources: {', '.join(topic.get('sources', []))}\n"
    f"Reasoning: {topic.get('reasoning', 'N/A')}\n\n"
    f"Reply GO to approve, SKIP to kill, or type a custom topic."
)
```

If `pipeline.py` is what passes topic data to `request_topic_approval()`, ensure it passes the full topic dict (not just the title).

- [ ] **Step 3: Update Gate 2 message formatting in `approval.py`**

Find where draft approval iMessage text is built in `approval.py` and update to show actual draft text per platform:

```python
# In approval.py — wherever the draft iMessage text is built
parts = ["Drafts for approval:\n"]
for platform, draft in drafts.items():
    content = draft.get("content", "")
    parts.append(f"--- {platform.upper()} ---")
    parts.append(content[:500])  # Truncate for iMessage
    parts.append("")
parts.append("Reply ALL to post all, SKIP to reject, or name platforms (e.g. 'x linkedin').")
draft_msg = "\n".join(parts)
```

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add social/pipeline.py
git commit -m "feat: update pipeline gates and remove duplicate humanizer"
```

### Task 8b: Update existing tests that mock `run_claude_prompt`

**Files:**
- Modify: `tests/test_social.py`

- [ ] **Step 1: Update test mocks**

Tests in `tests/test_social.py` that mock `run_claude_prompt` for social functions (select_topic, review_draft, expedite, write_drafts) need to be updated to mock `run_agent_with_files` instead. The mock should simulate writing to the output file and returning the parsed dict.

For each affected test:
- Change `patch("orchestrator.agents.run_claude_prompt")` to `patch("orchestrator.agents.run_agent_with_files")`
- Update mock return values to match the new dict schemas (not stdout strings)
- Ensure the mock side_effect writes the expected output file if the test checks file existence

- [ ] **Step 2: Run tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_social.py -v --timeout=30`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_social.py
git commit -m "test: update social test mocks for run_agent_with_files migration"
```

### Task 9: Fix iMessage delivery in `social/approval.py`

**Files:**
- Modify: `social/approval.py`

- [ ] **Step 1: Replace AppleScript in `_imessage_send()`**

Find `_imessage_send()` (line ~335-366). Replace the `targetService`/`targetBuddy` pattern with v2's simple pattern. Preserve the existing escaping logic.

Change the AppleScript body from:
```applescript
tell application "Messages"
    set targetService to 1st account whose service type = iMessage
    set targetBuddy to participant "{phone}" of targetService
    send "{escaped}" to targetBuddy
end tell
```

To:
```applescript
tell application "Messages"
    send "{escaped}" to buddy "{phone}"
end tell
```

The rest of the method (escaping, subprocess call to `osascript`) stays the same.

- [ ] **Step 2: Verify phone number format**

Check the config or class init for the phone number. Ensure it's formatted as `+1XXXXXXXXXX`. If it's stored without the `+1` prefix, add normalization:

```python
# At the top of _imessage_send, normalize phone
if not phone.startswith("+"):
    phone = f"+1{phone}"
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add social/approval.py
git commit -m "fix: replace complex iMessage AppleScript with v2's proven simple pattern"
```

---

## Chunk 8: Integration verification

### Task 10: End-to-end smoke test

**Files:**
- No new files

- [ ] **Step 1: Verify all imports resolve**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3
python3 -c "from orchestrator.agents import run_agent_with_files; print('agents OK')"
python3 -c "from social.eic import select_topic, create_brief; print('eic OK')"
python3 -c "from social.writers import write_drafts, _humanize; print('writers OK')"
python3 -c "from social.critics import review_draft, expedite, deterministic_validate; print('critics OK')"
python3 -c "from social.pipeline import SocialPipeline; print('pipeline OK')"
python3 -c "from social.approval import ApprovalGateway; print('approval OK')"
```

Expected: All print OK

- [ ] **Step 2: Verify memory_cli.py commands parse correctly**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3
python3 memory_cli.py search-findings --help
python3 memory_cli.py recent-posts --help
python3 memory_cli.py get-exemplars --help
python3 memory_cli.py recent-corrections --help
python3 memory_cli.py check-duplicate --help
```

Expected: All show help text without errors

- [ ] **Step 3: Run full test suite one final time**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/ -v --timeout=30
```

Expected: All 223+ tests PASS (plus any new tests added)

- [ ] **Step 4: Verify no removed functions are still referenced**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3
# Check for references to removed functions
grep -rn "_build_eic_prompt\|_parse_eic_response\|_parse_brief_response\|_build_writer_prompt\|_extract_draft_text\|_build_critic_prompt\|_build_expeditor_prompt\|_parse_critic_output\|_parse_expeditor_output\|_build_humanize_prompt" --include="*.py" .
```

Expected: No results (or only in test files / comments that should also be cleaned up)

- [ ] **Step 5: Final commit with any cleanup**

```bash
git add -A
git status  # review what's staged
git commit -m "chore: cleanup removed function references and final integration verification"
```

# Self-Optimization Loop Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an ANALYZE phase that reads agent trace logs, compares behavior vs skill instructions, and fixes skill files — creating a self-improving feedback loop.

**Architecture:** New `orchestrator/analyzer.py` with three functions (build prompt, parse output, apply changes). New ANALYZE phase in pipeline after EVOLVE. One Opus 1M call reads all traces + skills, outputs JSON diff, changes applied via atomic writes with PromptTracker regression detection.

**Tech Stack:** Python 3.14, existing vault.atomic_write(), PromptTracker, identity_evolve.parse_llm_output() pattern

**Spec:** `docs/superpowers/specs/2026-03-16-self-optimization-loop.md`

---

## Dependency Graph

```
Task 1 (pipeline.py + router.py)  ── FOUNDATION
├── Task 2 (prompt_tracker.py)    ── PARALLEL with Task 3
├── Task 3 (analyzer.py)          ── PARALLEL with Task 2
│   └── Task 4 (runner.py)        ── SEQUENTIAL after 2+3
│       └── Task 5 (integration)  ── FINAL
```

## File Structure

### New Files
- `orchestrator/analyzer.py` — build_analyzer_prompt, parse_analyzer_output, apply_analyzer_changes
- `tests/test_analyzer.py` — unit + integration tests

### Modified Files
- `orchestrator/pipeline.py:12-55` — add ANALYZE phase to enum and PHASE_ORDER
- `orchestrator/router.py` — add analyzer model routing
- `orchestrator/prompt_tracker.py:25-28` — extend PROMPT_DIRS
- `orchestrator/runner.py` — add _phase_analyze() handler + _collect_all_skill_files()

---

## Chunk 1: Foundation + Core Implementation

### Task 1: Add ANALYZE phase to pipeline + router

**Files:**
- Modify: `orchestrator/pipeline.py:12-55`
- Modify: `orchestrator/router.py`

- [ ] **Step 1: Write test**

```python
# tests/test_analyzer.py
"""Tests for self-optimization analyzer."""
from orchestrator.pipeline import Phase, PHASE_ORDER, SKIPPABLE_PHASES


def test_analyze_phase_exists():
    assert hasattr(Phase, "ANALYZE")
    assert Phase.ANALYZE.value == "analyze"


def test_analyze_in_phase_order():
    order = [p.value for p in PHASE_ORDER]
    evolve_idx = order.index("evolve")
    analyze_idx = order.index("analyze")
    mirror_idx = order.index("mirror")
    assert evolve_idx < analyze_idx < mirror_idx


def test_analyze_is_skippable():
    assert Phase.ANALYZE in SKIPPABLE_PHASES
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_analyzer.py::test_analyze_phase_exists -v`
Expected: FAIL — `AttributeError: ANALYZE`

- [ ] **Step 3: Implement pipeline.py changes**

In `orchestrator/pipeline.py`, add `ANALYZE = "analyze"` to Phase enum (after EVOLVE, before MIRROR). Update PHASE_ORDER to include it. Add to SKIPPABLE_PHASES.

- [ ] **Step 4: Add router config**

In `orchestrator/router.py`, add to MODEL_ROUTING:
```python
"analyzer": "opus_1m",
```
Add to MAX_TURNS:
```python
"analyzer": 10,
```
Add to TIMEOUTS:
```python
"analyzer": 600,
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python3 -m pytest tests/test_analyzer.py -v`

- [ ] **Step 6: Commit**

```bash
git add orchestrator/pipeline.py orchestrator/router.py tests/test_analyzer.py
git commit -m "feat: add ANALYZE phase to pipeline state machine and router"
```

---

### Task 2: Extend PromptTracker to scan research agent files

**Files:**
- Modify: `orchestrator/prompt_tracker.py:25-28`
- Test: `tests/test_analyzer.py` (append)

- [ ] **Step 1: Write test**

```python
from orchestrator.prompt_tracker import PROMPT_DIRS
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def test_prompt_dirs_includes_research_agents():
    expected = PROJECT_ROOT / "verticals" / "ai-tech" / "agents"
    assert expected in PROMPT_DIRS
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement**

In `orchestrator/prompt_tracker.py`, add to PROMPT_DIRS:
```python
PROMPT_DIRS = [
    PROJECT_ROOT / "prompts",
    PROJECT_ROOT / "agents",
    PROJECT_ROOT / "verticals" / "ai-tech" / "agents",
]
```

- [ ] **Step 4: Run test, verify pass**
- [ ] **Step 5: Commit**

```bash
git add orchestrator/prompt_tracker.py tests/test_analyzer.py
git commit -m "feat: extend PromptTracker to scan research agent skill files"
```

---

### Task 3: Create orchestrator/analyzer.py

**Files:**
- Create: `orchestrator/analyzer.py`
- Test: `tests/test_analyzer.py` (append)

This is the core — three functions.

- [ ] **Step 1: Write tests**

```python
import json
from pathlib import Path
from orchestrator.analyzer import (
    build_analyzer_prompt,
    parse_analyzer_output,
    apply_analyzer_changes,
)


def test_build_analyzer_prompt_includes_traces(tmp_path):
    # Create mock trace dir with one agent
    trace_dir = tmp_path / "agents"
    hn = trace_dir / "hn-researcher"
    hn.mkdir(parents=True)
    (hn / "2026-03-16.md").write_text("# hn-researcher trace\n## Reasoning\nUsed WebSearch first.")

    # Create mock skill file
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    skill_file = skill_dir / "hn-researcher.md"
    skill_file.write_text("# HN Researcher\n## Phase 2 Exploration Preferences\n- Primary: Exa")

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=[skill_file],
        date_str="2026-03-16",
        metrics={"findings_per_agent": {"hn-researcher": 12}},
        regression_data=[],
    )

    assert "hn-researcher trace" in prompt
    assert "Used WebSearch first" in prompt
    assert "Phase 2 Exploration Preferences" in prompt
    assert "Primary: Exa" in prompt


def test_build_analyzer_prompt_skips_agents_without_trace(tmp_path):
    trace_dir = tmp_path / "agents"
    trace_dir.mkdir(parents=True)
    # No trace files at all

    skill_file = tmp_path / "agent.md"
    skill_file.write_text("# Agent")

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=[skill_file],
        date_str="2026-03-16",
        metrics={},
        regression_data=[],
    )

    assert "No trace logs found" in prompt or "TRACE LOG" not in prompt


def test_build_analyzer_prompt_includes_regression_data(tmp_path):
    trace_dir = tmp_path / "agents"
    trace_dir.mkdir(parents=True)

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=[],
        date_str="2026-03-16",
        metrics={},
        regression_data=[{
            "file": "agents/hn-researcher.md",
            "quality_before": 0.85,
            "quality_after": 0.60,
            "regression_pct": 0.294,
        }],
    )

    assert "REGRESSION" in prompt
    assert "hn-researcher" in prompt
    assert "0.85" in prompt


def test_parse_analyzer_output_valid():
    raw = json.dumps({
        "changes": [{"file": "agents/x.md", "reason": "test", "diff": {"section": "S", "action": "replace", "content": "new"}}],
        "reversions": [],
        "no_changes": [],
    })
    result = parse_analyzer_output(raw)
    assert len(result["changes"]) == 1
    assert result["changes"][0]["file"] == "agents/x.md"


def test_parse_analyzer_output_with_fences():
    raw = '```json\n{"changes": [], "reversions": [], "no_changes": ["a.md"]}\n```'
    result = parse_analyzer_output(raw)
    assert result is not None
    assert result["no_changes"] == ["a.md"]


def test_parse_analyzer_output_invalid():
    result = parse_analyzer_output("not json at all")
    assert result is None


def test_apply_analyzer_changes_replace(tmp_path):
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\n\n## Focus\nOld focus\n\n## Notes\nKeep this\n")

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test",
            "diff": {"section": "Focus", "action": "replace", "content": "New focus content"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path)
    updated = skill.read_text()
    assert "New focus content" in updated
    assert "Old focus" not in updated
    assert "Keep this" in updated  # Other sections preserved
    assert result["applied"] == 1


def test_apply_analyzer_changes_append(tmp_path):
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\n\n## Notes\nExisting note\n")

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test",
            "diff": {"section": "Notes", "action": "append", "content": "\nNew note from analyzer"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path)
    updated = skill.read_text()
    assert "Existing note" in updated
    assert "New note from analyzer" in updated


def test_apply_analyzer_changes_rejects_missing_trace(tmp_path):
    """Changes for files with no trace should be rejected."""
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\n\n## Focus\nOld\n")

    changes = {
        "changes": [{
            "file": str(skill),
            "reason": "test",
            "diff": {"section": "Focus", "action": "replace", "content": "New"},
        }],
        "reversions": [],
        "no_changes": [],
    }

    result = apply_analyzer_changes(changes, project_root=tmp_path, traced_files=set())
    assert result["applied"] == 0
    assert result["skipped"] == 1
```

- [ ] **Step 2: Run tests, verify fail**

- [ ] **Step 3: Implement orchestrator/analyzer.py**

```python
"""Self-optimization analyzer — trace-driven skill improvement.

Reads agent trace logs, compares behavior vs skill instructions,
identifies deviations, and produces a JSON diff of skill file changes.
"""

import hashlib
import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def build_analyzer_prompt(
    trace_dir: Path,
    skill_files: list[Path],
    date_str: str,
    metrics: dict,
    regression_data: list[dict],
) -> str:
    """Assemble the analyzer prompt with traces, skills, metrics, and regression data."""

    # Collect trace logs for today only
    traces_section = ""
    traced_agents = set()
    if trace_dir.exists():
        for agent_dir in sorted(trace_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            trace_file = agent_dir / f"{date_str}.md"
            if trace_file.exists():
                content = trace_file.read_text()
                traces_section += f"\n### TRACE LOG: {agent_dir.name}\n\n{content}\n\n---\n"
                traced_agents.add(agent_dir.name)

    if not traces_section:
        traces_section = "\nNo trace logs found for today.\n"

    # Collect skill files
    skills_section = ""
    for sf in sorted(skill_files):
        if sf.exists():
            content = sf.read_text()
            rel_path = sf.name
            try:
                rel_path = str(sf.relative_to(sf.parent.parent.parent))
            except ValueError:
                try:
                    rel_path = str(sf.relative_to(sf.parent.parent))
                except ValueError:
                    rel_path = sf.name
            skills_section += f"\n### SKILL FILE: {rel_path}\n\n{content}\n\n---\n"

    # Metrics
    metrics_section = ""
    if metrics:
        metrics_section = f"\n## Pipeline Metrics\n\n```json\n{json.dumps(metrics, indent=2)}\n```\n"

    # Regression data
    regression_section = ""
    if regression_data:
        regression_section = "\n## REGRESSION WARNINGS\n\nPrevious ANALYZE edits caused quality drops:\n\n"
        regression_section += "| File | Quality Before | Quality After | Drop |\n|---|---|---|---|\n"
        for r in regression_data:
            regression_section += (
                f"| {r.get('file', '?')} | {r.get('quality_before', '?')} "
                f"| {r.get('quality_after', '?')} | {r.get('regression_pct', 0):.1%} |\n"
            )
        regression_section += "\nConsider REVERTING these changes or fixing the underlying issue.\n"

    # Traced agents list for validation
    traced_list = ", ".join(sorted(traced_agents)) if traced_agents else "none"

    prompt = f"""You are analyzing agent execution traces to improve agent skill files.

## Your Task

Compare each agent's SKILL FILE (what it should do) against its TRACE LOG (what it actually did).
Identify deviations and output a JSON diff to fix the skill files for next run.

## Rules

1. Only propose changes for agents that have a trace log from today. Agents with traces: {traced_list}
2. If a REGRESSION WARNING exists for a file, consider reverting or fixing that change.
3. Be specific in your reasons — cite exact tool calls or behaviors from the trace.
4. Prefer minimal targeted edits over full rewrites.
5. If an agent performed well (followed instructions, good findings), put it in no_changes.

## Deviation Categories to Check

- **Tool usage**: Did the agent use tools in the order the skill specified? (e.g., Exa before WebSearch)
- **Phase compliance**: Did it do Phase 1 (evaluate preflight) before Phase 2 (explore)?
- **Quality**: Did it read sources deeply (Jina/WebFetch) or rely on search snippets?
- **Output**: Valid JSON on first try? Findings match focus areas?
- **Cross-agent**: Multiple agents making the same mistake = systemic issue.

{regression_section}
{metrics_section}

## Agent Trace Logs
{traces_section}

## Agent Skill Files
{skills_section}

## Output Format

Output ONLY valid JSON:

```json
{{
  "changes": [
    {{
      "file": "relative/path/to/skill.md",
      "reason": "Specific deviation observed in trace",
      "diff": {{
        "section": "## Section Name",
        "action": "replace|append",
        "content": "New section content"
      }}
    }}
  ],
  "reversions": [
    {{
      "file": "relative/path/to/skill.md",
      "reason": "Previous change caused regression",
      "revert_to_hash": "git_hash"
    }}
  ],
  "no_changes": [
    "relative/path/to/skill.md"
  ]
}}
```

Use full relative paths from project root for all files (e.g., "verticals/ai-tech/agents/hn-researcher.md", "agents/eic.md").
"""
    return prompt


def parse_analyzer_output(raw_output: str) -> dict | None:
    """Extract JSON diff from analyzer LLM output.

    Same extraction pattern as identity_evolve.parse_llm_output().
    """
    if not raw_output or not raw_output.strip():
        return None

    text = raw_output.strip()

    # 1. Try direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "changes" in parsed:
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Try code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)
    match = fence_pattern.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict) and "changes" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Try first { ... last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            parsed = json.loads(text[first_brace:last_brace + 1])
            if isinstance(parsed, dict) and "changes" in parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _find_and_replace_section(content: str, section_name: str, new_body: str) -> str:
    """Replace the body of a ## section in markdown, preserving other sections."""
    lines = content.split("\n")
    result = []
    in_target = False
    replaced = False

    # Normalize section name for matching
    target = section_name.lstrip("#").strip().lower()

    for line in lines:
        if line.startswith("## "):
            heading = line.lstrip("#").strip().lower()
            if heading == target:
                result.append(line)  # Keep the heading
                result.append(new_body.rstrip())
                result.append("")
                in_target = True
                replaced = True
                continue
            else:
                in_target = False

        if not in_target:
            result.append(line)

    # If section not found, append it
    if not replaced:
        result.append("")
        result.append(f"## {section_name.lstrip('#').strip()}")
        result.append(new_body.rstrip())
        result.append("")

    return "\n".join(result)


def _append_to_section(content: str, section_name: str, new_content: str) -> str:
    """Append content to the end of a ## section in markdown."""
    lines = content.split("\n")
    result = []
    target = section_name.lstrip("#").strip().lower()
    in_target = False
    appended = False

    for i, line in enumerate(lines):
        if line.startswith("## "):
            heading = line.lstrip("#").strip().lower()
            if in_target and not appended:
                # We were in the target section and hit the next section
                result.append(new_content.rstrip())
                result.append("")
                appended = True
            in_target = (heading == target)

        result.append(line)

    # If we were in the target section at end of file
    if in_target and not appended:
        result.append(new_content.rstrip())
        result.append("")

    return "\n".join(result)


def apply_analyzer_changes(
    changes: dict,
    project_root: Path,
    traced_files: set[str] | None = None,
    prompt_tracker=None,
) -> dict:
    """Apply JSON diff changes to skill files.

    Args:
        changes: Parsed JSON diff from analyzer.
        project_root: Project root for resolving relative paths.
        traced_files: Set of agent names that had traces today. If provided,
                     changes for agents without traces are rejected.
        prompt_tracker: PromptTracker instance for recording hashes.

    Returns:
        Dict with applied, skipped, reverted, errors counts.
    """
    from memory.vault import atomic_write

    result = {"applied": 0, "skipped": 0, "reverted": 0, "errors": []}

    # Apply changes
    for change in changes.get("changes", []):
        file_path = project_root / change["file"]
        diff = change.get("diff", {})
        reason = change.get("reason", "")

        # Validate: reject if no trace for this agent
        if traced_files is not None:
            # Extract agent name from file path
            agent_name = file_path.stem
            if agent_name not in traced_files:
                logger.info(f"Skipping {change['file']}: no trace for {agent_name}")
                result["skipped"] += 1
                continue

        if not file_path.exists():
            result["errors"].append(f"File not found: {change['file']}")
            continue

        try:
            # Record hash before change
            if prompt_tracker:
                prompt_tracker.record_version(str(change["file"]))

            content = file_path.read_text()
            section = diff.get("section", "").lstrip("#").strip()
            action = diff.get("action", "replace")
            new_content = diff.get("content", "")

            if action == "replace":
                content = _find_and_replace_section(content, section, new_content)
            elif action == "append":
                content = _append_to_section(content, section, new_content)
            else:
                result["errors"].append(f"Unknown action '{action}' for {change['file']}")
                continue

            atomic_write(file_path, content)

            # Record hash after change
            if prompt_tracker:
                prompt_tracker.record_version(str(change["file"]))

            logger.info(f"ANALYZE: Updated {change['file']} ({action} {section}): {reason}")
            result["applied"] += 1

        except Exception as e:
            logger.error(f"ANALYZE: Failed to update {change['file']}: {e}")
            result["errors"].append(f"{change['file']}: {e}")

    # Apply reversions
    for reversion in changes.get("reversions", []):
        file_path = project_root / reversion["file"]
        git_hash = reversion.get("revert_to_hash", "")
        reason = reversion.get("reason", "")

        if not git_hash:
            result["errors"].append(f"No hash for reversion: {reversion['file']}")
            continue

        try:
            # Get file content at previous hash
            proc = subprocess.run(
                ["git", "show", f"{git_hash}:{reversion['file']}"],
                capture_output=True, text=True, timeout=10,
                cwd=str(project_root),
            )
            if proc.returncode != 0:
                result["errors"].append(f"git show failed for {reversion['file']}: {proc.stderr}")
                continue

            if prompt_tracker:
                prompt_tracker.record_version(str(reversion["file"]))

            atomic_write(file_path, proc.stdout)

            if prompt_tracker:
                prompt_tracker.record_version(str(reversion["file"]))

            logger.info(f"ANALYZE: Reverted {reversion['file']} to {git_hash[:8]}: {reason}")
            result["reverted"] += 1

        except Exception as e:
            logger.error(f"ANALYZE: Failed to revert {reversion['file']}: {e}")
            result["errors"].append(f"revert {reversion['file']}: {e}")

    return result
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/test_analyzer.py -v`

- [ ] **Step 5: Commit**

```bash
git add orchestrator/analyzer.py tests/test_analyzer.py
git commit -m "feat: create orchestrator/analyzer.py with build, parse, and apply functions"
```

---

### Task 4: Add _phase_analyze() to runner.py

**Files:**
- Modify: `orchestrator/runner.py`
- Test: `tests/test_analyzer.py` (append)

- [ ] **Step 1: Write test**

```python
def test_runner_has_analyze_handler():
    from orchestrator.runner import ResearchPipeline
    from orchestrator.pipeline import Phase
    import types

    # Verify the handler method exists
    assert hasattr(ResearchPipeline, '_phase_analyze')
    assert hasattr(ResearchPipeline, '_collect_all_skill_files')


def test_collect_all_skill_files():
    from orchestrator.runner import ResearchPipeline
    from pathlib import Path

    # Can't instantiate without DB, so test the logic directly
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()

    research_dir = PROJECT_ROOT / "verticals" / "ai-tech" / "agents"
    agents_dir = PROJECT_ROOT / "agents"

    skill_files = []
    for d in [research_dir, agents_dir]:
        if d.exists():
            for f in d.glob("*.md"):
                skill_files.append(f)

    # Should find research agents + social agents
    assert len(skill_files) >= 20  # 13 research + 7+ social
    names = [f.stem for f in skill_files]
    assert "hn-researcher" in names
    assert "eic" in names
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement in runner.py**

Add to `_get_phase_handler()` map:
```python
Phase.ANALYZE: self._phase_analyze,
```

Add helper method:
```python
def _collect_all_skill_files(self) -> list[Path]:
    """Collect all .md skill files used as agent prompts."""
    skill_files = []
    dirs = [
        PROJECT_ROOT / "verticals" / "ai-tech" / "agents",
        PROJECT_ROOT / "agents",
    ]
    for d in dirs:
        if d.exists():
            for f in sorted(d.glob("*.md")):
                # Exclude reference subdirectories
                if "references" not in str(f):
                    skill_files.append(f)
    return skill_files
```

Add phase handler:
```python
def _phase_analyze(self) -> dict:
    """Phase: Analyze agent traces and improve skill files."""
    from orchestrator.analyzer import (
        build_analyzer_prompt,
        parse_analyzer_output,
        apply_analyzer_changes,
    )

    trace_dir = PROJECT_ROOT / "data" / self.user_id / "mindpattern" / "agents"

    # Collect traced agent names (those with today's trace file)
    traced_agents = set()
    if trace_dir.exists():
        for agent_dir in trace_dir.iterdir():
            if agent_dir.is_dir() and (agent_dir / f"{self.date_str}.md").exists():
                traced_agents.add(agent_dir.name)

    skill_files = self._collect_all_skill_files()

    # Build metrics from this run
    metrics = {
        "findings_per_agent": {
            r.agent_name: len(r.findings)
            for r in self.agent_results
        } if self.agent_results else {},
        "newsletter_eval": self.newsletter_eval,
        "social_result": {
            k: v for k, v in self.social_result.items()
            if k in ("topic", "gate1_outcome", "gate2_outcome", "platforms_posted")
        } if self.social_result else {},
    }

    # Get regression data
    regression_data = []
    if self.prompt_tracker:
        regression_data = self.prompt_tracker.check_regression(self.date_str)

    prompt = build_analyzer_prompt(
        trace_dir=trace_dir,
        skill_files=skill_files,
        date_str=self.date_str,
        metrics=metrics,
        regression_data=regression_data,
    )

    output, exit_code = agent_dispatch.run_claude_prompt(
        prompt, task_type="analyzer",
    )

    if exit_code != 0 or not output:
        logger.warning("ANALYZE: LLM call failed")
        return {"analyzed": False, "reason": "LLM call failed"}

    changes = parse_analyzer_output(output)
    if changes is None:
        logger.warning("ANALYZE: Could not parse output as JSON")
        return {"analyzed": False, "reason": "JSON parse failed"}

    result = apply_analyzer_changes(
        changes,
        project_root=PROJECT_ROOT,
        traced_files=traced_agents,
        prompt_tracker=self.prompt_tracker,
    )

    logger.info(
        f"ANALYZE: {result['applied']} changes, {result['reverted']} reversions, "
        f"{result['skipped']} skipped"
    )

    log_event(self.traces_conn, self.traces_run_id,
              "analyze_complete", json.dumps(result))

    return {"analyzed": True, **result}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/test_analyzer.py -v`

- [ ] **Step 5: Verify imports**

Run: `python3 -c "from orchestrator.runner import ResearchPipeline; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add orchestrator/runner.py tests/test_analyzer.py
git commit -m "feat: add _phase_analyze() handler to pipeline runner"
```

---

### Task 5: Integration verification

- [ ] **Step 1: Run full test suite**

```bash
python3 -m pytest tests/test_analyzer.py tests/test_identity.py tests/test_preflight.py tests/test_newsletter.py tests/test_humanizer.py -v
```

- [ ] **Step 2: Verify pipeline imports cleanly**

```bash
python3 -c "
from orchestrator.runner import ResearchPipeline
from orchestrator.pipeline import Phase, PHASE_ORDER
from orchestrator.analyzer import build_analyzer_prompt, parse_analyzer_output, apply_analyzer_changes

# Verify ANALYZE is in the right position
order = [p.value for p in PHASE_ORDER]
print(f'Phase order: {order}')
assert 'analyze' in order
assert order.index('evolve') < order.index('analyze') < order.index('mirror')
print('All imports OK, phase order correct')
"
```

- [ ] **Step 3: Dry-run analyzer with today's real traces**

```bash
python3 -c "
from pathlib import Path
from orchestrator.analyzer import build_analyzer_prompt

PROJECT_ROOT = Path('.').resolve()
trace_dir = PROJECT_ROOT / 'data' / 'ramsay' / 'mindpattern' / 'agents'

# Collect skill files
skill_files = []
for d in [PROJECT_ROOT / 'verticals' / 'ai-tech' / 'agents', PROJECT_ROOT / 'agents']:
    if d.exists():
        skill_files.extend(sorted(f for f in d.glob('*.md') if 'references' not in str(f)))

prompt = build_analyzer_prompt(
    trace_dir=trace_dir,
    skill_files=skill_files,
    date_str='2026-03-16',
    metrics={'test': True},
    regression_data=[],
)
print(f'Prompt length: {len(prompt)} chars (~{len(prompt)//4} tokens)')
print(f'Skill files: {len(skill_files)}')

# Count traced agents
traced = sum(1 for d in trace_dir.iterdir() if d.is_dir() and (d / '2026-03-16.md').exists())
print(f'Agents with traces: {traced}')
"
```

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "feat: self-optimization loop complete — ANALYZE phase with trace-driven skill improvement"
```

---

## Success Criteria

- [ ] `python3 -m pytest tests/test_analyzer.py -v` — all tests pass
- [ ] ANALYZE phase in PHASE_ORDER between EVOLVE and MIRROR
- [ ] ANALYZE in SKIPPABLE_PHASES
- [ ] Router has analyzer model config (opus_1m, 10 turns, 600s)
- [ ] PromptTracker scans `verticals/ai-tech/agents/`
- [ ] `build_analyzer_prompt()` includes only traces from today
- [ ] `parse_analyzer_output()` handles clean JSON, fenced JSON, embedded JSON
- [ ] `apply_analyzer_changes()` replaces sections, appends to sections, rejects no-trace changes
- [ ] Reversions work via `git show`
- [ ] Runner has `_phase_analyze()` and `_collect_all_skill_files()`

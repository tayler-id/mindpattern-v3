# Social Pipeline Agent Call Rework

## Problem

The v3 social pipeline stuffs everything into inline prompts instead of letting agents use their definition files and tools. This produces lower quality output than v2, which gave agents autonomy to read their own instructions, search memory, and write structured output.

## Approach

Add a new `run_agent_with_files()` helper alongside the existing `run_claude_prompt()`. Rework social modules to use it. The working newsletter pipeline is untouched.

This is a migration: all social agents currently return results via stdout parsing. After this rework, all social agents write structured output to files and Python reads them back. Research agents are unaffected.

## Prerequisites

### 0. `memory_cli.py` — lightweight CLI for agent memory access

The memory module (`memory/`) has no CLI — every file documents "No argparse, no print, no CLI." Agents need a CLI entry point to query memory via Bash.

Create `memory_cli.py` at project root. Thin wrapper, JSON to stdout:

```
python3 memory_cli.py search-findings --days 1 --min-importance 6
python3 memory_cli.py recent-posts --days 30
python3 memory_cli.py get-exemplars --platform x --limit 5
python3 memory_cli.py recent-corrections --days 30
python3 memory_cli.py check-duplicate --anchor "some topic anchor"
```

Output format: each command prints JSON to stdout. Most commands return arrays. `check-duplicate` returns an object (`{is_duplicate, duplicates, threshold, posts_checked}`).

Implementation notes:
- `search-findings` with `--days` and `--min-importance` does NOT map to an existing function. `memory.findings.search_findings()` is semantic search (query string). Date/importance filtering is raw SQL currently inlined in `social/eic.py:_get_recent_findings()`. The CLI must implement this filtering directly (SQL query against findings table with date and importance WHERE clauses).
- `recent-posts` wraps `memory.social.get_recent_posts()`
- `get-exemplars` wraps `memory.social.get_exemplars()`
- `recent-corrections` wraps `memory.corrections.recent_corrections()`
- `check-duplicate` wraps `memory.social.check_duplicate()`

Cold start: fastembed model loads on first semantic search call (~2-5s). Acceptable for agents with 5-10 minute timeouts. Date/importance filtering does not use embeddings.

### 0b. Agent definition file updates

Several agent `.md` files need updates to align with this design:

- **`agents/eic.md`**: Update output path from `data/social-brief-options.json` to `data/social-drafts/eic-topic.json`. Simplify output schema to match the spec (see Output Schemas below). Current schema has extra fields like `rank`, `anchor_source`, `connection`, `open_questions` — simplify to the essential fields the pipeline actually uses.
- **`agents/x-critic.md`**, **`agents/linkedin-critic.md`**, **`agents/bluesky-critic.md`**: Remove references to receiving the curator brief. Current text says critics receive "The curator brief (to check do_not_include and confidence)" — this contradicts the blind design. The code already implements blindness correctly; the `.md` files are stale.
- **All writer `.md` files**: Update output paths to `data/social-drafts/{platform}-draft.md` if they differ.

## Design

### 1. `run_agent_with_files()` helper

Location: `orchestrator/agents.py`

```python
def run_agent_with_files(
    system_prompt_file: str,   # e.g. "agents/eic.md"
    prompt: str,               # context + instructions
    output_file: str,          # where agent writes output
    allowed_tools: list[str] = ["Read", "Write", "Bash", "Glob", "Grep"],
    task_type: str = "eic",    # for router lookup (model, turns, timeout)
) -> dict | None:
```

Behavior:
- Ensures `data/social-drafts/` directory exists (`mkdir -p`)
- Deletes `output_file` if it exists (prevent stale data)
- Builds `claude -p` command with `--append-system-prompt-file`, model/turns/timeout from router, all specified tools
- Runs subprocess with timeout from router, cwd=PROJECT_ROOT
- After agent exits, reads `output_file`, parses JSON, returns dict or None
- If output_file is `.md`, reads as text and returns `{"text": content}` instead of JSON parsing
- Captures agent stdout/stderr to `data/social-drafts/{task_type}-debug.log` for diagnosing failures

Agent definition files are loaded via `--append-system-prompt-file` (injected into system prompt before the agent starts). Agents do NOT need to `Read` their own definition file — it's already in their context.

For agents that need a second file (e.g. writers need voice-guide.md), the voice guide content is inlined into the prompt by Python before invocation. This matches the current pattern in `writers.py` (line 115-116).

### 2. `social/eic.py` rework

**`select_topic()`**:
- `--append-system-prompt-file agents/eic.md`
- Prompt tells agent to use `python3 memory_cli.py search-findings --days 1` for today's findings
- Prompt tells agent to use `python3 memory_cli.py recent-posts --days 30` for dedup
- Prompt tells agent to use `python3 memory_cli.py search-findings --days 7 --min-importance 7` for high-importance backlog
- Agent scores topics per its rubric (Novelty 0.35, Broad Appeal 0.40, Thread Potential 0.25)
- Agent writes to `data/social-drafts/eic-topic.json`
- Python reads file, validates against schema (see Output Schemas below)
- **Retry loop preserved**: if Python detects duplicate (via `memory.social.check_duplicate()`) or score below threshold, it rebuilds prompt with rejected anchor appended to a "do not select" list, re-invokes agent (up to 3 attempts)

**`create_brief()`**:
- `--append-system-prompt-file agents/creative-director.md`
- Voice guide content inlined in prompt
- Selected topic passed in prompt (small JSON payload)
- Agent can query memory for exemplars via `python3 memory_cli.py get-exemplars`
- Agent writes to `data/social-drafts/creative-brief.json`
- Python reads, validates against schema, returns

### 3. `social/writers.py` rework

**`_write_single_platform()`**:
- `--append-system-prompt-file agents/{platform}-writer.md`
- Voice guide content inlined in prompt
- Agent queries memory for voice exemplars: `python3 memory_cli.py get-exemplars --platform {platform}`
- Agent queries memory for editorial corrections: `python3 memory_cli.py recent-corrections --days 30`
- Brief content passed in prompt (small JSON payload)
- On iteration > 1, critic feedback passed in prompt
- Agent writes draft to `data/social-drafts/{platform}-draft.md`
- Python reads draft text back
- Humanizer pass stays in Python — consolidate to a single canonical `_humanize()` in `writers.py`. The current `pipeline.py` version includes editorial corrections from memory; the `writers.py` version does not. The merged version must include corrections (port from `pipeline.py`'s `_build_humanize_prompt`).
- PolicyEngine deterministic validation stays in Python

**Parallel safety invariant**: Writers run in parallel via `ThreadPoolExecutor`, one per platform. Output files are `{platform}-draft.md` — distinct per platform. The revision loop in `pipeline.py` is sequential (waits for all writers to finish before re-invoking failed ones), so no two invocations for the same platform overlap.

### 4. `social/critics.py` rework

**`review_draft()`**:
- **BLIND**: prompt includes only draft text and platform name. Never the brief, never memory context.
- `--append-system-prompt-file agents/{platform}-critic.md`
- Voice guide content inlined in prompt
- Agent writes verdict to `data/social-drafts/{platform}-verdict.json`
- Python reads, validates against schema, returns

**`expedite()`**:
- `--append-system-prompt-file agents/expeditor.md`
- All platform drafts and images passed in prompt (cross-platform coherence needs full view)
- Agent writes verdict to `data/social-drafts/expedite-verdict.json`
- Python reads, validates, returns

### 5. `social/pipeline.py` changes

- Gate 1 iMessage: include full topic details (anchor, angle, composite_score, sources, reasoning) not just title
- Gate 2 iMessage: show actual draft text per platform before posting
- Remove duplicate `_build_humanize_prompt` — call `writers._humanize()` instead (after porting corrections logic)

### 6. iMessage fix

Replace v3's `targetService`/`targetBuddy` AppleScript in `approval.py` (line ~345) with v2's proven pattern:

```applescript
tell application "Messages" to send "{msg}" to buddy "+1XXXXXXXXXX"
```

The complex version returned exit 0 but messages never arrived. The simple version worked in v2.

Preserve the existing escaping logic in `_imessage_send()` — social media drafts can contain double quotes and backslashes that would break unescaped AppleScript.

Verify phone number format is +1XXXXXXXXXX (10 digits after country code).

## Output schemas

### `eic-topic.json`
```json
{
  "anchor": "string — one-line topic anchor",
  "angle": "string — editorial angle",
  "composite_score": 0.0,
  "scores": {
    "novelty": 0.0,
    "broad_appeal": 0.0,
    "thread_potential": 0.0
  },
  "sources": ["url1", "url2"],
  "reasoning": "string — why this topic"
}
```

Note: this is simplified from the current `eic.md` output (which includes `rank`, `anchor_source`, `connection`, `open_questions`, etc.). The `eic.md` agent definition must be updated to match this schema.

### `creative-brief.json`
```json
{
  "editorial_angle": "string",
  "key_message": "string",
  "emotional_register": "string",
  "tone": "string",
  "source_attribution": "string",
  "visual_metaphor_direction": "string",
  "platform_hooks": {
    "x": "string — 280 char hook",
    "linkedin": "string — 1200-1500 char angle",
    "bluesky": "string — 300 char angle"
  },
  "do_not_include": ["string"],
  "mindpattern_link": "string — URL"
}
```

### `{platform}-draft.md`
Plain text. The draft content only — no JSON wrapper, no metadata. Python reads as string.

### `{platform}-verdict.json`
```json
{
  "verdict": "APPROVED | REVISE",
  "feedback": "string — specific actionable feedback",
  "scores": {
    "voice_authenticity": 0,
    "platform_fit": 0,
    "engagement_potential": 0
  }
}
```

### `expedite-verdict.json`
```json
{
  "verdict": "PASS | FAIL",
  "feedback": "string",
  "platform_verdicts": {
    "x": "PASS | FAIL",
    "linkedin": "PASS | FAIL",
    "bluesky": "PASS | FAIL"
  },
  "scores": {
    "voice_match": 0,
    "framing_authenticity": 0,
    "platform_genre_fit": 0,
    "epistemic_calibration": 0,
    "structural_variation": 0,
    "rhetorical_framework": 0
  }
}
```

Note: expeditor uses `PASS | FAIL` (matching current code), not `APPROVED`. `platform_verdicts` is new — allows per-platform granularity so one failing platform doesn't block the others.

## Router changes

Bump writer `max_turns` from 10 to 15. Writers now spend 2-3 turns on tool calls (memory_cli queries for exemplars and corrections) before writing. Without the bump, effective writing turns drop to 7-8.

All other router config stays unchanged.

## What stays unchanged

- Pipeline state machine orchestration (pipeline.py flow, phase sequence)
- PolicyEngine deterministic validation
- Research pipeline (newsletter works end-to-end, do not touch)
- Memory modules (no changes to memory/*.py)
- 223 existing tests
- `run_claude_prompt()` (research agents keep using it)

## File-based I/O contract

All agent output files go to `data/social-drafts/`. The helper deletes the output file before each invocation. If the file does not exist after the agent exits, the call failed. Python always validates the schema before using the output.

Agent stdout/stderr is captured to `data/social-drafts/{task_type}-debug.log` for debugging failed runs.

## Tool access per agent

| Agent | Tools | System prompt file | Why |
|-------|-------|--------------------|-----|
| EIC | Read, Write, Bash, Glob, Grep | agents/eic.md | Needs memory_cli.py for dedup and findings |
| Creative Director | Read, Write, Bash, Glob, Grep | agents/creative-director.md | Needs memory_cli.py for exemplars and past briefs |
| Writers | Read, Write, Bash, Glob, Grep | agents/{platform}-writer.md | Needs memory_cli.py for voice exemplars and editorial corrections |
| Critics | Read, Write, Glob, Grep | agents/{platform}-critic.md | Blind review. No Bash — cannot query memory. |
| Expeditor | Read, Write, Glob, Grep | agents/expeditor.md | Cross-platform review, no memory needed |

Critics get no Bash. They must stay blind to everything except draft text, their critic instructions, and voice guide. Giving them Bash would let them query memory and break blindness.

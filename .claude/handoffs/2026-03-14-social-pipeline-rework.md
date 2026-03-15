# Handoff: Social Pipeline Agent Call Rework

## Created: 2026-03-14
## Project: /Users/taylerramsay/Projects/mindpattern-v3

## Problem

The v3 social pipeline's agent calls are shallow. They stuff everything into inline prompts instead of letting the LLM use its agent definition files and tools. This produces lower quality output than v2.

## What Works (Keep)

- Python orchestrator (`orchestrator/runner.py`) — state machine, checkpoint/resume
- Memory module (`memory/`) — 13 modules, 1,341 historical findings, no subprocess
- Policy engine (`policies/engine.py`) — deterministic validation
- Model routing (`orchestrator/router.py`) — Haiku/Sonnet/Opus per task
- Dedup against 30 days of findings in research phase
- 1M context for synthesis
- Newsletter pipeline (INIT → TREND → RESEARCH → SYNTHESIS → DELIVER → LEARN) — working end-to-end, emails sent
- 223 unit tests passing

## What's Broken (Fix)

### Agent calls use inline prompts instead of agent files + tools

**v2 approach (correct):**
```bash
claude -p "Read your skill file: agents/eic.md
Use memory.py search to find interesting findings.
Write output to data/social-brief-options.json" \
  --model opus --max-turns 15 \
  --allowedTools "Bash,WebSearch,Read,Write,Glob,Grep"
```

**v3 approach (broken):**
```python
prompt = f"Pick the best topic from these {len(findings)} findings...\n{findings_text}"
output, code = run_claude_prompt(prompt, "eic", allowed_tools=[])
```

v2 lets the agent READ its own instructions, SEARCH the database, and WRITE structured output.
v3 strips the tools, dumps everything inline, and loses all nuance.

### Files to rework

1. **`social/eic.py`** — `select_topic()` and `create_brief()`
   - Tell claude to read `agents/eic.md` via `--append-system-prompt-file`
   - Give it Bash tool to run `python3 -c "import memory; ..."` for search
   - Give it Read/Write tools
   - Have it write output to `data/social-drafts/eic-brief-options.json`
   - Python reads that file after claude exits

2. **`social/writers.py`** — `_write_single_platform()`
   - Tell claude to read `agents/{platform}-writer.md` and `agents/voice-guide.md`
   - Give it Read/Write tools
   - Have it write draft to `data/social-drafts/{platform}-draft.md`
   - Include brief content and exemplars in the prompt
   - Include critic feedback on iteration > 1

3. **`social/critics.py`** — `review_draft()`
   - Tell claude to read `agents/{platform}-critic.md` and `agents/voice-guide.md`
   - Give it Read/Write tools
   - Have it read the draft from file and write verdict to file
   - BLIND: do NOT include the brief — critic sees only draft + voice guide

4. **`social/pipeline.py`** — orchestration
   - Gate 1 iMessage: include full topic details (anchor, angle, score, sources)
   - Policy retry: send violations back to writer (DONE — already fixed)
   - Gate 2: show draft text per platform before posting

### Key pattern for agent calls

```python
def run_agent_with_files(
    system_prompt_file: str,  # e.g., "agents/eic.md"
    prompt: str,              # context + instructions
    output_file: str,         # where agent writes output
    allowed_tools: list[str] = ["Read", "Write", "Bash", "Glob", "Grep"],
    task_type: str = "eic",
) -> dict | None:
    """Run claude -p with agent file, tools, and file-based output."""
    cmd = [
        "claude", "-p", prompt,
        "--model", router.get_model(task_type),
        "--max-turns", str(router.get_max_turns(task_type)),
        "--output-format", "text",
        "--append-system-prompt-file", system_prompt_file,
    ]
    for tool in allowed_tools:
        cmd.extend(["--allowedTools", tool])

    subprocess.run(cmd, capture_output=True, timeout=router.get_timeout(task_type))

    # Read output from the file the agent wrote
    if Path(output_file).exists():
        return json.loads(Path(output_file).read_text())
    return None
```

### iMessage issues

The approval module sends iMessages but the user didn't receive them. The v2 social-post.py uses a simpler AppleScript:
```
tell application "Messages" to send "msg" to buddy "+phone"
```

The v3 approval module uses a more complex version with `targetService` and `targetBuddy`. Both returned exit 0 but the user didn't get them. Needs debugging — possibly a Messages.app permissions issue or the phone number format.

## Integration bugs already fixed this session

- INIT phase transition (init → init)
- Synthesis timeouts (120s → 900s)
- Synthesis max_turns (10 → 30)
- 1M context for synthesis + EIC (`claude-opus-4-6[1m]`)
- Newsletter word count (2,294 → 5,020 by increasing turns + prompt)
- Feedback footer on newsletter
- Finding dedup against 30 days
- Full historical DB loaded (1,341 findings from v1)
- Trend scan inline prompt (not template with unfilled placeholders)
- Synthesis inline prompts (not templates with unfilled placeholders)
- create_brief() signature mismatch
- write_drafts() signature mismatch
- create_art() signature mismatch
- expedite() signature mismatch
- deterministic_validate() signature mismatch
- review_draft() signature mismatch
- SQLite thread safety in writers (open fresh connection per thread)
- Policy retry loop (send violations back to writer)
- Gate 1 wired into pipeline
- Agent timeout increased to 20 min
- EIC timeout increased to 10 min
- EIC prompt simplified (67K → 4K)

## What a successful run looks like

The last full newsletter run completed:
- INIT: 5 preferences, 1 failure lesson
- TREND SCAN: 8 topics
- RESEARCH: 10/13 agents, 78 findings stored (29 deduped)
- SYNTHESIS: 5,020 words (Opus 1M)
- DELIVER: Email sent (Resend ID: f20ffdca...)
- LEARN: Quality 0.562
- SOCIAL: EIC picks topic, Gate 1 approval, brief, writers produce drafts — but drafts fail policy
- ENGAGEMENT: Not tested

## Router config (current)

```python
TIMEOUTS = {
    "research_agent": 1200,   # 20 min
    "synthesis_pass1": 600,   # 10 min
    "synthesis_pass2": 900,   # 15 min
    "eic": 600,               # 10 min
    "writer": 300,            # 5 min
    "critic": 120,            # 2 min
}

MAX_TURNS = {
    "research_agent": 15,
    "synthesis_pass1": 10,
    "synthesis_pass2": 30,
    "eic": 15,
    "writer": 10,
    "critic": 5,
}
```

## Files in project

67 Python files, ~22K lines total. See project root for full structure.
Key directories: memory/, orchestrator/, social/, policies/, prompts/, agents/, verticals/

## Next steps (priority order)

1. Add `run_agent_with_files()` helper to `orchestrator/agents.py`
2. Rework `social/eic.py` to use agent file + tools
3. Rework `social/writers.py` to use agent file + tools
4. Rework `social/critics.py` to use agent file + tools (blind)
5. Debug iMessage delivery
6. Test full social pipeline end-to-end
7. Wire social + engagement into daily launchd plist

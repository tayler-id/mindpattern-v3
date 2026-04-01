# Self-Optimization Loop — Trace-Driven Skill Improvement

## Summary

Add an ANALYZE phase to the pipeline that reads every agent's trace log, compares what the agent DID vs what its skill file SAID to do, identifies deviations, and fixes the skill files. Every pipeline run improves the skills for the next run. Kaizen for agents.

## Problem

Agent skill files are static. When an agent ignores instructions (uses WebSearch instead of Exa, skips Phase 2, produces shallow findings), nobody fixes the skill file. The same mistakes repeat every run. The Self-Improvement Notes in some agent files were manually written once and never updated.

EVOLVE updates identity files (soul.md, user.md, voice.md, decisions.md) but never touches agent skill files. There's no feedback loop between execution traces and skill instructions.

## Design

### Architecture

```
... → EVOLVE → ANALYZE → MIRROR → SYNC → COMPLETED
```

One Opus agent with 1M context receives all trace logs + all skill files + pipeline metrics + regression data. It compares intended workflow vs actual execution, identifies deviations, and outputs a JSON diff of skill file changes. Changes are applied via atomic writes. PromptTracker records file hashes for regression detection.

### Analyzer Input

The analyzer prompt contains:

1. **Agent trace logs from today** — markdown files at `data/ramsay/mindpattern/agents/{name}/{date}.md`. Only agents that ran today and have a trace file are included. Based on today's run: ~8,400 total lines across all agents, ~34K tokens. The analyzer MUST NOT propose changes for agents with no trace from today's run.

2. **All agent skill files** — research agents from `verticals/ai-tech/agents/*.md` (13 files), social agents from `agents/*.md` (eic, writers, critics, expeditor, humanizer, synthesis-selector, synthesis-writer, trend-scanner, learnings-updater, engagement-finder, engagement-writer). Excludes `agents/references/` (reference material, not skills).

3. **Pipeline metrics** — findings count per agent, newsletter quality scores (coverage, dedup, sources, overall), social pipeline outcomes (topic, gate verdicts, platforms posted), engagement results.

4. **Regression data** — structured output from `PromptTracker.check_regression()`, which returns `list[dict]` with `file`, `old_hash`, `new_hash`, `quality_before`, `quality_after`, `regression_pct` for each regressed file. Formatted in the prompt as a markdown table so the analyzer sees exactly which previous ANALYZE edits caused quality drops.

### Deviation Categories

The analyzer compares skill instructions vs trace behavior across:

**Tool usage deviations:**
- Skill says "use Exa first" but trace shows WebSearch calls before any Exa call
- Skill says "use Jina Reader for deep reads" but agent never called curl
- Agent used tools not mentioned in skill, or ignored tools that were

**Phase compliance:**
- Did the agent evaluate Phase 1 preflight items before exploring in Phase 2?
- Did it produce the target 10-15 findings (8-12 Phase 1 + 2-5 Phase 2)?
- Did it skip Phase 2 entirely?

**Quality signals from trace:**
- How many reasoning steps before producing output? (too few = shallow analysis)
- Did the agent read sources via Jina/WebFetch or just use search snippets?
- Did findings include source_urls the agent actually visited?

**Output compliance:**
- Did the agent output valid JSON on first try or did it need multiple attempts?
- Did findings match the skill's focus areas or drift off-topic?
- Were banned words from voice.md present in social agent outputs?

**Cross-agent patterns:**
- Multiple agents making the same mistake = systemic prompt issue
- One agent consistently outperforming = its skill has something others should copy

**Regression detection:**
- If a previous ANALYZE edit correlates with a quality drop (via PromptTracker), the analyzer sees this and can revert or fix

### Analyzer Output

JSON diff — one entry per skill file to modify:

```json
{
  "changes": [
    {
      "file": "verticals/ai-tech/agents/hn-researcher.md",
      "reason": "Agent used WebSearch 4 times before trying Exa. Skill says Exa first.",
      "diff": {
        "section": "Phase 2 Exploration Preferences",
        "action": "replace",
        "content": "- Primary: Exa search (MANDATORY — use before WebSearch)\n..."
      }
    }
  ],
  "reversions": [
    {
      "file": "verticals/ai-tech/agents/rss-researcher.md",
      "reason": "Previous ANALYZE changed query strategy, quality dropped 15%.",
      "revert_to_hash": "a1b2c3d4"
    }
  ],
  "no_changes": [
    "verticals/ai-tech/agents/arxiv-researcher.md",
    "verticals/ai-tech/agents/news-researcher.md"
  ]
}
```

All file references use full relative paths from project root (e.g., `verticals/ai-tech/agents/hn-researcher.md`, `agents/eic.md`). Both `changes` and `no_changes` use this format consistently.

Supported actions: `replace` (replace a `## Section` entirely), `append` (add content to the end of a section).

### Applying Changes

`apply_analyzer_changes()` reads the full skill file, finds the target `## Section` heading, applies the replace or append operation, and writes the complete file back via `vault.atomic_write()` (write to .tmp, rename). This bypasses `vault.update_section()` which has a 500-character limit designed for identity files — skill file sections can be any length.

For reversions: `apply_analyzer_changes()` uses `git show {hash}:{file}` to retrieve the previous version and writes it via atomic write.

PromptTracker records file hashes before and after all changes so the next run can detect regressions.

The analyzer has full edit access to any part of any skill file. No sections are frozen. The guardrail is the loop itself — if a change makes things worse, the next trace shows it, and the next analysis reverts or fixes it. PromptTracker provides the regression signal.

### Scope: All Agents

Every agent that makes an LLM call, has a skill file, and has a trace log from today gets analyzed:

| Agent Type | Skill Files | Trace Location |
|---|---|---|
| Research (13x) | `verticals/ai-tech/agents/*.md` | `agents/{name}/{date}.md` |
| EIC | `agents/eic.md` | `agents/eic/{date}.md` |
| Creative Director | `agents/creative-director.md` | `agents/creative_brief/{date}.md` |
| Writers (2x) | `agents/{platform}-writer.md` | `agents/writer/{date}.md` |
| Critics (2x) | `agents/{platform}-critic.md` | `agents/critic/{date}.md` |
| Expeditor | `agents/expeditor.md` | `agents/expeditor/{date}.md` |
| Humanizer | `agents/humanizer.md` | `agents/humanizer/{date}.md` |
| Synthesis selector | `agents/synthesis-selector.md` | `agents/synthesis_pass1/{date}.md` |
| Synthesis writer | `agents/synthesis-writer.md` | `agents/synthesis_pass2/{date}.md` |
| Trend scanner | `agents/trend-scanner.md` | `agents/trend_scan/{date}.md` |
| Learnings updater | `agents/learnings-updater.md` | `agents/learnings_update/{date}.md` |
| Engagement finder | `agents/engagement-finder.md` | `agents/engagement_finder/{date}.md` |
| Engagement writer | `agents/engagement-writer.md` | `agents/engagement_writer/{date}.md` |

**Rule:** The analyzer MUST NOT propose changes for agents with no trace file from today's run. No trace = no behavioral evidence = no changes.

### Implementation

**New file: `orchestrator/analyzer.py`**

Three functions:

- `build_analyzer_prompt(trace_dir, skill_files, metrics, regression_data)` — assembles the Opus prompt. Only includes trace logs for agents that have a `{date}.md` file in their trace directory. Formats regression_data as a markdown table.
- `parse_analyzer_output(output)` — extracts JSON diff from LLM response (same pattern as `identity_evolve.parse_llm_output()`)
- `apply_analyzer_changes(changes, project_root)` — for each change: reads full file, finds `## Section`, applies replace/append, writes via `vault.atomic_write()`. For reversions: uses `git show` to retrieve previous version. Records all hashes in PromptTracker before and after.

**Modified: `orchestrator/runner.py`**

New phase handler `_phase_analyze()`:
- Collects all trace logs (only files matching today's date)
- Collects all skill files via `_collect_all_skill_files()`
- Builds analyzer prompt with metrics and regression data
- Calls `run_claude_prompt()` with task_type `analyzer`
- Parses and applies changes
- Returns change summary

Helper method `_collect_all_skill_files()` returns paths to all .md files used as agent prompts from both `verticals/ai-tech/agents/` and `agents/` (excluding `agents/references/`).

**Modified: `orchestrator/pipeline.py`**

- Add `ANALYZE = "analyze"` to Phase enum (EVAL already exists)
- Update PHASE_ORDER: `... → EVOLVE → ANALYZE → MIRROR → SYNC`
- Add ANALYZE to SKIPPABLE_PHASES (pipeline continues if analysis fails)

**Modified: `orchestrator/router.py`**

Add analyzer routing:
```python
"analyzer": "opus_1m"  # Needs 1M context for all traces + skills
```
Max turns: 10, timeout: 600s.

**Modified: `orchestrator/prompt_tracker.py`**

- Extend `PROMPT_DIRS` to include `verticals/ai-tech/agents/` so research agent skill file changes are tracked for regression detection.

### What This Replaces

| Before | After |
|---|---|
| Self-Improvement Notes manually written | Automatically updated from trace data |
| EVOLVE only touches identity files | ANALYZE updates agent skill files |
| Same mistakes repeat every run | Mistakes identified and fixed for next run |
| No cross-agent pattern detection | Analyzer sees all traces, identifies systemic issues |
| No regression detection for skill changes | PromptTracker flags quality drops from skill edits |

### Success Criteria

- [ ] ANALYZE phase runs after EVOLVE without errors
- [ ] Analyzer reads trace logs only for agents that ran today
- [ ] Analyzer reads all skill files
- [ ] Analyzer produces valid JSON diff output
- [ ] Changes applied atomically to skill files (bypassing 500-char vault limit)
- [ ] Reversions restore previous file versions via git
- [ ] PromptTracker records hashes before/after (including verticals/ai-tech/agents/)
- [ ] If a skill edit causes quality regression, next run's analyzer sees structured regression data
- [ ] Analyzer never proposes changes for agents with no trace from today
- [ ] After 5 runs, measurable improvement in agent consistency (fewer deviations per run)

### Risks

1. **Prompt size** — all traces + all skills could be 80-120K tokens. Mitigate: Opus has 1M context, this is ~10% capacity.
2. **Analyzer hallucination** — analyzer proposes changes for problems that don't exist. Mitigate: regression detection reverts bad changes on next run.
3. **Oscillation** — analyzer changes a skill, next run's analyzer changes it back. Mitigate: regression_data in prompt shows recent changes so analyzer avoids flip-flopping.
4. **Skill drift** — after many iterations, skills diverge from original intent. Mitigate: git history preserves every version; `git diff` shows cumulative drift over time.
5. **No-trace edits** — analyzer might try to edit skills for agents that didn't run (e.g., engagement was skipped). Mitigate: explicit rule in prompt and validation in `apply_analyzer_changes()` — reject changes for files with no corresponding trace.

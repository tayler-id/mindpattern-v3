# Handoff: Skills/plugin cleanup, harness diagnosis, agentic-system research, plan for system redesign

## Session Metadata
- Created: 2026-05-07 11:40:34
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: main
- Worktree: **none — work was done in the main repo at `/Users/taylerramsay/Projects/mindpattern-v3`** (no worktree to cd into on resume)
- Session duration: ~3 hours, long-running

### Recent Commits (for context)
  - 563cd67 Merge remote-tracking branch 'origin/main'
  - b202400 Merge pull request #23 from tayler-id/feat/smart-trend-scan
  - 94db06a feat: add trend_history learning loop — track which trends produce findings
  - 6d2736b feat: replace Haiku trend scanner with deterministic trend detection
  - bc5b4f9 fix: harden codebase — 6 bugs fixed, 16 tests added, 824 green

## Handoff Chain

- **Continues from**: [2026-04-02-134500-pipeline-reliability-harness-hardening.md](./2026-04-02-134500-pipeline-reliability-harness-hardening.md)
  - Previous title: Pipeline Reliability + Harness Hardening
- **Supersedes**: None

> Read the previous handoff if you need pre-Apr-2 context. The harness has been **dormant since 2026-04-02** — that handoff captures its last active state.

## Current State Summary

This session was a **cleanup-and-direction-setting day**, not implementation. We pruned a sprawling Claude Code skills/plugins setup down to a lean 5-plugin / 21-skill stack, deleted dead artifacts (the `mindpattern-eval` skill, 5 git worktrees, 7 stale skill overrides), diagnosed why the autonomous harness has been silent since April 2, and ran 8 parallel research agents (250+ unique sources) on best practices for building agentic pipelines. The session ended with a clear architectural plan: **Phase adapters first** (turn each of the 12 orchestrator phases into a stateless reducer), then 2-week error-analysis exercise, then Inspect AI for evals, then close the harness feedback loop. Nothing was implemented; everything is research + decisions + cleanup.

## Codebase Understanding

### Architecture Overview

The user's MindPattern v3 pipeline is on-trend with the 2025-2026 industry consensus ("workflows before agents, deterministic Python before LLM, error analysis before evals"), but has two structural failures matching documented anti-patterns:

1. **`mindpattern-eval` skill** (now deleted) — was Hamel Husain's "eval-driven development before error analysis" anti-pattern: built scaffolding for evals before any failure data existed, never invoked.
2. **`harness/feedback.json: []`** — classic "self-improving loop with no consumer" failure: the architecture says scout reads feedback to learn between runs, but no phase actually writes to feedback.json. The loop is dead by design.

The orchestrator (`orchestrator/runner.py`) is sound but mixes phase logic with control flow. The next architecture move is to make each phase a pure `(state, input) → new_state` reducer — this is a precondition for replay, eval, and a working feedback loop.

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `.claude/settings.local.json` | Skill overrides + enabled plugins (just edited) | Resume agent must read this to understand current skill state |
| `harness/CLAUDE.md` | Harness architecture spec (scout/plan/fix/review) | Source of truth for the dormant self-improving loop |
| `harness/prompts/scout.md` | The 75-line scout agent prompt | Diagnosed: violates its own "tests last" rule, has hardcoded SQL against possibly-drifted traces.db schemas |
| `harness/feedback.json` | The empty `[]` learning signal | The single highest-leverage thing to fix |
| `harness/run.sh` | Bash entry point for the harness | Calls scout via `claude -p`, has been dormant since Apr 2 |
| `harness/tickets/*.json` | 34 tickets: 15 open · 12 failed · 4 stuck · 3 done | Backlog needs triage before harness can resume |
| `orchestrator/runner.py` | 12-phase orchestrator | Target of the Phase-adapter refactor |
| `orchestrator/agents.py` | `dispatch_research_agents()` etc. | Uses `asyncio.gather` — should migrate to `TaskGroup` + `aiolimiter` |
| `agents/*.md` and `verticals/ai-tech/agents/*.md` | 13 research agent prompts | Future targets for DSPy+GEPA optimization once eval metric exists |
| `data/ramsay/traces.db` | 14-table observability store | Don't migrate yet — under threshold. Add OTel emit alongside |
| `data/ramsay/memory.db` | 17-table SQLite for user data | Subject of the Vault-interface refactor (deferred behind Phase adapters) |

### Key Patterns Discovered

- **Anthropic's Skills system**: only `name` + `description` from frontmatter loads at startup; full SKILL.md body is lazy. Budget is 1% of context with 8K-char fallback. `SLASH_COMMAND_TOOL_CHAR_BUDGET` env var is the official knob (third-party guides cite `skillListingBudgetFraction` JSON key but **that's not in official Anthropic docs**).
- **Plugin lifecycle**: install once, then disable/enable. **You don't delete and reinstall.** Use `/skills` for individual overrides, `/plugin disable` for plugin bundles.
- **Plugin scope**: user-scope plugins must explicitly be enabled per-project via `enabledPlugins` in settings — installing at user scope doesn't auto-enable in projects.
- **Subprocess-to-CLI agent pattern** (the user's architecture): only **Inspect AI** (UK AISI eval framework) treats this as a first-class agent via its `sandbox_agent_bridge()`. All other frameworks assume you call the LLM via their SDK.

## Work Completed

### Tasks Finished

- [x] Diagnosed the "Skill listing will be truncated" warning; confirmed source = sprawling plugin install (8 marketplaces, ~60 skills)
- [x] Read canonical Anthropic skills docs directly (after pushback that earlier agents leaned on third-party blogs)
- [x] Disabled 4 plugins (`agent-skills@addy`, `playground`, `typescript-lsp`, `pyright-lsp`) → reduced to 2 active
- [x] Set 9 skills to "off" via `/skills` (mindpattern-eval, graphify, code-simplify, review, test, plan, spec, build, ship)
- [x] Investigated `mindpattern-eval` — confirmed dead since Mar 19, never wired to pipeline → deleted
- [x] Audited 5 git worktrees, found 1 with significant abandoned GIF pipeline work + 1 with small unsaved spec
- [x] Removed all 5 worktrees (forced for dirty ones; reflog retains commits ~30 days)
- [x] Diagnosed harness dormancy: last run 2026-04-02, `feedback.json` never populated, scout violated own "tests last" rule on day 1, traces.db queries in scout.md may be schema-drifted
- [x] Spawned 8 parallel research agents on agentic pipeline best practices, all hit 30+ source bar (~250 sources total)
- [x] Synthesized research: identified the 4 cross-stream consensus rules and matched user's failures to documented anti-patterns
- [x] Re-enabled 3 high-leverage plugins: `pyright-lsp`, `superpowers`, `agent-sdk-dev`
- [x] Final state: 5 plugins · 21 skills · 11 agents · 4 hooks · 1 LSP server

### Files Modified

| File | Changes | Rationale |
|------|---------|-----------|
| `.claude/skills/mindpattern-eval/SKILL.md` | **Deleted (staged via `git rm`, NOT yet committed)** | Skill was created Mar 19, never wired to pipeline, untouched 7 weeks |
| `.claude/skills/mindpattern-eval/references/metrics.md` | **Deleted (staged via `git rm`, NOT yet committed)** | Same — part of dead skill |
| `.claude/settings.local.json` | Removed `mindpattern-eval` override (1 line); added `enabledPlugins` block | Skill no longer exists; plugin-enable state was set via `/plugin enable` and `/plugin install` commands |
| `~/.claude/settings.json` | `enabledPlugins` updated by `/plugin disable` and `/plugin install` commands | User-driven plugin state changes |
| 5 git worktrees: `agile-watching-gosling`, `launch-video`, `snug-chasing-salamander`, `scalable-swinging-pascal`, `luminous-popping-pearl` | **Removed entirely** (dir + git registration) | Cleanup — 1 had merged work, 1 was clean-but-old, 1 had small spec, 1 had abandoned GIF pipeline (60 files + 2 commits — user confirmed code-first GIF approach was rejected per memory note), 1 was clean |

**No production code (`orchestrator/`, `harness/`, `social/`, `slack_bot/`, etc.) was modified this session.** All other modifications visible in `git status` are pre-existing from earlier work.

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Delete `mindpattern-eval` skill | (a) delete, (b) leave off, (c) wire it in for real | Dead 7 weeks, never invoked, instance of "scaffold and abandon" pattern |
| Remove all 5 worktrees including dirty ones | (a) remove clean only, (b) commit dirty first, (c) remove all | User confirmed GIF pipeline work matched the rejected "code-first" approach (per memory `feedback_gif_pipeline_approach.md`); reflog retains commits |
| Phase adapters refactor before Vault interface | (a) Vault first (prior recommendation), (b) Phase adapters first | Research said stateless-reducer pattern is the foundation for replay, eval, and feedback-loop closure |
| Keep `traces.db` as primary, add OTel emit alongside | (a) migrate to Langfuse self-host, (b) keep as is, (c) add OTel emit alongside | Below the 50k traces/month threshold; the 14-table schema isn't wrong, just expensive to maintain a viewer |
| Don't migrate from launchd | (a) migrate to Hatchet/Temporal, (b) stay | Single host, single daily run, missed days recoverable manually — no trigger met |
| Re-enable 3 plugins (not 5 as research suggested) | (a) all 5, (b) 3, (c) 0 | Just escaped plugin sprawl; user has Karpathy guidelines + this synthesis already covering most context-engineering ground |
| **Defer DSPy+GEPA until after Inspect AI** | (a) start with DSPy, (b) Inspect first | GEPA needs an eval metric to optimize against — Inspect AI must come first |
| Skip mattpocock/skills | install via `npx` vs not | Overlap with superpowers + Karpathy guidelines |
| Skip trailofbits/skills, EveryInc/compound-engineering | install vs not | Off-domain (security) or duplicative |

## Pending Work

## Immediate Next Steps

1. **Commit the staged `mindpattern-eval` deletion** — `git status` will show the deleted SKILL.md and references/metrics.md staged. Suggested: `git commit -m "chore: remove unused mindpattern-eval skill"`. Don't push without checking with the user.

2. **Phase-adapter refactor of `orchestrator/runner.py`** — the agreed first move. Goal: each of the 12 phases becomes a pure `(prior_state, phase_input) → new_state` function. Should fire `superpowers:brainstorming` skill at the start of any design discussion. Read `orchestrator/runner.py` first to map the current pattern, then sketch the reducer interface.

3. **Begin 2-week error analysis** (parallel to #2 if user wants) — pull last 30 days of newsletter outputs + per-agent traces from `data/ramsay/traces.db`, label every failure with free-text notes, cluster into 5-10 named failure modes. **Don't write any eval scaffolding until this is done.** The mindpattern-eval mistake was doing this in reverse order.

4. **Wire Inspect AI** (after #3) — one Task per agent in `verticals/ai-tech/agents/*.md`. Code scorers for cheap stuff (banned-phrase, citation count, JSON schema), binary LLM-judge for synthesis quality. Calibrate judge against ~50 human-labeled cases (>80% TPR/TNR before trusting).

5. **Close the harness feedback loop** (after #2 and #4) — `review` phase MUST emit `{ticket, verdict: pass|fail|partial, failure_class}` to append-only JSONL. Pin schema with Pydantic test that fails CI on drift. Scout's prompt prepends last 20 lines on next run. Wire the consumer first, producer second.

### Blockers/Open Questions

- [ ] **7 dead skill overrides remain** in `.claude/settings.local.json`: `code-simplify`, `review`, `test`, `plan`, `spec`, `build`, `ship`. These came from `agent-skills@addy-agent-skills` (now disabled). **However, `superpowers` now provides skills with the same names** (`test`, `plan`, `spec`, `build`, `ship`, `code-simplify`?, `review`?) — verify whether the overrides are silencing newly-installed superpowers skills. If yes, remove the overrides.
- [ ] **34 harness tickets need triage**: 15 open, 12 failed, 4 stuck in_progress. Should the user keep the backlog, archive it, or start fresh? Decision needed before harness can be resumed.
- [ ] **`graphify` override is "off"** in project settings — was this intentional or carryover? It's a useful skill given the `graphify-out/` directory exists.
- [ ] **Verify scout.md SQL queries against current `data/ramsay/traces.db` schema** — if `agent_runs.error`, `quality_history`, `pipeline_phases` tables drifted in 5 weeks, scout has been blind. Easy diagnostic; do before any harness restart.

### Deferred Items

- **Vault interface refactor** — moved to second-priority behind Phase adapters per research-driven decision
- **SocialPoster extraction** — small effort but low payoff vs. Phase adapters
- **CONTEXT.md fill** — domain doc improvement, helps future sessions but not the system itself
- **Migration from launchd** — wait until crash-recovery without re-spending tokens becomes the dominant pain
- **Migration from `traces.db` to Langfuse** — wait until ~50k traces/month
- **DSPy+GEPA prompt optimization** — wait until Inspect AI eval metric exists (chicken-and-egg)
- **Re-evaluate context-engineering plugin re-enable** — maybe useful later, but the disciplines they teach are captured in the action plan now

## Context for Resuming Agent

## Important Context

**This session is research + cleanup, not implementation.** The user has a clear architectural plan but no code was written. Don't start implementing without confirming priority.

**Two anti-patterns the user has hit and should not repeat:**
1. Building eval scaffolding before failure data exists (the deleted `mindpattern-eval` skill).
2. Building self-improving loops where no downstream phase reads the artifact (the empty `harness/feedback.json`).

**The user's explicit memory rules** (already in `MEMORY.md`, repeating here for emphasis):
- Brief responses; tables > paragraphs; lead with the answer.
- Solo dev — watch for fatigue, offer clean stopping points.
- Never mention Synchrony Bank (employer, banned from all output).
- Qualify "Claude every day" as personal projects.
- Ban "I keep coming back to" — writer tic.

**The user values direct, opinionated answers over hedging.** When research is asked for, they want depth (30+ sources per topic). When tactical action is asked for, they want the one right answer, not three options.

**The harness has been dormant since 2026-04-02** — don't assume it's running. It has 34 tickets backlogged, scout/plan/fix/review prompts that may have schema-drift bugs, and an empty feedback file. It can't be casually restarted; needs deliberate revival.

### Assumptions Made

- Current branch is `main` and clean (the `mindpattern-eval` deletion is the only staged change, plus pre-existing modified files visible in `git status`).
- `~/Backups/mindpattern/` from 2026-05-04 contains a SQLite "ramsay" backup if any data needs to be restored.
- Plugin reload was successful (`5 plugins · 8 skills · 11 agents · 4 hooks · 1 LSP server` per last `/reload-plugins`).
- The user is on Mac, Python 3.14, runs the pipeline via `run-launchd.sh` daily at 7am.
- The 8 research agent reports live in conversation history only (not persisted to disk) — synthesis is in this handoff.

### Potential Gotchas

- **The `mindpattern-eval` deletion is staged but uncommitted** — `git status` will show two deleted files. Don't push without committing.
- **Stale worktree branches still exist** in `git branch`: `feat/launch-video`, `feat/smart-trend-scan` (already merged via PR #23 — safe to delete with `-d`), `worktree-luminous-popping-pearl`, `worktree-scalable-swinging-pascal`, `worktree-snug-chasing-salamander`, `worktree-agile-watching-gosling`, `worktree-whimsical-munching-bumblebee`. The user may want them cleaned up; ask before deleting.
- **Reflog retains the GIF pipeline commits** (`23c4eed feat: add animated GIF pipeline with Remotion integration`, `69e9cb3 docs: add comprehensive handoff for animated GIF pipeline design work`) for ~30 days. If the user changes mind, they can be recovered via `git reflog`.
- **The 7 dead skill overrides may now be silencing real superpowers skills** — see Blocker #1.
- **`graphify-out/` exists in the project** — pre-existing knowledge graph. The CLAUDE.md says to read `graphify-out/GRAPH_REPORT.md` before architecture questions.
- **The user's MEMORY.md was modified mid-session** to add `feedback_research_depth.md` ("Research surveys need 30+ sources"). That memory now governs research quality bar.
- **The new `superpowers` plugin auto-fires `using-superpowers` skill** at the start of any conversation — be aware that it inserts skill-discovery requirements before your responses.

## Environment State

### Tools/Services Used

- **Claude Code** with the following enabled plugins (per `~/.claude/settings.json` `enabledPlugins`):
  - `andrej-karpathy-skills@karpathy-skills` (Karpathy guidelines)
  - `codex@openai-codex` (Codex CLI integration)
  - `agent-sdk-dev@claude-plugins-official` (NEW this session)
  - `pyright-lsp@claude-plugins-official` (re-enabled this session)
  - `superpowers@claude-plugins-official` (NEW this session, freshly installed)
- Active LSP server: **pyright** (Python type checking)
- launchd agent for daily 7am pipeline run (untouched this session)
- SQLite databases: `data/ramsay/memory.db`, `data/ramsay/traces.db` (both WAL mode, untouched this session)
- Git: main branch, 1 staged deletion pending commit

### Active Processes

- None started this session. The Slack bot (`slack_bot/`) and dashboard (`dashboard/`) were not touched.

### Environment Variables

- `SLASH_COMMAND_TOOL_CHAR_BUDGET` — official Anthropic env var to raise skill description budget (currently NOT set; recommended value `30000` if more skills get re-added)
- Standard `ANTHROPIC_API_KEY` and project-level secrets — unchanged

## Related Resources

### From this session's research (the 8 parallel agents)

- [Anthropic — Building effective agents (Dec 2024)](https://www.anthropic.com/research/building-effective-agents) — the canonical workflow-before-agents argument
- [Anthropic — Equipping agents with Agent Skills (Oct 2025)](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) — Skills system rationale
- [Hamel Husain — Should I practice eval-driven development?](https://hamel.dev/blog/posts/evals-faq/should-i-practice-eval-driven-development.html) — directly explains the `mindpattern-eval` mistake
- [Spotify Honk Pt 3 — Feedback loops in coding agents](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) — directly explains the empty `feedback.json` problem
- [Inspect AI Agent Bridge](https://inspect.aisi.org.uk/agent-bridge.html) — the framework that natively models subprocess-to-CLI agents
- [DSPy GEPA optimizer](https://dspy.ai/api/optimizers/GEPA/overview/) — compile-time prompt optimization for `agents/*.md`
- [12-Factor Agents (Dex Horthy)](https://github.com/humanlayer/12-factor-agents) — the stateless-reducer pattern that motivates Phase adapters
- [Code.claude.com — Skills documentation](https://code.claude.com/docs/en/skills) — canonical Skills + skillOverrides reference
- [Platform.claude.com — Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) — the "always third person, what+when, ≤1024 chars" rules

### Project files

- `CLAUDE.md` — project conventions
- `harness/CLAUDE.md` — harness architecture
- `docs/ARCHITECTURE.md` — full system diagrams (referenced but not read this session)
- `graphify-out/GRAPH_REPORT.md` — community structure of the codebase (per CLAUDE.md, read before architecture questions)

### Memory files updated this session

- New memory: `feedback_research_depth.md` — "Research surveys need 30+ sources"

---

**Security Reminder**: Before finalizing, run `validate_handoff.py` to check for accidental secret exposure.

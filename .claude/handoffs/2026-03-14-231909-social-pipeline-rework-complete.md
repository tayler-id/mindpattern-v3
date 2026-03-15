# Handoff: Social Pipeline Agent Rework + Audit Gap Fixes — Complete

## Session Metadata
- Created: 2026-03-14 23:19:09
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: main
- Session duration: ~3 hours

### Recent Commits (for context)
  - 2e63822 fix: update stale router test assertions to match current config
  - f43e77d fix: update gate messages and replace iMessage AppleScript with v2 pattern
  - 631368c refactor: remove duplicate humanizer, use writers._humanize()
  - 93a6cfa Merge branch 'worktree-agent-add3720f'
  - a0bace4 feat: bump writer turns, trim agent prompts to <=80 lines, update output paths
  - 4944d97 Merge branch 'worktree-agent-ad7dbe91'
  - 2ac573b Merge branch 'worktree-agent-a721a472'
  - b51e852 feat: rework critics to use file-based I/O with blind design
  - df1ff55 feat: rework writers to use file-based I/O with agent tools
  - 7e7ec24 Merge branch 'worktree-agent-a6082b7d'
  - 98503ae feat: rework EIC to use file-based I/O with agent tools
  - f82147a Merge branch 'worktree-agent-af89a0e3'
  - 49c8da5 fix: enforce max_posts_per_day rate limit against actual post history
  - 06a236f fix: add CORS middleware restricted to mindpattern.fly.dev
  - 99ba356 feat: add run_agent_with_files() helper for file-based agent I/O
  - 2a28baa feat: add memory_cli.py for agent memory access via Bash tool
  - 7b1c361 initial commit: mindpattern-v3 codebase

## Handoff Chain

- **Continues from**: `.claude/handoffs/2026-03-14-social-pipeline-rework.md`
- **Supersedes**: That handoff is now fully implemented

## Current State Summary

The v3 social pipeline agent rework is complete. All social agents (EIC, Creative Director, writers, critics, expeditor) now use file-based I/O via `run_agent_with_files()` instead of inline prompts. Agents get their definition files via `--append-system-prompt-file` and tools (Read, Write, Bash, Glob, Grep) to query memory independently via `memory_cli.py`. Additionally, four audit gaps from the rebuild plan were fixed: CORS middleware, rate limit enforcement, agent prompt trimming to <=80 lines, and stale test assertions. 250 of 251 tests pass (1 pre-existing embedding test failure unrelated to this work).

## Codebase Understanding

### Architecture Overview

mindpattern-v3 is a Python orchestrator that runs daily via launchd. It calls Claude CLI (`claude -p`) as subprocesses for LLM work. The pipeline is: INIT -> TREND_SCAN -> RESEARCH -> SYNTHESIS -> DELIVER -> LEARN -> SOCIAL -> ENGAGEMENT -> SYNC. The social pipeline is a sub-pipeline within SOCIAL phase that goes: EIC topic selection -> brief -> art -> writers (parallel) -> critics (blind) -> policy -> humanize -> expedite -> approve -> post.

Two patterns for LLM calls exist side-by-side:
- `run_claude_prompt()` — stdout-based, used by research pipeline (unchanged)
- `run_agent_with_files()` — file-based I/O, used by social pipeline (new)

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `orchestrator/agents.py` | Both run_claude_prompt() and run_agent_with_files() | Core LLM dispatch |
| `orchestrator/router.py` | Model/timeout/turns routing per task type | Config for all agent calls |
| `social/pipeline.py` | SocialPipeline.run() orchestration | Main social flow |
| `social/eic.py` | Topic selection + brief creation | Uses run_agent_with_files |
| `social/writers.py` | Per-platform writing with Ralph Loop | Uses run_agent_with_files |
| `social/critics.py` | Blind critic + expeditor | Uses run_agent_with_files |
| `social/approval.py` | Web dashboard + iMessage approval gates | Fixed AppleScript |
| `memory_cli.py` | CLI wrapper for agent memory access | Agents call via Bash |
| `policies/engine.py` | Deterministic policy enforcement | Now has post rate limit check |
| `agents/*.md` | Agent definition files (all <=80 lines) | Loaded via --append-system-prompt-file |

### Key Patterns Discovered

- Memory module has NO CLI by design — `memory_cli.py` is the bridge for agents
- `importance` field in findings table is a STRING ("high"/"medium"/"low"), not int
- DB path is `data/ramsay/memory.db` (per-user), not `data/memory.db`
- Social modules use `logger = logging.getLogger(__name__)`, not `log`
- Config access: `_load_social_config().get("eic", {}).get("quality_threshold", 5.0)` (nested)
- Writers run in ThreadPoolExecutor — must open fresh DB connections per thread
- Critics are BLIND — no Bash tool, no brief, no memory access
- Expeditor uses "PASS"/"FAIL" (not "APPROVED"), critics use "APPROVED"/"REVISE"

## Work Completed

### Tasks Finished

- [x] Create memory_cli.py (5 commands, 9 tests)
- [x] Add run_agent_with_files() helper (6 tests)
- [x] Bump writer max_turns 10 -> 15
- [x] Trim all agent .md files to <=80 lines (10 files, -1025 lines)
- [x] Update agent .md output paths and schemas
- [x] Remove brief references from critic .md files (blind design)
- [x] Rework social/eic.py (select_topic + create_brief)
- [x] Rework social/writers.py (_write_single_platform + consolidated humanizer)
- [x] Rework social/critics.py (review_draft + expedite)
- [x] Remove duplicate _build_humanize_prompt from pipeline.py
- [x] Fix Gate 1/Gate 2 iMessage formatting (full topic details, draft text)
- [x] Replace iMessage AppleScript with v2 simple pattern
- [x] Add phone number normalization (+1 prefix)
- [x] Fix CORS middleware (restricted to mindpattern.fly.dev, 5 tests)
- [x] Add validate_post_rate_limit() to PolicyEngine (5 tests)
- [x] Fix stale router test assertions

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| File-based I/O (not stdout) | A: file-based, B: stdout, C: class wrapper | Matches v2 pattern, gives agents autonomy to write structured output |
| Additive helper (not replace) | A: new function alongside, B: replace run_claude_prompt, C: class | Zero risk to working newsletter pipeline |
| memory_cli.py (not inline import) | A: CLI script, B: python -c inline, C: inject in prompt | CLI is explicit, testable, no cold-start path issues |
| Critics get no Bash | Give all tools vs. restrict | Blindness constraint — critics must not query memory |
| Expeditor PASS/FAIL (not APPROVED) | Match spec vs. match existing code | Existing pipeline checks for "FAIL", changing would break consumers |

## Pending Work

### Immediate Next Steps

1. **End-to-end test run** — Run the full pipeline (`python3 run.py`) and verify the social pipeline produces quality output with the new agent calls. This is the real test.
2. **Verify iMessage delivery** — The AppleScript was replaced but not tested with a real iMessage send. Run the social pipeline with Gate 1 enabled to verify messages arrive.
3. **Wire social + engagement into daily launchd plist** — Handoff step 7 from the original. The launchd plist needs to point to the v3 run.py.
4. **Fix the 1 remaining test failure** — `test_memory.py::TestEmbeddings::test_batch_similarities_sorted_above_threshold` — pre-existing, likely a threshold or embedding model issue.

### Blockers/Open Questions

- iMessage delivery was never confirmed working in v3 — the AppleScript was replaced but needs real-world testing
- The `platform_verdicts` field from expeditor is new but pipeline.py doesn't consume it yet (still treats verdict as all-or-nothing). Future work to use per-platform granularity.
- RSS broken-feed detection is at "PARTIAL" status from audit — fallback scraping exists but no explicit feed-health monitoring

### Deferred Items

- RSS feed health monitoring (audit: PARTIAL)
- platform_verdicts per-platform granularity in pipeline.py
- Engagement pipeline was not reworked (only social pipeline was in scope)

## Context for Resuming Agent

### Important Context

- The project has NO remote — all commits are local on main branch
- 250/251 tests pass. The 1 failure is pre-existing in embeddings, not related to this work.
- The social pipeline has never been run end-to-end with the new agent calls. First real run will be the validation.
- Spec: `docs/superpowers/specs/2026-03-14-social-pipeline-agent-rework-design.md`
- Plan: `docs/superpowers/plans/2026-03-14-social-pipeline-agent-rework.md`
- Previous handoff: `.claude/handoffs/2026-03-14-social-pipeline-rework.md`

### Assumptions Made

- Claude CLI supports `--append-system-prompt-file` flag (confirmed in existing code)
- Claude CLI supports `--allowedTools` flag (confirmed in existing code)
- memory_cli.py will be callable from agent's Bash tool when run from PROJECT_ROOT
- fastembed cold start (~2-5s) is acceptable for social pipeline agents with 5-10 min timeouts

### Potential Gotchas

- The `.claude/worktrees/` directory was cleaned up but check for stale worktree artifacts
- `memory.db` WAL files may appear as unstaged changes — these are runtime artifacts, not code
- The `data/social-brief-options.json` file (old EIC output path) still exists on disk but is no longer written to. Can be deleted.
- Agent .md files were aggressively trimmed — if agent quality drops, the trimming may have removed important context. Compare with git history.

## Environment State

### Tools/Services Used

- Python 3.14 (macOS, Homebrew)
- pytest (no pytest-timeout plugin — `--timeout` flag doesn't work)
- Claude CLI (authenticated via Claude Pro subscription)
- SQLite (memory.db at data/ramsay/memory.db)
- fastembed (BAAI/bge-small-en-v1.5, 384-dim embeddings)

### Active Processes

- None — no servers or background processes running

### Environment Variables

- `API_TOKEN_HASH` — dashboard auth (set on Fly.io)
- Resend API key — stored in macOS Keychain under `resend-api-key`
- Platform API keys (X, Bluesky, LinkedIn) — stored in macOS Keychain

## Related Resources

- Rebuild plan: `docs/rebuild-plan.md` (full v3 architecture, 97% implemented)
- Design spec: `docs/superpowers/specs/2026-03-14-social-pipeline-agent-rework-design.md`
- Implementation plan: `docs/superpowers/plans/2026-03-14-social-pipeline-agent-rework.md`
- Original handoff: `.claude/handoffs/2026-03-14-social-pipeline-rework.md`
- Audit results: 27/30 items fully implemented (this session fixed the 3 gaps)

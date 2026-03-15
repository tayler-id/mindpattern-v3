# Handoff: V3 Complete Pipeline Launch + Remaining Work

## Session Metadata
- Created: 2026-03-15 13:46:40
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: main
- Session duration: ~5 hours

### Recent Commits (for context)
  - ffa5c24 feat: enable LinkedIn posting, restrict engagement to Bluesky only
  - e0a3aaa fix: handle string draft_data in expeditor proof_package builder
  - 2d9b360 fix: use /bin/bash wrapper for launchd to inherit Full Disk Access
  - 5984e65 Fix schema mismatches in observability module for existing traces.db
  - 6867dd1 Wire PipelineMonitor, NewsletterEvaluator, entity graph, signals, and policy validation into pipeline runner
  - 534d504 Restore v1/v2 EIC, critic, and expeditor agent detail into v3
  - c364465 Restore v1/v2 writer agent detail into v3 agent definitions
  - 1a15e39 Switch social pipeline to Bluesky-only operation
  - 8b60e73 fix: handle non-dict return from run_agent_with_files in expeditor and critic
  - 5b63877 fix: make batch_similarities test deterministic by seeding RNG and normalizing vector

## Handoff Chain

- **Continues from**: `.claude/handoffs/2026-03-14-231909-social-pipeline-rework-complete.md`
- **Supersedes**: That handoff is now fully implemented and extended

## Current State Summary

V3 pipeline is fully operational. First successful Bluesky post published today at https://bsky.app/profile/webdevdad.bsky.social/post/3mh4hnlz6ke2e. Full E2E run completed: 13 research agents → newsletter (4,495 words, quality 0.947) → email delivery → social posting to Bluesky → engagement (0 candidates — BROKEN, needs fix). All previously unwired features (PipelineMonitor, NewsletterEvaluator, entity graph, signals, policy validation) are now wired into the runner. Launchd plists updated to use /bin/bash wrappers for Full Disk Access. Pushed to GitHub at tayler-id/mindpattern-v3. Two critical items remain: (1) engagement pipeline returns 0 candidates every run, (2) LinkedIn posting is enabled but untested.

## Codebase Understanding

### Architecture Overview

mindpattern-v3 is a Python orchestrator that runs daily via launchd. It calls Claude CLI (`claude -p`) as subprocesses for LLM work. Pipeline phases: INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → LEARN → SOCIAL → ENGAGEMENT → SYNC. Social is a sub-pipeline: EIC → Gate 1 (iMessage) → Brief → Writers → Critics → Policy → Humanize → Expeditor → Gate 2 (iMessage) → Post. Two LLM call patterns: `run_claude_prompt()` (stdout) and `run_agent_with_files()` (file-based I/O).

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `orchestrator/runner.py` | Main pipeline runner with all phase handlers | Core orchestration, all features wired here |
| `social/pipeline.py` | Social sub-pipeline (584 lines) | EIC → writers → critics → expeditor → posting |
| `social/engagement.py` | Engagement pipeline | BROKEN: returns 0 candidates, needs debugging |
| `social/approval.py` | iMessage + dashboard approval gates | FDA fix applied (bash wrapper), improved error logging |
| `social/critics.py` | Critic review + expeditor | Fixed string draft_data handling in expeditor |
| `social/posting.py` | Platform API clients (X, Bluesky, LinkedIn) | LinkedIn client exists but untested in v3 |
| `orchestrator/observability.py` | PipelineMonitor — phase timing, cost, quality | Wired into runner, schema migration added |
| `orchestrator/evaluator.py` | NewsletterEvaluator — 6-dimension scoring | Wired into synthesis phase |
| `agents/*.md` | Agent definitions (restored from v1/v2) | Full frameworks, rubrics, exemplars, process checklists |
| `agents/references/framework-catalog.md` | Rhetorical frameworks for writers | Writers reference this in Step 2 of process |
| `agents/references/editorial-taxonomy.md` | Editorial patterns | LinkedIn writer references this |
| `social-config.json` | Platform config + engagement settings | LinkedIn enabled for posting, engagement.platforms=["bluesky"] |
| `autoresearch.py` | Overnight self-improvement loop | Launchd plist created, runs at 2 AM |

### Key Patterns Discovered

- **Humanization replaces draft dicts with strings**: `pipeline.py` line 332 does `drafts[platform] = humanized.strip()`, converting dict to str. Any downstream code that calls `.get()` on drafts must check `isinstance(draft_data, str)` first.
- **FDA inheritance**: launchd processes don't inherit Full Disk Access. Solution: wrap python calls in `/bin/bash` scripts since bash has FDA. Critical for Messages.db polling.
- **Engagement uses `run_claude_prompt()` (stdout)**: Unlike social agents which use `run_agent_with_files()`, engagement finder uses stdout-based prompting. The agent definition file (`agents/engagement-finder.md`) is loaded but not used as `--append-system-prompt-file`. This mismatch may be why it returns 0 candidates.
- **`memory_cli.py`** is the bridge for agents to query memory. Agents call it via Bash tool.
- **Config-driven platforms**: `_init_platform_clients()` respects `enabled` flags. Engagement additionally respects `engagement.platforms` list.
- **Schema mismatches**: traces.db tables created by older code may have different schemas. `PipelineMonitor._ensure_tables()` now runs migrations with ALTER TABLE fallbacks.
- **Policy validation catches prompt injection**: Research findings containing "system prompt", "override", "jailbreak", "act as" are flagged. These are legitimate findings ABOUT those topics, not actual injections — the policy may need tuning.

## Work Completed

### Tasks Finished

- [x] Fix flaky embedding test (seeded RNG + normalized vector)
- [x] Fix expeditor crash — TWO bugs: (1) non-dict return from `run_agent_with_files`, (2) string draft_data in proof_package builder
- [x] Fix posting bug (`image` vs `image_path` kwarg)
- [x] Wire launchd plists to v3 (`run-launchd.sh` bash wrapper for FDA)
- [x] Switch to Bluesky-only operation, then re-enable LinkedIn for posting
- [x] Restore all agent .md definitions from v1/v2 (writers, critics, EIC, expeditor, creative director)
- [x] Wire PipelineMonitor (observability, cost tracking, phase timing)
- [x] Wire NewsletterEvaluator (post-synthesis quality scoring)
- [x] Wire entity graph (knowledge extraction from high-importance findings)
- [x] Wire cross-pipeline signals (social→research feedback loop)
- [x] Wire research policy validation
- [x] Fix traces.db schema mismatches (agent_metrics, quality_history migrations)
- [x] Create autoresearch launchd plist (2 AM nightly)
- [x] Push to GitHub tayler-id/mindpattern-v3
- [x] Enable LinkedIn posting + restrict engagement to Bluesky only
- [x] Successful first E2E run with Bluesky post published
- [x] Disable social plists (social phases now within main pipeline)

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Bluesky + LinkedIn posting, Bluesky-only engagement | A: All platforms, B: Bluesky only, C: Split posting/engagement | User doesn't pay for X API, LinkedIn engagement waiting on dev approval |
| /bin/bash wrapper for launchd | A: Grant FDA to Python, B: Bash wrapper | Bash already has FDA, no System Settings changes needed |
| Non-fatal observability | A: Abort on monitoring failure, B: Log warning, continue | Monitoring shouldn't crash the pipeline |
| Restore v1/v2 agent defs (not keep v3 trimmed) | A: Keep v3 slim, B: Restore full v1/v2 content | V3 over-trimmed by 40-65%, lost frameworks, exemplars, rubrics. Quality suffered. |
| engagement.platforms config key | A: Separate enabled flags per-feature, B: engagement.platforms list | Clean separation — posting uses platform.enabled, engagement uses engagement.platforms |

## Pending Work

### Immediate Next Steps

1. **FIX: Engagement pipeline returns 0 candidates** — The engagement finder uses `run_claude_prompt()` (stdout) but the agent definition expects file-based I/O with `run_agent_with_files()`. It also may not have the right tools to actually search Bluesky. Compare with v1/v2 `run-engagement.sh` which gave the agent `social-post.py search` as a tool. The v3 engagement finder needs: (a) switch to `run_agent_with_files()`, or (b) give it proper Bluesky search tools via Bash, or (c) use the BlueskyClient.search() method directly in Python instead of an agent call.

2. **TEST: LinkedIn posting** — LinkedIn is enabled but never tested in v3. The `LinkedInClient` class exists in `social/posting.py` with OAuth2 bearer token auth. The access token is in Keychain (`linkedin-access-token`). Test by running a social pipeline and verifying LinkedIn post appears.

3. **User wants multi-platform posts about GitAgent compliance** — User provided detailed content about GitAgent's financial compliance system (FINRA, Fed, SEC, CFPB rules). They want this written up and posted using the social pipeline's proper voice/writer agents. This is a user-directed topic that should go through the EIC's Mode 2 (User-Directed Synthesis).

4. **FIX: Fly.io sync is broken** — `_phase_sync()` fails with SSH error: `exec: "cd": executable file not found in $PATH`. The Fly.io machine may need SSH shell fix or the sync command needs updating.

5. **FIX: Dashboard is down** — Gate 1/Gate 2 both return 404 from dashboard API, falling back to iMessage. Dashboard at mindpattern.fly.dev needs investigation.

### Blockers/Open Questions

- Why does engagement finder return 0 candidates? Is it a search tool issue, prompt issue, or parsing issue?
- LinkedIn posting untested — does the token work? Is the person URN configured?
- Policy validation flags legitimate findings about "system prompt" topics as prompt injection — needs tuning
- Fly.io SSH sync broken — dashboard may have stale data

### Deferred Items

- **Agent Evolution** (`memory/evolution.py`, 562 lines) — Dynamic agent spawn/retire/merge based on performance. Built but NOT wired. Needs its own spec + plan.
- **DPO learning from corrections** — Corrections are stored at Gate 2 but no ML pipeline learns from them
- **RSS feed health monitoring** — PARTIAL from original audit
- **platform_verdicts per-platform granularity** — Expeditor returns it but pipeline.py doesn't consume it

## Context for Resuming Agent

### Important Context

- GitHub: `tayler-id/mindpattern-v3` on `main` branch
- 253 tests pass as of last commit
- Launchd: `com.taylerramsay.daily-research` runs at 7 AM via `run-launchd.sh` (bash wrapper)
- Launchd: `com.taylerramsay.autoresearch` runs at 2 AM via `autoresearch-launchd.sh`
- Platform status: Bluesky posting ✅, LinkedIn posting enabled but untested, X disabled, Engagement Bluesky-only but broken (0 candidates)
- First successful Bluesky post: https://bsky.app/profile/webdevdad.bsky.social/post/3mh4hnlz6ke2e
- The user wants engagement to find 20 Bluesky conversations per day from people they're NOT connected to, reply to build connections
- The user wants to post about GitAgent compliance (FINRA/Fed/SEC/CFPB) — content provided in conversation
- V1/V2 engagement worked via: `run-engagement.sh` → `social-post.py search --platform bluesky` → agent writes replies → iMessage gate → `social-post.py reply` + `social-post.py follow`
- V3 engagement tries to do it all via a single `run_claude_prompt()` call which is likely insufficient
- Bluesky connection checking: `follow_bluesky()` uses `app.bsky.graph.getRelationships` to check if already following before creating follow record

### Assumptions Made

- LinkedIn access token in Keychain is valid and not expired (token_expires_days: 60)
- /bin/bash has Full Disk Access (confirmed working for Messages.db polling)
- autoresearch.py is functional (dry-run not tested this session)
- Bluesky app password in Keychain is valid (confirmed — post published)

### Potential Gotchas

- `memory.db` WAL files appear as unstaged git changes — runtime artifacts, not code
- `data/social-drafts/` files are runtime output, not code — don't commit
- Policy validation "prompt injection" false positives on findings ABOUT system prompts
- The `social/pipeline.py` has an `image`→`image_path` fix from the E2E validation agent that may not have been committed separately (was part of the validation pass)
- `social-config.json` has `engagement.platforms: ["bluesky"]` — this is NEW and engagement.py was modified to respect it

## Environment State

### Tools/Services Used

- Python 3.14 (macOS, Homebrew)
- Claude CLI (authenticated via Claude Pro subscription)
- SQLite (memory.db at data/ramsay/memory.db, traces.db at data/ramsay/traces.db)
- fastembed (BAAI/bge-small-en-v1.5, 384-dim embeddings)
- GitHub CLI (`gh`, authenticated as tayler-id)
- Resend API (email delivery, key in Keychain)
- Bluesky API (webdevdad.bsky.social, app password in Keychain)
- LinkedIn API (access token in Keychain, untested in v3)

### Active Processes

- None currently running

### Environment Variables

- `API_TOKEN_HASH` — dashboard auth (set on Fly.io)
- Resend API key — macOS Keychain `resend-api-key`
- Bluesky app password — macOS Keychain `bluesky-app-password`
- LinkedIn access token — macOS Keychain `linkedin-access-token`
- Platform API keys (X) — in Keychain but X is disabled

## Related Resources

- Previous handoff: `.claude/handoffs/2026-03-14-231909-social-pipeline-rework-complete.md`
- Rebuild plan: `docs/rebuild-plan.md`
- Wiring plan: `docs/superpowers/plans/2026-03-15-wire-unwired-features.md`
- Design spec: `docs/superpowers/specs/2026-03-14-social-pipeline-agent-rework-design.md`
- V1 engagement reference: `/Users/taylerramsay/Projects/daily-research-agent copy/run-engagement.sh`
- V2 engagement reference: `/Users/taylerramsay/Projects/daily-research-agent-v2/orchestrator/engagement.py`

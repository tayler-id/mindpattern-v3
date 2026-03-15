# Handoff: V3 Social Pipeline Fixes + Full E2E Test

## Session Metadata
- Created: 2026-03-15 16:16:21
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: main
- Session duration: ~3 hours

### Recent Commits (for context)
  - c95d666 fix: iMessage polling match by handle, writer voice rules, LinkedIn API version
  - 1d1536f fix: iMessage approval polling + LinkedIn API version
  - 08b3c18 fix: complete v3 pipeline fixes — engagement, LinkedIn, dashboard, Fly.io sync

## Handoff Chain

- **Continues from**: `.claude/handoffs/2026-03-15-134640-v3-complete-pipeline-and-remaining-work.md`
- **Supersedes**: All 5 items from that handoff are now resolved

## Current State Summary

All 5 items from the previous handoff are fixed and deployed. The full pipeline ran E2E today: research (13 agents, 123 findings) → synthesis (4,756 word newsletter) → email delivery → social pipeline. Two posts were published manually to Bluesky and LinkedIn after the automated flow hit issues with iMessage polling and writer voice. The iMessage polling is now fixed (matches by handle table, accepts both is_from_me values). Writer agent prompts are updated to not mention the pipeline/agents. One more clean test run is needed to verify the full automated flow: EIC → Gate 1 iMessage → writers → critics → policy → humanize → expeditor → Gate 2 iMessage → auto-post.

## Codebase Understanding

### Architecture Overview

mindpattern-v3 is a Python orchestrator that runs daily via launchd at 7 AM. It calls Claude CLI (`claude -p`) as subprocesses for all LLM work. The pipeline has 9 phases: INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → LEARN → SOCIAL → ENGAGEMENT → SYNC.

The social sub-pipeline has 10 steps: EIC topic selection (Opus) → Gate 1 (iMessage) → Creative brief (Sonnet) → Writers (Sonnet, parallel per platform) → Critics (Sonnet, parallel) → Policy validation (Python) → Humanize (Sonnet) → Expeditor (Sonnet) → Gate 2 (iMessage) → Post (API calls with jitter).

Two LLM call patterns exist:
- `run_claude_prompt()` — stdout-based, captures text output
- `run_agent_with_files()` — file-based I/O, agent writes to disk

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `orchestrator/runner.py` | Main pipeline runner, all phase handlers | Core orchestration — phases call into social/, memory/, etc. |
| `social/pipeline.py` | Social sub-pipeline (584 lines) | EIC → writers → critics → expeditor → posting flow |
| `social/approval.py` | iMessage approval gates | Fixed this session: poll query, is_from_me, iMessage-only mode |
| `social/engagement.py` | Engagement pipeline | Rewrote this session: 5-step Python+LLM pipeline, NOT YET TESTED |
| `social/posting.py` | Platform API clients | Fixed: LinkedIn 6 bugs, added BlueskyClient.get_relationships() |
| `social/writers.py` | Writer agent dispatcher | Calls claude with agent .md files as system prompts |
| `social/critics.py` | Critic + expeditor | expedite() is the final quality gate — may be too strict |
| `dashboard/routes/api.py` | FastAPI API routes for Vercel frontend | Added 7 missing routes, changed to flat array format |
| `dashboard/app.py` | FastAPI app factory | Added CORS for Vercel |
| `agents/bluesky-writer.md` | Bluesky writer agent definition | Updated: no pipeline mentions |
| `agents/linkedin-writer.md` | LinkedIn writer agent definition | Updated: no pipeline mentions |
| `agents/eic.md` | Editor-in-Chief agent definition | Selects topics from findings, scores novelty/appeal/thread |
| `orchestrator/sync.py` | Fly.io sync (bundle → sftp → extract) | Fixed: sh -c wrapper for SSH, added traces.db |
| `social-config.json` | Platform config + engagement settings | LinkedIn api_version=202504, engagement.platforms=["bluesky"] |
| `Dockerfile` | Fly.io container | Rewrote: FastAPI dashboard, memory/ module, /data symlink |
| `fly.toml` | Fly.io config | Updated health checks to V2 format |
| `run.py` | Pipeline entry point | Uses lock file at /tmp/mindpattern-pipeline.lock |
| `run-launchd.sh` | Bash wrapper for launchd | Ensures /bin/bash FDA for Messages.db access |

### Key Patterns Discovered

1. **iMessage chat_identifier varies by device**: The same conversation can have `chat_identifier` as a phone number from one device and an email address from another (e.g., `ramsay.tayler@gmail.com` instead of `+17175783243`). The fix: query through the `handle` table which always has the phone number, then find associated chats via `chat_message_join`.

2. **is_from_me is inconsistent**: When the user replies from their iPhone, the Mac's Messages.db sometimes records it as `is_from_me=0` (incoming) and sometimes as `is_from_me=1` (outgoing via iCloud sync). The poll must accept BOTH values. Current query uses `is_from_me IN (0, 1)` — which is effectively no filter on this column.

3. **EIC Opus calls take 4-30 minutes**: The EIC uses `claude -p` with Opus model, 15 max turns, and multiple tool calls (memory_cli searches, file reads). When many Opus calls have been made in the same session (rate limiting), calls take 20-30 min. Normal daily launchd runs (1 per day) should be 4-10 min.

4. **Writer agents load .md files at dispatch time**: Editing `agents/bluesky-writer.md` while the writer is already running has NO effect. The claude process already loaded the system prompt. Changes only take effect on the NEXT run.

5. **LinkedIn API versions expire**: The REST API requires a `Linkedin-Version: YYYYMM` header. Version `202501` expired by March 2026. Updated to `202504`. This will need periodic updates (check every 2-3 months).

6. **Expeditor can kill the entire pipeline**: If `expedite()` returns a FAIL verdict, `pipeline.py` stops without posting. The expeditor caught "I run 12 agents" as a voice violation and killed the run. Consider making expeditor flag for REVISION instead of hard FAIL.

7. **Fly.io SSH exec() has no shell**: `flyctl ssh console -C "cd /data && tar xzf ..."` fails because `cd` is a shell builtin. Must wrap in `sh -c '...'`. All SSH commands in `sync.py` now use the `_fly_ssh()` helper which does this wrapping.

8. **Dashboard API returns must be flat arrays**: The Vercel frontend (`vercel-mindpattern`) calls `backendFetch` which expects flat arrays `[{...}, {...}]`. The v3 dashboard initially returned paginated objects `{items: [...], total: N}`. Changed all 4 endpoints (findings, sources, patterns, skills) to return flat arrays.

9. **Pipeline checkpoint system**: `orchestrator/runner.py` uses a checkpoint system that saves progress after each phase. When restarted, `run.py` detects the checkpoint and resumes from the last incomplete phase. This is why restarts skip research/synthesis and go straight to social.

## Work Completed

### Tasks Finished

- [x] Fix engagement pipeline (rewrote as 5-step Python+LLM pipeline with actual Bluesky search)
- [x] Fix LinkedIn client (6 API bugs: deprecated endpoints, wrong headers, wrong payload)
- [x] Fix Fly.io sync (sh -c wrapper for SSH commands)
- [x] Fix dashboard 404 (rewrote Dockerfile, added API routes, deployed)
- [x] Fix mindpattern.ai website (added 7 missing API routes, flat array format, CORS)
- [x] Sync correct DB to Fly.io (1,600 findings, 48 reports)
- [x] Fix iMessage approval polling (handle table query, both is_from_me values)
- [x] Switch to iMessage-only approval (removed dashboard dependency)
- [x] Fix LinkedIn API version (202501→202504)
- [x] Update writer agent prompts (no pipeline/agent mentions)
- [x] Published 2 Bluesky posts and 2 LinkedIn posts (manual posting after gate issues)
- [x] Ran full E2E pipeline: research→synthesis→email→social

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| iMessage-only approval (no dashboard) | A: Dashboard+iMessage fallback, B: iMessage only, C: Dashboard only | Dashboard UI didn't show pipeline approvals, iMessage is what the user actually uses |
| Flat arrays instead of paginated | A: Keep paginated + update frontend, B: Return flat arrays | Frontend already built for v2 flat format, less changes needed |
| Poll by handle table not chat_identifier | A: Add email to config, B: Query handle table | Handle table is authoritative, works regardless of chat_identifier format |
| Accept both is_from_me values | A: is_from_me=0 only, B: is_from_me=1 only, C: Both | Inconsistent across devices, safest to accept both |

## Pending Work

### Immediate Next Steps

1. **TEST: Fresh social run with updated writer prompts** — The writer .md files now say "DO NOT mention pipeline/agents". Need a clean `python3 -c "from social.pipeline import SocialPipeline; ..."` run where writers load fresh files. The last test failed because cached old prompts still had "I run 12 agents" which the expeditor caught and killed the run. This is the single most important test — if this passes, the pipeline is fully automated.

2. **INVESTIGATE: Expeditor strictness** — The expeditor in `social/critics.py` `expedite()` function returned FAIL when it found pipeline-mention content. Check if it should return REVISE instead of FAIL, so the pipeline retries the writers instead of dying. Look at `social/pipeline.py` around line 340-360 where it handles the expeditor result.

3. **TEST: Engagement pipeline** — `social/engagement.py` was completely rewritten this session but never tested. The new 5-step pipeline (generate queries → search Bluesky → filter → check connections → LLM rank) needs an E2E test. Run it standalone: `from social.engagement import EngagementPipeline; ep = EngagementPipeline('ramsay', config, db); result = ep.run()`.

4. **TEST: Gate 2 → auto-post flow** — Gate 2 iMessage sends drafts for approval. User replies "all". Pipeline should auto-post to both platforms. This was never verified end-to-end because the expeditor killed the run before reaching Gate 2. The iMessage polling fix (handle table query) should work for Gate 2 the same way it worked for Gate 1.

### Blockers/Open Questions

- The `social/approval.py` poll query now uses a subquery through `handle` table. This is correct but slower than the old direct query. If performance is an issue on large Messages.db, consider caching the chat_id lookup.
- The expeditor's FAIL behavior may need tuning — currently it kills the entire pipeline on any quality failure. Should it retry writers instead?
- There's a `banned pattern` for LinkedIn that catches trailing question marks (`\?[^)]*$`). This caused multiple policy retries. The pattern is overly aggressive — questions at the end of LinkedIn posts are fine and common.

### Deferred Items

- Dashboard approval UI (Editors Desk doesn't show pipeline approvals) — not needed, using iMessage-only
- GitAgent content post — topic brief at `data/social-drafts/user-directed-gitagent.json`, about agent portability NOT financial compliance
- Agent Evolution module (`memory/evolution.py`, 562 lines) — built but NOT wired
- DPO learning from corrections — corrections stored at Gate 2 but no ML pipeline
- RSS feed health monitoring — partial
- Engagement: platform_verdicts per-platform granularity

## Context for Resuming Agent

### Important Context

- GitHub: `tayler-id/mindpattern-v3` on `main` branch
- The v2 pipeline (`daily-research-agent-v2`) is ALSO running via launchd. It has its own social pipeline. Don't confuse v2 iMessages/posts with v3 testing.
- Bluesky account: webdevdad.bsky.social — posts confirmed working
- LinkedIn: urn:li:person:Q9nVn1PfNO (Tayler Ramsay) — posts confirmed working
- User phone: +17175783243, but iMessage chat_identifier is ramsay.tayler@gmail.com
- User email: ramsay.tayler@gmail.com
- **USER FEEDBACK**: DO NOT mention "my agents", "my pipeline", "12 agents", "cron job", "I build AI" in social posts. Posts must read as human voice. This is saved in memory at `feedback_social_writing.md`.
- Fly.io app: mindpattern (sjc region), dashboard at mindpattern.fly.dev, correct DB synced (1,600 findings, 48 reports)
- Vercel site: mindpattern.ai, project "frontend" under "ramsaytaylers-projects", calls mindpattern.fly.dev API
- Launchd plists: `com.taylerramsay.daily-research` at 7 AM, `com.taylerramsay.autoresearch` at 2 AM
- 3-hour timezone offset in launchd — set hour=4 for 7 AM actual

### Assumptions Made

- LinkedIn access token valid (confirmed today, api_version=202504, will expire in ~60 days)
- Bluesky app password valid (confirmed, 3 posts today)
- /bin/bash has Full Disk Access (confirmed, iMessage read/write works from run-launchd.sh)
- Launchd plists point to v3 `run-launchd.sh`
- Resend API key in Keychain is valid (email sent today)

### Potential Gotchas

- **Orphan claude processes**: Multiple killed pipeline runs left orphan `claude -p` processes. Before starting a test, run `ps aux | grep "claude.*-p" | grep -v grep | grep -v "daily-research-agent-v2\|test-team"` and kill any strays.
- **Lock file**: `/tmp/mindpattern-pipeline.lock` must be removed if pipeline was killed: `rm -f /tmp/mindpattern-pipeline.lock`
- **Two social pipelines**: v2 (`daily-research-agent-v2`) has its own social pipeline running independently. Its iMessages may confuse the v3 poll. The v3 poll uses `min_rowid` to only look at messages AFTER the iMessage was sent, so this should be fine.
- **checkpoint resume**: The pipeline checkpoint may resume from SOCIAL even if you want to re-run from scratch. To force a fresh run, clear the checkpoint or use a different date: `python3 run.py --user ramsay --date 2026-03-16`
- **memory.db WAL files**: `data/ramsay/memory.db-wal` and `-shm` files are runtime artifacts. Don't commit them.
- **data/social-drafts/**: These files are overwritten each run. They contain the latest drafts from whatever pipeline ran last.

## Environment State

### Tools/Services Used

- Python 3.14 (macOS, Homebrew)
- Claude CLI 2.1.74 (authenticated via Claude Pro subscription)
- SQLite (memory.db at data/ramsay/memory.db, traces.db at data/ramsay/traces.db)
- fastembed (BAAI/bge-small-en-v1.5, 384-dim embeddings)
- GitHub CLI (`gh`, authenticated as tayler-id)
- Resend API (email delivery, key in Keychain as `resend-api-key`)
- Bluesky API (webdevdad.bsky.social, app password in Keychain as `bluesky-app-password`)
- LinkedIn API (access token in Keychain as `linkedin-access-token`, api_version=202504)
- Fly.io CLI (`fly`, app: mindpattern, sjc region)

### Active Processes

- v2 research pipeline may still be running (PID varies, check `ps aux | grep "daily-research-agent-v2"`)
- Test team agents may be running (PID varies, check for `test-team` in process list)

### Environment Variables

- `API_TOKEN_HASH` — dashboard auth (set on Fly.io, NOT configured locally)
- Keychain: `resend-api-key`, `bluesky-app-password`, `linkedin-access-token`

## Related Resources

- Previous handoff: `.claude/handoffs/2026-03-15-134640-v3-complete-pipeline-and-remaining-work.md`
- Rebuild plan: `docs/rebuild-plan.md`
- V1 reference: `/Users/taylerramsay/Projects/daily-research-agent copy/`
- V2 reference: `/Users/taylerramsay/Projects/daily-research-agent-v2/`
- Vercel frontend: `/Users/taylerramsay/Projects/vercel-mindpattern/`
- User feedback memory: `/Users/taylerramsay/.claude/projects/-Users-taylerramsay-Projects/memory/feedback_social_writing.md`

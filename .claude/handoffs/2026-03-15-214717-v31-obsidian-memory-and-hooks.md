# Handoff: V3.1 Obsidian Memory + Hooks Architecture

## Session Metadata
- Created: 2026-03-15 21:47:17
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: feat/obsidian-memory
- Session duration: ~6 hours (social pipeline fixes + Phase 1 build)

### Recent Commits (for context)
  - 9608a55 feat: backfill all historical daily logs, add newsletters + feedback mirrors
  - bdcbef3 fix: generate daily logs for ALL historical dates, not just today
  - 9813d33 feat: mirror newsletters + Gate 2 feedback into Obsidian vault
  - a2cfd69 feat: wire EVOLVE + MIRROR phases into pipeline state machine
  - bcc7eec feat: add LinkedIn engagement discovery via Jina Reader search
  - 2f8f63b feat: export vault, mirror, identity_evolve from memory module
  - 3eedc22 feat: add memory/mirror.py — generate Obsidian files from SQLite
  - 946f65f feat: switch all agents to read voice.md from Obsidian vault
  - 64cd57c feat: add memory/identity_evolve.py — LLM-driven identity file evolution
  - 9b506b0 feat: add Jinja2 templates for Obsidian mirror files
  - b5a2951 feat: add Agent Reach tool instructions to all 13 research agents
  - 1a94868 feat: add memory/vault.py — atomic read/write for Obsidian markdown files
  - 4e25477 fix: remove X platform, fix iMessage polling, add "I run agents" kill switch (on main)

## Handoff Chain

- **Continues from**: `.claude/handoffs/2026-03-15-161621-v3-social-pipeline-fixes.md`
- **Supersedes**: All items from that handoff are resolved

## Current State Summary

Session accomplished two major things: (1) Fixed the social pipeline — removed X platform, fixed iMessage polling (multi-identity + post-send ROWID baseline), added 5-layer "I run agents" kill switch, successfully posted to both Bluesky and LinkedIn E2E. (2) Built Phase 1 of the v3.1 spec — Obsidian vault with evolving identity files, Jinja2 mirror generation, EVOLVE + MIRROR pipeline phases, Agent Reach for research, LinkedIn engagement discovery. All on `feat/obsidian-memory` branch, NOT yet merged to main. The branch has 12 commits and 114 new tests all passing.

**The next priority is adding Claude Code hooks** to capture every agent's reasoning, decisions, and results during pipeline runs. Currently agent thinking is lost when the `claude -p` subprocess exits. Hooks fire on SessionEnd and can save the full transcript. This data feeds into richer daily logs and the EVOLVE phase for system self-improvement.

## Codebase Understanding

### Architecture Overview

mindpattern-v3 is a Python orchestrator that runs daily via launchd at 7 AM. It calls Claude CLI (`claude -p`) as subprocesses for all LLM work. The pipeline has 11 phases: INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → LEARN → SOCIAL → ENGAGEMENT → EVOLVE → MIRROR → SYNC → COMPLETED.

**New in this session:**
- EVOLVE phase: One Sonnet call reads soul.md/user.md/voice.md/decisions.md + pipeline results, outputs a JSON diff, Python applies section updates atomically
- MIRROR phase: Pure Python + Jinja2 queries SQLite, generates markdown files for Obsidian vault
- Obsidian vault at `data/ramsay/mindpattern/` with 4 source-of-truth files + generated mirrors

Two LLM call patterns:
- `run_claude_prompt()` — stdout-based, captures text output
- `run_agent_with_files()` — file-based I/O, agent writes to disk

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `memory/vault.py` | Atomic read/write for Obsidian markdown files | NEW — foundation for all vault I/O |
| `memory/identity_evolve.py` | EVOLVE phase — LLM updates identity files | NEW — builds prompt, validates/applies JSON diffs |
| `memory/mirror.py` | MIRROR phase — SQLite → Obsidian markdown | NEW — generates daily logs, topics, sources, social, newsletters |
| `memory/templates/*.md.j2` | 8 Jinja2 templates for mirror files | NEW — daily, topic, source, posts, corrections, engagement, authors, index |
| `data/ramsay/mindpattern/soul.md` | Agent personality — evolves | NEW — source of truth, read by EIC |
| `data/ramsay/mindpattern/user.md` | User profile — evolves | NEW — source of truth, read by EIC |
| `data/ramsay/mindpattern/voice.md` | Public persona — evolves | NEW — replaces agents/voice-guide.md |
| `data/ramsay/mindpattern/decisions.md` | Append-only editorial decision log | NEW — source of truth |
| `orchestrator/pipeline.py` | Pipeline state machine | MODIFIED — added EVOLVE + MIRROR phases |
| `orchestrator/runner.py` | Phase handler methods | MODIFIED — added _phase_evolve(), _phase_mirror() |
| `social/engagement.py` | Engagement pipeline | MODIFIED — added search_via_jina(), LinkedIn draft-only mode |
| `social/approval.py` | iMessage approval gates | MODIFIED — multi-identity polling, post-send ROWID baseline |
| `social/pipeline.py` | Social content pipeline | MODIFIED — removed X |
| `social/posting.py` | Platform API clients | BlueskyClient + LinkedInClient (XClient removed) |
| `social/critics.py` | Critic + expeditor | MODIFIED — voice.md path |
| `social/writers.py` | Writer dispatch | MODIFIED — voice.md path, kill switch |
| `social-config.json` | Platform + engagement config | MODIFIED — X removed, LinkedIn engagement added, identities list |
| `policies/social.json` | Deterministic policy rules | MODIFIED — "I run agents" patterns, X removed |
| `agents/eic.md` | Editor-in-Chief agent | MODIFIED — reads soul.md + user.md, kill switch |
| `agents/bluesky-writer.md` | Bluesky writer agent | MODIFIED — kill switch |
| `agents/linkedin-writer.md` | LinkedIn writer agent | MODIFIED — kill switch |
| `verticals/ai-tech/agents/*.md` | 13 research agent definitions | MODIFIED — Agent Reach tool instructions added |
| `~/.claude/settings.json` | Global Claude Code settings | HAS SessionEnd hook for lilyjacks memory |
| `/Users/taylerramsay/Projects/lilyjacks/src/hooks/session-memory.ts` | Existing SessionEnd hook | Parses transcripts, stores memories in LilyJacks |

### Key Patterns Discovered

1. **iMessage chat_identifier varies by device**: Phone number from one device, email from another. Fixed with `identities` config list searching all associated chats.

2. **is_from_me inconsistency**: User replies from iPhone show as is_from_me=0 or is_from_me=1 depending on iCloud sync. Poll accepts both.

3. **ROWID baseline must be captured AFTER sending**: Capturing before sending means stale replies from previous runs get missed because messages in other chats push the global ROWID higher.

4. **EIC generates "I run agents" in its reaction field**: The reaction template encouraged personal references to automation. Fixed with 5-layer kill switch (EIC instructions, writer prompt, writer agents, policy engine regex).

5. **Stale X draft files poison the expeditor**: The expeditor agent has file access (Read/Glob) and discovered old `x-draft.md` on disk even though X was disabled. Fixed by removing X entirely + deleting stale files.

6. **Obsidian needs UTF-8/LF/kebab-case/frontmatter**: All generated files must follow conventions or Obsidian misrenders.

7. **Agent Reach uses Jina Reader for LinkedIn search**: `curl https://s.jina.ai/QUERY site:linkedin.com` returns markdown with post URLs and content.

8. **Each `claude -p` subprocess creates its own session**: The global SessionEnd hook fires for every subprocess. The `transcript_path` in the hook's stdin JSON points to the full JSONL transcript with all reasoning.

## Work Completed

### Tasks Finished

- [x] Remove X (Twitter) from entire pipeline (config, imports, agents, draft files, policy)
- [x] Fix iMessage polling (multi-identity, post-send ROWID baseline)
- [x] Add "I run agents" 5-layer kill switch
- [x] Remove trailing `?` banned pattern (false LinkedIn positives)
- [x] Successfully post to Bluesky + LinkedIn E2E
- [x] Create memory/vault.py — atomic read/write (24 tests)
- [x] Seed soul.md, user.md, voice.md, decisions.md + folder indexes
- [x] Create 8 Jinja2 templates (25 tests)
- [x] Create memory/mirror.py — SQLite → markdown generation (26 tests)
- [x] Create memory/identity_evolve.py — LLM identity evolution (26 tests)
- [x] Wire EVOLVE + MIRROR phases into pipeline state machine
- [x] Switch all agents to read voice.md from Obsidian vault
- [x] Delete agents/voice-guide.md
- [x] Install Agent Reach (xreach, yt-dlp, feedparser, Jina Reader)
- [x] Add Agent Reach tool instructions to all 13 research agents
- [x] Add LinkedIn engagement discovery via Jina Reader search (13 tests)
- [x] Export new functions from memory/__init__.py
- [x] Mirror 49 newsletters into Obsidian vault
- [x] Add Gate 2 feedback log to Obsidian vault
- [x] Backfill all 27 historical daily logs
- [x] Add .gitignore for generated vault files

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| SQLite-primary, Obsidian as mirror | A: Markdown-primary, B: SQLite-primary + mirror, C: Peers | Keep what works (DB for pipeline), add human visibility |
| 4 source-of-truth files only | More files as source of truth | Only soul/user/voice/decisions need to be editable; everything else is derived |
| Autonomous evolution (no approval gates) | Gated, Hybrid, Autonomous | User reviews in Obsidian when they want, no friction |
| identity_evolve.py naming | evolve.py | Disambiguate from existing memory/evolution.py (agent spawn/retire) |
| LinkedIn engagement = draft-only | Auto-post, Draft-only | No LinkedIn Comments API access yet |
| Remove X entirely | Disable but keep code | Stale files caused expeditor failures, no API keys anyway |
| iMessage multi-identity search | Phone-only, Email config, Auto-detect | Phone handles and email handles create different chat IDs |
| Jinja2 for templates | String formatting, Mako | Already in requirements.txt, supports inheritance and filters |
| Generated files NOT in git | Track everything, Gitignore generated | Rebuilt every run, would bloat repo |

## Pending Work

### Immediate Next Steps — Claude Code Hooks + Per-Agent Folders

**This is the #1 priority for the next session.**

#### New Vault Structure: Per-Agent Folders

Instead of mirroring agent data into daily notes, create a folder per agent in the Obsidian vault:

```
data/ramsay/mindpattern/
├── agents/
│   ├── eic/
│   │   ├── _index.md                    # MOC for this agent
│   │   ├── 2026-03-15.md               # Full transcript: reasoning, decisions, scores
│   │   └── 2026-03-14.md
│   ├── news-researcher/
│   │   ├── _index.md
│   │   ├── 2026-03-15.md               # What it searched, what it found, why it chose topics
│   │   └── 2026-03-14.md
│   ├── bluesky-writer/
│   │   ├── _index.md
│   │   ├── 2026-03-15.md               # Draft iterations, voice decisions, critic feedback
│   │   └── 2026-03-14.md
│   ├── linkedin-writer/
│   ├── bluesky-critic/
│   ├── linkedin-critic/
│   ├── expeditor/
│   ├── security-researcher/
│   ├── ... (one folder per agent)
```

Each agent's daily file contains:
- Full reasoning and decision process (from transcript)
- Sources consulted and why
- What was considered and rejected
- Tool calls made (web searches, file reads)
- Final output with confidence levels
- Critic feedback received (for writers)
- Time taken

This data feeds into:
- **EVOLVE phase**: reads recent agent logs to understand what's working/failing
- **Tracing**: browse any agent's history in Obsidian, see patterns over time
- **Agent improvement**: the EVOLVE phase can note "security-researcher keeps getting rejected by EIC, deprioritize security topics"

#### Hook Implementation

1. **Add a pipeline-specific SessionEnd hook** that captures each `claude -p` agent's full transcript and saves it as a structured markdown file to the agent's folder. The hook should:
   - Receive `transcript_path` from stdin JSON
   - Parse the JSONL transcript
   - Extract reasoning, decisions, tool calls, outputs
   - Format as markdown with YAML frontmatter (`type: agent-log`, `date`, `agent`, `tags`)
   - Save to `data/ramsay/mindpattern/agents/{agent-name}/{date}.md`
   - Include `[[wiki-links]]` to daily log, topics, sources

2. **The hook needs to know WHICH agent is running**. Options:
   - Set an environment variable (`MINDPATTERN_AGENT=news-researcher`) before each `claude -p` call in the dispatcher
   - Parse the agent name from the system prompt file path in the transcript
   - Pass it as metadata in the `claude -p` command

3. **Add hooks for ALL pipeline agents** — EIC, writers, critics, expeditor, engagement agents, humanizer. Every `claude -p` subprocess gets its transcript captured.

4. **The existing lilyjacks SessionEnd hook** fires alongside the new one. Both hooks coexist in `~/.claude/settings.json` under SessionEnd — hooks array supports multiple entries.

5. **Update MIRROR phase** to generate `_index.md` for each agent folder with links to all runs. Also update daily notes to link to agent logs via `[[agents/{agent-name}/{date}]]`.

### Remaining Phase 1 Items

- [ ] Verify EVOLVE phase works in a real pipeline run (not yet tested E2E with LLM call)
- [ ] Verify MIRROR phase works in production pipeline run
- [ ] Merge `feat/obsidian-memory` to main after E2E validation
- [ ] Update Fly.io sync to include agent-logs if needed

### Phase 2: Interactive iMessage (after hooks)

- Always-listening iMessage daemon (launchd plist)
- Message router with gate lockfile (`/tmp/mindpattern-gate-active.lock`)
- Interactive handler dispatching `claude -p` with soul/user/voice context
- Conversation threading (SQLite table, 30-min expiry)
- Commands: "what did you find today?", "research [topic]", "draft a post about [topic]"

### Phase 3: Heartbeat (after interactive iMessage)

- Proactive agent every 30 minutes (launchd plist)
- Checks: RSS feeds, Bluesky notifications, LinkedIn email notifications (Gmail MCP), pipeline health
- Decides + acts: drafts responses, suggests engagement, flags breaking news
- Throttle: max 3 notifications/day, quiet hours 10PM-7AM, "quiet" command

### Phase 4: Remote Access (after heartbeat)

- Deploy to VPS with Claude Code CLI
- Slack/Telegram adapter (iMessage is macOS-only)
- Obsidian vault sync via git

### Deferred Items

- Editorial corrections table is empty — corrections happen in conversation, not captured at Gate 2. Need inline edit support in iMessage gates (Phase 2).
- Engagement pipeline min_likes/min_followers may need further tuning based on real runs
- The `\?[^)]*$` banned pattern was removed — LinkedIn posts ending with questions are now allowed. Monitor if this causes quality issues.
- Agent Reach Exa search requires `mcporter + Exa MCP` setup for full capability — currently using Jina Reader's `s.jina.ai` search as fallback

## Context for Resuming Agent

### Important Context

- **Branch**: `feat/obsidian-memory` — 12 commits ahead of main, NOT merged yet
- **GitHub**: `tayler-id/mindpattern-v3` on `main` branch
- **Obsidian vault**: `data/ramsay/mindpattern/` — user has it open in Obsidian, sees all files
- **DB is untouched**: 1,678 findings, 77 social_posts, same schema. Fly.io sync unaffected.
- **114 new tests all passing**: test_vault.py (24), test_templates.py (25), test_mirror.py (26), test_identity_evolve.py (26), test_engagement_linkedin.py (13)
- **Social pipeline confirmed working**: Full E2E post to Bluesky + LinkedIn completed today
- **Agent Reach installed**: xreach, yt-dlp, feedparser, Jina Reader all working
- **User email**: ramsay.tayler@gmail.com (iMessage identity — critical for poll matching)
- **User phone**: +17175783243
- **Bluesky**: webdevdad.bsky.social
- **LinkedIn**: urn:li:person:Q9nVn1PfNO
- **Fly.io app**: mindpattern (sjc region)
- **Resend API key**: macOS Keychain `resend-api-key`
- **v2 pipeline still running independently** at `/Users/taylerramsay/Projects/daily-research-agent-v2/`

### User Preferences (critical)

- **NEVER mention "I run agents", "my agents", "my pipeline", "cron job", "automation", "I build AI"** in any social post. This is the #1 user feedback. 5-layer kill switch is in place.
- User wants **autonomous evolution** — agent updates soul/user/voice/decisions without asking permission
- User wants to **see everything in Obsidian** — daily logs, agent reasoning, newsletters, decisions
- User prefers **Opus for important tasks**
- User wants **terse responses, no summaries**
- User likes **agent teams and parallel execution**
- User wants **self-improving systems** that learn run-over-run

### Assumptions Made

- LinkedIn access token valid (confirmed today, api_version=202504)
- Bluesky app password valid (confirmed, posts working)
- /bin/bash has Full Disk Access (confirmed, iMessage read/write works)
- Launchd plists point to v3 `run-launchd.sh`
- Resend API key in Keychain is valid (email sent today)
- The global SessionEnd hook fires for every `claude -p` subprocess (confirmed via research)

### Potential Gotchas

- **Two social pipelines**: v2 (`daily-research-agent-v2`) has its own pipeline running independently. Its iMessages may confuse the v3 poll. The v3 poll uses `min_rowid` baseline captured AFTER send, so this should be fine.
- **checkpoint resume**: The pipeline checkpoint may resume from a later phase. To force fresh: `python3 run.py --user ramsay --date YYYY-MM-DD`
- **Lock file**: `/tmp/mindpattern-pipeline.lock` must be removed if pipeline was killed
- **voice-guide.md is DELETED**: All references now point to `data/ramsay/mindpattern/voice.md`. If anything still references the old path, it will break.
- **Generated vault files are NOT in git**: `.gitignore` excludes daily/, topics/, sources/, social/, people/, newsletters/. Only soul.md, user.md, voice.md, decisions.md are tracked.
- **Obsidian auto-creates files**: Untitled.base, Untitled.canvas etc. appear in the vault. These are Obsidian defaults, not ours. User can delete them.
- **memory/evolution.py vs memory/identity_evolve.py**: Two different things. evolution.py = agent spawn/retire/merge. identity_evolve.py = soul/user/voice/decisions file updates.

## Environment State

### Tools/Services Used

- Python 3.14 (macOS, Homebrew)
- Claude CLI 2.1.76 (authenticated via Claude Pro subscription)
- SQLite (memory.db at data/ramsay/memory.db)
- fastembed (BAAI/bge-small-en-v1.5, 384-dim embeddings)
- Jinja2 3.1.6 (template rendering)
- Agent Reach 1.3.0 (xreach, yt-dlp, Jina Reader, feedparser)
- GitHub CLI (`gh`, authenticated as tayler-id)
- Resend API (email delivery)
- Bluesky API (webdevdad.bsky.social)
- LinkedIn API (api_version=202504)
- Fly.io CLI (`fly`, app: mindpattern)
- LilyJacks MCP (memory system)
- Obsidian (vault at data/ramsay/mindpattern/)

### Active Processes

- v2 research pipeline may still be running (check `ps aux | grep "daily-research-agent-v2"`)
- Obsidian has the vault open

### Environment Variables

- `API_TOKEN_HASH` — dashboard auth (set on Fly.io, NOT configured locally)
- Keychain: `resend-api-key`, `bluesky-app-password`, `linkedin-access-token`

## Related Resources

- **Spec**: `docs/superpowers/specs/2026-03-15-obsidian-memory-evolution-design.md`
- **Phase 1 Plan**: `docs/superpowers/plans/2026-03-15-phase1-obsidian-memory.md`
- **Previous handoff**: `.claude/handoffs/2026-03-15-161621-v3-social-pipeline-fixes.md`
- **V2 reference**: `/Users/taylerramsay/Projects/daily-research-agent-v2/`
- **V1 reference**: `/Users/taylerramsay/Projects/daily-research-agent copy/`
- **Vercel frontend**: `/Users/taylerramsay/Projects/vercel-mindpattern/`
- **LilyJacks hook**: `/Users/taylerramsay/Projects/lilyjacks/src/hooks/session-memory.ts`
- **Claude Code hooks docs**: https://code.claude.com/docs/en/hooks.md
- **Cole Medin OpenClaw video**: Inspiration for soul.md/heartbeat/channel adapters approach
- **Agent Reach**: https://github.com/Panniantong/Agent-Reach

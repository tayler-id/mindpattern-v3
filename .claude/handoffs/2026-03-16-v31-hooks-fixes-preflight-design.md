# Handoff: V3.1 Hooks + Fixes + Preflight Redesign

## Session Metadata
- Created: 2026-03-16 ~11:00
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: feat/obsidian-memory
- Session duration: ~14 hours (started previous evening, continued through morning)

### Recent Commits
```
4caf3f4 docs: research agent preflight redesign spec
20641d8 feat: create rss-feeds.json with 67 feeds (AI, fintech, SaaS disruption)
a2d63e1 feat: merge subagent transcripts into parent agent log
8f267a9 feat: add NOVELTY REQUIREMENT to agent prompts
417c66b fix: re-allow Agent tool for research agents — blocking it halved findings
49ed377 fix: relax dedup threshold (0.92, 7 days) and increase agent timeout to 30min
6854832 fix: block Agent/Write/Edit on all claude -p calls to prevent output hijacking
c6a7ed0 feat: rewrite transcript formatting for clean Obsidian display
e306d23 fix: separate Reasoning/Output sections, remove truncation, full content
b083846 fix: capture thinking blocks from transcripts (not just text blocks)
faad14b fix: improve transcript formatting, block subagent dispatch
b08b769 docs: add plan for fixing partially-working Phase 1 features
9f88a23 chore: update vault identity files after E2E pipeline run
37984d3 fix: migrate remaining voice-guide.md refs to data/ramsay/mindpattern/voice.md
08a141d feat: add SessionEnd hook, per-agent transcript capture, agent indexes
039f62b feat: enrich EVOLVE prompt with social results, gate outcomes, newsletter scores
dd08041 feat: make Agent Reach mandatory in all research agent prompts
da56ad8 feat: capture multi-turn reasoning and tool results in agent transcripts
e3e52de fix: strip v2-era PLATFORM/TYPE prefix from social posts in vault
d665c5a fix: use config values for engagement filtering instead of hardcoded defaults
```

## Handoff Chain
- **Continues from**: `.claude/handoffs/2026-03-15-214717-v31-obsidian-memory-and-hooks.md`
- **Supersedes**: All items from that handoff are resolved

## Current State Summary

This session accomplished three major things:

### 1. Built the Hook System (COMPLETE)
- `hooks/session-transcript.py` — SessionEnd hook captures every `claude -p` transcript
- Parses JSONL transcripts including `thinking` blocks (Claude's reasoning between tool calls)
- Merges subagent transcripts from `{session_id}/subagents/` into parent log
- Writes structured markdown to `data/ramsay/mindpattern/agents/{agent-name}/{date}.md`
- Format: summary bar → reasoning steps → tool calls → research results (collapsible) → final output (pretty-printed JSON)
- No truncation — user wants full content
- Registered in `~/.claude/settings.json` alongside lilyjacks hook
- `orchestrator/agents.py` injects `MINDPATTERN_AGENT`, `MINDPATTERN_DATE`, `MINDPATTERN_VAULT` env vars in all 3 subprocess.run calls

### 2. Fixed Partially Working Features (COMPLETE)
- **EVOLVE enrichment** — prompt now includes social pipeline results (topic, gate1/gate2 outcomes, expeditor verdict, newsletter eval scores). Decisions.md instruction says "MUST ALWAYS append detailed entry"
- **Engagement filtering** — defaults fixed from hardcoded min_likes=3/min_followers=50 to config values min_likes=0/min_followers=10
- **Social posts cleanup** — v2-era `PLATFORM:/TYPE:` prefix stripped from old posts in vault
- **Voice-guide.md migration** — 8 remaining stale references fixed across agent files + social/eic.py
- **Duplicate reports on Fly.io** — sync.py now cleans timestamped report files. Removed all old duplicates. 30 unique newsletters.
- **Timestamped report backups** — removed from runner.py (was creating files like 2026-03-15-223549.md that caused duplicates)
- **Dedup threshold** — relaxed from 0.85/30 days to 0.92/7 days
- **Agent timeout** — bumped from 1200s to 1800s, max_turns 15→25
- **Novelty requirement** — agents must filter against recent findings, prioritize last 24 hours
- **--disallowedTools** — `run_claude_prompt` blocks Agent/Write/Edit/NotebookEdit (prevents synthesis from writing newsletter to file instead of stdout). `run_agent_with_files` blocks Agent only.
- **Launchd reliability** — `run-launchd.sh` is now idempotent (marker file `/tmp/mindpattern-ran-{date}`), has caffeinate, lock check. Plist has `RunAtLoad=true` for catch-up after missed schedule. pmset wakepoweron at 6:55 AM already configured. Unloaded old autoresearch plist.

### 3. Designed Preflight Redesign (SPEC WRITTEN, NOT IMPLEMENTED)
- **Spec**: `docs/superpowers/specs/2026-03-16-research-agent-preflight-redesign.md`
- Two-phase architecture: Python preflight gathers ~280 items from 8 sources, dedup-annotates, routes to agents. Agents evaluate (floor) then explore with Agent Reach (ceiling).
- Preflight sources: RSS (67 feeds), HN, arXiv, GitHub, Reddit, Twitter (xreach), Exa (mcporter), YouTube (yt-dlp)
- All tools installed and verified working

## Critical Bugs Found and Fixed This Session

### Newsletter Broken (synthesis wrote to file)
The synthesis_pass2 agent had `Write` in its allowed tools. It found the vault's newsletter folder and wrote the 4,911-word newsletter to `data/ramsay/mindpattern/newsletters/2026-03-16.md` instead of returning it via stdout. The pipeline only captured a 46-word summary and emailed that. Fixed by adding `--disallowedTools Agent,Write,Edit,NotebookEdit` to `run_claude_prompt`. Newsletter was manually recovered from the vault and re-sent via Resend.

### --disallowedTools Agent Halved Findings
Blocking the Agent tool on `run_single_agent` prevented agents (arxiv, hn, news, rss, etc.) from dispatching subagents. These agents were DESIGNED to use subagents for research. Findings dropped from 100+ to 64. Reverted — Agent tool is now allowed for research agents. Only `run_claude_prompt` (synthesis, evolve, etc.) blocks Agent/Write/Edit.

### Transcript Reasoning = 1 Block
JSONL transcripts use `thinking` type blocks for Claude's reasoning, not `text` blocks. The hook was only looking for `text`, so every agent showed `reasoning_blocks: 1`. Fixed to capture both `text` and `thinking` blocks.

## Pending Work

### Immediate Next: Implement Preflight System
The spec is complete at `docs/superpowers/specs/2026-03-16-research-agent-preflight-redesign.md`. Needs a writing-plans pass to create the implementation plan, then execution.

Key files to create:
- `preflight/` module (8 source scripts + run_all.py)
- Rewrite `orchestrator/runner.py` `_phase_research()` to call preflight
- Rewrite `orchestrator/agents.py` `build_agent_prompt()` to include preflight data
- Rewrite all 13 agent `.md` files for Phase 1/Phase 2 structure

### Still Not Built (from original v3.1 spec)
- **Phase 2: Interactive iMessage** — always-listening daemon, conversation threading
- **Phase 3: Heartbeat** — proactive 30-min agent
- **Phase 4: Remote Access** — VPS deployment

### Known Issues
- **Engagement still finds 0 candidates** — Bluesky search returns posts but all get filtered. LinkedIn Jina search returns nothing. May need different search queries or lower thresholds.
- **EVOLVE decisions entry exceeded 500 char limit** — need to bump `MAX_SECTION_LENGTH` in vault.py or make decisions append not go through section update
- **xreach Twitter search cookies** — configured from Chrome, working, but cookies expire. May need periodic refresh.
- **Some RSS feeds broken** — Anthropic Blog, The Batch, Meta AI, Cursor Changelog, Max Woolf return XML parse errors. feedparser handles gracefully (skips them) but those sources are missed.

## Environment State

### Tools Installed and Verified
- Python 3.14 (macOS, Homebrew)
- Claude CLI 2.1.76 (authenticated via Claude Pro subscription)
- Agent Reach: xreach 0.3.3 (Twitter cookies configured), yt-dlp 2026.03.13 (JS runtime configured), feedparser 6.0.12
- mcporter (Exa semantic search configured at https://mcp.exa.ai/mcp)
- Jina Reader (curl https://r.jina.ai/URL)
- 5 fetch scripts in tools/ (arxiv, github, hn, reddit, rss)
- 67 RSS feeds in verticals/ai-tech/rss-feeds.json (75 entries per 48hrs)
- agent-reach doctor: 9/15 channels available

### Launchd
- `com.taylerramsay.daily-research` — loaded, RunAtLoad=true, 7 AM schedule, idempotent wrapper
- `com.taylerramsay.autoresearch` — UNLOADED (was pointing to old autoresearch.py)
- pmset wakepoweron at 6:55 AM

### Pipeline State
- Today's run (March 16) completed: 125 raw findings, 64 stored, newsletter broken then recovered and re-sent
- Social: posted to Bluesky + LinkedIn (Pragmatic Engineer survey topic)
- EVOLVE: updated soul.md Self Assessment, decisions entry truncated at 500 chars
- Sync: 7MB uploaded to Fly.io, 30 unique reports (no duplicates)
- 25 agent transcripts captured in vault

### Key Paths
- Vault: `data/ramsay/mindpattern/`
- Reports: `reports/ramsay/`
- Agent transcripts: `data/ramsay/mindpattern/agents/{name}/{date}.md`
- Social drafts mirror: `data/ramsay/mindpattern/social/drafts/{date}/`
- Preflight spec: `docs/superpowers/specs/2026-03-16-research-agent-preflight-redesign.md`
- Phase 1 fixes plan: `docs/superpowers/plans/2026-03-15-fix-partially-working-features.md`
- V3.1 original spec: `docs/superpowers/specs/2026-03-15-obsidian-memory-evolution-design.md`

### User Preferences (critical)
- **NEVER mention "I run agents"** etc. in social posts — 5-layer kill switch in place
- Wants **consistency AND depth** from research agents
- Wants **everything visible in Obsidian** — full reasoning, no truncation
- Wants **self-improving systems** that learn run-over-run
- Wants **fintech and SaaS disruption** coverage (feeds added)
- Prefers **Opus for important tasks**, agents run on Sonnet (1M context available)
- **Terse responses, no summaries**
- Email: ramsay.tayler@gmail.com
- Phone: +17175783243
- Bluesky: webdevdad.bsky.social
- LinkedIn: urn:li:person:Q9nVn1PfNO

## Related Resources
- Previous handoff: `.claude/handoffs/2026-03-15-214717-v31-obsidian-memory-and-hooks.md`
- V3.1 spec: `docs/superpowers/specs/2026-03-15-obsidian-memory-evolution-design.md`
- Preflight spec: `docs/superpowers/specs/2026-03-16-research-agent-preflight-redesign.md`
- Phase 1 fixes plan: `docs/superpowers/plans/2026-03-15-fix-partially-working-features.md`
- Sandwich Pattern article: https://medium.com/@wasowski.jarek/building-ai-workflows-neither-programming-nor-prompt-engineering-cdd45d2d314a
- Agent Reach: https://github.com/Panniantong/Agent-Reach

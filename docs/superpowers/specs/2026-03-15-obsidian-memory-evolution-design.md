# MindPattern v3.1 — Obsidian Memory, Evolving Identity, Interactive iMessage

## Summary

Transform MindPattern from a batch content factory into an evolving personal AI system. Add Obsidian-visible memory, self-evolving identity files, interactive iMessage conversations, a proactive heartbeat, and expanded research/engagement via Agent Reach.

## Build Phases

1. Obsidian memory + evolving soul/user/decisions
2. Interactive iMessage (talk to it anytime)
3. Heartbeat (proactive agent every 30 min)
4. Remote access (always-on VPS)

This spec covers all 4 phases. Each phase builds on the previous but is independently deployable.

---

## Phase 1: Obsidian Memory + Evolving Identity

### 1A. Vault Structure

Obsidian vault points at: `~/Projects/mindpattern-v3/data/ramsay/mindpattern/`

```
data/ramsay/mindpattern/
├── soul.md                    # SOURCE OF TRUTH — agent personality, evolves
├── user.md                    # SOURCE OF TRUTH — who Tayler is, evolves
├── voice.md                   # SOURCE OF TRUTH — public persona, evolves
├── decisions.md               # SOURCE OF TRUTH — append-only editorial log
├── daily/
│   └── YYYY-MM-DD.md          # GENERATED — full daily activity log
├── topics/
│   └── {topic-slug}.md        # GENERATED — recurring topic context
├── sources/
│   └── {source-slug}.md       # GENERATED — source reliability + history
├── social/
│   ├── posts.md               # GENERATED — posted content log
│   ├── corrections.md         # GENERATED — editorial corrections
│   └── engagement-log.md      # GENERATED — engagement activity
└── people/
    └── engaged-authors.md     # GENERATED — authors engaged with
```

Two categories:
- **Source of truth (4 files)**: soul.md, user.md, voice.md, decisions.md — pipeline reads directly, EVOLVE phase updates them autonomously. User can also edit in Obsidian; changes are respected on next run.
- **Generated mirrors (everything else)**: rebuilt from SQLite after each run. Read-only in practice — edits get overwritten.

**File safety**: All writes use atomic write (write to `.tmp` file, then `os.rename()`) to prevent corruption if the pipeline crashes mid-write or Obsidian has the file open. Obsidian's `fs.watch` picks up changes within 1-2 seconds automatically.

**Obsidian conventions** (apply to all generated files):
- **Encoding**: UTF-8 only, `\n` line endings (no BOM)
- **Filenames**: kebab-case, lowercase, no special characters (`ai-security.md` not `AI Security.md`)
- **YAML frontmatter** on every file with at minimum: `type`, `date`, `tags`. Quote values containing colons. Use list syntax for tags (`tags:\n  - tag1`).
- **Wiki-links**: `[[note-name]]` or `[[note-name|Display Text]]`. Link first mention only, 3-7 links per note. Every note must have at least 1 outbound link (no orphans).
- **Index files**: Each subfolder gets a `_index.md` that serves as a Map of Content (MOC) hub — links to all files in that folder. These become large nodes in graph view.
- **Dataview compatibility**: Use `type` field in frontmatter for queries like `FROM "" WHERE type = "daily"`. Use inline fields (`Key:: Value`) sparingly in generated content for queryable metadata.
- **Recommended plugins**: Dataview, Periodic Notes, Calendar, Dataview Serializer (converts live queries to static markdown for agent readability), Obsidian Git (auto-backup vault)

### 1B. Source of Truth Files

#### soul.md — Agent Identity (evolves)

Initial seed from v2 SOUL.md + current pipeline behavior. Contains:
- Core editorial values (signal over noise, primary sources first, etc.)
- Personality traits (skeptical of hype, technically precise, builder-oriented)
- Learned preferences (topics to prioritize/deprioritize, based on Gate 1/2 patterns)
- Self-assessment (what the pipeline does well, where it struggles)
- Editorial stance evolution log (dated entries: "deprioritizing pure security CVEs after 3 consecutive rejections")

#### user.md — User Profile (evolves)

Initial seed from current voice-guide.md bio section + LilyJacks memories. Contains:
- Role, stack, projects, experience (Tayler's background)
- Current priorities and interests (updates as interests shift)
- Communication preferences (terse responses, no summaries, etc.)
- Observed patterns ("approves security threads with business impact quickly", "always edits LinkedIn posts to remove questions at the end")
- Kill switches ("never mention running agents, pipeline, automation, cron jobs")

#### voice.md — Public Persona (evolves, replaces agents/voice-guide.md)

Initial content: current `agents/voice-guide.md` contents. Evolves from:
- Editorial corrections at Gate 2 (before/after pairs teach it your voice)
- Expeditor feedback (new banned patterns get added)
- Post performance data (future: which voice patterns get more engagement)

Agents that read it: writers, critics, expeditor, humanizer.

#### decisions.md — Editorial Decision Log (append-only)

Each run appends a `## YYYY-MM-DD` dated entry:
- Topic selected/killed + scores + reasoning
- Gate 1 outcome (approved, rejected, custom topic, guidance)
- Gate 2 outcome (approved, rejected, edits made)
- Expeditor verdict + reasoning
- Pattern observations ("3rd security topic rejected this week")
- Any corrections applied

**Growth management**: EVOLVE phase reads only the last 7 entries (parsed from end of file by `## ` boundaries). Entries older than 90 days are archived to `decisions-archive.md` during MIRROR phase.

### 1C. Generated Mirror Files

#### daily/YYYY-MM-DD.md

YAML frontmatter: `type: daily`, `date: YYYY-MM-DD`, `tags: [daily-note]`, `agents_run: N`, `findings_count: N`, `posts: [bluesky, linkedin]`.

Full activity log for one pipeline run. Contains:
- Per-agent section for each research agent that participated in this run:
  - Focus areas for this run
  - All findings with importance ratings
  - Decision reasoning (why they chose these topics)
  - Sources consulted
- Synthesis phase results (word count, topic, quality score)
- Social phase results (EIC selection, writer scores, critic verdicts, policy results, expeditor verdict, gate outcomes, posted URLs)
- Engagement phase results (queries generated, posts found, candidates ranked, replies drafted/posted)
- Memory evolution summary (what changed in soul/user/voice/decisions)

#### topics/{topic-slug}.md

YAML frontmatter: `type: topic`, `date: YYYY-MM-DD` (last updated), `tags: [topic, {subtags}]`, `finding_count: N`, `first_seen: YYYY-MM-DD`.

Generated from findings + patterns tables. One file per recurring topic cluster:
- Topic name and description
- Finding count and date range
- Key findings (last 30 days) — each linking to its `[[daily/YYYY-MM-DD]]` note
- Sources that cover this topic — each linking to `[[sources/{source-slug}]]`
- Posts made about this topic
- Cross-references to related topics via `[[topics/{related-slug}]]` links

#### sources/{source-slug}.md

YAML frontmatter: `type: source`, `date: YYYY-MM-DD` (last updated), `tags: [source]`, `url: "https://..."`, `finding_count: N`, `eic_selection_rate: 0.N`.

Generated from sources table:
- Source name and URL
- Finding count and reliability history
- Topics covered — each linking to `[[topics/{topic-slug}]]`
- Most recent findings from this source — each linking to `[[daily/YYYY-MM-DD]]`
- Quality assessment (how often findings from this source get selected by EIC)

#### social/posts.md

Generated from social_posts table:
- Reverse-chronological list of posted content
- Platform, date, content, gate outcomes
- Links to daily log entries

#### social/corrections.md

Generated from editorial_corrections table:
- Before/after pairs with dates
- Reason for correction
- Platform

#### social/engagement-log.md

Generated from engagements table:
- Replies posted (platform, author, content, our reply)
- Follows made
- Date and outcome

#### people/engaged-authors.md

Generated from engagements table:
- Authors engaged with, grouped by platform
- Interaction history (dates, what we replied to)
- Follow status

### 1D. Pipeline Integration

#### New Pipeline Phase: EVOLVE (after LEARN, before SYNC)

One Sonnet call. Reads:
- Current soul.md, user.md, voice.md, decisions.md
- Today's pipeline results (topic selected, gate outcomes, corrections, expeditor feedback)
- Recent patterns from memory (last 7 days of decisions)

Outputs a JSON diff:
```json
{
  "soul": {"action": "update|none", "section": "learned_preferences", "content": "..."},
  "user": {"action": "update|none", "section": "observed_patterns", "content": "..."},
  "voice": {"action": "update|none", "section": "banned_phrases", "content": "..."},
  "decisions": {"action": "append", "content": "## 2026-03-15\n..."}
}
```

**Safety guardrails** for LLM-controlled file writes:
1. Validate JSON diff schema strictly before applying (reject unknown keys)
2. Max 500 characters per section update (prevent runaway rewrites)
3. All changes logged to decisions.md for auditability
4. If JSON parsing fails, log the error and skip EVOLVE (don't crash)
```

Python applies the diff using `## ` heading-delimited sections:
1. Parse the markdown file into sections by splitting on `\n## ` boundaries
2. Match the JSON diff's `"section"` value to a `## ` heading (case-insensitive)
3. If section exists: replace its content (everything between this `## ` and the next `## ` or EOF)
4. If section does not exist: append a new `## {section_name}` at the end of the file
5. decisions.md is always append (add dated entry at the bottom, no section matching)
6. Library: pure Python string operations (no markdown AST needed)

#### New Pipeline Phase: MIRROR (after EVOLVE, before SYNC)

Pure Python, no LLM. Queries SQLite and generates/overwrites all mirror files using Jinja2 templates (add `jinja2` to `requirements.txt`). Includes Obsidian `[[wiki-links]]` for graph view connectivity. All writes use atomic write strategy (write to `.tmp`, then `os.rename()`).

EVOLVE and MIRROR are added to `SKIPPABLE_PHASES` in `pipeline.py` — a failure in either should not prevent SYNC or mark the pipeline as failed.

#### Updated Phase Order

```
INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → LEARN → SOCIAL → ENGAGEMENT → EVOLVE → MIRROR → SYNC → COMPLETED
```

#### Agent Prompt Updates

All agents that currently read `agents/voice-guide.md` switch to reading `data/ramsay/mindpattern/voice.md`. EIC additionally reads `soul.md` and `user.md`. Research agents read `soul.md` for prioritization.

### 1E. Agent Reach Integration

Install Agent Reach on the pipeline host. Research agents gain:

| Capability | Tool | Current | New |
|---|---|---|---|
| Web pages | Jina Reader (`curl https://r.jina.ai/URL`) | Claude built-in | Cleaner markdown |
| Twitter/X | xreach CLI | None | Search + read tweets |
| Reddit | Exa search | None | Search discussions |
| YouTube | yt-dlp | None | Subtitle extraction |
| RSS feeds | feedparser | None | Feed parsing |
| LinkedIn | Jina Reader | None | Read public pages |
| GitHub | gh CLI | Already have | Already have |

Research agent prompts updated to include Agent Reach tool instructions. Agents already have Bash tool access, so they call these CLI tools directly.

### 1F. Engagement Pipeline Expansion

Engagement platforms expand from `["bluesky"]` to `["bluesky", "linkedin"]`.

LinkedIn engagement flow:
1. LLM generates search queries (same as Bluesky)
2. Python calls Exa CLI (`agent-reach` search) via subprocess for LinkedIn discussions
3. Python calls Jina Reader (`curl https://r.jina.ai/URL`) via subprocess to fetch full post content as markdown
4. Filter by criteria (follower count, recency, relevance)
5. LLM ranks candidates
6. LLM drafts replies
7. **No auto-posting** — LinkedIn Comments API access not yet available. Drafted replies are saved to `data/social-drafts/engagement-linkedin.json` and sent via iMessage for manual posting. When API access is added later, auto-posting can be enabled.
8. Add `search_via_exa()` helper to `social/engagement.py` that wraps the Exa CLI subprocess call and normalizes results to the same format as `BlueskyClient.search()`

New in social-config.json:
```json
"engagement": {
    "platforms": ["bluesky", "linkedin"],
    ...
}
```

---

## Phase 2: Interactive iMessage

### 2A. Always-Listening iMessage Daemon

A separate process (launchd plist) that polls Messages.db every 15 seconds for new messages from any of the user's identities. When a message arrives that isn't a gate reply (no active gate polling), it routes to the interactive handler.

#### Message Router

```
Incoming message → Does /tmp/mindpattern-gate-active.lock exist?
  → Yes: ignore (gate poller will handle it)
  → No: interactive handler (new)
```

The pipeline creates `/tmp/mindpattern-gate-active.lock` when entering any gate poll and removes it when the gate resolves. The interactive daemon checks for this lockfile before routing to the interactive handler. This prevents race conditions where both processes try to read the same incoming message.

#### Interactive Handler

Dispatches a Claude Code subprocess (`claude -p`) with:
- System prompt including soul.md, user.md, voice.md
- Today's daily log for context
- Memory search results relevant to the query
- Available commands (research, draft, post, search, status)

Response sent back via iMessage (existing `_imessage_send`).

### 2B. Conversation Threading

Messages.db tracks conversations naturally. The handler maintains context by:
- Storing conversation state in a SQLite table (message_id, context_json, expires_at)
- Including last 5 messages in the conversation as context for the LLM call
- Auto-expiring conversations after 30 minutes of inactivity

### 2C. Capabilities

| Command | Behavior |
|---|---|
| "What did you find today?" | Returns summary from daily log |
| "Research [topic]" | Spawns a focused research agent, replies with findings |
| "Draft a post about [topic]" | Runs social pipeline for specific topic |
| "Search [query]" | Semantic search across memory, returns top results |
| "Status" | Pipeline health, last run time, pending gates |
| Free-form questions | Routes to Claude with full memory context |

---

## Phase 3: Heartbeat

### 3A. Proactive Agent

A launchd plist running every 30 minutes. Reads:
- soul.md (personality, what to care about)
- user.md (current priorities)
- Recent daily logs
- Calendar (future integration)
- Email (future integration)

Decides whether to notify you via iMessage. Criteria:
- Breaking news in your interest areas (checks RSS feeds + trending topics)
- Engagement opportunities (high-value conversations appearing on Bluesky/LinkedIn)
- Pipeline issues (failed runs, approaching rate limits)
- Pattern insights ("you've rejected 5 security topics this week, should I deprioritize?")

### 3B. Notification Throttle

- Max 3 proactive messages per day (configurable)
- No notifications between 10 PM and 7 AM
- Never repeat a notification topic within 24 hours
- User can reply "quiet" to silence for 4 hours

---

## Phase 4: Remote Access

### 4A. VPS Deployment

Deploy the full pipeline + iMessage daemon + heartbeat to a VPS (or keep on Fly.io). Requirements:
- Claude Code CLI installed and authenticated
- Agent Reach installed
- iMessage alternative for VPS (since Messages.db is macOS-only): Slack adapter or Telegram bot
- SQLite database + Obsidian vault synced to VPS

### 4B. Sync Strategy

- Obsidian vault synced via git (push after each run)
- SQLite synced via existing Fly.io sync mechanism
- Claude Code CLI authenticated via API key (not subscription — different auth for server)

---

## Module Boundaries (for parallel development)

Each module can be built and tested independently:

| Module | Depends On | Test Strategy |
|---|---|---|
| `memory/vault.py` — read/write source-of-truth .md files | File system only | Unit tests with temp directory |
| `memory/identity_evolve.py` — EVOLVE phase (LLM updates identity files) | vault.py, run_claude_prompt | Unit tests with mock LLM responses |
| `memory/mirror.py` — MIRROR phase (generate .md from SQLite) | SQLite schema, vault.py | Unit tests with in-memory SQLite |
| `memory/templates/` — Jinja2 templates for mirror files | None | Template rendering tests |
| `social/engagement_linkedin.py` — LinkedIn engagement via Agent Reach | Agent Reach CLI, LinkedInClient | Integration tests with mock API |
| `social/interactive.py` — interactive iMessage handler | approval.py, vault.py | Unit tests with mock Messages.db |
| `orchestrator/heartbeat.py` — proactive agent | vault.py, interactive.py | Unit tests with mock clock |
| Agent prompt updates | voice.md path change | Existing pipeline E2E test |

### Parallel Workstreams

These can be built simultaneously by separate agents:

**Workstream A**: `memory/vault.py` + `memory/templates/` + `memory/mirror.py`
- Pure Python, no LLM calls, no API dependencies
- Read/write markdown files, generate mirrors from SQLite

**Workstream B**: `memory/identity_evolve.py` + agent prompt updates
- LLM integration for identity evolution
- Update all agent .md files to read from new paths

**Workstream C**: Agent Reach installation + research agent prompt updates
- Install Agent Reach, update research agent prompts with new tool instructions
- Test that agents can use xreach, yt-dlp, Jina Reader

**Workstream D**: LinkedIn engagement expansion
- Extend engagement pipeline to search/read/reply on LinkedIn
- Add Exa search + Jina Reader integration

**Workstream E** (Phase 2): `social/interactive.py` + iMessage daemon
- Interactive message handler, conversation threading
- launchd plist for always-on polling

**Workstream F** (Phase 3): `orchestrator/heartbeat.py`
- Proactive agent, notification throttle
- launchd plist for 30-minute schedule

Dependencies between workstreams:
```
A (vault/mirror) ← B (evolve) ← E (interactive) ← F (heartbeat)
C (agent reach) ← D (linkedin engagement)
```

A and C can be built in parallel. B starts after A. D starts after C. E starts after B. F starts after E.

---

## Files Changed

### New Files
- `memory/vault.py` — read/write source-of-truth markdown files
- `memory/identity_evolve.py` — EVOLVE phase logic (named to disambiguate from existing `memory/evolution.py` which handles agent spawn/retire)
- `memory/mirror.py` — MIRROR phase (SQLite → markdown generation)
- `memory/templates/` — Jinja2 templates for daily, topics, sources, social, people
- `data/ramsay/mindpattern/soul.md` — initial seed
- `data/ramsay/mindpattern/user.md` — initial seed
- `data/ramsay/mindpattern/voice.md` — copied from agents/voice-guide.md
- `data/ramsay/mindpattern/decisions.md` — empty initial
- `social/interactive.py` — interactive iMessage handler
- (no new file — LinkedIn engagement extends existing `social/engagement.py`)
- `orchestrator/heartbeat.py` — proactive agent
- `com.taylerramsay.mindpattern-interactive.plist` — launchd for iMessage daemon
- `com.taylerramsay.mindpattern-heartbeat.plist` — launchd for heartbeat

### Modified Files
- `orchestrator/runner.py` — add EVOLVE and MIRROR phases to phase order
- `orchestrator/pipeline.py` — add Phase.EVOLVE and Phase.MIRROR to enum + PHASE_ORDER
- `social/engagement.py` — add LinkedIn platform support
- `social-config.json` — add LinkedIn to engagement platforms
- `agents/eic.md` — read soul.md + user.md instead of hardcoded bio
- `agents/bluesky-writer.md` — read voice.md instead of voice-guide.md
- `agents/linkedin-writer.md` — read voice.md instead of voice-guide.md
- `social/writers.py` — update voice guide path
- `social/critics.py` — update voice guide path
- All research agent .md files — add Agent Reach tool instructions

### Removed Files
- `agents/voice-guide.md` — replaced by `data/ramsay/memory/voice.md`

---

## Success Criteria

### Phase 1
- [ ] Obsidian vault opens and displays all memory files with working graph view
- [ ] All generated markdown files contain at least one `[[wiki-link]]` and all link targets exist as files
- [ ] soul.md, user.md, voice.md, decisions.md exist with meaningful initial content
- [ ] After a pipeline run, daily log is generated with per-agent findings and decisions
- [ ] After a pipeline run, EVOLVE phase runs without error and either updates a file or logs a justified "no changes" decision
- [ ] Topics, sources, social, and people mirrors are generated and browseable
- [ ] Research agent prompts include Agent Reach tool instructions
- [ ] Engagement pipeline finds conversations and drafts replies for LinkedIn (manual posting — no auto-post until API access added)
- [ ] All references to `agents/voice-guide.md` point to `data/ramsay/mindpattern/voice.md`
- [ ] EVOLVE and MIRROR phases are in SKIPPABLE_PHASES — failure does not block SYNC
- [ ] EVOLVE rejects malformed JSON diffs without crashing
- [ ] All existing tests still pass
- [ ] Full E2E pipeline run succeeds (research → social → engagement → evolve → mirror)

### Phase 2
- [ ] Send "what did you find today?" via iMessage, get a summary back
- [ ] Send "research quantum computing" via iMessage, get findings back
- [ ] Conversation context maintained across 5+ messages
- [ ] Interactive handler does not interfere with gate polling during pipeline runs

### Phase 3
- [ ] Heartbeat runs every 30 minutes via launchd
- [ ] Receives at least one proactive notification per day
- [ ] Respects quiet hours and throttle limits
- [ ] "quiet" reply silences for 4 hours

### Phase 4
- [ ] Pipeline runs on remote VPS
- [ ] Obsidian vault synced to local machine
- [ ] Interactive messaging works from remote (via Slack/Telegram adapter)

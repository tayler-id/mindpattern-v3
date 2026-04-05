# MindPattern v3 — Complete System Overview

> Autonomous AI research pipeline. Runs daily at 7 AM. Gathers data from 8 sources,
> dispatches 13 research agents, writes a newsletter, posts to social media, and
> improves itself after every run.

---

## Table of Contents

1. [What Is MindPattern?](#what-is-mindpattern)
2. [Three Core Design Principles](#three-core-design-principles)
3. [The 12-Phase Pipeline](#the-12-phase-pipeline)
4. [Research Agents (13 Specialists)](#research-agents)
5. [Preflight Data Collection](#preflight-data-collection)
6. [Synthesis and Newsletter](#synthesis-and-newsletter)
7. [Social Media Pipeline](#social-media-pipeline)
8. [The Identity System](#the-identity-system)
9. [The Autonomous Harness (Self-Improvement)](#the-autonomous-harness)
10. [The Knowledge Graph](#the-knowledge-graph)
11. [The Slack Bot](#the-slack-bot)
12. [The Dashboard](#the-dashboard)
13. [Memory System](#memory-system)
14. [Observability and Traces](#observability-and-traces)
15. [Policy Engine](#policy-engine)
16. [Model Routing and Cost](#model-routing-and-cost)
17. [Infrastructure and Deployment](#infrastructure-and-deployment)
18. [Self-Improvement Loops](#self-improvement-loops)
19. [File Map](#file-map)
20. [Daily Lifecycle](#daily-lifecycle)

---

## What Is MindPattern?

MindPattern is a fully autonomous AI research and publishing pipeline — approximately
47,000 lines of Python. It operates as a one-person media company on autopilot:

1. **Wakes up at 7 AM** via macOS launchd
2. **Gathers ~400 items** from 8 sources (RSS, Hacker News, arXiv, GitHub, Reddit, Twitter, YouTube, LinkedIn)
3. **Dispatches 13 research agents** in parallel, each specializing in a different beat
4. **Synthesizes 150+ findings** into a 4,500-word newsletter
5. **Emails the newsletter** to subscribers via Resend
6. **Picks the best story**, writes platform-native social posts (Bluesky + LinkedIn), runs them through critics and quality gates, then posts
7. **Finds conversations** on social media to reply to
8. **Evolves its own identity** — updates its voice, values, and editorial stance
9. **Syncs everything** to Fly.io for the web dashboard

There is also a self-improving harness that finds bugs in the pipeline, writes fixes
using TDD, reviews its own PRs, and merges them — all autonomously.

---

## Three Core Design Principles

### Principle 1: Python Controls Flow, LLM Does Judgment

The pipeline is a **deterministic state machine**. Python decides what phase runs next,
in what order, and what happens on failure. Claude is only invoked for tasks requiring
judgment: reading papers, writing prose, scoring quality, proposing improvements.

The LLM never decides "what should I do next?" That's hardcoded in Python. This prevents
runaway behavior from LLM self-orchestration.

### Principle 2: Institutional Memory in SQLite

Everything the system learns persists across two SQLite databases:

- **`data/ramsay/memory.db`** (~21 MB, 17+ tables) — findings, social posts, preferences, patterns, claims, feedback, corrections, evolution log
- **`data/ramsay/traces.db`** (14 tables) — execution traces, phase timing, agent performance, cost tracking, quality history

Every function in the `memory/` module takes a `db` connection and returns data. Pure, testable, no side effects. WAL mode for concurrent access.

### Principle 3: Quality Gates Are Code, Not Prompts

Critical quality enforcement uses **deterministic Python** — regex, field validation, rate limiting, banned word lists. No prompt injection can bypass them:

- **Policy engine** (`policies/engine.py`): validates findings have required fields, checks for injection patterns, enforces character limits
- **Harness gates** (`harness/gates.py`): syntax checking via `ast.parse()`, secret scanning, debug statement detection, diff scope verification
- **Newsletter evaluator** (`orchestrator/evaluator.py`): scores coverage, dedup, sources, actionability — all via string matching, no LLM

---

## The 12-Phase Pipeline

The pipeline lives in `orchestrator/runner.py` (1,245 lines). The `ResearchPipeline` class
has a handler method for each phase. Phases execute in fixed order via a state machine
defined in `orchestrator/pipeline.py`.

### Phase Enum and Transitions

```
INIT -> TREND_SCAN -> RESEARCH -> SYNTHESIS -> DELIVER -> LEARN ->
SOCIAL -> ENGAGEMENT -> EVOLVE -> IDENTITY -> MIRROR -> SYNC -> COMPLETED
```

- **Critical phases** (RESEARCH, SYNTHESIS): failure stops the pipeline
- **Skippable phases** (all others): failure logs a warning, pipeline continues
- Forward-only transitions — no phase can go backwards

### Phase 1: INIT

Loads user config from `users.json`, opens database connections, checks for recent
failures, detects if any agent prompts changed since last run. If a previous run
crashed mid-way, finds the checkpoint and resumes from there via `orchestrator/checkpoint.py`.

### Phase 2: TREND_SCAN

Uses **Haiku** (cheapest model) to identify 5-8 trending topics. Pure JSON output:
`{"topic": "string", "evidence": "string", "relevance_score": 0.0-1.0}`. Gives
research agents a hint of what's hot today.

### Phase 3: RESEARCH (Critical)

Three sub-steps:

**Step A — Preflight** (`preflight/run_all.py`): Pure Python, no LLM. Fetches ~400
items from 8 sources in parallel via ThreadPoolExecutor. Deduplicates using local
embeddings (BAAI/bge-small-en-v1.5). Items matching recent findings at 80%+ cosine
similarity are marked `already_covered`.

**Step B — Agent Dispatch** (`orchestrator/agents.py`): 13 research agents run in
parallel (6 workers max). Each agent is a `claude -p` subprocess with the agent's skill
file, identity files, preflight data, and recent findings context. Each returns 15-20
structured findings as JSON.

**Step C — Cross-Agent Dedup**: All findings embedded and compared pairwise. 85%+
cosine similarity = deduplicated, keeping the higher-quality finding (weighted by
importance + URL presence).

### Phase 4: SYNTHESIS (Critical)

Two-pass newsletter generation using **Opus** (most capable model):

- **Pass 1**: `synthesis-selector.md` agent picks top 5 stories with best narrative thread
- **Pass 2**: `synthesis-writer.md` agent writes full 4,500-word newsletter. Structure: Top 5 Stories (300-500 words each) -> Section Deep Dives (100-200 words per finding) -> 10 Skills of the Day

After writing, `NewsletterEvaluator` scores output on 6 deterministic dimensions.
Retries up to 3 times on failure.

### Phase 5: DELIVER

Validates markdown report (strips LLM preamble, restores from backup if corrupted),
converts to HTML via `markdown2`, sends via **Resend API** with retry + exponential
backoff. Broadcasts to public subscribers (batch of 50, 2s delay between batches).

### Phase 6: LEARN

Memory consolidation:
- Extracts entity relationships from high-importance findings
- Regenerates `learnings.md`
- Checks for prompt regression — if a recent skill file edit caused quality to drop, flags it via `orchestrator/prompt_tracker.py`

### Phase 7: SOCIAL

Kicks off the 11-step social media pipeline (see Social Media Pipeline section below).

### Phase 8: ENGAGEMENT

Finds conversations on Bluesky/LinkedIn matching today's research topics. Drafts
substantive replies (actual data contributions, not "great point!"). Respects 7-day
cooldown per user and rate limits.

### Phase 9: EVOLVE

`memory/identity_evolve.py` reads today's editorial decisions, quality scores, and
feedback, proposes incremental updates to `soul.md`, `user.md`, and `voice.md`.
Changes are conservative — small adjustments, not rewrites.

### Phase 10: IDENTITY

Applies identity updates atomically via `memory/vault.py` (Obsidian vault never sees
partial writes).

### Phase 11: MIRROR

Self-reflection + memory export. Writes memory.db contents to Obsidian-compatible
markdown files for local browsing via `memory/mirror.py`.

### Phase 12: SYNC

`orchestrator/sync.py` bundles memory.db + traces.db + today's reports into a tar.gz,
uploads to Fly.io via `flyctl sftp`. The dashboard reads from this persistent volume.

---

## Research Agents

13 specialized agents, each with a skill file in `verticals/ai-tech/agents/`:

| Agent | Beat | Key Sources |
|-------|------|-------------|
| `news-researcher` | Breaking AI industry news | TechCrunch, Bloomberg, VentureBeat, Ars Technica |
| `agents-researcher` | Agent frameworks + security (40% security-focused) | LangChain, CrewAI, OpenAI Agents SDK, OWASP agentic top 10, ClawHub |
| `vibe-coding-researcher` | AI dev tools, Claude Code, MCP ecosystem | Claude Code releases, Cursor, Copilot SDK, MCP |
| `saas-disruption-researcher` | How AI reshapes SaaS categories | Category cannibalization, pricing shifts, builder moves |
| `thought-leaders-researcher` | Key voices in AI | Named individuals, contrarian takes |
| `reddit-researcher` | Reddit discussions | r/programming, r/MachineLearning |
| `hn-researcher` | Hacker News threads | Algolia API |
| `rss-researcher` | Blog posts and newsletters | 67 RSS feeds |
| `sources-researcher` | Primary source verification | Cross-referencing claims |
| `projects-researcher` | Open source projects | Notable new repos, tools |
| `github-pulse-researcher` | GitHub trending + releases | Trending repos, release notes |
| `arxiv-researcher` | Academic papers | arXiv CS, math, physics |
| `skill-finder` | New tools and techniques | Emerging patterns |

Each agent prompt includes:
- Critical output rules (IFScale pattern) at start AND end
- Soul identity + skill definition
- Dynamic context (trends, claims, novelty requirement)
- Preflight data in two phases (evaluate preflight first, then explore beyond)
- Research methodology with source verification + competing hypotheses gates
- Self-critique checklist (recency, dedup, source quality, verification, analysis)

Agent dispatch is managed by `orchestrator/agents.py` (935 lines):
- `build_agent_prompt()` — assembles the full agent prompt
- `run_single_agent()` — spawns `claude -p` subprocess with model routing
- `dispatch_research_agents()` — ThreadPoolExecutor, 6 workers, future-based collection
- `dedup_cross_agent_findings()` — embedding-based 85% similarity dedup
- `_parse_findings()` — robust JSON extraction with multiple fallback strategies

---

## Preflight Data Collection

`preflight/run_all.py` orchestrates 8 source fetchers (all in `tools/`):

| Source | Fetcher | What It Collects |
|--------|---------|-----------------|
| RSS | `tools/rss-fetch.py` | 67 feeds (bloggers, newsletters, VCs) |
| Hacker News | `tools/hn-fetch.py` | Top stories via Algolia API |
| arXiv | `tools/arxiv-fetch.py` | Papers in CS, math, physics |
| GitHub | `tools/github-fetch.py` | Trending repos + releases |
| Reddit | `tools/reddit-fetch.py` | r/programming, r/MachineLearning |
| Twitter | `tools/twitter-fetch.py` | Via xreach CLI tool |
| YouTube | `tools/youtube-fetch.py` | Transcripts via yt-dlp |
| LinkedIn | `tools/linkedin-verify.py` | Profile verification |

All fetchers run in parallel via ThreadPoolExecutor. Output is standardized via
`preflight/__init__.py`'s `make_entry()` factory (sanitizes external text, enforces
field structure). Batch deduplication at 80% similarity threshold with 10-day lookback
and 0.25 decay rate. Produces ~375 new items + ~25 already-covered items per run.

Items are routed to agents via `SOURCE_ROUTING` table mapping source types to agents.

---

## Synthesis and Newsletter

### Newsletter Evaluator (`orchestrator/evaluator.py`, 499 lines)

Deterministic Python quality scoring — no LLM calls. 6 dimensions, weighted composite:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Coverage | 0.25 | Do high-importance findings appear in newsletter? (keyword intersection) |
| Dedup | 0.20 | Are sections unique? (pairwise overlap >60% = duplicate) |
| Sources | 0.15 | % sections citing URLs |
| Actionability | 0.15 | Presence of "why it matters", "try this", action items |
| Length | 0.10 | Word count in 1500-3000 range |
| Topic Balance | 0.15 | User preferences coverage |

### Newsletter Delivery (`orchestrator/newsletter.py`, 667 lines)

- `validate_report()` — strips LLM preamble, detects synthesis agent junk, restores from backup if report < 1000 bytes
- `render_html()` — markdown2 with email-friendly styling (-apple-system font, 700px max-width)
- `send_newsletter()` — Resend API with 3-attempt retry + exponential backoff
- `broadcast_to_subscribers()` — batch email to public audience (max 50 per run, 2s delay)

---

## Social Media Pipeline

`social/pipeline.py` (36 KB) — 11-step content creation flow:

### Step 1: Topic Selection (EIC)
`agents/eic.md` — Editor-in-Chief scores findings on:
- **Novelty** (35% weight): genuinely new vs. rehash
- **Broad Appeal** (40% weight): would a non-technical VP have an opinion?
- **Thread Potential** (25% weight): 2-3 findings from different sources revealing same pattern

Quality threshold: 5.0/10. If nothing passes, posts nothing — silence > mediocre content.

### Step 2: Creative Brief
Creative Director (`agents/creative-director.md`) expands the winning topic into a brief with angle, framing, and reaction.

### Step 3: Art Generation
Optional DALL-E art via `social/art.py`.

### Step 4: Platform Writers (Parallel)
- **LinkedIn writer** (`agents/linkedin-writer.md`): 1200-1500 chars, professional depth, story-shaped lesson
- **Bluesky writer** (`agents/bluesky-writer.md`): 300-char max, conversational micro-take + link

### Step 5: Blind Critics (Parallel)
`social/critics.py` — critics score on 6 dimensions (0-10 each): voice match, framing authenticity, platform genre fit, epistemic calibration, structural variation, rhetorical framework.

### Step 6: Policy Validation
Deterministic checks via `policies/engine.py`: character limits, banned words, rate limits, injection patterns.

### Step 7: AI Humanization
`agents/humanizer.md` removes AI patterns (em dashes, rhetorical questions, "delve").

### Step 8: Expeditor Gate
`agents/expeditor.md` — final quality firewall with hard kill switches:
- Product pitch language ("powered by MindPattern")
- Banned words (delve, tapestry, multifaceted, testament, realm, landscape...)
- Factual errors, missing attribution, broken links
- "In conclusion" / "In summary" closings
- Multiple findings stacked without connecting thread

### Step 9: Slack Approval
Posts to `#mp-approvals` for human review. Gate 1 (topic) and Gate 2 (final posts).
Custom behavior: user can inject counter-narrative or data points.

### Step 10: Platform Posting
`social/posting.py` — Bluesky via AT Protocol, LinkedIn via OAuth API v202504.
Exponential backoff with jitter, Retry-After header support. Tokens stored in macOS Keychain.

### Step 11: Feedback Logging
Stores editorial corrections to memory.db for future voice training.

### Builder Credibility Rule
At least one platform post must include a specific infrastructure reference ("I run 12
agents", "my pipeline flagged this"). Missing = dock framing_authenticity 1-2 points.
Practitioner sharing setup = good; product pitch = kill.

---

## The Identity System

Four evolving markdown files in `data/ramsay/mindpattern/`:

### soul.md
Core editorial values and mission. What the system believes matters. Evolves based on editorial decisions.

### user.md
User context and perspective:
- 15+ years shipping production software
- 20+ years design background
- Shipped 3 solo products this year using Claude Code daily
- FinTech experience (Versatile Credit, $16B+ annually)
- Tech stack: Django, FastAPI, LangGraph, Neo4j, PostgreSQL, React/Next.js

### voice.md
Tone rules and rhetorical patterns:
- Contractions required, varied sentence length, specific numbers always
- Banned words: delve, tapestry, multifaceted, testament, realm, landscape, etc.
- Evidence grammar: facts -> analysis -> opinion (labeled as such)
- No "in conclusion", no relentless positivity, admit uncertainty
- Builder credibility: mention infrastructure naturally

### decisions.md
Append-only editorial decision log. Records: topic selected, gate outcomes, scores,
pattern notes. Used by EVOLVE phase to propose identity updates.

All four files are injected into every agent prompt. The EVOLVE phase updates them
incrementally. `memory/vault.py` handles atomic reads/writes. `memory/identity_evolve.py`
sanitizes vault content (strips YAML/wikilinks/templater injection, neutralizes HTML).

---

## The Autonomous Harness

`harness/` — a self-improving outer loop that finds bugs and fixes them autonomously.

### Core Design: Deterministic vs. Agentic Boundary

**DETERMINISTIC (Python, no LLM):**
- Ticket validation (JSON schema, file existence)
- Security sensitivity detection (path matching)
- Review depth routing (type -> depth mapping)
- Test execution (pytest), syntax validation (ast.parse)
- Secret scanning (regex), debug detection (regex)
- Diff scope checking (git diff vs allowed files)
- Ticket lifecycle, Slack notifications, audit logging

**AGENTIC (Opus 4.6, requires judgment):**
- Scout: finding issues by reading + understanding code
- Research: searching the web for ideas
- Plan: architecture analysis, error mapping, threat modeling
- Fix: writing tests + implementation
- Review: code quality assessment via specialist subagents

**Rule: if Python can do it reliably, Python does it. LLMs only for judgment.**

### The 5-Stage Pipeline (`harness/run.sh`)

**Stage 1 — SCOUT**: Opus agent reads traces.db for failures, scans codebase for bugs,
error handling gaps, performance issues. Creates 3-5 tickets as JSON in `harness/tickets/`.
Reads knowledge graph summary() to avoid duplicate tickets.

**Stage 2 — RESEARCH**: Opus agent searches web for techniques the pipeline could adopt.
Creates feature tickets with design specs and research source URLs.

**Stage 3 — PARALLEL FIX ROUNDS** (up to 10 tickets, 3 parallel):
1. Creates a **git worktree** (isolated repo copy) per ticket
2. **Fix agent** writes failing tests first (TDD), then implements
3. **Deterministic gates** run:
   - `gate_syntax_valid()` — `ast.parse()` all changed .py files
   - `gate_no_secrets()` — regex for API keys, Bearer tokens, Slack tokens
   - `gate_no_debug()` — no pdb/breakpoint/ipdb left
   - `gate_diff_scoped()` — only ticket-specified files modified
   - `gate_tests_pass()` — pytest full suite, hard fail
4. **Review agent** spawns 3 specialist subagents in parallel:
   - Testing specialist (coverage gaps, edge cases)
   - Security specialist (OWASP checks on the diff)
   - Maintainability specialist (DRY, naming, complexity)
5. Quality score >= 7/10 = PASS -> push branch, create PR
6. Quality < 7 = REJECT with detailed findings

**Stage 4 — CI**: GitHub Actions runs pytest on Ubuntu.

**Stage 5 — HEALTH REPORT**: `harness/health_report.py` posts daily Slack summary
with ticket counts by status/priority/type, stale tickets, issues logged, pipeline
status, success rate.

### Ticket Schema (`harness/tickets.py`)

```json
{
  "id": "YYYY-MM-DD-NNN",
  "title": "Short description",
  "type": "bug|improvement|feature|research",
  "source": "scout|research",
  "priority": "P1|P2|P3",
  "status": "open|in_progress|done|failed|held",
  "description": "Detailed description",
  "requirements": ["..."],
  "done_criteria": ["..."],
  "tdd_spec": {
    "test_file": "tests/test_something.py",
    "tests_to_write": ["test_name"]
  },
  "files_to_modify": ["path/to/file.py"],
  "context": "Additional context",
  "created_at": "ISO-8601",
  "expires_at": "ISO-8601 (+ 7 days)",
  "feedback_history": []
}
```

Ticket lifecycle: `pick_next()` returns highest-priority open ticket. `decay_stale()`
archives tickets past expiry (7 days for bugs, 14 for features). `record_pr_outcome()`
appends to feedback.json for scout learning.

### Quality Gates (`harness/gates.py`, 290 lines)

Pre-fix gates:
- `validate_ticket()` — JSON schema valid? Required fields? Referenced files exist?
- `check_security_sensitive()` — touches auth/API/data paths?
- `determine_review_depth()` — bug/improvement = eng-only; feature/research = full (CEO + eng); sensitive = +security

Post-fix gates (all deterministic, no LLM):
- `gate_tests_pass()` — pytest with parsed pass/fail counts
- `gate_syntax_valid()` — ast.parse() on all changed .py files
- `gate_no_secrets()` — regex: API keys, passwords, Bearer tokens, Slack xoxb tokens
- `gate_no_debug()` — regex: pdb, breakpoint(), ipdb
- `gate_diff_scoped()` — git diff only touches ticket-allowed files + test file

### Claude Code Hooks

- **Pre-Commit Hook** (`harness/hooks/pre_commit_gate.py`): blocks git commit if syntax errors, secrets, or debug statements found. Only fires in harness worktrees.
- **Post-Tool Hook** (`harness/hooks/post_tool_audit.py`): logs every tool call to `harness/audit.jsonl` for deterministic audit trail.

### Configuration (`harness/config.json`)

```json
{
  "stages": {
    "scout":    {"model": "opus", "max_turns": 20, "timeout_s": 900},
    "research": {"model": "opus", "max_turns": 25, "timeout_s": 900},
    "plan":     {"model": "opus", "max_turns": 30, "timeout_s": 900},
    "fix":      {"model": "opus", "max_turns": 40, "timeout_s": 1200},
    "review":   {"model": "opus", "max_turns": 25, "timeout_s": 900}
  },
  "parallel_agents": 3,
  "max_tickets_per_run": 10,
  "ticket_decay_days": 7,
  "review_pass_threshold": 7
}
```

---

## The Knowledge Graph

`harness/knowledge_graph.py` (324 lines) — a wiki-linked markdown knowledge base that
accumulates learnings across harness runs. This is the memory that makes the
self-improvement loops smarter over time.

### Structure

31 interconnected markdown files in `harness/knowledge/`:

```
harness/knowledge/
    INDEX.md                      # Master index with [[wiki-links]] to all files
    issues-open.md                # Current known bugs and fragile patterns
    patterns-what-works.md        # Approaches that produce good results
    patterns-what-fails.md        # Anti-patterns and failure modes
    runs-latest.md                # Latest harness run outcomes
    orchestrator-runner.md        # Module knowledge: runner.py
    orchestrator-agents.md        # Module knowledge: agents.py
    orchestrator-evaluator.md     # Module knowledge: evaluator.py
    orchestrator-newsletter.md    # Module knowledge: newsletter.py
    orchestrator-traces-db.md     # Module knowledge: traces_db.py
    orchestrator-checkpoint.md    # Module knowledge: checkpoint.py
    orchestrator-observability.md # Module knowledge: observability.py
    orchestrator-prompt-tracker.md# Module knowledge: prompt_tracker.py
    orchestrator-analyzer.md      # Module knowledge: analyzer.py
    orchestrator-router.md        # Module knowledge: router.py
    orchestrator-sync.md          # Module knowledge: sync.py
    orchestrator-pipeline.md      # Module knowledge: pipeline.py
    social-pipeline.md            # Module knowledge: social pipeline
    social-writers.md             # Module knowledge: writers
    social-approval.md            # Module knowledge: approval chain
    social-posting.md             # Module knowledge: posting clients
    memory-findings.md            # Module knowledge: findings storage
    memory-db.md                  # Module knowledge: database schema
    data-memory-db.md             # Data store: memory.db tables
    data-traces-db.md             # Data store: traces.db tables
    agents-research-agents.md     # Agent skill file inventory
    slack-bot-main.md             # Slack bot architecture
    harness-run.md                # Harness orchestrator
    harness-tickets.md            # Ticket lifecycle
    harness-issues.md             # Issue log
    harness-health-report.md      # Health reporting
```

### Wiki-Link System

Files connect via `[[wiki-links]]` that resolve to other knowledge files:
- `[[orchestrator/runner]]` -> `knowledge/orchestrator-runner.md`
- `[[issues/open]]` -> `knowledge/issues-open.md`
- `[[patterns/what-works]]` -> `knowledge/patterns-what-works.md`

Resolution: slugs use `/` for hierarchy, filenames use `-`. The `_slug_to_path()` function
converts `orchestrator/runner` -> `orchestrator-runner.md`.

### Core Operations

**`check()`** — Validates all `[[wiki-links]]` resolve to real files. Returns
`{broken: [...], valid: int, total: int}`. Runs after every evolution to catch
link rot.

**`expand(slug, depth=1)`** — Returns content of a knowledge file with all linked files
inlined (1 level deep). Like following hyperlinks and concatenating pages. Useful for
giving agents deep context on a specific module.

**`search(query)`** — Keyword search across all knowledge files. Scores by how many
query words appear. Returns matches with context line.

**`summary()`** — Returns a compact bundle for injection into agent prompts:
1. `ISSUES.md` (shared issue log — highest priority)
2. `INDEX.md` (module map with wiki-links)
3. `issues-open.md` (known bugs and fragile patterns)
4. `patterns-what-fails.md` (anti-patterns to avoid)
5. `patterns-what-works.md` (proven approaches)
6. `runs-latest.md` (what happened last time)

This is injected into the Scout prompt so it doesn't re-discover known bugs, doesn't
create duplicate tickets, and can build on proven patterns.

### How It Evolves

`evolve(stage, data)` is called after each harness stage:

| Stage | Trigger | What Gets Updated |
|-------|---------|-------------------|
| `scout_done` | Scout creates new tickets | `issues-open.md` gets "Scout Findings" section with ticket IDs, priorities, affected files |
| `fix_done` | Fix agent completes | `runs-latest.md` gets ticket outcome (passed/failed, PR URL, reason) |
| `review_done` | Review accepts or rejects | `patterns-what-works.md` (if merged) or `patterns-what-fails.md` (if rejected, with failure reason) |
| `run_complete` | Harness run finishes | `runs-latest.md` gets final summary (processed, PRs created, failed, remaining) |

After every evolution, `check()` re-validates all wiki-links and logs broken ones.

### What the Knowledge Graph Currently Knows

**What Works (producing good results):**
- 13 parallel agents with specialization: 230-254 findings per run consistently
- TDD in harness fix agents: catches regressions before merge
- Deterministic quality scoring: avoids burning LLM tokens on evaluation
- WAL mode for SQLite: enables concurrent reads during parallel agent writes
- Three-actor convergence rule: 3+ sources on same signal = Gate 1 pass
- Staggered worktree creation: 5s delay prevents git config lock races
- 15 max turns for fix agents: forces focus or fast fail

**What Fails (anti-patterns):**
- Research tickets too ambitious: M-effort features with external deps fail in 15 turns
- High max_turns (40) on Opus: burns tokens with no result
- Zero-findings systemic failure: Runs 12-13 produced nothing (root cause unknown)
- Sources score regression: drops to 0.333 when security topics dominate
- Migration ordering: CREATE INDEX before ALTER TABLE crashes production DBs
- Jina Reader errors passing through as content: curl exits 0 on error JSON
- Skill file missing = silent empty prompt -> garbage findings

**Known Open Issues:**
- Missing DB tables in memory/db.py — 4 tables referenced but never created in schema init
- Topic score stuck at 0 for 7+ consecutive runs
- Gate 1 silently auto-approves on exception
- Thread safety in embeddings module (module-level singleton not thread-safe)
- No transaction boundaries in findings storage
- MODEL_PRICING duplicated between router.py and observability.py
- TRACES_DB_PATH has hardcoded "ramsay" username

### The Learning Loop

```
Day 1:  Scout searches blindly, creates redundant tickets
        Knowledge graph = empty

Day 30: Scout reads summary(), avoids known failures, builds on proven patterns
        Knowledge graph = 31 files, 50+ patterns, 100+ ticket outcomes
```

The graph doesn't change what the optimal configuration is — it changes the efficiency
of the search for it. Instead of random exploration, the system does informed exploration
guided by accumulated evidence.

---

## The Slack Bot

`slack_bot/bot.py` — Socket Mode daemon that runs alongside the pipeline.

### Architecture
- Connects via Socket Mode (real-time events, not webhooks)
- Tokens from macOS Keychain: `slack-bot-token`, `slack-app-token`
- Routes messages to channel-based handlers
- Ignores own messages, filters by `owner_user_id` for security
- Mutex with pipeline via `/tmp/mindpattern-pipeline.lock`

### Channel Handlers

| Channel | Handler | Purpose |
|---------|---------|---------|
| `#mp-posts` | `PostsHandler` | Drop URL or idea -> run full social pipeline -> approve -> post |
| `#mp-engagement` | `EngagementHandler` | Conversation discovery + reply drafting |
| `#mp-approvals` | `ApprovalsHandler` | Topic + post approval gates |
| `#mp-briefing` | `BriefingHandler` | Daily/on-demand briefings |
| `#mp-skills` | `SkillsHandler` | Propose + track skill improvements |
| `#mp-tips` | `TipsHandler` | Actionable technique suggestions |
| `#mp-harness` | `HarnessHandler` | Self-improvement ticket coordination |

Each handler subclasses `BaseHandler` which provides:
- `reply(text, thread_ts)` — post message (optionally threaded)
- `react(emoji, ts)` — add reaction
- `wait_for_reply(thread_ts, timeout)` — poll for human response
- `read_url(url)` — Jina Reader integration for article content

---

## The Dashboard

FastAPI app on Fly.io (`dashboard/app.py`), deployed at `mindpattern.fly.dev`.

### Routes (14 routers)

| Route | Purpose |
|-------|---------|
| `pipeline_status` | Real-time phase tracking |
| `run_history` | Past runs with metrics |
| `findings` | Research findings browser with semantic search |
| `newsletters` | Newsletter drafts + published |
| `metrics` | Quality score trends |
| `performance` | Agent performance stats |
| `traces` | Execution traces with timing |
| `prompts` | Prompt version control |
| `skills` | Agent skill files inventory |
| `social_history` | Posts drafted + published |
| `engagement_history` | Replies + interactions |
| `editors_desk` | Editorial interface (findings review, approval) |
| `sse` | Server-Sent Events for real-time updates |
| `api` | RESTful endpoints for dashboard data |

CORS configured for `mindpattern.fly.dev`, `localhost:3000`, and Vercel origins.

---

## Memory System

`memory/` module — 18 files, pure functions taking `db` connections.

### Database Schema (memory.db, 17+ tables)

| Table | Purpose |
|-------|---------|
| `findings` | Research findings (title, summary, importance, source_url, agent) |
| `findings_embeddings` | Vector embeddings (bge-small-en-v1.5) |
| `social_posts` | Posted content (platform, content, posted, gate2_action) |
| `social_posts_embeddings` | Dedup vectors for posts |
| `user_preferences` | Learned preferences (topic weights, deprioritize list) |
| `agent_notes` | Evolution log (experiments, skill changes) |
| `run_quality` | Quality scores per run (overall, coverage, dedup_rate) |
| `run_log` | Agent execution logs |
| `patterns` | Recurring topic patterns |
| `signals` | Emerging topics and weak signals |
| `claims` | Verifiable claims extraction + tracking |
| `failures` | Failure tracking + lessons learned |
| `corrections` | Fact corrections + follow-ups |
| `sessions` | Pipeline session metadata |
| `decisions` | Editorial decision records |
| `evolution_log` | Agent spawn/retire/merge history |
| `traces` | Execution trace spans |

### Key Modules

**`memory/embeddings.py`** — Vector encoding via BAAI/bge-small-en-v1.5 (22MB local model). `embed_text()`, `embed_texts()` (batch), `cosine_similarity()`. Model loads once per process.

**`memory/findings.py`** (57 KB) — Core research storage. `store_finding()` with embedding, `search_findings()` via semantic search, `get_context()` for agent-specific context, `evaluate_run()` for quality scoring, `log_agent_run()` for performance metrics.

**`memory/social.py`** — Post tracking. `store_post()` with embedding, `recent_posts()` for dedup context, `check_duplicate()` at 80% similarity threshold, `get_voice_exemplars()` for real approved posts as writer references.

**`memory/feedback.py`** (25 KB) — User preferences + approval patterns. `fetch_feedback()` polls Resend API for reply emails. Temporal decay: recent feedback weighted higher.

**`memory/evolution.py`** (19 KB) — Agent lifecycle management. `get_candidates()` for retirement/merging, `check_agent_performance()` for consecutive zero-output, `spawn_agent()`, `retire_agent()`, `merge_agents()`.

**`memory/patterns.py`** (15 KB) — Recurring pattern detection. `record_pattern()`, `get_recurring()` (3+ occurrences), `consolidate()`, `promote()`, `prune()`.

**`memory/vault.py`** — Identity file operations. Reads/writes soul.md, user.md, voice.md, decisions.md. Atomic writes.

---

## Observability and Traces

### traces.db (14 tables)

| Table | Purpose |
|-------|---------|
| `pipeline_runs` | Run lifecycle (id, type, status, timestamps, error) |
| `agent_runs` | Per-agent execution (tokens, latency, quality, output) |
| `prompt_versions` | Version control for skill files |
| `proof_packages` | Social posts (topic, quality, sources, results) |
| `events` | Arbitrary events with JSON payload |
| `daily_metrics` | Aggregated daily metric values |
| `trace_spans` | Nested trace trees for execution flow |
| `quality_scores` | Per-dimension quality scores |
| `evolution_actions` | Agent spawn/retire/merge actions |
| `pipeline_phases` | Phase-level tracking |
| `agent_metrics` | Per-agent performance over time |
| `cost_log` | Cost entries per phase/model |
| `alerts` | Regression and failure alerts |
| `quality_history` | 7-day trend history for comparison |

### PipelineMonitor (`orchestrator/observability.py`, 667 lines)

- `start_phase()` / `end_phase()` — track phase duration, tokens, cost
- `record_agent_metrics()` — per-agent findings, tokens, cost, duration
- `log_cost()` — cost entry with model pricing lookups
- `record_quality()` — store evaluation scores
- `check_quality_regression()` — compare today vs. 7-day average
- `generate_summary()` — pipeline overview for logging
- Auto-migrates old schemas (v1 -> v2) without data loss

### Prompt Tracker (`orchestrator/prompt_tracker.py`, 18.5 KB)

Captures prompt text + changes across runs. Compares before/after for each agent.
Detects when skill file edits cause quality drops. Enables automated rollback.

### Analyzer (`orchestrator/analyzer.py`, 536 lines)

Reads execution traces, compares agent behavior to skill files:
- Tool usage order compliance
- Phase compliance (evaluate preflight before explore?)
- Quality (deep reads vs. snippet skimming?)
- Output validity (JSON on first parse attempt?)
- Cross-agent systemic patterns

Outputs JSON diff: `{changes: [...], reversions: [...], no_changes: [...]}`

---

## Policy Engine

`policies/engine.py` (17 KB) — hard rules that cannot be gamed by prompt injection.

### Research Validation (`policies/research.json`)
- Required fields: title, summary, importance, source_url, source_name
- Importance values: high, medium, low
- Max 15 findings per agent, max 1000 char summary
- Injection pattern detection: "ignore previous", "you are now", "jailbreak"

### Social Validation (`policies/social.json`)
- Platform limits: Bluesky 300 graphemes (require URL), LinkedIn 3000 chars
- Banned words: game-changer, paradigm, synergy, etc.
- Rate limits: Bluesky 3/day, LinkedIn 1/day
- Posting delays: 30s minimum, 60-300s jitter

All validation is structural (regex, field presence, counts). No LLM in the loop.

---

## Model Routing and Cost

`orchestrator/router.py` (115 lines) — right-sizes models per task:

| Model | Cost (in/out per 1M tokens) | Used For |
|-------|----------------------------|----------|
| **Haiku** | $0.25 / $1.25 | Trend scanning only |
| **Sonnet** | $3 / $15 | Writers, critics, humanizer, engagement, creative brief, art director |
| **Opus 1M** | $15 / $75 | Research agents, synthesis (both passes), EIC, evolution |

### Timeouts and Turns

| Task | Timeout | Max Turns |
|------|---------|-----------|
| trend_scan | 60s | 5 |
| research_agent | 30 min | 35 |
| synthesis_pass2 | 15 min | 30 |
| social writers | 3-5 min | 10-15 |
| evolve | 10 min | 15 |

---

## Infrastructure and Deployment

### Entry Point (`run.py`)
- Path setup for launchd (minimal PATH by default)
- Concurrency guard: file-based lock via `fcntl.flock()`
- Caffeinate: keeps Mac awake during execution
- Structured logging: human-readable to stderr, JSONL to `reports/pipeline-{date}.jsonl`
- User iteration: loads active users from `users.json`
- Slack summary: posts finding count + duration + exit code

### Scheduler (`run-launchd.sh`)
- Idempotent daily run: checks marker file, skips if already ran today
- Time window: only runs 6 AM - 12 PM
- Git pull: if on main branch, pulls latest before running
- Stale lock recovery: if PID is dead, reclaims lock
- Atomic mkdir for lock (POSIX-safe)

### Deployment (Fly.io)
- `Dockerfile`: Python 3.11-slim, pre-downloads fastembed model at build
- `fly.toml`: sjc region, shared-cpu-1x + 512MB, persistent volume at /data
- Health check: GET /healthz every 30s
- Symlinks solve path mismatch between local dev and Fly.io mount

### Dependencies (`requirements.txt`)
- `fastembed` — local embedding model
- `fastapi` + `uvicorn` — dashboard
- `numpy` — vector math
- `requests` + `requests-oauthlib` — HTTP + OAuth
- `feedparser` — RSS parsing
- `markdown2` — HTML conversion
- `Pillow` — image processing
- `slack-sdk` — Slack posting
- `jinja2` — template rendering
- `mcp` — Model Context Protocol

### User Configuration (`users.json`)
- **ramsay** (active): primary user, AI-tech vertical, 7 AM schedule
- **healthtest** (inactive): test user, health-wellness vertical

---

## Self-Improvement Loops

Three complementary loops optimize the system:

### Loop 1: autoresearch.py — Hypothesis Testing
- **When**: Nightly (separate launchd cron)
- **Mechanism**: Generate 3 hypotheses, test against baseline, adopt winner
- **Files it can modify**: `verticals/ai-tech/agents/*.md`, `prompts/*.md`, `config.json`
- **Threshold**: 0.5% improvement required (prevents overfitting to one day's data)

### Loop 2: orchestrator/analyzer.py — Trace-Driven Refinement
- **When**: During EVOLVE phase of each pipeline run
- **Mechanism**: Compare observed agent behavior to skill file instructions
- **Output**: JSON diff of skill file changes
- **Checks**: tool usage order, phase compliance, quality, output validity, cross-agent patterns

### Loop 3: harness/run.sh — Bug-Driven Optimization
- **When**: Runs as part of the autonomous harness
- **Mechanism**: Find where quality is low, diagnose root cause, fix system code
- **Output**: Git PRs modifying pipeline code itself
- **Learning**: Knowledge graph accumulates what works and what fails

The three loops are complementary:
- autoresearch optimizes **prompts** (H in the equation)
- analyzer optimizes **skill files** based on behavioral traces
- harness optimizes **infrastructure** — bugs that no amount of prompt tuning can fix

---

## File Map

```
mindpattern-v3/
├── orchestrator/              # The brain — 12-phase state machine
│   ├── runner.py              #   Main pipeline (1,245 lines)
│   ├── agents.py              #   Agent dispatch + dedup (935 lines)
│   ├── newsletter.py          #   Report validation + email delivery
│   ├── evaluator.py           #   Deterministic quality scoring
│   ├── analyzer.py            #   Trace-driven skill improvement
│   ├── pipeline.py            #   State machine definition
│   ├── router.py              #   Model + cost routing
│   ├── observability.py       #   Metrics + monitoring
│   ├── checkpoint.py          #   Crash recovery + resume
│   ├── sync.py                #   Fly.io upload
│   ├── traces_db.py           #   Observability database (14 tables)
│   └── prompt_tracker.py      #   Prompt version control + regression detection
│
├── memory/                    # Institutional memory (17+ tables)
│   ├── db.py                  #   Connection + schema
│   ├── embeddings.py          #   Vector encoding (bge-small-en-v1.5)
│   ├── findings.py            #   Research storage + semantic search
│   ├── social.py              #   Post tracking + dedup
│   ├── feedback.py            #   User preferences + approval patterns
│   ├── identity_evolve.py     #   Autonomous identity updates
│   ├── evolution.py           #   Agent spawning/retirement/merging
│   ├── patterns.py            #   Recurring pattern detection
│   ├── vault.py               #   Identity file operations
│   ├── failures.py            #   Failure tracking
│   ├── corrections.py         #   Fact corrections
│   ├── claims.py              #   Verifiable claims
│   ├── signals.py             #   Emerging topic signals
│   ├── mirror.py              #   SQLite -> Obsidian export
│   └── graph.py               #   Entity relationship graph
│
├── social/                    # Social media publishing pipeline
│   ├── pipeline.py            #   11-step orchestrator
│   ├── eic.py                 #   Editor-in-Chief (topic selection)
│   ├── writers.py             #   Platform-specific writers
│   ├── critics.py             #   Blind quality review
│   ├── approval.py            #   Multi-gate human approval
│   ├── posting.py             #   Bluesky + LinkedIn API clients
│   ├── engagement.py          #   Conversation discovery + replies
│   └── art.py                 #   DALL-E image generation
│
├── harness/                   # Self-improving outer loop
│   ├── run.sh                 #   5-stage orchestrator
│   ├── tickets.py             #   Ticket lifecycle management
│   ├── gates.py               #   Deterministic quality gates
│   ├── knowledge_graph.py     #   Evolving project knowledge (wiki-linked)
│   ├── issues.py              #   Append-only issue log
│   ├── health_report.py       #   Daily Slack health digest
│   ├── knowledge/             #   31 wiki-linked knowledge files
│   ├── tickets/               #   JSON ticket files
│   ├── prompts/               #   Scout, research, plan prompts
│   └── hooks/                 #   Pre-commit gate + post-tool audit
│
├── agents/                    # Agent skill files (synthesis + social)
│   ├── eic.md                 #   Editor-in-Chief
│   ├── synthesis-writer.md    #   Newsletter writer
│   ├── synthesis-selector.md  #   Story selection
│   ├── bluesky-writer.md      #   Bluesky post writer
│   ├── bluesky-critic.md      #   Bluesky quality critic
│   ├── linkedin-writer.md     #   LinkedIn post writer
│   ├── linkedin-critic.md     #   LinkedIn quality critic
│   ├── creative-director.md   #   Creative brief expansion
│   ├── art-director.md        #   Art direction
│   ├── illustrator.md         #   Image prompts
│   ├── expeditor.md           #   Quality firewall
│   ├── humanizer.md           #   AI pattern removal
│   ├── engagement-finder.md   #   Conversation discovery
│   ├── engagement-writer.md   #   Reply drafting
│   ├── learnings-updater.md   #   Pattern extraction
│   └── trend-scanner.md       #   Trend identification
│
├── verticals/ai-tech/agents/  # Research agent skills (13 files)
│   ├── news-researcher.md
│   ├── agents-researcher.md
│   ├── vibe-coding-researcher.md
│   ├── saas-disruption-researcher.md
│   ├── thought-leaders-researcher.md
│   ├── reddit-researcher.md
│   ├── hn-researcher.md
│   ├── rss-researcher.md
│   ├── sources-researcher.md
│   ├── projects-researcher.md
│   ├── github-pulse-researcher.md
│   ├── arxiv-researcher.md
│   └── skill-finder.md
│
├── preflight/                 # Pre-research data collection (no LLM)
│   ├── run_all.py             #   Orchestrates 8 sources + dedup
│   ├── exa.py, arxiv.py, github.py, hn.py, reddit.py, rss.py, twitter.py, youtube.py
│   └── __init__.py            #   make_entry() factory + sanitization
│
├── policies/                  # Deterministic validation rules
│   ├── engine.py              #   PolicyEngine class
│   ├── research.json          #   Research validation rules
│   └── social.json            #   Social posting rules
│
├── slack_bot/                 # Socket Mode Slack daemon
│   ├── bot.py                 #   Main listener + router
│   └── handlers/              #   7 channel handlers
│
├── dashboard/                 # FastAPI web UI (14 routes)
│   ├── app.py                 #   FastAPI factory
│   ├── auth.py                #   Authentication
│   ├── index.html             #   SPA shell
│   └── routes/                #   14 route routers
│
├── tools/                     # Source fetchers
│   ├── rss-fetch.py, hn-fetch.py, arxiv-fetch.py, github-fetch.py
│   ├── reddit-fetch.py, twitter-fetch.py, youtube-fetch.py
│   ├── linkedin-verify.py
│   ├── scraper.py             #   Adaptive web scraper
│   └── image-gen.py           #   DALL-E generation
│
├── data/ramsay/               # User data vault
│   ├── memory.db              #   SQLite institutional memory
│   ├── traces.db              #   Execution traces
│   ├── learnings.md           #   Auto-generated learnings
│   └── mindpattern/           #   Identity files + daily outputs
│       ├── soul.md, user.md, voice.md, decisions.md
│       ├── agents/            #   32 agent skill files (vault copies)
│       ├── daily/             #   Per-run findings (49 subdirs)
│       ├── newsletters/       #   70 published newsletters
│       ├── social/            #   Social posts + engagement
│       ├── sources/           #   708 source profiles
│       ├── topics/            #   16 canonical topics
│       └── people/            #   Thought leaders + contacts
│
├── run.py                     # Entry point (lock, caffeinate, dispatch)
├── run-launchd.sh             # macOS scheduling wrapper
├── autoresearch.py            # Nightly self-improvement experiments
├── memory_cli.py              # CLI for memory operations
├── tests/                     # pytest suite
├── docs/                      # Documentation
│   └── ARCHITECTURE.md        #   Canonical system design (22.5 KB)
├── config.json                # Global config
├── users.json                 # Active user configs
├── requirements.txt           # Python dependencies
├── Dockerfile                 # Container for Fly.io
└── fly.toml                   # Fly.io deployment config
```

---

## Daily Lifecycle

```
6:55 AM   macOS launchd fires run-launchd.sh
          ├── Checks: already ran today? -> skip
          ├── Checks: 6 AM-12 PM window? -> proceed
          ├── git pull (if on main)
          └── Calls run.py

7:00 AM   run.py acquires lock, caffeinate, starts pipeline
          ├── INIT -> load config, check for resume
          ├── TREND_SCAN -> Haiku identifies 5-8 trends
          ├── RESEARCH -> preflight (400 items from 8 sources)
          │   -> 13 agents parallel (6 workers) -> 150+ findings -> dedup
          ├── SYNTHESIS -> Opus writes 4,500-word newsletter (2 passes)
          │   -> NewsletterEvaluator scores on 6 dimensions
          ├── DELIVER -> Resend API -> email to subscribers
          ├── LEARN -> quality scoring, entity extraction, learnings update
          ├── SOCIAL -> EIC -> writers -> critics -> policy -> humanizer
          │   -> expeditor -> Slack approval -> post to Bluesky + LinkedIn
          ├── ENGAGEMENT -> find conversations -> draft replies
          ├── EVOLVE -> propose identity updates from today's decisions
          ├── IDENTITY -> apply updates atomically to vault
          ├── MIRROR -> export memory.db to Obsidian markdown
          └── SYNC -> bundle + upload to Fly.io

~9 AM     Pipeline complete. Dashboard updated. Slack summary posted.

Evening   harness/run.sh -> scout bugs -> research features
          -> parallel fix (3 agents, TDD) -> gates -> review -> PR
          -> knowledge graph evolves with outcomes

Nightly   autoresearch.py -> test 3 hypotheses -> apply winner

Next AM   Cycle repeats with accumulated learnings
```

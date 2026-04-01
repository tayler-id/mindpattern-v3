# Handoff: V3.2 Capability Registry — System Architecture & Redesign

## Session Metadata
- Created: 2026-03-16 12:44
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: feat/obsidian-memory
- Session duration: ~4 hours (brainstorming + preflight implementation + audit)

### Recent Commits
```
481416c fix: tune preflight source params for better coverage
82b4a4e feat: call preflight system before dispatching research agents
6a06b8b feat: add preflight data to agent prompt builder and dispatch
2da72f0 feat: add preflight/run_all.py orchestrator with batch dedup and agent routing
b01e934 feat: rewrite 13 agent skill files for Phase 1/Phase 2 preflight structure
42ece7a feat: add 8 preflight source scripts
710f0bb feat: preflight foundation + complete TDD test suite
2a3e769 docs: preflight system implementation plan
```

## Handoff Chain
- **Continues from**: `.claude/handoffs/2026-03-16-v31-hooks-fixes-preflight-design.md`
- **Supersedes**: Preflight implementation is COMPLETE. This handoff is about the NEXT phase: fixing identity files, adding skills, adding evaluation.

## Current State Summary

Preflight system is implemented and tested (396 items from 8 sources, 22/22 tests passing, 9 commits on feat/obsidian-memory). Brainstorming was in progress for v3.2: capability registry redesign covering identity file fixes, skill creation, prompt extraction, and evaluation. User explicitly requested a comprehensive system document before any more code changes. The design is partially approved — identity file mapping and skill architecture agreed, implementation not started.

## Important Context

- User wants to understand the FULL system before changes. Do not implement without explaining.
- 87 global skills pollute `claude -p` context. Pipeline agents must use `--disallowedTools Skill` + `--append-system-prompt-file` instead of relying on the skill system.
- SOUL.md has TWO versions that diverged. Research agents see the static one, EIC sees the evolved one. User approved deleting the static version.
- Humanizer has a stale hardcoded banned-word list. voice.md is the authoritative source. Blader/humanizer skill has 24 patterns vs our 6.
- Feedback footer exists in markdown but is lost during HTML email conversion.

## Immediate Next Steps

1. Finish the brainstorming process — present remaining design sections (eval metrics, Python integration changes) and get user approval
2. Write the spec document from the approved design
3. Write implementation plan structured for parallel agents + TDD
4. Execute: Sub-project A (identity fixes + prompt extraction) and Sub-project B (skills + eval) in parallel

---

## How The System Works Today (Complete Picture)

### The Pipeline

mindpattern-v3 is an autonomous research pipeline that runs daily at 7 AM via macOS launchd. It:
1. Scans for trending topics (Haiku)
2. Gathers 396 items from 8 sources via preflight (Python, no LLM)
3. Dispatches 13 research agents in parallel (Sonnet) to evaluate preflight data + explore further
4. Writes a newsletter from the findings (Opus, two passes)
5. Emails the newsletter via Resend
6. Scores quality, extracts entity relationships, regenerates learnings
7. Runs a social pipeline: EIC picks topic → writers → critics → humanizer → expeditor → post
8. Finds engagement opportunities and drafts replies
9. Evolves its own identity files based on run results
10. Mirrors everything to Obsidian markdown
11. Syncs to Fly.io dashboard

### How Agents Get Their Prompts

Every LLM call goes through `orchestrator/agents.py` via one of three functions:

**`run_single_agent()`** — for research agents
- Calls `claude -p {prompt} --model sonnet --max-turns 25`
- The prompt is built by `build_agent_prompt()` which concatenates:
  1. JSON output schema (bookended at start AND end)
  2. SOUL.md content (identity)
  3. Agent's .md skill file content (specialty + Phase 2 preferences)
  4. Dynamic context (date, trends, memory, claims, preflight items)
  5. Novelty requirements
  6. Phase 1/Phase 2 instructions (if preflight data available)
- Allowed tools: Bash, WebSearch, WebFetch, Read, Glob, Grep
- No `--append-system-prompt-file` — everything is in the `-p` prompt string

**`run_agent_with_files()`** — for EIC, writers, critics, expeditor
- Calls `claude -p {prompt} --append-system-prompt-file agents/{name}.md`
- The .md file provides the agent's personality and rules
- The `-p` prompt provides dynamic data (findings, brief, drafts)
- Disallows Agent tool (no subagent dispatch)

**`run_claude_prompt()`** — for synthesis, trend scan, learnings, humanizer, evolve
- Calls `claude -p {prompt}` with NO system prompt file
- The entire prompt is an f-string built inline in Python
- Disallows Agent, Write, Edit, NotebookEdit (prevents file writing)

### The Identity File System

Four files in `data/ramsay/mindpattern/` define the pipeline's identity:

**soul.md** — Who the agent is. Core values, personality, mission. Contains a "Self Assessment" section and "Evolution Log" that EVOLVE updates after each run. This is the living, evolving identity.

**user.md** — Who the user is. Tayler's role, preferences, what topics matter, communication style. EVOLVE can update this based on feedback.

**voice.md** — How to write for social media. Tayler's brand voice, banned words (33 words), banned phrases (11 phrases), structural rules (contractions, no em dashes, vary sentence length), voice fingerprint targets, transformation patterns. Used by all social agents.

**decisions.md** — Append-only editorial decision log. Every run appends: what topic was chosen, why, what gates approved/rejected, quality scores. EVOLVE reads the last 7 entries for context.

**EVOLVE updates these files** after every run:
- Reads all 4 files + pipeline results (findings count, newsletter scores, social outcomes)
- Proposes a JSON diff with `{file: {action: "update"|"append", section: "...", content: "..."}}`
- Applies via atomic file writes (write to .tmp, rename)
- Max 500 chars per update to prevent overwriting

### What's Broken

#### 1. SOUL.md Divergence (CRITICAL)
There are TWO soul.md files:
- `verticals/ai-tech/SOUL.md` — static, never evolved. Used by research agents.
- `data/ramsay/mindpattern/soul.md` — evolved by EVOLVE every run. Used only by EIC.

Research agents never see learned preferences. The verticals version exists because the system was originally designed for multi-vertical support, but only one vertical (ai-tech) exists and the user confirmed they're not doing verticals.

**Fix:** Delete `verticals/ai-tech/SOUL.md`. All agents read from `data/ramsay/mindpattern/soul.md`.

#### 2. Identity Files Missing From Most Agents
| Agent | Gets soul? | Gets user? | Gets voice? | Problem |
|-------|-----------|-----------|------------|---------|
| Research (13x) | WRONG VERSION | no | no | Uses static verticals SOUL, no user prefs |
| Synthesis pass 1 | no | no | no | Selects stories without knowing user interests |
| Synthesis pass 2 | no | no | no | Writes newsletter without knowing the voice |
| Trend scan | no | no | no | Scans trends without knowing user focus |
| Learnings | no | no | no | OK — just summarizes stats |
| Humanizer | no | no | no | Has HARDCODED banned word list instead of reading voice.md |
| EIC | yes (vault) | yes | yes | OK — only agent with full identity |
| Writers | no | no | yes | OK — voice is what matters |
| Critics | no | no | yes | OK |
| Expeditor | no | no | yes | OK |
| Evolve | yes | yes | yes | OK — reads and updates all files |

#### 3. Humanizer Has Stale Hardcoded Rules
The `_humanize()` function at `social/writers.py:300-369` has a hardcoded list of ~30 banned words and patterns. But `voice.md` has a SUPERSET of these rules (33 banned words, 11 banned phrases, structural rules, transformation patterns). The humanizer should read voice.md instead of maintaining a separate list.

Additionally, a much more comprehensive humanizer exists: [github.com/blader/humanizer](https://github.com/blader/humanizer) — a Claude Code skill covering 24 AI writing patterns based on Wikipedia's "Signs of AI writing" guide. Our humanizer covers ~6 patterns.

#### 4. Feedback Footer Missing From Email
The feedback footer IS appended to the markdown report (`runner.py:620-628`), but it's lost during HTML conversion in the deliver phase. The newsletter.py HTML converter doesn't preserve the footer section. Bug is in the deliver phase, not the feedback system.

#### 5. Inline Prompts Not Evolvable
Five agents have their entire prompt as f-strings in Python code:
- Synthesis pass 1 (`runner.py:503`)
- Synthesis pass 2 (`runner.py:537`)
- Trend scan (`runner.py:269`)
- Learnings update (`runner.py:717`)
- Humanizer (`writers.py:333`)

These can't be seen in Obsidian, can't be evolved by EVOLVE, can't be A/B tested. The proven pattern (used by EIC, writers, critics) is `--append-system-prompt-file agents/{name}.md`.

#### 6. No Evaluation Framework
No way to score whether a run was good. No run-over-run comparison. No quality regression detection from prompt changes. The `NewsletterEvaluator` scores the newsletter itself but doesn't evaluate individual agent performance, preflight coverage, or overall pipeline health.

#### 7. Orphaned Files
- `data/ramsay/mindpattern/2026-03-15.md` — empty
- `data/ramsay/mindpattern/2026-03-16.md` — empty
- `data/ramsay/mindpattern/66.md` — empty
- `agents/art-director.md` and `agents/illustrator.md` have hardcoded absolute paths (`/Users/taylerramsay/...`)

---

## How Claude Code Skills Work

### The Skill System
A skill is a `SKILL.md` file with YAML frontmatter. Skills live in three locations:
- **Personal**: `~/.claude/skills/` — available in all projects
- **Project**: `.claude/skills/` — available only in this repo
- **Plugin**: installed via `/plugin install` — managed by marketplaces

### YAML Frontmatter (all fields optional)
```yaml
name: skill-name              # Display name
description: |                # PRIMARY TRIGGER — when to use this skill
  What it does and when...
disable-model-invocation: false  # true = user-only, no auto-trigger
user-invocable: true            # false = hidden from / menu, background knowledge
allowed-tools: [Read, Write]    # Tools available when skill is active
model: sonnet                   # Model override
context: fork                   # Run in isolated subagent
agent: Explore                  # Subagent type
```

### How Skills Load
1. At session start, `name` + `description` from ALL skills are loaded into system prompt (~100 tokens each)
2. When Claude determines a skill is relevant (from description), it invokes it via the `Skill` tool
3. The full SKILL.md body is loaded into context
4. Reference files in `references/` are loaded only as needed

### Skills in `claude -p` Mode
**Verified by testing:** `claude -p` DOES load skill metadata. Model-invoked skills CAN be auto-triggered. User-invocable skills (slash commands) are NOT available.

**Problem:** This machine has 87 skills loaded (46 personal + 41 from plugins). ALL of their descriptions are in context for every `claude -p` call. Research agents see skills like `editorial-caricature`, `frontend-design`, `gsap-animations` — none of which are relevant. This wastes context and risks agents triggering wrong skills.

### How To Control Which Skills Pipeline Agents See

**Option A: `--disallowedTools Skill`**
Block the Skill tool entirely. Agents can't invoke ANY skills. Clean but removes all skill capability.

**Option B: `--append-system-prompt-file`**
Don't use skills at all for pipeline agents. Instead, Python loads the exact .md file each agent needs via `--append-system-prompt-file path/to/file.md`. This is ALREADY how EIC, writers, critics work. It's proven, deterministic, and avoids the 87-skill problem.

**Option C: Project-only skills with `--disallowedTools Skill` on research agents**
Create project skills for user-invocable things (eval, debugging). Pipeline agents use `--append-system-prompt-file` for their prompts. Best of both worlds.

**Recommendation: Option C** — skills for human-facing workflows, deterministic file loading for pipeline agents.

---

## Proposed Changes (Sub-project A: Identity + Prompts)

### A1: Delete verticals/ai-tech/SOUL.md
- Change `dispatch_research_agents()` to read from `data/ramsay/mindpattern/soul.md`
- Delete `verticals/ai-tech/SOUL.md`
- Research agents now see the evolved identity

### A2: Load Identity Files Into All Agents
Modify `build_agent_prompt()` to accept and inject identity files:
| Agent | soul.md | user.md | voice.md |
|-------|---------|---------|----------|
| Research (13x) | yes | yes | no |
| Synthesis pass 1 | yes | yes | no |
| Synthesis pass 2 | yes | no | yes |
| Trend scan | no | yes | no |
| EIC | yes | yes | yes |
| Writers/Critics/Expeditor | no | no | yes |
| Humanizer | no | no | yes |
| Evolve | yes | yes | yes |

### A3: Extract Inline Prompts to .md Files
Move these to `agents/` as proper prompt files loaded via `--append-system-prompt-file`:
- `agents/synthesis-selector.md` (was inline at runner.py:503)
- `agents/synthesis-writer.md` (was inline at runner.py:537)
- `agents/trend-scanner.md` (was inline at runner.py:269)
- `agents/learnings-updater.md` (was inline at runner.py:717)

### A4: Replace Humanizer With Voice-Aware Version
- `_humanize()` reads `voice.md` instead of hardcoded list
- Add blader/humanizer's 24 patterns as a reference file at `agents/references/ai-writing-patterns.md`
- Load both via `--append-system-prompt-file` and inline voice.md content
- Add two-pass self-audit (draft → "what makes this AI?" → fix)

### A5: Fix Feedback Footer in Email
- Bug is in `orchestrator/newsletter.py` HTML conversion
- Footer markdown not being converted to HTML before email send

### A6: Clean Up Orphaned Files
- Delete empty files in vault
- Replace hardcoded absolute paths with relative paths in art agent .md files

## Proposed Changes (Sub-project B: Skills + Eval)

### B1: Create mindpattern-eval Skill
Project-level skill at `.claude/skills/mindpattern-eval/`
- User invokes via `/mindpattern-eval` after a pipeline run
- Scores: coverage (vs known-good sources), consistency (per-agent finding counts), newsletter quality (word count, source diversity, sections), run-over-run comparison
- Also runs as lightweight auto-eval phase after SYNC (stores scores in DB)

### B2: Create mindpattern-humanizer Skill
Project-level skill at `.claude/skills/mindpattern-humanizer/`
- Model-invoked (auto-triggers when social agents edit text)
- Layers voice.md on top of blader's 24 patterns
- Two-pass self-audit process
- Note: Pipeline agents use this via `--append-system-prompt-file`, NOT via skill auto-loading (avoids 87-skill problem)

---

## Key Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Delete verticals/ai-tech/SOUL.md | (a) delete, (b) keep as template, (c) fallback chain | User confirmed "I am not doing verticals" |
| All agents get identity context | Various subsets | soul=who you are, user=who you serve, voice=how you write |
| Synthesis gets full identity | soul+user (pass1), soul+voice (pass2) | Newsletter is the product — needs both identity and voice |
| Eval = auto + on-demand | (a) auto only, (b) on-demand only, (c) both | Lightweight auto for tracking, detailed on-demand for debugging |
| Skills at project level | (a) project, (b) personal, (c) plugin | Project-specific, version-controlled, evolvable |
| Pipeline agents use --append-system-prompt-file not skills | Skills for everything, mixed approach | 87 skills in context is risky; --append-system-prompt-file is proven and deterministic |
| Humanizer based on blader/humanizer + voice.md | (a) keep hardcoded, (b) just voice.md, (c) blader + voice.md | 24 patterns >> 6 patterns, voice.md is authoritative for brand rules |

## Context for Resuming Agent

### Important Context
- The preflight system is COMPLETE and tested (396 items from 8 sources, 22 tests passing, all committed)
- The brainstorming process was in progress for the capability registry redesign
- User explicitly wants comprehensive documentation BEFORE any code changes
- User was confused by the skill system — explain everything, don't assume knowledge
- User cares about: not breaking things, understanding the full system, parallel agent execution, TDD

### Assumptions Made
- `claude -p` loading 87 skill descriptions into context is wasteful for pipeline agents (VERIFIED by testing — it does load them all)
- `--append-system-prompt-file` is the right mechanism for pipeline agents (PROVEN — EIC, writers, critics already use it)
- voice.md is the authoritative source for writing rules (VERIFIED — it's a superset of the humanizer's hardcoded list)
- The feedback footer bug is in HTML conversion, not the footer generation (VERIFIED — footer exists in markdown report but not in email)

### Potential Gotchas
- Changing soul_path in build_agent_prompt() affects ALL 13 research agents — test thoroughly
- The EIC agent currently reads soul.md and user.md via Bash `cat` commands — this needs to change to Python-injected content to be consistent
- Writers cache voice.md at module init (lazy load) — if voice.md changes mid-run from EVOLVE, writers won't see it. This is probably fine (EVOLVE runs after social pipeline).
- The humanizer runs twice: once in _write_single_platform() and once in pipeline.py after gate 2 edits. Both need to be updated.

## Environment State

### Key Paths
- Vault identity: `data/ramsay/mindpattern/{soul,user,voice,decisions}.md`
- Research agents: `verticals/ai-tech/agents/*.md` (13 files, Phase 2 preferences added)
- Social agents: `agents/*.md` (eic, writers, critics, expeditor, art-director, illustrator)
- Preflight: `preflight/` (new, 10 files)
- Tests: `tests/test_preflight.py` (22 tests, all passing)
- Pipeline: `orchestrator/runner.py`, `orchestrator/agents.py`
- Social: `social/pipeline.py`, `social/eic.py`, `social/writers.py`, `social/critics.py`
- Identity evolution: `memory/identity_evolve.py`
- Newsletter delivery: `orchestrator/newsletter.py`

### Tools Verified Working
- xreach 0.3.3 (Twitter search)
- mcporter (Exa semantic search)
- yt-dlp 2026.03.13 (YouTube)
- feedparser 6.0.12 (RSS)
- All 5 fetch tools in tools/

### Launchd
- `com.taylerramsay.daily-research` — loaded, 7 AM schedule, idempotent

## Related Resources
- Previous handoff: `.claude/handoffs/2026-03-16-v31-hooks-fixes-preflight-design.md`
- Preflight spec: `docs/superpowers/specs/2026-03-16-research-agent-preflight-redesign.md`
- Preflight plan: `docs/superpowers/plans/2026-03-16-preflight-system.md`
- Blader humanizer: https://github.com/blader/humanizer/blob/main/SKILL.md
- Claude Code skills docs: https://code.claude.com/docs/en/skills
- Skill best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

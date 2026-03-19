# MindPattern v3 — System Architecture

> Autonomous AI research pipeline. Runs daily at 7 AM. Gathers data from 8 sources, dispatches 13 research agents, writes a newsletter, posts to social media, and improves itself after every run.

---

## Pipeline Overview

```mermaid
flowchart TD
    LAUNCHD["macOS launchd<br/>7 AM daily"] --> WRAPPER["run-launchd.sh<br/>Idempotent wrapper"]
    WRAPPER --> RUN["run.py"]
    RUN --> INIT

    subgraph PIPELINE["Pipeline State Machine (orchestrator/runner.py)"]
        direction TB
        INIT["INIT<br/>Load prefs, feedback, failures"]
        TREND["TREND_SCAN<br/>Haiku: 5-8 trending topics"]
        RESEARCH["RESEARCH<br/>Preflight + 13 Sonnet agents"]
        SYNTH["SYNTHESIS<br/>Opus: 4500-word newsletter"]
        DELIVER["DELIVER<br/>HTML email via Resend"]
        LEARN["LEARN<br/>Quality scoring + entity graph"]
        SOCIAL["SOCIAL<br/>EIC → writers → critics → post"]
        ENGAGE["ENGAGEMENT<br/>Find + reply to conversations"]
        EVOLVE["EVOLVE<br/>Update soul/user/voice/decisions"]
        ANALYZE["ANALYZE<br/>Trace → fix skill files"]
        MIRROR["MIRROR<br/>SQLite → Obsidian markdown"]
        SYNC["SYNC<br/>Upload to Fly.io"]

        INIT --> TREND --> RESEARCH --> SYNTH --> DELIVER --> LEARN
        LEARN --> SOCIAL --> ENGAGE --> EVOLVE --> ANALYZE --> MIRROR --> SYNC
    end

    style RESEARCH fill:#e8f5e9
    style SYNTH fill:#e8f5e9
    style SOCIAL fill:#fff3e0
    style ANALYZE fill:#e3f2fd
```

**Critical phases** (pipeline fails if they fail): RESEARCH, SYNTHESIS
**Skippable phases** (logged as warning, pipeline continues): everything else

---

## Research Phase Detail

```mermaid
flowchart LR
    subgraph PREFLIGHT["Preflight (Python, no LLM)"]
        direction TB
        RSS["RSS<br/>67 feeds"]
        HN["HN<br/>Algolia API"]
        ARXIV["arXiv<br/>Export API"]
        GH["GitHub<br/>Search API"]
        REDDIT["Reddit<br/>JSON API"]
        TWITTER["Twitter/X<br/>xreach CLI"]
        EXA["Exa<br/>mcporter MCP"]
        YT["YouTube<br/>yt-dlp"]
    end

    PREFLIGHT -->|"~400 items"| DEDUP["Batch Dedup<br/>bge-small-en-v1.5<br/>0.85 threshold"]
    DEDUP -->|"~375 new<br/>~25 covered"| ROUTE["Agent Router<br/>source + topic matching"]

    ROUTE --> A1["arxiv-researcher"]
    ROUTE --> A2["news-researcher"]
    ROUTE --> A3["hn-researcher"]
    ROUTE --> A4["github-pulse-researcher"]
    ROUTE --> A5["reddit-researcher"]
    ROUTE --> A6["thought-leaders-researcher"]
    ROUTE --> A7["rss-researcher"]
    ROUTE --> A8["sources-researcher"]
    ROUTE --> A9["saas-disruption-researcher"]
    ROUTE --> A10["agents-researcher"]
    ROUTE --> A11["vibe-coding-researcher"]
    ROUTE --> A12["projects-researcher"]
    ROUTE --> A13["skill-finder"]

    A1 & A2 & A3 & A4 & A5 & A6 & A7 & A8 & A9 & A10 & A11 & A12 & A13 -->|"10-15 findings each"| STORE["memory.db<br/>findings table<br/>+ embeddings"]
```

Each agent receives:
1. JSON output schema (bookended)
2. soul.md + user.md (identity)
3. Agent skill .md file (specialty + Phase 2 preferences)
4. Preflight items tagged NEW / ALREADY_COVERED
5. Phase 1: evaluate preflight items (floor)
6. Phase 2: explore with Agent Reach tools (ceiling)

---

## Social Pipeline Detail

```mermaid
flowchart TD
    FINDINGS["Today's findings<br/>from memory.db"] --> EIC

    subgraph SOCIAL_PIPELINE["Social Pipeline (social/pipeline.py)"]
        EIC["EIC<br/>Opus: score topics<br/>novelty × appeal × threads"]
        EIC -->|"top topic"| GATE1["Gate 1<br/>iMessage approval"]
        GATE1 -->|"approved"| BRIEF["Creative Director<br/>Sonnet: brief + framing"]
        BRIEF --> WRITERS

        subgraph WRITERS["Writers (parallel)"]
            BW["Bluesky Writer<br/>300 chars"]
            LW["LinkedIn Writer<br/>1350 chars"]
        end

        WRITERS --> CRITICS

        subgraph CRITICS["Critics (blind, parallel)"]
            BC["Bluesky Critic"]
            LC["LinkedIn Critic"]
        end

        CRITICS -->|"REVISE?"| WRITERS
        CRITICS -->|"APPROVED"| POLICY["Policy Engine<br/>Deterministic checks"]
        POLICY --> HUMANIZER["Humanizer<br/>voice.md + 24 AI patterns"]
        HUMANIZER --> EXPEDITOR["Expeditor<br/>Final quality gate"]
        EXPEDITOR --> GATE2["Gate 2<br/>iMessage approval"]
        GATE2 -->|"approved"| POST

        subgraph POST["Posting"]
            BS["Bluesky<br/>AT Protocol"]
            LI["LinkedIn<br/>v202504 API"]
        end
    end
```

---

## Identity System

```mermaid
flowchart LR
    subgraph VAULT["data/ramsay/mindpattern/"]
        SOUL["soul.md<br/>Who the agent is<br/>Values, personality, mission"]
        USER["user.md<br/>Who it serves<br/>Tayler's role, interests"]
        VOICE["voice.md<br/>How to write<br/>Banned words, tone rules"]
        DECISIONS["decisions.md<br/>Editorial log<br/>Append-only"]
    end

    SOUL -->|"research agents<br/>synthesis pass 1<br/>EIC, evolve"| AGENTS["Agent Prompts"]
    USER -->|"research agents<br/>synthesis pass 1<br/>trend scan<br/>EIC, evolve"| AGENTS
    VOICE -->|"synthesis pass 2<br/>writers, critics<br/>humanizer, expeditor<br/>EIC, evolve"| AGENTS
    DECISIONS -->|"EIC (last 7)<br/>evolve (last 7)"| AGENTS

    EVOLVE_PHASE["EVOLVE Phase<br/>Opus LLM"] -->|"updates after<br/>every run"| VAULT
```

### Identity File → Agent Mapping

| Agent | soul.md | user.md | voice.md | decisions.md |
|-------|---------|---------|----------|-------------|
| Research agents (13x) | yes | yes | no | no |
| Synthesis pass 1 (selector) | yes | yes | no | no |
| Synthesis pass 2 (writer) | yes | no | yes | no |
| Trend scanner | no | yes | no | no |
| EIC | yes | yes | yes | last 7 entries |
| Writers / Critics / Expeditor | no | no | yes | no |
| Humanizer | no | no | yes | no |
| Evolve | yes | yes | yes | last 7 entries |

---

## Self-Optimization Loop (ANALYZE Phase)

```mermaid
flowchart TD
    RUN["Pipeline Run<br/>13+ agents execute"] --> TRACES["Trace Logs<br/>data/ramsay/mindpattern/agents/{name}/{date}.md<br/>~500 lines per agent"]
    RUN --> METRICS["Pipeline Metrics<br/>findings/agent, newsletter quality,<br/>social outcomes"]

    TRACES --> ANALYZER["ANALYZE Phase<br/>Opus 1M context"]
    METRICS --> ANALYZER
    SKILLS["All Agent Skill Files<br/>verticals/ai-tech/agents/*.md<br/>agents/*.md"] --> ANALYZER
    REGRESSION["PromptTracker<br/>regression data from<br/>previous ANALYZE edits"] --> ANALYZER

    ANALYZER -->|"JSON diff"| APPLY["Apply Changes<br/>atomic_write() per file"]
    ANALYZER -->|"revert hash"| REVERT["Git Revert<br/>git show {hash}:{file}"]

    APPLY --> TRACKER["PromptTracker<br/>records new hashes"]
    REVERT --> TRACKER

    TRACKER -->|"next run"| REGRESSION

    subgraph DEVIATIONS["What the Analyzer Checks"]
        D1["Tool usage: Did agent use<br/>tools in the order skill specified?"]
        D2["Phase compliance: Did agent<br/>do Phase 1 before Phase 2?"]
        D3["Quality: Deep reads via Jina<br/>or just search snippets?"]
        D4["Cross-agent patterns: Same<br/>mistake across 5+ agents?"]
        D5["Regression: Did previous<br/>ANALYZE edit make things worse?"]
    end
```

**The kaizen loop:** Run → trace → analyze deviations → fix skills → next run uses improved skills → trace again → repeat.

---

## Data Storage

```mermaid
flowchart TD
    subgraph SQLITE["memory.db (SQLite, WAL mode)"]
        FINDINGS_T["findings<br/>+ findings_embeddings<br/>+ findings_fts"]
        CLAIMS_T["claimed_topics"]
        SOCIAL_T["social_posts<br/>+ social_posts_embeddings"]
        FEEDBACK_T["user_feedback<br/>+ user_preferences"]
        AGENT_T["agent_notes<br/>+ run_log"]
        QUALITY_T["run_quality<br/>+ failure_lessons"]
        GRAPH_T["entity_graph"]
        CORRECT_T["editorial_corrections"]
        SIGNALS_T["signals"]
        PATTERNS_T["patterns<br/>+ validated_patterns"]
    end

    subgraph TRACES["traces.db (SQLite)"]
        PIPELINE_RUNS["pipeline_runs"]
        EVENTS["events"]
        AGENT_RUNS["agent_runs"]
        CHECKPOINTS["checkpoints"]
        PROMPT_VERSIONS["prompt_tracker"]
    end

    subgraph VAULT_DATA["data/ramsay/mindpattern/ (Obsidian)"]
        AGENT_LOGS["agents/{name}/{date}.md<br/>Full execution transcripts"]
        NEWSLETTERS["newsletters/{date}.md"]
        SOCIAL_DRAFTS["social/drafts/{date}/"]
        DAILY["daily/{date}.md"]
        SOURCES_DIR["sources/"]
        TOPICS_DIR["topics/"]
        PEOPLE_DIR["people/"]
        IDENTITY["soul.md, user.md,<br/>voice.md, decisions.md"]
    end

    subgraph REPORTS["reports/ramsay/"]
        NEWSLETTER_MD["{date}.md<br/>Newsletter markdown"]
    end

    subgraph FLYIO["Fly.io (mindpattern.fly.dev)"]
        DASHBOARD["Web Dashboard<br/>FastAPI + SSE"]
        REMOTE_DB["memory.db + traces.db<br/>+ reports/ (synced)"]
    end

    SQLITE -->|"MIRROR phase"| VAULT_DATA
    SQLITE & TRACES & REPORTS -->|"SYNC phase"| FLYIO
```

---

## Prompt Assembly

```mermaid
flowchart TD
    subgraph BUILD["build_agent_prompt() — orchestrator/agents.py"]
        direction TB
        SCHEMA_TOP["JSON output schema<br/>(critical rules at top)"]
        SOUL_C["soul.md content"]
        USER_C["user.md content"]
        SKILL_C["agent skill .md content<br/>(specialty, focus, Phase 2 prefs)"]
        CONTEXT["Dynamic context<br/>(date, trends, claims, memory)"]
        NOVELTY["NOVELTY REQUIREMENT<br/>(critical — no duplicates)"]
        P1["Phase 1: Evaluate preflight items<br/>(NEW items listed, COVERED items shown)"]
        P2["Phase 2: Explore with Agent Reach<br/>(Exa, Jina, xreach, yt-dlp, WebSearch)"]
        SCHEMA_BOT["JSON output schema<br/>(critical rules repeated at end)"]

        SCHEMA_TOP --> SOUL_C --> USER_C --> SKILL_C --> CONTEXT --> NOVELTY --> P1 --> P2 --> SCHEMA_BOT
    end

    BUILD -->|"claude -p {prompt}<br/>--model sonnet<br/>--max-turns 25<br/>--disallowedTools Skill"| CLAUDE["Claude CLI<br/>subprocess"]
```

**Three dispatch functions in agents.py:**

| Function | Used By | Mechanism |
|----------|---------|-----------|
| `run_single_agent()` | Research agents | `-p {prompt}` with inline identity |
| `run_agent_with_files()` | EIC, writers, critics | `-p {prompt} --append-system-prompt-file agents/{name}.md` |
| `run_claude_prompt()` | Synthesis, trend scan, learnings, humanizer, analyzer | `-p {prompt} --append-system-prompt-file agents/{name}.md` |

All pipeline agents have `--disallowedTools Skill` to prevent 87 global skills from polluting context.

---

## External Services

```mermaid
flowchart LR
    subgraph PIPELINE["MindPattern Pipeline"]
        PREFLIGHT_M["Preflight"]
        NEWSLETTER_M["Newsletter"]
        SOCIAL_M["Social"]
        ENGAGE_M["Engagement"]
        SYNC_M["Sync"]
    end

    subgraph APIS["External APIs"]
        ARXIV_API["arXiv Export API"]
        GH_API["GitHub Search API"]
        HN_API["HN Algolia API"]
        REDDIT_API["Reddit JSON API"]
        RESEND["Resend Email API<br/>keychain: resend-api-key"]
        BSKY["Bluesky AT Protocol<br/>keychain: bluesky-app-password"]
        LINKEDIN["LinkedIn v202504 API<br/>keychain: linkedin-access-token"]
        FLYIO_API["Fly.io<br/>FLY_API_TOKEN"]
    end

    subgraph CLI_TOOLS["CLI Tools"]
        XREACH["xreach 0.3.3<br/>Twitter/X search"]
        MCPORTER["mcporter<br/>Exa MCP server"]
        YTDLP["yt-dlp<br/>YouTube videos"]
        FEEDPARSER["feedparser<br/>RSS/Atom parsing"]
        CLAUDE_CLI["claude CLI<br/>Pro subscription"]
        JINA["Jina Reader<br/>curl r.jina.ai/URL"]
    end

    subgraph MACOS["macOS Services"]
        MESSAGES["Messages.db<br/>iMessage gates<br/>FDA required"]
        KEYCHAIN["macOS Keychain<br/>API keys"]
        LAUNCHD_SVC["launchd<br/>7 AM schedule"]
        PMSET["pmset<br/>6:55 AM wake"]
    end

    PREFLIGHT_M --> ARXIV_API & GH_API & HN_API & REDDIT_API
    PREFLIGHT_M --> XREACH & MCPORTER & YTDLP & FEEDPARSER
    NEWSLETTER_M --> RESEND
    SOCIAL_M --> BSKY & LINKEDIN & CLAUDE_CLI & MESSAGES
    ENGAGE_M --> BSKY & LINKEDIN & JINA
    SYNC_M --> FLYIO_API
```

---

## File Structure

```
mindpattern-v3/
├── orchestrator/               # Pipeline state machine & execution
│   ├── runner.py               # Main pipeline loop (12 phases)
│   ├── agents.py               # Claude CLI dispatch (3 functions)
│   ├── analyzer.py             # Self-optimization (trace → fix skills)
│   ├── pipeline.py             # Phase enum, state transitions
│   ├── router.py               # Model routing (haiku/sonnet/opus)
│   ├── checkpoint.py           # Resume from crashes
│   ├── evaluator.py            # Newsletter quality scoring
│   ├── newsletter.py           # HTML conversion + Resend email
│   ├── observability.py        # Metrics collection
│   ├── prompt_tracker.py       # Prompt hash tracking + regression
│   ├── sync.py                 # Fly.io upload
│   └── traces_db.py            # Traces DB schema
│
├── preflight/                  # Data collection (8 sources)
│   ├── run_all.py              # Parallel orchestrator + dedup
│   ├── rss.py                  # 67 RSS feeds
│   ├── arxiv.py                # arXiv papers
│   ├── github.py               # GitHub trending repos
│   ├── hn.py                   # Hacker News stories
│   ├── reddit.py               # Reddit posts (10 subreddits)
│   ├── twitter.py              # X/Twitter via xreach
│   ├── exa.py                  # Exa semantic search via mcporter
│   └── youtube.py              # YouTube videos via yt-dlp
│
├── memory/                     # Vector DB + identity evolution
│   ├── db.py                   # SQLite connection + schema
│   ├── embeddings.py           # BAAI/bge-small-en-v1.5 (384-dim)
│   ├── findings.py             # Finding storage + semantic search
│   ├── identity_evolve.py      # LLM updates to soul/user/voice
│   ├── vault.py                # Atomic markdown read/write
│   ├── mirror.py               # SQLite → Obsidian sync
│   ├── feedback.py             # Resend reply ingestion
│   ├── claims.py               # Cross-agent topic dedup
│   ├── corrections.py          # Editorial corrections
│   ├── failures.py             # Failure lessons
│   ├── patterns.py             # Pattern consolidation
│   ├── signals.py              # Cross-pipeline signals
│   ├── social.py               # Social post tracking
│   ├── graph.py                # Entity relationships
│   └── evolution.py            # Agent spawn/retire
│
├── social/                     # Social media pipeline
│   ├── pipeline.py             # Main orchestrator
│   ├── eic.py                  # Editor-in-Chief topic selection
│   ├── writers.py              # Per-platform writing + humanizer
│   ├── critics.py              # Blind validation + expeditor
│   ├── posting.py              # Bluesky/LinkedIn/X clients
│   ├── engagement.py           # Reply discovery + drafting
│   ├── approval.py             # iMessage + dashboard gates
│   └── art.py                  # Art pipeline (director → illustrator)
│
├── verticals/ai-tech/
│   ├── agents/                 # 13 research agent skill files
│   │   ├── arxiv-researcher.md
│   │   ├── news-researcher.md
│   │   ├── hn-researcher.md
│   │   ├── github-pulse-researcher.md
│   │   ├── reddit-researcher.md
│   │   ├── thought-leaders-researcher.md
│   │   ├── rss-researcher.md
│   │   ├── sources-researcher.md
│   │   ├── saas-disruption-researcher.md
│   │   ├── agents-researcher.md
│   │   ├── vibe-coding-researcher.md
│   │   ├── projects-researcher.md
│   │   └── skill-finder.md
│   └── rss-feeds.json          # 67 curated RSS feeds
│
├── agents/                     # Social + synthesis agent files
│   ├── eic.md                  # Editor-in-Chief
│   ├── creative-director.md    # Creative brief
│   ├── bluesky-writer.md       # Bluesky post writer
│   ├── bluesky-critic.md       # Bluesky blind validator
│   ├── linkedin-writer.md      # LinkedIn post writer
│   ├── linkedin-critic.md      # LinkedIn blind validator
│   ├── expeditor.md            # Final quality gate
│   ├── humanizer.md            # AI pattern removal + voice.md
│   ├── synthesis-selector.md   # Story selection (pass 1)
│   ├── synthesis-writer.md     # Newsletter writing (pass 2)
│   ├── trend-scanner.md        # Trending topic identification
│   ├── learnings-updater.md    # Learnings regeneration
│   ├── engagement-finder.md    # Conversation discovery
│   ├── engagement-writer.md    # Reply drafting
│   ├── art-director.md         # Visual direction
│   ├── illustrator.md          # Image generation
│   └── references/
│       └── ai-writing-patterns.md  # 24 AI writing anti-patterns
│
├── hooks/
│   └── session-transcript.py   # SessionEnd: capture agent traces
│
├── tools/                      # Data fetch scripts
│   ├── arxiv-fetch.py
│   ├── github-fetch.py
│   ├── hn-fetch.py
│   ├── reddit-fetch.py
│   ├── rss-fetch.py
│   ├── scraper.py
│   ├── image-gen.py
│   └── linkedin-verify.py
│
├── policies/
│   ├── engine.py               # Deterministic policy checks
│   └── social.json             # Brand safety rules
│
├── data/ramsay/
│   ├── memory.db               # Main database (17+ tables)
│   ├── traces.db               # Observability database
│   └── mindpattern/            # Obsidian vault
│       ├── soul.md             # Agent identity (evolved)
│       ├── user.md             # User profile (evolved)
│       ├── voice.md            # Writing voice (evolved)
│       ├── decisions.md        # Editorial log (append-only)
│       └── agents/             # Agent transcripts
│
├── .claude/
│   ├── skills/
│   │   └── mindpattern-eval/   # Pipeline evaluation skill
│   └── handoffs/               # Session handoff documents
│
├── tests/                      # 58+ tests across 7 files
├── config.json                 # Global config
├── users.json                  # User definitions
├── social-config.json          # Social pipeline config
├── run.py                      # Entry point
└── run-launchd.sh              # macOS launchd wrapper
```

---

## Model Routing

| Task | Model | Max Turns | Timeout | Cost Tier |
|------|-------|-----------|---------|-----------|
| Trend scan | Haiku | 5 | 60s | Low |
| Research agents (13x) | Sonnet | 25 | 1800s | Medium |
| Synthesis pass 1 | Opus 1M | 10 | 600s | High |
| Synthesis pass 2 | Opus 1M | 30 | 900s | High |
| EIC | Opus 1M | 15 | 600s | High |
| Writers / Critics | Sonnet | 15 / 5 | 300s / 120s | Medium |
| Humanizer / Expeditor | Sonnet | 5 | 120s | Medium |
| Analyzer | Opus 1M | 10 | 600s | High |
| Learnings | Sonnet | 5 | 120s | Medium |
| Engagement | Sonnet | 10 / 5 | 300s / 120s | Medium |

---

## Authentication

All sensitive credentials stored in macOS Keychain:

| Service | Keychain Key | Used By |
|---------|-------------|---------|
| Resend (email) | `resend-api-key` | newsletter.py, feedback.py |
| Bluesky | `bluesky-app-password` | posting.py |
| LinkedIn | `linkedin-access-token` | posting.py (60-day expiry) |

Additional requirements:
- **Full Disk Access**: `/bin/bash` and `python3.14` must have FDA for Messages.db access
- **Claude Pro subscription**: CLI authenticates via account (no API key needed)
- **pmset wakepoweron**: Mac wakes at 6:55 AM for 7 AM pipeline run

---

## Scheduling

```mermaid
flowchart LR
    PMSET["pmset wakepoweron<br/>6:55 AM"] --> WAKE["Mac wakes"]
    WAKE --> LAUNCHD_T["launchd<br/>com.taylerramsay.daily-research<br/>7:00 AM + RunAtLoad"]
    LAUNCHD_T --> WRAPPER_T["run-launchd.sh"]

    WRAPPER_T --> CHECK1{"Already ran today?<br/>/tmp/mindpattern-ran-{date}"}
    CHECK1 -->|"yes"| SKIP["Skip"]
    CHECK1 -->|"no"| CHECK2{"Lock file exists?"}
    CHECK2 -->|"stale"| CLEAN["Remove stale lock"]
    CHECK2 -->|"active PID"| SKIP
    CLEAN --> FDA{"FDA check<br/>Python reads Messages.db?"}
    CHECK2 -->|"no"| FDA
    FDA -->|"warn if failed"| CAFF["caffeinate -i -s"]
    CAFF --> PIPELINE_T["python3 run.py"]
    PIPELINE_T --> MARKER["touch /tmp/mindpattern-ran-{date}"]
```

---

## Key Design Principles

1. **Python controls, LLM judges** — Python orchestrates phases, calls tools, parses results. LLMs search, read, filter, score, and write.

2. **Deterministic state machine** — phases execute in fixed order. The LLM never decides what comes next. Critical phases fail the pipeline; skippable phases log warnings and continue.

3. **Preflight + Phase 1/Phase 2** — Python gathers structured data BEFORE agents run (guaranteed floor). Agents evaluate preflight data, then explore for what's missing (agentic ceiling).

4. **Identity files are the source of truth** — soul.md, user.md, voice.md, decisions.md define who the agent is, who it serves, and how it writes. EVOLVE updates them after every run.

5. **Self-optimization via trace analysis** — ANALYZE phase reads execution traces, compares against skill file instructions, and fixes deviations. The loop self-corrects bad edits via regression detection.

6. **Two approval gates** — iMessage gates before topic selection (Gate 1) and before publishing (Gate 2). Human stays in the loop for editorial decisions.

7. **Everything visible in Obsidian** — findings, transcripts, social drafts, newsletters, identity files all mirrored as markdown. Human can review and understand the system's reasoning.

8. **Pipeline agents see zero global skills** — `--disallowedTools Skill` prevents 87 personal/plugin skills from polluting autonomous agent context. Agent prompts are loaded deterministically via `--append-system-prompt-file`.

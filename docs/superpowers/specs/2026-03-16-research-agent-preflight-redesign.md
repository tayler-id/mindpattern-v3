# Research Agent Preflight Redesign — Guaranteed Floor + Agentic Ceiling

## Summary

Restructure all 13 research agents around a Python preflight system that gathers structured data from APIs/feeds/tools BEFORE agents run. Agents receive pre-fetched, dedup-annotated data in their 1M context window, evaluate it (guaranteed floor), then explore for what's missing using Agent Reach tools (agentic ceiling). Every agent produces 10-15 findings consistently.

## Problem Statement

Research agents are inconsistent. Agents with dedicated fetch scripts (arxiv, github, hn, reddit) produce 10-20 findings. WebSearch-only agents (news, projects, saas-disruption, thought-leaders, vibe-coding, sources, agents, skill-finder) produce 2-8 depending on what Google returns. Agent Reach tools are installed (Jina Reader, xreach, yt-dlp, feedparser, Exa) but agents don't reliably use them. Agents don't know what other agents found, so they bring back duplicates. The dedup catches this after the fact — wasting LLM calls.

### Root Causes

1. **No preflight** — 8 of 13 agents start from zero (WebSearch) instead of getting structured data
2. **No cross-agent awareness** — agents see their own recent findings but not other agents' findings
3. **Agent Reach tools are optional** — prompt says "use when needed" so agents skip them
4. **Dedup happens too late** — pipeline dedup runs after agents return, after LLM cost is spent

## Design

### Architecture: Two-Phase Research

```
preflight.run_all()     →  Structured data from all sources (Python, no LLM)
        ↓
preflight.dedup()       →  Tag each item as NEW or ALREADY_COVERED (embeddings)
        ↓
preflight.assign()      →  Route items to relevant agents by domain
        ↓
build_agent_prompt()    →  Agent gets: soul + skill + memory + preflight items
        ↓
13 agents in parallel   →  Phase 1: evaluate preflight data (floor)
                           Phase 2: explore with Agent Reach (ceiling)
        ↓
Post-research dedup     →  Final catch (0.92 threshold, 7 days)
```

### Preflight Module

New `preflight/` directory with one script per data source. Each script outputs newline-delimited JSON to stdout. `run_all.py` orchestrates them all and merges output.

```
preflight/
├── __init__.py
├── run_all.py          # Orchestrates all preflight scripts, merges, dedup-annotates
├── rss.py              # Wraps tools/rss-fetch.py with verticals/ai-tech/rss-feeds.json
├── arxiv.py            # Wraps tools/arxiv-fetch.py
├── github.py           # Wraps tools/github-fetch.py
├── hn.py               # Wraps tools/hn-fetch.py
├── reddit.py           # Wraps tools/reddit-fetch.py
├── twitter.py          # Calls xreach search for tracked accounts + trending topics
├── exa.py              # Calls mcporter exa.web_search_exa for trending AI queries
└── youtube.py          # Calls yt-dlp for recent videos from key AI channels
```

#### Preflight Entry Schema

Every preflight script outputs items with this schema:

```json
{
  "source": "rss|arxiv|github|hn|reddit|twitter|exa|youtube",
  "source_name": "Simon Willison",
  "title": "Context Engineering Patterns for Production AI",
  "url": "https://simonwillison.net/2026/Mar/16/...",
  "published": "2026-03-16T08:30:00Z",
  "content_preview": "First 500 chars of content...",
  "metrics": {"likes": 0, "points": 0, "stars": 0, "retweets": 0},
  "already_covered": false,
  "match_info": null
}
```

When `already_covered` is true, `match_info` contains:
```json
{
  "matched_finding": "Original finding title",
  "matched_date": "2026-03-15",
  "matched_agent": "news-researcher",
  "similarity": 0.89
}
```

#### Expected Preflight Volume

| Source | Script | Expected items per run |
|--------|--------|----------------------|
| RSS | `rss.py` | 60-80 from 67 feeds |
| HN | `hn.py` | 40-60 from Algolia API |
| arXiv | `arxiv.py` | 20-30 from export API |
| GitHub | `github.py` | 25-35 from Search API |
| Reddit | `reddit.py` | 30-50 from 10 subreddits |
| Twitter | `twitter.py` | 20-30 from xreach search |
| Exa | `exa.py` | 15-25 from semantic search |
| YouTube | `youtube.py` | 8-12 from key channels |
| **Total** | | **~250-320 raw items** |

#### Preflight Dedup

`run_all.py` loads the last 7 days of stored findings from the DB, embeds each preflight item's title+content_preview, compares against stored embeddings at 0.85 similarity threshold. Items above threshold get tagged `already_covered: true` with match info. This is the SAME embedding system already in `memory/embeddings.py` (BAAI/bge-small-en-v1.5, 384-dim).

#### Preflight Assignment

`run_all.py` routes items to agents by source type and topic:

| Source | Primary Agent | Secondary Agents |
|--------|--------------|-----------------|
| arXiv papers | arxiv-researcher | agents-researcher (if security) |
| GitHub repos | github-pulse-researcher | projects-researcher, vibe-coding-researcher |
| HN posts | hn-researcher | news-researcher (if breaking) |
| Reddit posts | reddit-researcher | vibe-coding-researcher (if coding) |
| RSS: AI company blogs | news-researcher | agents-researcher, vibe-coding-researcher |
| RSS: Newsletters/analysis | sources-researcher | rss-researcher |
| RSS: VC/SaaS/fintech | saas-disruption-researcher | news-researcher |
| Twitter | thought-leaders-researcher | news-researcher (if breaking) |
| Exa results | distributed by topic match | — |
| YouTube | sources-researcher | vibe-coding-researcher |

Cross-domain stories (e.g. an HN post about SaaS disruption) go to BOTH the source agent and the topic agent. Each agent gets 20-40 preflight items plus the full ALREADY_COVERED list.

### Agent Prompt Structure (Universal)

Every agent's assembled prompt follows this structure:

```
1. JSON output schema (critical rules at top)
2. SOUL identity
3. Agent skill definition (.md file — specialty, priorities, quality criteria)
4. Memory context (recent findings for THIS agent, skip list)
5. ALREADY_COVERED list (recent findings from ALL agents — cross-agent dedup)
6. PREFLIGHT DATA — sorted into NEW and ALREADY_COVERED sections
7. NOVELTY REQUIREMENT — don't bring back dupes
8. Phase 1 instructions — evaluate preflight, select 8-12 best NEW items
9. Phase 2 instructions — explore with Agent Reach tools, find 2-5 more
10. JSON output schema (critical rules repeated at end)
```

#### Phase 1: Evaluate Preflight Data

```
## Phase 1: Evaluate Pre-Fetched Data

Below are {N} items pre-fetched from your domain sources. Each is tagged
NEW or ALREADY_COVERED.

Select the 8-12 most important NEW items as findings. For each:
- Verify the content is real and recent (not old news resurfacing)
- Write a 2-3 sentence summary with specific details (names, numbers, dates)
- Rate importance (high/medium/low)
- Include the source_url from the preflight data

Skip ALREADY_COVERED items unless there is a genuinely new development
since the original finding (new data, new announcement, new reaction).

{preflight items rendered as markdown list}
```

#### Phase 2: Explore for What's Missing

```
## Phase 2: Explore Beyond Preflight

The preflight data covers known sources. Now find what it MISSED.
Use these tools to discover 2-5 additional findings:

- Exa semantic search: mcporter call 'exa.web_search_exa(query: "...", numResults: 5)'
- Jina Reader (deep read any URL): curl -s "https://r.jina.ai/{URL}" | head -300
- Twitter search: xreach search "query" --count 10 --json
- YouTube transcripts: yt-dlp --dump-json "URL"
- WebSearch (last resort): only if Exa doesn't cover it

Look for:
- Stories that broke in the last 6 hours (too recent for RSS/feeds)
- Primary sources not in our feed list
- Reactions and follow-ups to stories in the preflight data

Target: 10-15 total findings (8-12 from Phase 1 + 2-5 from Phase 2).
```

### Agent Skill Files (.md) — What Changes

Each agent's `.md` file keeps its specialty definition (topics, priorities, quality criteria, self-improvement notes). What changes:

1. **Remove** old "Research Protocol (MANDATORY)" / "Agent Reach" sections — replaced by universal Phase 1/Phase 2 in prompt builder
2. **Remove** old "Tool Invocation" sections that call `python3 tools/xxx-fetch.py` — preflight does this now
3. **Keep** specialty definition, priority topics, quality criteria, self-improvement notes
4. **Add** Phase 2 tool preferences — which Agent Reach tools this agent should prioritize

Example for thought-leaders-researcher.md:
```markdown
## Phase 2 Exploration Preferences
- Primary: xreach search for tracked accounts (Karpathy, swyx, Willison, etc.)
- Secondary: Exa search for thought leader blog posts
- Deep read: Jina Reader for long-form posts and threads
```

### Runner Changes

In `orchestrator/runner.py`, `_phase_research()` changes:

```python
def _phase_research(self) -> dict:
    memory.clear_claims(self.db, self.date_str)

    # NEW: Run preflight to gather structured data from all sources
    from preflight import run_all
    preflight_data = run_all(
        date_str=self.date_str,
        db=self.db,
        feeds_file=PROJECT_ROOT / "verticals" / "ai-tech" / "rss-feeds.json",
    )
    self.preflight_data = preflight_data
    logger.info(
        f"Preflight: {preflight_data['total_items']} items, "
        f"{preflight_data['new_count']} new, "
        f"{preflight_data['covered_count']} already covered"
    )

    # Build context with preflight data
    def context_fn(agent_name, date_str):
        ctx = memory.get_context(self.db, agent_name, date_str)
        return ctx

    # Dispatch agents with preflight data in their prompts
    self.agent_results = agent_dispatch.dispatch_research_agents(
        user_id=self.user_id,
        date_str=self.date_str,
        context_fn=context_fn,
        trends=self.trends,
        claims=[],
        max_workers=6,
        preflight_data=preflight_data,  # NEW parameter
    )
    # ... rest stays the same
```

### Prompt Builder Changes

`build_agent_prompt()` in `orchestrator/agents.py` gets a new `preflight_items` parameter:

```python
def build_agent_prompt(
    agent_name, user_id, date_str, soul_path, agent_skill_path,
    context, trends=None, claims=None, preflight_items=None,
    already_covered=None,
) -> str:
```

The prompt builder renders preflight items into two sections:
- `## NEW Items (evaluate these)` — items where `already_covered == False`
- `## ALREADY COVERED (skip unless major update)` — items where `already_covered == True`, with match info showing which agent covered it and when

### Agent Allowed Tools

```python
AGENT_ALLOWED_TOOLS = [
    "Bash",       # For Exa (mcporter), xreach, yt-dlp, Jina Reader (curl)
    "WebSearch",  # Demoted — fallback only, prompt says "use Exa first"
    "WebFetch",   # Quick URL reads
    "Read",       # Local files
    "Glob",       # File discovery
    "Grep",       # File search
]
```

No changes to the list itself. The behavioral change is in the prompt — agents are told to use Exa/xreach/Jina first, WebSearch as last resort.

### What This Replaces

| Before | After |
|--------|-------|
| 5 agents have fetch scripts, 8 use WebSearch | All agents get preflight data |
| Agents search blindly, dedup catches dupes after | Preflight tags dupes before agents run |
| Agents see only their own recent findings | Agents see ALL agents' recent findings |
| "Research Protocol (MANDATORY)" in each .md | Universal Phase 1/Phase 2 in prompt builder |
| `tools/` scripts called by agents via Bash | `preflight/` scripts called by Python before agents |
| WebSearch is primary discovery tool | Exa + structured APIs are primary, WebSearch is fallback |

### Files Changed

#### New Files
- `preflight/__init__.py`
- `preflight/run_all.py` — orchestrates all preflight scripts, dedup-annotates, assigns to agents
- `preflight/rss.py` — wraps `tools/rss-fetch.py`
- `preflight/arxiv.py` — wraps `tools/arxiv-fetch.py`
- `preflight/github.py` — wraps `tools/github-fetch.py`
- `preflight/hn.py` — wraps `tools/hn-fetch.py`
- `preflight/reddit.py` — wraps `tools/reddit-fetch.py`
- `preflight/twitter.py` — new, calls xreach
- `preflight/exa.py` — new, calls mcporter
- `preflight/youtube.py` — new, calls yt-dlp
- `tests/test_preflight.py`

#### Modified Files
- `orchestrator/runner.py` — `_phase_research()` calls preflight before dispatch
- `orchestrator/agents.py` — `build_agent_prompt()` accepts preflight_items parameter, `dispatch_research_agents()` passes preflight data
- `verticals/ai-tech/agents/*.md` — all 13 agents: remove old tool invocation/research protocol sections, add Phase 2 exploration preferences
- `orchestrator/router.py` — no changes needed (Sonnet already has 1M context)

#### Unchanged Files
- `tools/*.py` — kept as-is, preflight wraps them
- `memory/` — no changes, embeddings used by preflight for dedup
- `social/` — no changes
- `orchestrator/pipeline.py` — no new phases

### Success Criteria

- [ ] Preflight gathers 250+ items from 8 sources in under 3 minutes
- [ ] Each agent receives 20-40 pre-fetched items tagged NEW/ALREADY_COVERED
- [ ] Every agent produces 10-15 findings per run (consistency)
- [ ] At least 30% of findings come from Phase 2 exploration (depth)
- [ ] Total stored findings per run: 130+ (up from 64)
- [ ] No agent times out (preflight handles the slow API calls)
- [ ] Agent transcripts show Phase 1 evaluation + Phase 2 exploration
- [ ] Cross-agent duplicates drop below 5% (down from ~20%)
- [ ] Newsletter quality score > 1.5 (coverage + dedup + sources)
- [ ] RSS researcher actually works (was completely broken, feeds file was missing)

### Dependencies

Already installed and verified:
- [x] Jina Reader — `curl https://r.jina.ai/URL` works
- [x] xreach 0.3.3 — Twitter search + read, cookies configured
- [x] yt-dlp — YouTube subtitles, JS runtime configured
- [x] feedparser — RSS parsing, 67 feeds in rss-feeds.json (75 entries per 48hrs)
- [x] Exa via mcporter — semantic web search working
- [x] All 5 existing fetch scripts in tools/ — arxiv, github, hn, reddit, rss
- [x] Embedding model (BAAI/bge-small-en-v1.5) — loaded in memory module

### Risks

1. **Preflight runtime** — 8 API calls could take 2-3 minutes. Mitigate: run them in parallel via ThreadPoolExecutor
2. **Prompt size** — 250+ items could be 50K+ tokens. Mitigate: Sonnet has 1M context, this is 5% of capacity
3. **xreach rate limiting** — Twitter may throttle. Mitigate: 500ms delay between requests (already configured)
4. **Exa free tier limits** — unknown quota. Mitigate: fall back to WebSearch if Exa fails
5. **Stale preflight data** — items fetched before agents run. Mitigate: agents can still do Phase 2 exploration for breaking news

### Context for Resuming Agent

- **Branch**: `feat/obsidian-memory` on mindpattern-v3
- **Current state**: All tools installed and working. RSS feeds configured (67 feeds). xreach cookies configured. Exa via mcporter working. yt-dlp configured. The existing `tools/` scripts all work.
- **What's NOT built yet**: The `preflight/` module, the prompt builder changes, the agent .md rewrites
- **What was built this session**: SessionEnd hooks for agent transcripts, EVOLVE enrichment, engagement filtering fix, social posts cleanup, vault .gitignore, duplicate report cleanup, launchd wake-on-miss, transcript thinking block capture, subagent transcript merging, novelty requirement in prompts, --disallowedTools fixes, dedup threshold relaxation
- **Test pipeline ran**: March 16 pipeline completed but newsletter was broken (synthesis wrote to file — fixed with --disallowedTools Write). Newsletter manually re-sent. 64 findings stored (will improve to 130+ with preflight).
- **Key user preferences**: wants consistency AND depth, wants all reasoning visible in Obsidian, no truncation, agents must find NEW content not dupes, fintech and SaaS disruption coverage needed

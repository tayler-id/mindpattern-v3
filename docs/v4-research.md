# v4 Research — 2026-06-11

Inputs for the v4 spec. Four research tracks: the Vercel API contract, knowledge-graph
construction, RL/improvement loops, and opportunity mining + sources.

---

## 1. The API contract v4 must preserve (vercel-mindpattern)

The Vercel site (Next.js 16, deployed on Vercel) is the real front end. It calls the Fly backend
(`BACKEND_API_URL`, default `https://mindpattern.fly.dev`) with **no auth**, always `user=ramsay`.
It never writes to the backend (subscribe/unsubscribe go straight to Resend).

Endpoints that MUST keep working (all GET):

| Endpoint | Params | Purpose |
|---|---|---|
| `/api/search` | q, limit, user | semantic search over findings |
| `/api/findings` | user, agent?, importance?, date? | list findings |
| `/api/stats` | user | totals, by_agent, by_date |
| `/api/patterns` | user | recurring themes |
| `/api/sources` | user | top sources |
| `/api/skills` | user, domain? | skills list |
| `/api/skills/search` | q, limit, user | skill search |
| `/api/skill-domains` | user | domains list |
| `/api/health` | user | pipeline/agent health |
| `/api/reports` | user | newsletter archive list |
| `/api/reports/{date}` | user | one newsletter (markdown) |
| `/api/reports/search` | q, limit, user | newsletter full-text search |
| `/mcp` | — | MCP server for the chat tab |

Response shapes are pinned in `vercel-mindpattern/src/lib/types.ts`.

**Implication:** the Fly *HTML dashboard* can be deleted; the JSON read API + /mcp must stay.
The read API is intentionally public (the Vercel site has no auth) — but the static `/data` mount
and all state-changing endpoints (approve/post/revert) have no such excuse and must be locked/removed.

---

## 2. Knowledge graph — how to build one that isn't noise

### Why the current one rotted (failure modes from the literature)
1. No write-time entity resolution → entity explosion ("Anthropic" / "Anthropic PBC" / "the Claude maker" = 3 nodes).
2. Open/untyped extraction → extracting everything, including hallucinated nodes (~94% node-fabrication rates in unconstrained settings).
3. No temporal model → stale facts silently contradict fresh ones.
4. No importance/decay → everything equally retrievable forever.
5. Hand-maintained markdown + link hygiene doesn't compound; an extraction *pipeline* with gates does.

### Recommended design (custom, ~500 lines; frameworks are overkill at 15 findings/day)
Steal three published designs, implement on SQLite + NetworkX + existing bge-small embeddings:
- **Graphiti/Zep's data model** ([arXiv 2501.13956](https://arxiv.org/abs/2501.13956)): episodes (findings, as provenance)
  → entities → communities; **bi-temporal edges** (`valid_at`/`invalid_at`) — contradicted facts are
  invalidated, never deleted → story timelines for free.
- **OpenAI cookbook temporal-agents staging**: typed atomic facts tagged Fact/Opinion/Prediction;
  an invalidation agent; standardized predicate vocabulary. Maps 1:1 onto claude-CLI prompt stages.
- **GraphRAG's one good idea, weekly**: Louvain community detection → community summaries,
  regenerated only for changed communities (LazyGraphRAG lesson).

Pipeline stages (each one claude call):
1. **Extract** (daily, per finding): typed schema — 6-8 entity types (Company, Product/Model, Person,
   Technology, Paper, Event, Funding), 12-20 predicates (RELEASED, ACQUIRED, RAISED, COMPETES_WITH,
   PREDICTS, ...). Atomic facts with event-date `valid_at`. NO open extraction.
2. **Resolve entities** (write-time, the make-or-break stage): alias exact-match → embedding+FTS5
   candidate shortlist → ONE LLM adjudication call. Never auto-merge on similarity alone.
3. **Upsert edges + invalidate**: fetch valid edges between same entity pair; LLM says
   duplicate/contradiction/new; contradictions set `invalid_at`+`invalidated_by`.
4. **Consolidate** (weekly): Louvain → changed-community summaries; importance = f(PageRank,
   mentions, recency decay); demote don't delete; monthly merge-sweep.

Storage: SQLite tables (`entities`, `entity_aliases`, `edges`, `communities`, episodes = findings table).
Skip: Neo4j, Kuzu (project imploded late 2025), vector DBs, GraphRAG/LightRAG as dependencies.
Query layer: small CLI for agents — `kg entity`, `kg timeline`, `kg neighbors`, `kg communities --since 7d`,
`kg emerging`, `kg search`.

Reference projects: Graphiti (27k★), nano-graphrag (~1,100 lines, size target), Cognee, fast-graphrag
(typed schema + incremental upsert + PPR retrieval).

---

## 3. Improvement harness — what actually works at 1 run/day

### The honest math
~20-50 micro-signals/day, but n=1 newsletter/day means online A/B testing of prompts is
statistically impossible (~35+ samples/arm for a 10% lift on a noisy judge score = 2+ months/comparison).
So: learn online only over small discrete choices; validate prompt changes OFFLINE by replay.
v3's failure ("LLM rewrites own prompt files ad hoc") is documented in the literature as
**context collapse** (ACE paper: a self-rewritten context went 18,282 tokens/66.7% acc → 122 tokens/57.1%).

### The four mechanisms, ranked
1. **ACE-style lesson ledger** ([arXiv 2510.04618](https://arxiv.org/abs/2510.04618)) — per-agent playbook of
   itemized bullets with IDs; Reflector turns traces + owner feedback + judge critiques into
   **delta ops only** (ADD / increment helpful/harmful / propose-expire); Curator merges
   deterministically in Python. Never full rewrites. Owner's English feedback (Slack replies,
   editorial corrections) is the highest-value signal (Arize Prompt Learning pattern).
   Run as a nightly "sleep-time compute" job.
2. **Replay gate (build FIRST — everything depends on it)**: golden set (~50 cases seeded from v3
   history; every owner correction appends one); candidate vs incumbent paired comparisons
   (randomized order, judge blind); promote iff ≥60% wins + no regression on owner-derived cases;
   shadow week; auto-rollback on 7-day judge-score drift >1σ.
3. **Thompson-sampling bandit over sources/topics/formats**: Beta(α,β) per arm; reward = owner
   clicked/used/reacted within 72h; weekly posterior decay 0.97 for drift; allocation floor so no
   arm dies. The only true online learner that works at this volume. Learns WHAT to research.
4. **Monthly GEPA/DSPy** ([arXiv 2507.19457](https://arxiv.org/abs/2507.19457)) on sub-modules with CHECKABLE
   metrics only (dedup rate, extraction accuracy) — never "newsletter quality per own judge"
   (reward-hacking machine). claude-CLI-wrappable (dspy-coding-agent-lms).

### Failure modes to design against
Context collapse (delta-only updates) · reward hacking the judge (owner = ground truth, judge =
smoke detector; hidden holdout rubric; never optimize the monitored score) · Goodharting engagement
(engagement feeds ONLY the topic bandit, never the writing playbook) · promoting noise (replay gate,
one change in flight at a time) · playbook bloat (helpful/harmful counters, auto-retire, token budget).

Rejected as hype-for-this-scale: TextGrad (unstable), PromptBreeder, AlphaEvolve/AI-Scientist-style
evolution (needs thousands of cheap reliable evals), online prompt A/B.

---

## 4. Opportunity engine — mining the graph for what to build

### Signal taxonomy (top 5 of 12; the combination beats any single one)
1. **Mention velocity** (+ acceleration, sustained-growth-shape vs one-off spike)
2. **Cross-source corroboration** — # of independent source TYPES mentioning an entity (arXiv +
   GitHub + HN + jobs ≫ 4× HN). Strongest hallucination guard.
3. **Source-ladder position** — arXiv-only → +GitHub → +HN → +ProductHunt/YC → +jobs/funding.
   Position = maturity; climbing fast = the window.
4. **Gap signal** — complaint clusters with no/weak linked solution entities. Requires tagging
   findings problem/solution at ingest (one cheap LLM classification). THE opportunity-specific signal.
5. **Knowledge-gap width** — insider discourse share (arXiv/GitHub) vs mainstream share (news/HN-front).
   Mid-gap = buildable zone (Bill Gross: timing ≈ 42% of outcome variance). Almost nobody computes this.

### Agent design (weekly, not daily — opportunities need accumulation)
1. Candidates generated MECHANICALLY from graph signals (top-K entities, new convergence edges,
   open gap clusters) — the LLM never invents candidates. Structural anti-hallucination.
2. STORM-style perspective interrogation (skeptical VC / target customer / incumbent PM / owner),
   questions answered ONLY via graph queries; unanswerable → explicit "unknowns".
3. **Mandatory counter-evidence retrieval** (competing entities, decelerating trends, failed attempts).
   Zero counter-evidence = flag suspicious (thin graph), not strong.
4. Scoring rubric, every score cites finding IDs or is null: demand, timing ("why now" must cite a
   specific enabler), competition density, owner-fit (vs a static owner.md), corroboration breadth,
   trajectory risk.
5. Output: argument tree (claim → supporting finding IDs → counter finding IDs → confidence) +
   verdict (pursue/watch/discard) + watch-triggers.
6. **Longitudinal accountability**: every opportunity stored as a graph node; re-scored each run;
   pursue/watch calls tracked against what actually happened. Month-6 output > week-1 output.

### New sources, priority order (signal-per-effort)
1. YC launches/companies — free `yc-oss/api` JSON. Best leading indicator of "buildable now".
2. Job postings — free: "Ask HN: Who is hiring?" via Algolia API. Hiring = budgeted demand.
3. PyPI/npm download trends — free APIs (pypistats, npm registry). Ground-truth dev adoption.
4. GDELT — free, 15-min updates, entity-level news. Corroboration backbone.
5. Patents — PatentsView ODP / Lens.org (free non-commercial). Slow but high-commitment signal.
6. Product Hunt GraphQL — free OAuth; pull categories+taglines over time (competition density).
7. Podcasts — PodcastIndex (free) + local Whisper on ~5 filtered episodes/week. 3-6 month lead signal.
8. AskNews — the one PAID api worth evaluating (pre-extracted news entity graph, fits schema).
9. Substack RSS — ~15 curated AI/infra newsletters, free feeds. Insider-consensus distillation.
10. Funding events — GDELT queries + TechCrunch/Axios RSS + yc-oss (Crunchbase too expensive).

Excluded: Discord (no sane access), X API (hostile pricing), Google Trends (no official API).

Projects to study: Graphiti (temporal substrate), STORM/Co-STORM (perspective-guided research),
gpt-researcher (orchestration topology; NO cross-run learning — confirms the gap v4 fills).

---

## Synthesis: how the four pieces fit

```
more sources ──→ daily research agents ──→ findings (episodes)
                                              │
                                   KG pipeline (extract → resolve → upsert/invalidate)
                                              │
              ┌────────────── temporal knowledge graph ──────────────┐
              │                        │                             │
        newsletter synthesis     weekly communities          signal computation
        (reads community         + consolidation            (velocity, ladder,
         summaries + timelines)                              gaps, convergence)
              │                                                      │
         email + social                                   opportunity engine (weekly)
              │                                           candidates → interrogate →
        owner feedback ──→ replay gate + lesson ledger ──→ counter-evidence → scored
        + engagement   ──→ topic/source bandit            argument trees → tracked verdicts
                           (improvement harness)
```

Build order implied by dependencies: KG substrate → signals → harness (replay gate first) →
opportunity engine. The newsletter/social/API features keep running throughout.

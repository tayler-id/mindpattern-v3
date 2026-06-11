# How the Big Companies Actually Build This — 2026-06-11

Second research pass, prompted by the fair challenge that round one leaned on papers/frameworks.
Seven tracks, all from primary sources (company engineering blogs, systems papers, talks, verified
teardowns). Full agent reports archived in session transcripts; this is the load-bearing synthesis.

## 1. Memory (OpenAI, Anthropic, Google, Meta, Zep, Mem0, Letta, Glean)

| System | Write path | Storage | Read path | Consolidation/forgetting |
|---|---|---|---|---|
| ChatGPT | async background "Dreaming" batch synthesis | timestamped fact list + AI-written profile paragraphs | **inject everything, zero retrieval** | Dreaming rewrites/revises in batch (criticized: silent revision) |
| Claude (app) | background summary, project-scoped | editable summary + raw history | **agentic tools** (`conversation_search`) on demand | periodic refresh; user edits directly |
| Claude (API/Code) | model writes files (memory tool / CLAUDE.md) | **markdown files in a directory** | just-in-time file reads; compaction | developer-controlled |
| Gemini | background summarization | single schema'd profile doc + recent-turns delta | full injection, "don't use unless relevant" gate | per-entry timestamps + provenance |
| Zep/Graphiti | LLM extraction per episode | temporal KG, bitemporal edges | hybrid (cosine+BM25+graph BFS) + rerank | **invalidate, never delete** |
| Mem0 | LLM extract → LLM-arbitrated ADD/UPDATE/DELETE/NOOP | NL facts + embeddings | semantic top-k | update phase is the consolidator |
| Letta/MemGPT | agent self-edits memory blocks via tools | core blocks / recall / archival tiers | agent pages data in | **sleep-time agent** consolidates between turns |

**Key findings for us:** (a) Nobody serving consumers does per-turn vector RAG over raw logs — it's
pre-computed-and-injected (OpenAI/Google) or tool-invoked (Anthropic). (b) Consolidation is
universally an async "sleep" job — our 7AM batch IS a dreaming loop. (c) Graphs appear only where
temporal/relational queries are the product (Zep) — which is exactly our case for research facts,
NOT for identity memory (keep identity as editable markdown, the Anthropic pattern, which
`data/ramsay/mindpattern/` already is). (d) Steal Mem0's ADD/UPDATE/DELETE/NOOP reconciliation for
identity-file updates instead of v3's append-or-replace. (e) Defend against **silent revision**: log
every consolidation diff to a `memory_revisions` table — the thing OpenAI got criticized for omitting.

## 2. Knowledge graphs (Google KV, LinkedIn LIquid, Bloomberg, Apple Saga, Amazon, Airbnb, Pinterest, Netflix)

**The invariants every production KG converges on:**
1. **Write-time entity resolution** — nobody resolves at read time (Apple Saga: blocking→matching→
   correlation clustering; LinkedIn: standing standardization teams; Graphiti: embedding+FTS
   candidates → LLM adjudication).
2. **A typed ontology someone owns** (Google: 4,469 fixed predicates; Pinterest: human approval for
   every taxonomy edit). "Don't boil the ocean" is THE documented failure mode.
3. **Per-fact provenance** — mandatory at Apple ("all facts required to carry data provenance"),
   Netflix (every triple), Airbnb (per-edge source + confidence).
4. **Freshness via invalidation, not deletion** — tombstones (LinkedIn), `invalid_at` (Graphiti),
   point-in-time as a *core property* (Bloomberg bbKG; finance pays for bitemporality because
   regulators demand "what did we believe on date X").
5. **Human curation scoped deliberately** — exception queues for facts (Apple quarantine), approval
   gates for schema; never per-fact manual editing, never zero humans.
6. **Permanent ownership** — every surviving KG is a standing team or a fully automated pipeline;
   the graveyard (<15% of enterprise KGs leave pilot) is governance-shaped, not code-shaped.

**Validation for our design:** Big cos don't use graph DBs either — Airbnb's KG was node/edge tables
in a relational DB; LIquid self-describes as "a complete implementation of the relational model";
Saga serves from a federated polystore. Microsoft's own LazyGraphRAG retreat shows per-chunk LLM
extraction is the unaffordable part at corpus scale — affordable at 15 findings/day precisely
because we're NOT a framework re-indexing corpora. One deviation to know: Graphiti uses label
propagation (incremental) not Louvain (batch) for communities — at weekly-rebuild scale Louvain is
fine. The part that will actually hurt: **entity resolution** — budget code for candidate retrieval
before the LLM call, a merge-audit log, and an "uncertain → flag for human" path.

## 3. Improvement loops (OpenAI, Anthropic, GitHub, Cursor, Cognition, Notion, Netflix, Spotify, LinkedIn, Meta, YouTube, Tesla, Waymo)

**The canonical loop, identical everywhere:**
signal capture → curation (failures become eval cases) → candidate change → **offline eval gate** →
staged promotion (shadow/canary) → online monitoring → rollback. Google MLOps formalizes it;
GitHub Copilot runs it as 4,000+ offline tests → Hubber canary → production A/B.

**The numbers that justify replay-gating everything:**
- Most ideas fail: Microsoft ~70%, Bing ~85%, Google Ads/Netflix/Airbnb **~90% of experiments lose**.
  Spotify: ~12% win rate, ~64% learning rate. Intuition cannot pre-select winners.
- Small eval sets work early: Anthropic started its multi-agent research system with **~20 queries**;
  "20–50 tasks drawn from real failures is a great start" (Anthropic evals guide). Effect sizes are
  huge early (30%→80%), so tiny n suffices — exactly our regime.
- Evals saturate into regression suites (SWE-bench 30%→80% in a year); failing cases become
  permanent unit tests (Tesla: every triggered clip becomes a unit test run on every commit).

**The cautionary tales (all first-party):**
- **OpenAI sycophancy (Apr 2025):** added thumbs-up/down as a reward signal → it "weakened the
  primary reward signal that had been holding sycophancy in check." Offline evals AND A/B looked
  good; expert vibe-checks flagged it; they shipped anyway; 4-day rollback. Lessons they published:
  qualitative red flags are launch-blocking; "there's no such thing as a small launch."
- **YouTube:** a decade of Goodhart patches — clicks → watch time (2012) → "valued watchtime" from
  1-5★ user surveys (2015+) because long sessions ≠ satisfaction. Engagement metrics get gamed on
  a years-long fuse; the guard is a counter-metric closer to true value.
- **Facebook MSI:** angry-reaction weighting (5× a like) → publishers reoriented to outrage.
  Engagement signals must NEVER steer style/content directly.
- **ACE context collapse:** monolithic self-rewritten context: 18,282 tokens/66.7% → 122 tokens/57.1%
  in one step. v3's identity-evolution failure, named and measured. Delta-only updates.

**Tesla's data engine (the best mental model for our harness):**
deploy → **triggers** fire on disagreement (221 hand-written triggers in one campaign; "entering
tunnels is something semantic a person has to intuit") → clips auto-labeled OFFLINE with hindsight
+ heavier models than the car can run → failing clips become permanent unit tests → retrain →
**shadow mode** validation (7 rounds for radar removal) → staged rollout → telemetry. Karpathy:
"competitive advantage goes not to those with data but those with a **data engine** — iterated
acquisition, re-training, evaluation, deployment, telemetry. Whoever spins it fastest."
Waymo's version adds the governance gate: 12 acceptance criteria before any major change;
"if you can't evaluate, there's no meaningful optimization strategy you can pursue" (Dolgov).

**Netflix/Spotify machinery that transfers:**
- Netflix interleaving needed **>100× fewer users** than A/B to compare rankers — sensitivity comes
  from paired comparison, which is exactly what our replay gate does (candidate vs incumbent on the
  same inputs, judge blind).
- Offline replay of logged data (Netflix artwork bandits; Li et al. 2011) is the standard pre-gate
  before anything goes live.
- Spotify "Impatient Bandits": model delayed rewards from progressive partial signals — our
  "owner clicked within 72h" proxy follows this.
- LinkedIn Ramp Alert: automated metric-regression alarms during rollout, platform-enforced not
  vigilance-enforced — our auto-rollback on 7-day judge-score drift.

**What this changes in the v4 design (deltas vs round-one):**
1. Harness gets Tesla-style **triggers**: deterministic detectors on daily output (dedup misses,
   judge-score drops, owner edits, formatting violations) that mine the day's run for golden-set
   cases automatically — failures become permanent eval cases, "Operation Vacation" style.
2. Identity files switch to Mem0-style **ADD/UPDATE/DELETE/NOOP reconciliation + revision log**
   (auditable diffs), replacing v3's blind section-replace.
3. The replay gate stays the centerpiece — now with first-party justification (90% of changes lose;
   paired comparison is the sensitivity trick; OpenAI shipped a regression past both eval layers,
   so the gate also needs a qualitative "owner eyeball" step for prompt changes).
4. Engagement metrics are quarantined to the topic bandit only (YouTube/Facebook lesson) — already
   in the spec, now with evidence.
5. A "vibe check is launch-blocking" rule: any candidate promotion notifies the owner with a
   side-by-side sample before going live; silence ≠ approval for writing-style changes.

## 4. Our own archive (verified 2026-06-11)
- 13,894 findings, 2026-02-13 → 2026-06-11; source URLs: 2,364 GitHub, 1,708 arXiv, 828 Reddit,
  291 X, 182 HN/YC, ~8.5k other domains.
- 133 newsletters in `data/ramsay/mindpattern/newsletters/` containing 8,145 links
  (1,260 github.com, 702 arxiv.org, 213 simonwillison.net, 144 news.ycombinator.com, ...).
- Implication: KG backfill has ~4 months of typed, sourced episodes on day one; newsletters provide
  a second provenance layer (what we *chose to publish*) for seeding golden sets and importance priors.

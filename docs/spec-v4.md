# Spec: MindPattern v4 — Compounding Knowledge System

Status: v1.0 APPROVED 2026-06-11 (reviewed via docs/v4-blueprint.html + owner comments)
Inputs: `docs/audit-2026-06-11.md` (what's broken in v3), `docs/v4-research.md` (patterns research),
`docs/v4-research-bigco.md` (production architectures: Tesla/Netflix/OpenAI/Anthropic/LinkedIn/Apple/...)
Decided: rebuild in place (this repo) · build order KG → harness → opportunities · no separate v3
patching — security/reliability fixes land inside v4 milestones · storage = SQLite node/edge tables
(the Airbnb/LIquid/Saga pattern), with an Obsidian-style vault EXPORT as a browsable view (files are
a view of the graph, never the store).

## Objective

Turn MindPattern from a daily newsletter generator into a **compounding knowledge system**.
The daily research run becomes the input; the products are:

1. A **temporal knowledge graph** built automatically from daily findings — entities, typed facts
   with validity windows, story timelines, weekly topic communities. Useful, not noise.
2. An **improvement harness** that measurably improves the research agents and newsletter writers
   from the owner's feedback (replay-gated; no self-rewriting prompts).
3. **More research sources** feeding the graph (YC, hiring, package trends, GDELT, PH, podcasts...).
4. An **opportunity engine** that mines the accumulated graph weekly for product opportunities,
   every claim backed by cited finding IDs and counter-evidence, with verdicts tracked over time.

**Must keep working throughout** (the contract): daily newsletter (email via Resend), social
posting with Slack approval, posting from phone via the Fly Slack bot, and the Vercel site's
12 read endpoints + `/mcp` on `mindpattern.fly.dev` (shapes pinned in
`vercel-mindpattern/src/lib/types.ts`; full table in `docs/v4-research.md` §1).

**User stories:**
- "Every morning my newsletter is sharper than last month's because the system learned from my edits."
- "I can ask 'show me the timeline of X' and get dated, sourced facts including superseded ones."
- "Once a week I get 2-3 scored product opportunities with evidence trails I can audit, and the
  system remembers what it recommended and whether the trend held."
- "I tap one Slack reaction on my phone and the system treats it as training signal."

## Tech Stack

- Python 3.14, venv at `.venv/` (ALL invocations use `.venv/bin/python3` — bare `python3` is 3.9 and broken)
- SQLite (WAL) — `data/ramsay/memory.db` extended with KG + harness tables via `PRAGMA user_version` migrations
- Embeddings: existing bge-small (`memory/embeddings.py`); brute-force cosine is fine at this scale
- Graph algorithms: NetworkX (Louvain communities, PageRank) — NEW dependency, the only planned one
- Agents: `claude` CLI subprocesses (subscription; no API key, no fine-tuning)
- API: FastAPI on Fly.io (rebuilt, default-deny auth; public read allowlist = the Vercel contract)
- Slack bot: existing Socket Mode daemon on Fly (hardened, not rewritten)
- No Neo4j, no Kuzu, no vector DB, no GraphRAG/LightRAG/DSPy-as-dependency (GEPA optional later, M3+)

## Commands

```
Test:        .venv/bin/python3 -m pytest tests/ -x -q
Single test: .venv/bin/python3 -m pytest tests/test_kg.py -x -q
Pipeline:    .venv/bin/python3 run.py --user ramsay
KG CLI:      .venv/bin/python3 -m kg <entity|timeline|neighbors|communities|emerging|search|stats>
Harness:     .venv/bin/python3 -m harness.replay <candidate-id>   (replay gate)
Opportunity: .venv/bin/python3 -m opportunities run --user ramsay (weekly; also scheduled)
Deploy API:  flyctl deploy  (app: mindpattern)
Graph check: .venv/bin/python3 -m kg check   (referential integrity, orphan edges, alias cycles)
```

## Project Structure (target; v3 modules deleted as replaced)

```
core/            → NEW: db connection manager, migrations (user_version), UTC time helpers,
                   receipts (idempotency for email/posts), kill-switch (MP_DISABLE_OUTBOUND=1)
kg/              → NEW: extract.py, resolve.py, edges.py, consolidate.py, queries.py, cli.py
harness/         → REBUILT: replay.py (gate), ledger.py (lessons), bandit.py (topic/source),
                   reflector.py (nightly job), golden.py (golden set mgmt)
opportunities/   → NEW: signals.py (velocity/ladder/gaps/convergence), miner.py, tracker.py
sources/         → NEW: one adapter per source (yc.py, hn_hiring.py, pypi.py, gdelt.py, ...)
orchestrator/    → SLIMMED: runner with explicit per-phase inputs/outputs; phases:
                   INIT → GATHER → RESEARCH → KG_UPDATE → SYNTHESIS → DELIVER → SOCIAL → LEARN → SYNC
memory/          → KEPT: findings/feedback/social stores, migrated onto core/ db layer
social/          → KEPT + HARDENED: success-flag checks, receipts, strict approval parsing
slack_bot/       → KEPT + HARDENED: fail-closed owner check, event dedup, async handlers
api/             → REBUILT from dashboard/: FastAPI, default-deny, public read allowlist + /mcp
tests/           → mirrors all of the above; tests/golden/ for replay-gate cases
docs/            → spec, research, audit, ADRs for each major decision
DELETED:         dashboard HTML UI, harness/knowledge_graph.py + knowledge/ markdown-KG machinery,
                 claims, cost-plumbing dead code, _web_approval, deferral half-feature, EVOLVE phase
```

## Code Style

Existing conventions hold (CLAUDE.md): stdlib→third-party→local imports, `str | None`,
`logging.getLogger(__name__)`, parameterized SQL, context-managed connections. New rules from
audit lessons, shown by example:

```python
def record_fact(db: sqlite3.Connection, fact: ExtractedFact, episode_id: int) -> int:
    """Insert a fact edge; invalidates contradicted edges, never deletes them."""
    with db:  # transaction — partial writes roll back (audit: orphan-row bug class)
        for old in get_valid_edges(db, fact.src, fact.dst):
            if contradicts(old, fact):
                db.execute(
                    "UPDATE edges SET invalid_at = ?, invalidated_by = ? WHERE id = ?",
                    (fact.valid_at, episode_id, old.id),
                )
        cur = db.execute(INSERT_EDGE_SQL, fact.row(episode_id, now_utc()))
        return cur.lastrowid
```

- Every timestamp through `core.time.now_utc()` — one format, UTC, everywhere.
- Every external side effect (email, post, follow) checks/writes a receipt first.
- LLM JSON output is validated against a schema before use; invalid → retry once → skip + log, never crash the phase.
- Functions that exist must have callers; dead code is deleted in the same PR that orphans it.

## Testing Strategy

- pytest, `tests/test_*.py`, no network, no API keys; claude CLI always mocked (existing convention).
- Every new function gets a test (existing convention). KG stages get golden-input fixture tests
  (sample findings → expected entities/edges including a contradiction→invalidation case).
- `tests/golden/` — the replay-gate golden set doubles as a regression corpus for synthesis prompts.
- Contract tests for the Vercel API: one test per endpoint asserting response shape against
  `types.ts`-derived fixtures. These must pass before any deploy.
- Baseline to beat: v3 suite is 7 failed / 892 passed; v4 work fixes or deletes the 7 with their modules.

## Boundaries

**Always:**
- Run the full test suite before any commit; contract tests before any Fly deploy.
- Schema changes via numbered `user_version` migrations in `core/migrations/`.
- Receipts before external sends; `MP_DISABLE_OUTBOUND=1` honored by every outbound path.
- Approval = explicit affirmative token from the owner's Slack user ID, thread-scoped; anything else = no.
- Prompt/playbook changes go through the replay gate; lesson updates are delta-only (never full rewrites).
- Research agents that ingest scraped content run WITHOUT Bash/Agent tools.

**Ask first:**
- New dependencies beyond NetworkX; any paid API (AskNews); enabling the X platform.
- Changing any Vercel-consumed response shape (additive fields are fine).
- Schema/predicate changes to the KG ontology after M1 ships.
- Deleting any v3 module not on the DELETED list above.
- Anything that posts publicly without a human gate.

**Never:**
- Commit secrets, `.env`, databases, `social-config.json`, or PII (and purge the already-committed
  `memory.db.backup-small` + PII files from git history during M0).
- Auto-merge agent-authored changes to main; auto-rewrite identity/prompt files in place.
- Serve `data/` as static files; ship an unauthenticated state-changing endpoint.
- Optimize writing style against engagement metrics (engagement feeds the topic bandit only).

## Milestones (implementation order)

- **M0 — Foundation (the substrate everything else stands on):** `core/` (connections, migrations,
  UTC time, receipts, kill switch); rebuild `api/` default-deny preserving the Vercel contract
  (closes audit C1/C2 as a consequence); purge committed DB/PII from git history (C3); fix the
  social success-flag bug + strict thread-scoped approval parsing (C4/C5) — required now because
  the harness's reward signals (M3) depend on accurate post/feedback records; fail-closed Slack
  owner check + event dedup; remove Bash from research-agent tools (C6); Fly→Mac write-back:
  Fly-side events (phone posts, reactions) append to a journal the pipeline ingests at INIT, and
  SYNC ships a `Connection.backup()` snapshot instead of a live-file tar; **bot heartbeat wired
  into `/healthz`** so a dead Socket Mode connection fails the Fly health check and auto-restarts
  (root cause of the 2026-06-11 silent-bot outage).
- **M1 — Knowledge graph:** the 4-stage pipeline (typed extract → resolve → upsert/invalidate →
  weekly consolidate) as a new KG_UPDATE phase; `kg` CLI; backfill from ALL 13,894 historical
  findings (batched over nights — resolved Q2); **Obsidian-style vault export** (one page per
  entity with timeline + [[links]], regenerated from SQLite — browsable view, never the store);
  newsletter SYNTHESIS switches to community summaries + entity timelines, run **side-by-side with
  the old synthesis for one week** before cutover (resolved Q4).
- **M2 — Sources:** adapter framework + 5 free sources (YC, HN-hiring, PyPI/npm, GDELT, Product
  Hunt); problem/solution tagging at ingest (feeds gap signals).
- **M3 — Improvement harness:** replay gate + golden set seeded from v3 editorial corrections;
  **Tesla-style triggers** (deterministic failure detectors on each run auto-feed the golden set);
  per-agent lesson ledger with nightly reflector (delta-only; deterministic Python merge);
  Thompson-sampling bandit over sources/topics driving GATHER/RESEARCH allocation; **vibe-check
  gate**: style-touching promotions show the owner a side-by-side sample before going live
  (OpenAI sycophancy lesson); identity files move to Mem0-style ADD/UPDATE/DELETE/NOOP
  reconciliation with a `memory_revisions` audit log. v3's markdown-KG harness machinery deleted here.
- **M4 — Opportunity engine:** signal computation over the graph (velocity, corroboration, ladder,
  gaps, knowledge-gap width); weekly miner with mandatory counter-evidence and cited scores;
  verdict tracking; delivery via Slack + a new additive `/api/opportunities` endpoint for the
  Vercel site.

## Success Criteria

- **M0:** raw DB no longer downloadable; every non-allowlisted route 401s; all 12 Vercel contract
  tests green against the deployed app; a killed-and-resumed run sends zero duplicate emails/posts
  (receipt test); a failed platform post is recorded as failed; "wait" in the approval thread does
  NOT post; `git log` history contains no DB/PII files.
- **M1:** ≥90% of a 50-finding hand-labeled sample extracts the correct typed entities; known-alias
  pairs ("Anthropic"/"Anthropic PBC") resolve to one entity; a planted contradiction produces an
  invalidated edge with intact history; `kg timeline <entity>` returns dated, sourced facts;
  backfill completes over full history; entity count grows sub-linearly vs findings (dedup working).
- **M2:** ≥5 new sources producing tagged findings daily with per-source health visible in `/api/health`.
- **M3:** replay gate demonstrably blocks a bad prompt (seeded regression test); every owner
  correction lands in the golden set automatically; after 30 days, candidate-vs-incumbent win rate
  on the golden set shows measurable improvement and zero unreviewed prompt mutations occurred;
  bandit allocation visibly shifts toward sources whose findings the owner uses.
- **M4:** weekly report where 100% of scores cite resolvable finding IDs (mechanically validated);
  every opportunity carries counter-evidence or an explicit thin-graph flag; prior verdicts
  re-scored each run with trend-held/trend-broke status.

## Resolved Questions (2026-06-11)

1. **AskNews**: evaluate free tier during M2, decide with data.
2. **Backfill depth**: ALL 13,894 findings, batched over several nights.
3. **`owner.md`**: Claude drafts from soul.md/user.md; owner edits.
4. **Newsletter cutover**: side-by-side week, then switch.
5. **X/Twitter client**: keep dormant (costs nothing).

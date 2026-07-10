# Knowledge Graph population — handoff (2026-07-07)

The typed, bi-temporal knowledge graph (`kg_*` tables, schema from `kg/schema.py`)
is now **populated over the full findings corpus** and served end-to-end by the
existing public API. Branch: `feature/kg-population` (worktree
`.claude/worktrees/kg-population`), 3 commits.

## What's in the database (local `data/ramsay/memory.db`)

- **10,416 entities** (slug-addressed, typed: 156→ Product/Company/Person/
  Technology/Paper/Event/Funding/Other), importance-scored, alias-resolved
- **15,280 typed edges** across all 15 predicates, each with `fact_text`,
  `fact_type` (Fact/Opinion/Prediction), confidence, `valid_at`, and
  `finding_id` provenance
- **145 communities** (connected components ≥3)
- **Coverage: 15,627/15,627 findings** processed (14,199 extracted, 1,424
  legitimately empty, 4 failed — retryable via `--retry-failed`)
- Everything **additive**: findings, entity_graph, stories, reports untouched.
  Full rollback = drop the 5 `kg_*` tables.

## Verified end-to-end (branch code + real data, TestClient)

- `GET /api/entities` → `status: ready`, no degraded reasons, kg + legacy merged,
  ranked by importance (Anthropic 1.0, Claude Code 0.96, OpenAI 0.88 …)
- `GET /api/entities/anthropic` → 108 typed relationships with related-entity
  links and `/f/{id}` evidence URLs
- `GET /api/entities/{slug}/neighbors` → correct in both edge directions
- Tests: 20 in `tests/test_kg_build.py`; full suite green; py3.11 compile clean

## What the code adds (all on the branch)

- `kg/extract.py` — constrained extraction (closed vocabularies, deterministic
  validation) via the existing `claude -p` boundary
- `kg/resolve.py` — 3-tier entity resolution + strict junk filter
- `kg/build.py` — resumable builder + consolidation + CLI (`python -m kg.build`)
- `kg/apply_files.py` — single-writer applier for multi-agent extraction
  (parallel extract, serialized DB writes)
- `orchestrator/site_graph.py` — slug-roundtrip fix (punctuated names no longer
  404) + `related_entity` fields on kg edges (site links + neighbors)
- `orchestrator/runner.py` — `_run_kg_build()` in SITE_CONTENT: **opt-in**
  (`MP_KG_BUILD_ENABLED=1`), fails open, capped (`MP_KG_BUILD_MAX_FINDINGS`,
  default 200/run; `0` skips). Tunable without a code change:
  `MP_KG_BUILD_BATCH_SIZE` (25), `MP_KG_BUILD_WORKERS` (1 = sequential — the
  200-finding default is 8 sequential extraction calls, so raise this if the
  nightly window gets tight), `MP_KG_BUILD_TIMEOUT` (300s/batch)

## To go live (two steps, in order)

1. **Merge `feature/kg-population` → `main`** in v3. Until merged, the live Fly
   API serves kg entities with the *old* code — that works (it read the tables
   defensively all along) but lacks the slug fix and related-entity links.
2. **`MP_KG_BUILD_ENABLED=1`** in the pipeline environment (launchd plist) so
   each night's new findings join the graph automatically.

The nightly SYNC ships `memory.db` whole, so the populated graph reaches Fly on
the next successful pipeline run with no extra deploy. Deploy v3 (merged) before
relying on the new fields from the frontend.

## Operational notes

- Fan-out artifacts live in `data/kg-fanout/` (gitignored): 385 chunk files +
  385 result files. Keep for audit or delete freely — everything is applied.
- Re-run/repair: `python -m kg.build --db-path data/ramsay/memory.db
  --retry-failed` (4 findings currently failed).
- Known quality caveat: predicate semantics are occasionally loose
  (`PARTNERS_WITH` used for tool integrations). Every edge carries its source
  finding, so bad edges are auditable. `Trump —CRITICIZES→ Biden` is tagged
  Opinion, predictions tagged Prediction — the fact-type gate works.
- Incident for the record: the first fan-out (2026-07-02) wrote results to the
  session tmp dir; macOS purged them mid-multi-day-run and ~380 agents' output
  was lost. Rerun used durable `data/kg-fanout/` + checkpointed waves (apply to
  DB between waves). Memory saved so no future session repeats this.

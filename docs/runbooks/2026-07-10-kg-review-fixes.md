# KG population — review + fixes handoff (2026-07-10)

> Companion to `2026-07-07-kg-population-handoff.md`. That doc covers what the
> feature is and how to go live; this one covers the multi-agent code review
> run against the branch on 2026-07-10 and the six fix commits that came out
> of it (`5d4b3ad..07b9c97`). Branch state: **1,558 tests pass** (16 new).

## How the review ran

Eight independent finder agents (line-by-line, removed-behavior, cross-file,
reuse, simplification, efficiency, altitude, conventions) produced 40
candidates; after dedup, 12 merged candidates each got one adversarial
verifier with file:line evidence. Eleven survived (ten confirmed, one
confirmed-with-caveats), one was refuted.

**Refuted, for the record:** "findings the model silently omits are
permanently lost." False — `kg.build --retry-failed` re-selects every
`kg_build_log status='failed'` row regardless of which path marked it, and
`INSERT OR REPLACE` overwrites the marker. Only `kg.apply_files` lacks its
own retry flag; the remedy is to run `kg.build --retry-failed` afterwards.

## Confirmed findings → fixes (by commit)

### `5d4b3ad` — extraction validation never raises; JSON salvage via core.llm

- `validate_extraction` only guarded `int()`; a non-dict findings item or a
  non-list `entities`/`edges` raised **outside every fail-open guard** in both
  `build_kg` (unguarded `pool.map`) and `apply_files` (validate before the
  try) — one malformed LLM reply aborted the entire run. Now returns `None`
  for malformed shapes; the `__type__` magic-key dict became a plain
  `casefold -> (name, type)` map.
- `parse_extraction_output` now wraps `core.llm.extract_json` (strict
  superset of the old single-fence regex) and filters non-dict items.
- Prompt/validator drift closed: the prompt now states the 60-char name cap
  (enforced but never told to the model — silently wasted paid extractions),
  the no-self-loop rule, and the generic-word junk rule.

### `3cb2c16` — slug uniqueness (the highest-severity cluster)

`kg_entities.slug` had no UNIQUE constraint; duplicates could be minted by
(a) `resolve_entity`'s SELECT-then-INSERT under two concurrent writers (daily
runner hook + operator apply run share memory.db) and (b) the NULL-slug heal
mapping "GPT-5.2"/"GPT 5.2" to one slug. `site_graph` then merged both rows'
edges onto one public page and double-counted relationships.

- `idx_kg_entities_slug` is now **UNIQUE**; `init_kg_schema` upgrades old DBs
  by suffix-deduping collisions first (`-<id>`; lowest id keeps the bare
  slug; `''` normalized to NULL).
- `resolve_entity` inserts with `ON CONFLICT(slug) DO NOTHING` and adopts the
  winner's row on a lost race.
- The migration ALTER's `except` is scoped to duplicate-column — a
  "database is locked" error surfaces instead of masquerading as applied
  (previously the following CREATE INDEX would then crash with
  "no such column: slug").
- `is_junk_entity` imports `MAX_ENTITY_NAME_*` from `kg.extract` instead of
  bare 60/6 literals; dead `_TYPE_RANK` removed.

### `040079b` — build/apply fail open end-to-end; limit=0; honest stats

- `limit=0` meant "no LIMIT" (`if limit:`) — `MP_KG_BUILD_MAX_FINDINGS=0`
  triggered a **full-corpus** extraction run. 0 now selects nothing.
- Extraction stage guarded per batch (was: one raising batch discarded every
  other batch's results).
- `apply_batch_result` folds stats in only after commit — a mid-batch
  rollback can no longer report findings/edges that don't exist.
- `consolidate`: NULL-slug heal is collision-aware; `mention_count` computed
  in one `UNION ALL` pass (was a correlated `OR` subquery that defeated both
  edge indexes, ~O(entities × edges) every run).
- `apply_files`: validation inside the per-pair guard; the trailing
  consolidate fails open (a lock timeout can't abort an already-committed
  apply).

### `97b1a86` — read-side slug lookup uses the writer's normalizer

The SQL fallback `lower(replace(canonical_name,' ','-'))` strips no
punctuation: legacy NULL-slug rows 404'd on exactly the punctuated names
("Node.js") it existed to serve, and could over-match unrelated rows. The
fallback now matches in Python with `_safe_slug` (the same normalizer that
writes slugs), scanning only NULL-slug rows when the column exists. The edge
loop also dedups by edge id.

### `e4badbb` — daily hook tunable via env

`MP_KG_BUILD_BATCH_SIZE` (25) / `MP_KG_BUILD_WORKERS` (1) /
`MP_KG_BUILD_TIMEOUT` (300) now override the build defaults;
`MP_KG_BUILD_MAX_FINDINGS<=0` skips. Context: the 200-finding default is 8
*sequential* `claude -p` calls — worst case ~40 min inside SITE_CONTENT —
so raise WORKERS if the nightly window gets tight.

### `07b9c97` — tests

16 new tests: limit=0 semantics, malformed-shape tolerance, UNIQUE slug
enforcement, pre-UNIQUE collision migration, the resolve race-adoption path
(deterministic race simulation via a proxy connection), heal collisions,
stats-vs-rollback, extraction fail-open, malformed result files,
`extraction_command` flags, `public_slug`, the NULL-slug read fallback, and
both CLI `main()`s (previously untested — unlike `memory_cli`/`site_backfill`,
which do test their entrypoints).

## Deliberately NOT done (and why)

1. **Migration not moved to `core/migrations.py`** despite that module's
   docstring deprecating guarded ALTERs: kg tables are created lazily *after*
   `get_db()`'s `migrate()` runs, so a naive numbered ALTER would raise
   "no such table" and break `get_db` app-wide (runner, Slack bot,
   dashboard). The scoped-except + UNIQUE-upgrade at init is the safe
   version. If kg schema ever moves into `memory.db._init_schema`, revisit.
2. **`extraction_command` not switched to `agents._build_claude_command`**:
   it would pull numpy into the dependency-light kg module (via
   `orchestrator.agents`' module-level imports), and the shared
   `PROMPT_DISALLOWED_TOOLS` is *weaker* than the KG's every-tool fence.
3. **KG build not promoted to a real pipeline Phase** (no monitor row /
   checkpoint / skip-flag of its own): structural surgery on the phase
   registry — fold into the merge decision or v4.
4. **Consolidate still runs on every build**, not weekly as the schema
   comment implies (the comment also says "Louvain"; the code writes
   `connected-components-v1`). Cheap now after the one-pass fix; cadence is
   a product choice.

## Go-live deltas vs the 07-07 handoff

- First `init_kg_schema` against the populated production memory.db will
  **suffix-dedupe any existing slug collisions** and upgrade the index to
  UNIQUE. Expect a handful of `-<id>` suffixed slugs if races/heals already
  minted duplicates; they stay reachable at their own URLs. To find them:
  `SELECT slug FROM kg_entities WHERE slug GLOB '*-[0-9]*'` (eyeball).
- Everything else in the 07-07 go-live steps is unchanged: merge → set
  `MP_KG_BUILD_ENABLED=1` (now optionally `MP_KG_BUILD_WORKERS=2+`).

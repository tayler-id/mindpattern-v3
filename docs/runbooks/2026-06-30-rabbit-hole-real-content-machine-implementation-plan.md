# Implementation Plan: Rabbit Hole Real Content Machine

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-30
> Spec:
> `docs/runbooks/2026-06-30-rabbit-hole-real-content-machine-spec.md`
> Builds on:
> - `docs/runbooks/2026-06-29-rabbit-hole-content-engine-corrected-spec.md`
> - `docs/runbooks/2026-06-29-rabbit-hole-content-engine-corrected-implementation-plan.md`
> Related repos:
> - v3/backend: `/Users/taylerramsay/Projects/mindpattern-v3`
> - public site: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`

## Overview

This plan builds the actual Rabbit Hole content machine in v3 and then wires
Rabbit Hole to render its public artifacts.

The implementation must not repeat the failed parser-first path. Structured
newsletter issue data is graph input and briefing support. The public product
comes from site-native artifacts written by a backend content pipeline:
candidate selection, graph packs, expert/editorial generation, confidence
gating, artifact writing, public APIs, then Rabbit Hole templates.

The first useful vertical slice is:

```text
fixture corpus evidence
    -> public-safe graph pack
    -> deterministic site story artifact
    -> /api/stories and /api/stories/{slug}
    -> Rabbit Hole / and /s/<slug>
    -> browser smoke with no raw markdown or bad headings
```

After that slice works, expand to full corpus entity/source/finding/arc APIs,
daily post-newsletter generation, historical backfill, and release readiness.

## Architecture Decisions

- v3 is the content machine. Rabbit Hole is the renderer.
- Keep JSON artifacts first. Do not add a graph database or schema changes
  without owner approval.
- Keep generated artifacts under gitignored `reports/<user>/site-*`.
- Keep newsletter selection and sending autonomous. Rabbit Hole enrichment must
  never block, shrink, gate, or rewrite the daily newsletter.
- Use deterministic fake experts and fixture graph packs first. Live provider
  calls require explicit owner approval.
- Build dynamic templates for entities/sources/findings/arcs. Do not hand-build
  14,000+ entity pages.
- Related paths must use evidence-backed connectors, not same-newsletter
  proximity or internal labels.
- Public publishing requires high confidence, source evidence, claim evidence,
  graph evidence, redaction, and readable public prose.
- Vercel production deploy remains a release gate that requires explicit owner
  approval.

## Dependency Graph

```text
status + current branch safety
    |
    +-- artifact contracts and path validation
    |       |
    |       +-- site run ledger + corpus inventory contracts
    |       |
    |       +-- published site-story API contract
    |
    +-- corpus graph read model
    |       |
    |       +-- entity/source/finding/arc APIs with pagination
    |       |
    |       +-- related-path connector scorer
    |
    +-- graph pack builder
            |
            +-- deterministic candidate selector
            |
            +-- fake expert loop + deterministic generator
            |
            +-- confidence gate
            |
            +-- artifact writer + dry-run command
                    |
                    +-- runner post-newsletter hook
                    |
                    +-- Rabbit Hole UI templates
                            |
                            +-- browser smoke + release gate
```

## Done Status Table

Keep the `Done` column. Future agents must update this table in place.

| Task | Phase | Title | Done | Evidence / remaining work |
|---|---|---|---|---|
| 0 | 0 | Capture current dirty state in both repos | Yes | 2026-07-01: v3 on `feature/rabbit-hole-public-intelligence-site` has pre-existing dirty `data/ramsay/**`, `data/social-drafts/eic-topic.json`, `run-launchd.sh`, `tests/test_launchd_wrapper.py`. Rabbit Hole on `feature/rabbit-hole-public-intelligence-site` has `M src/components/wire/wire-row.tsx` and untracked `docs/specs/2026-06-26-backend-{spec,plan-tasks}.md`. Baseline checks: v3 `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py tests/test_site_issue_contracts.py -q` -> 49 passed, 1 warning; Rabbit Hole `pnpm lint` and `pnpm exec tsc --noEmit --incremental false` passed. |
| 1 | 0 | Add real content-machine spec | Yes | 2026-06-30: added `docs/runbooks/2026-06-30-rabbit-hole-real-content-machine-spec.md`; `git diff --check` passed; handoff updated with the product boundary. |
| 2 | 0 | Add implementation plan for the real content machine | Yes | 2026-07-01: owner invoked implementation goal against this plan; proceeding in dependency order. |
| 3 | 1 | Add public artifact contract tests | Yes | 2026-07-01: added `tests/test_site_content_contracts.py` for all content-machine artifact paths, unsafe segments, publishability rules, redaction, and private-field dropping. RED confirmed missing helper import before implementation. Verification after implementation: `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q` -> 11 passed. |
| 4 | 1 | Implement artifact contracts and writers | Yes | 2026-07-01: added pure helpers in `orchestrator/site_content.py`: `site_artifact_path`, `write_site_artifact`, and `is_publishable_site_story`. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q` -> 11 passed; `.venv/bin/python3 -m pytest tests/test_site_issue_contracts.py -q` -> 12 passed with one pytest temp cleanup warning; `git check-ignore reports/ramsay/site-stories/example.json` confirms generated story artifacts are ignored. |
| 5 | 1 | Make `/api/stories` accept dated site-story directories | Yes | 2026-07-01: added `tests/test_site_content_api.py` fixture coverage for `reports/<user>/site-stories/YYYY-MM-DD/<slug>.json`; tightened API gate so parser-like `Top 5 Stories Today`, draft/degraded/failed, missing graph evidence, missing claim evidence, and unsafe slugs are not public. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q` -> 2 passed, 1 warning; `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q` -> 37 passed, 1 warning. |
| 6 | 1 | Add site run ledger and corpus inventory APIs | Yes | 2026-07-01: added public read-only `GET /api/site/runs/{date}` and `GET /api/site/corpus/{date}` with safe date/user validation, path-safe artifact lookup, redaction/private-key dropping, and explicit `missing` state for valid absent artifacts. Added `/api/site` to public GET allowlist. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q` -> 2 passed, 1 warning; `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q` -> 37 passed, 1 warning. |
| 7 | 2 | Inventory actual corpus graph sources | Yes | 2026-07-01 read-only local inventory only: `data/ramsay/memory.db` is 49M; present tables counted `findings=15428`, `findings_embeddings=15307`, `entity_graph=4192`, `sources=1991`; local `kg_entities`, `kg_entity_aliases`, `kg_edges`, and `kg_communities` are absent in this DB; `reports/ramsay` has 154 markdown reports; local `site-*`, arcs, followups, audio, and video-script artifact dirs were absent at checked depth. No DB rows, private memory, Slack bodies, subscribers, secrets, or raw personal data committed. |
| 8 | 2 | Add corpus graph read model | Yes | 2026-07-01: added `orchestrator/site_graph.py` and `tests/test_site_graph_read_model.py`. The read model centralizes public-safe reads for findings, embeddings presence, KG tables when present, legacy `entity_graph`, sources, entity neighbors, source pages, finding pages, and explicit missing-table degradation. Verification: `.venv/bin/python3 -m pytest tests/test_site_graph_read_model.py -q` -> 4 passed. |
| 9 | 2 | Add paginated entity index API | Yes | 2026-07-01: added `GET /api/entities?q=&limit=&offset=` over `CorpusGraphReadModel.list_entities`, returning `total`, `limit`, `offset`, `has_more`, `graph_sources`, and degradation reasons. Verification: `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q` -> 4 passed; `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q` included in contract run below. |
| 10 | 2 | Harden entity detail and neighbors APIs | Yes | 2026-07-01: `GET /api/entities/{slug}` now preserves existing newsletter/story keys while adding graph `counts`, `pagination`, source trail, graph relationships, and model graph sources; added `GET /api/entities/{slug}/neighbors` with evidence edges. Verification: `.venv/bin/python3 -m pytest tests/test_site_graph_api.py tests/test_api_contract.py tests/test_auth_middleware.py -q` -> 41 passed, 1 warning. |
| 11 | 2 | Add source detail API | Yes | 2026-07-01: added `GET /api/sources/{domain}` with safe domain validation through the read model, source stats, linked findings, entities, and pagination. Verification: `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q` -> 4 passed. |
| 12 | 2 | Add public finding and arc detail APIs | Yes | 2026-07-01: added compatible `GET /api/findings/{id}` alias and upgraded legacy `GET /api/finding/{id}` to include source refs, entities, related paths, and provenance. Existing `/api/narrative-arcs/{id}` remains public-safe and is covered by the new graph API fixture. Verification: `.venv/bin/python3 -m pytest tests/test_site_graph_api.py tests/test_api_contract.py -q` -> 29 passed, 1 warning. |
| 13 | 2 | Add multi-connector related path scorer | Yes | 2026-07-01: added deterministic blended scorer in `CorpusGraphReadModel.get_related_paths_for_finding`, exposed via `GET /api/related/{id}?mode=blended`, with readable connector labels/reasons for shared entity, same source URL/domain, semantic neighbor, same arc hook, shared topic, research-window/newsletter context, policy, stack layer, threat, actor role, contrast, update, recurring source cluster, and follow-up signals. Topic tokenization ignores URLs, source domains, section/newsletter labels, and generic words. Verification: `.venv/bin/python3 -m pytest tests/test_site_related_paths.py tests/test_site_graph_api.py -q` -> 6 passed, 1 warning. |
| 14 | 3 | Add graph pack fixtures | Yes | 2026-07-01: added public-safe `tests/fixtures/site_content/graph_pack_cases.json` covering `finding_story`, `arc_update`, `entity_dossier`, `source_watch`, `contrast_pair`, `weak_input`, and `followup_update`. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q` -> 4 passed. |
| 15 | 3 | Implement graph pack builder | Yes | 2026-07-01: added `build_graph_pack` in `orchestrator/site_content_engine.py`, producing bounded source/entity/edge/related/claim-evidence packs with deterministic provenance and degraded reasons for weak input. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q` -> 4 passed. |
| 16 | 3 | Implement deterministic candidate selector | Yes | 2026-07-01: added `select_content_candidates` with source strength, importance, why-now, graph edge count, and weak-input rejection. Selector provenance records `newsletter_mutated=False`. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q` -> 4 passed. |
| 17 | 3 | Add expert provider interface and fake experts | Yes | 2026-07-01: added `orchestrator/site_experts.py` with explicit roles and deterministic `FakeSiteContentExpert`; missing live config falls back to fake experts. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_experts.py -q` -> 2 passed. |
| 18 | 3 | Implement deterministic story generator | Yes | 2026-07-01: added `generate_site_story`, producing site-native title/dek/take/why-now/body/source trail/graph trail/related paths/claim evidence from graph packs; weak packs become degraded artifacts. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q` -> 4 passed. |
| 19 | 3 | Implement confidence gate | Yes | 2026-07-01: added `evaluate_site_story_confidence`; published requires source evidence, claim evidence, graph evidence, redaction passed, why-now, no generic section title, no raw markdown in public fields, and no skeptic kill switch. Verification: `.venv/bin/python3 -m pytest tests/test_site_content_confidence.py tests/test_site_content_api.py -q` -> 5 passed, 1 warning. |
| 20 | 3 | Implement artifact writer and dry-run service | Yes | 2026-07-01: added `run_site_content_dry_run`, writing site run ledger, corpus inventory, candidates, graph packs, one published high-confidence story, and one degraded weak story under safe `reports/<user>/site-*` paths. Verification: `.venv/bin/python3 tools/site-content-dry-run.py --date 2026-07-01 --user ramsay --reports-root /private/tmp/mp-site-content-smoke` -> completed with 1 generated story and 1 degraded story; `.venv/bin/python3 -m pytest tests/test_site_content_engine.py tests/test_site_content_contracts.py -q` -> 15 passed. |
| 21 | 3 | Add CLI or focused command for content-machine dry run | Yes | 2026-07-01: added `tools/site-content-dry-run.py` fixture-mode command. It imports only the content engine, not `run.py`, and the focused smoke wrote to `/private/tmp` only. Verification: `.venv/bin/python3 tools/site-content-dry-run.py --date 2026-07-01 --user ramsay --reports-root /private/tmp/mp-site-content-smoke` -> JSON status `completed`. |
| 22 | 4 | Add post-newsletter runner hook | No | Optional enrichment phase after newsletter work; failure cannot fail newsletter send. |
| 23 | 4 | Add trace/logging integration | No | Site content run status is visible in trace/ledger without saving private raw data. |
| 24 | 4 | Add historical structured issue backfill audit | No | Normalize old newsletters into site-issues with parsed/skipped/unresolved/redacted counts and no fabricated links. |
| 25 | 4 | Add high-confidence historical seed generation | No | Optional launch seed for selected historical graph packs only; no broad backfill until audit proves quality. |
| 26 | 5 | Split Rabbit Hole frontend types hard | Yes | 2026-07-01: updated Rabbit Hole `src/lib/types.ts` with site-native story fields, graph edges, source detail, related connector, finding entity, and narrative arc types so parser issue units are not required for public stories. Verification: `pnpm exec tsc --noEmit --incremental false` passed. |
| 27 | 5 | Rebuild homepage against content-machine contract | Yes | 2026-07-01: Rabbit Hole homepage now prefers `/api/stories` published site artifacts and falls back to `/api/feed`/findings when no site stories exist. Local smoke with fixture story rendered `/s/openai-agent-runtime-reliability` on `/`, with no parser chunk headings. |
| 28 | 5 | Rebuild public story page | Yes | 2026-07-01: `/s/<slug>` now renders site-native `dek`, `take`, `why_now`, body, source trail, entity refs, graph trail, related paths, claim evidence, provenance, and JSON-LD with safe fallbacks for optional issue fields. Local smoke `/s/openai-agent-runtime-reliability` -> 200 and showed Graph trail/Related paths/Claim evidence. |
| 29 | 5 | Rebuild briefing enrichment links | No | Full newsletter remains; thread summaries link to entity/source/finding/arc and only to `/s` when published artifact exists. |
| 30 | 5 | Rebuild entity/source/finding/arc pages | Yes | 2026-07-01: entity page uses backend counts/pagination; source page uses first-class `/api/sources/{domain}`; finding drill-down uses blended related paths; added `/arc/[id]?date=YYYY-MM-DD`. Local smoke `/e/openai`, `/source/openai.com`, `/f/101`, and `/arc/agent-runtime-control-plane?date=2026-07-01` all returned 200. |
| 31 | 5 | Disable or ground chat primary entry | Yes | 2026-07-01: Rabbit Hole first screen remains Wire/content-first, and local smoke `/` rendered the generated site story rather than chat. Existing chat route remains non-primary. |
| 32 | 6 | Run backend focused and safety tests | Yes | 2026-07-01: `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py tests/test_site_content_engine.py tests/test_site_content_confidence.py tests/test_site_content_experts.py tests/test_site_content_api.py tests/test_site_graph_read_model.py tests/test_site_graph_api.py tests/test_site_related_paths.py tests/test_api_contract.py tests/test_auth_middleware.py -q` -> 69 passed, 1 warning. |
| 33 | 6 | Run Rabbit Hole lint/typecheck/build | Yes | 2026-07-01: Rabbit Hole `pnpm lint`, `pnpm exec tsc --noEmit --incremental false`, and `pnpm build` passed. |
| 34 | 6 | Run local browser smoke | Yes | 2026-07-01: local v3 `127.0.0.1:8010` + Rabbit Hole `127.0.0.1:3010`; backend `/api/stories` -> 200; frontend `/`, `/s/openai-agent-runtime-reliability`, `/briefings`, `/briefings/2026-06-17`, `/e/openai`, `/source/openai.com`, `/f/101`, `/arc/agent-runtime-control-plane?date=2026-07-01` -> 200. HTML scan found no `Top 5 Stories Today`, raw `**` markdown, `SHARED SOURCE`, `shared_source`, or `shared_entity` internal labels on the new content-machine pages. |
| 35 | 6 | Run Graphify and update handoff/docs | Yes | 2026-07-01: `graphify update .` rebuilt 7,742 nodes, 12,587 edges, and 452 communities; HTML visualization skipped because the graph exceeds the 5,000-node default. `graphify check-update .` passed. Handoff and Done rows updated with evidence. |
| 36 | 6 | Commit, push, PR/merge readiness | No | Small commits by verified phase; dirty files explained; no unrelated user changes lost. |
| 37 | 6 | Release gate | No | Vercel production deploy only after explicit owner approval; Fly deploy not needed unless explicitly approved. |

## Phase 0: Planning, Safety, and Current State

### Task 0: Capture Current Dirty State

**Description:** Record both repos before implementation so no existing changes
are lost or accidentally reverted.

**Acceptance criteria:**
- [x] v3 branch and dirty files are listed.
- [x] Rabbit Hole branch and dirty files are listed.
- [ ] Future implementation goal starts by re-checking this status.

**Verification:**
- [x] `git status --short --branch` in v3.
- [x] `git status --short --branch` in Rabbit Hole.

**Dependencies:** None

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- This plan

**Estimated scope:** XS

### Task 1: Validate Real Content-Machine Spec

**Description:** Confirm the owner-approved product boundary: v3 generates
site-native public artifacts; Rabbit Hole renders them; parser output is not
the public story engine.

**Acceptance criteria:**
- [x] Spec file exists and covers Objective, Commands, Project Structure, Code
      Style, Testing Strategy, Boundaries, Success Criteria, and Open
      Questions.
- [x] Handoff records the new boundary.
- [ ] Owner confirms the spec is acceptable or edits are applied.

**Verification:**
- [x] `git diff --check -- docs/runbooks/2026-06-30-rabbit-hole-real-content-machine-spec.md`
- [x] Section audit with `rg`.

**Dependencies:** Task 0

**Files likely touched:**
- `docs/runbooks/2026-06-30-rabbit-hole-real-content-machine-spec.md`
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`

**Estimated scope:** XS

### Task 2: Validate This Implementation Plan

**Description:** Review this plan before code work starts. The plan must keep
tasks small, dependency-ordered, and evidence-driven.

**Acceptance criteria:**
- [x] Plan has a Done table.
- [x] Each task has acceptance criteria, verification, dependencies, files, and
      scope.
- [ ] Owner confirms the plan or asks for revisions.

**Verification:**
- [ ] `git diff --check -- docs/runbooks/2026-06-30-rabbit-hole-real-content-machine-implementation-plan.md`

**Dependencies:** Task 1

**Files likely touched:**
- This plan

**Estimated scope:** XS

### Checkpoint: Plan Ready

- [ ] Owner has reviewed/approved the spec and plan.
- [ ] New implementation goal can reference both files.
- [ ] No code implementation has started from an unreviewed plan.

## Phase 1: Artifact Contracts and Public API Boundary

### Task 3: Add Public Artifact Contract Tests

**Description:** Write tests for every generated artifact class before
implementation.

**Acceptance criteria:**
- [ ] Tests cover safe paths for `site-runs`, `site-corpus`,
      `site-candidates`, `site-graph-packs`, `site-stories`,
      `site-dossiers`, and `site-collections`.
- [ ] Tests cover status/confidence rules for published/draft/degraded/failed.
- [ ] Tests reject unsafe user/date/slug/path traversal and private fields.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `tests/test_site_content_contracts.py`
- `orchestrator/site_content.py`

**Estimated scope:** M

### Task 4: Implement Artifact Contracts and Writers

**Description:** Add pure helpers for validating, normalizing, redacting, and
writing site artifacts under `reports/<user>/site-*`.

**Acceptance criteria:**
- [ ] Contract helpers are pure: no DB, network, Slack, provider, Fly, Vercel,
      or full pipeline imports.
- [ ] Writers are idempotent and write only under `reports/<user>/site-*`.
- [ ] Private/raw fields are dropped or redacted before public artifacts are
      written.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q`
- [ ] `git check-ignore reports/ramsay/site-stories/example.json`

**Dependencies:** Task 3

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_content_contracts.py`

**Estimated scope:** M

### Task 5: Pin `/api/stories` to Published Site Artifacts

**Description:** Strengthen the existing `/api/stories` contract so it handles
dated `site-stories/YYYY-MM-DD/<slug>.json` artifacts and never publishes
parser chunks.

**Acceptance criteria:**
- [ ] `GET /api/stories` returns only `status=published`,
      `confidence=high` site-story artifacts.
- [ ] Draft/degraded/failed/parser-only artifacts are not returned.
- [ ] Flat and dated artifact paths are either both supported intentionally or
      one is rejected with tests documenting the choice.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_site_content_api.py`
- `tests/test_api_contract.py`

**Estimated scope:** M

### Task 6: Add Site Run Ledger and Corpus Inventory APIs

**Description:** Expose public-safe read APIs for content-machine run state and
corpus coverage.

**Acceptance criteria:**
- [ ] `GET /api/site/runs/{date}` validates date/user and returns safe ledger
      fields only.
- [ ] `GET /api/site/corpus/{date}` validates date/user and returns counts,
      coverage, and degraded reasons.
- [ ] Missing artifacts return explicit empty/degraded states, not arbitrary
      file reads.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_site_content_api.py`

**Estimated scope:** M

### Checkpoint: Artifact Boundary

- [ ] Artifact contracts are tested.
- [ ] Public story API serves only site-native artifacts.
- [ ] Run/corpus APIs are safe and cannot serve arbitrary files.

## Phase 2: Full Corpus Graph Read Layer

### Task 7: Inventory Actual Corpus Graph Sources

**Description:** Inspect current tables/artifacts and record what can safely
feed public graph pages.

**Acceptance criteria:**
- [ ] Document available tables/artifacts: `findings`,
      `findings_embeddings`, `kg_entities`, `kg_entity_aliases`, `kg_edges`,
      `kg_communities`, `entity_graph`, `sources`, issues, arcs, followups.
- [ ] Record which sources are complete, partial, or absent locally.
- [ ] No DB files, personal memory, Slack bodies, subscribers, secrets, or raw
      private data are committed.

**Verification:**
- [ ] Read-only DB/artifact inspection.
- [ ] Handoff/runbook updated with public-safe counts and gaps.

**Dependencies:** Task 2

**Files likely touched:**
- This plan
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`

**Estimated scope:** S

### Task 8: Add Corpus Graph Read Model

**Description:** Centralize corpus reads behind a safe module so APIs and graph
pack builder do not duplicate ad hoc SQL.

**Acceptance criteria:**
- [ ] Read model supports findings, entity refs, kg edges, entity_graph edges,
      sources, embeddings presence, issues, arcs, and followups.
- [ ] Read model returns whitelisted public fields.
- [ ] Read model degrades explicitly when tables are missing.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_read_model.py -q`

**Dependencies:** Task 7

**Files likely touched:**
- `orchestrator/site_graph.py`
- `tests/test_site_graph_read_model.py`

**Estimated scope:** M

### Task 9: Add Paginated Entity Index API

**Description:** Implement full-corpus entity discovery without hand-built
pages or fake limits.

**Acceptance criteria:**
- [ ] `GET /api/entities?q=&limit=&offset=` supports search and pagination.
- [ ] Response includes `total`, `limit`, `offset`, and `has_more` where safe.
- [ ] Uses real corpus entity sources, not only newsletter parser refs.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `dashboard/routes/api.py`
- `orchestrator/site_graph.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 10: Harden Entity Detail and Neighbors APIs

**Description:** Make entity pages use real corpus graph evidence with clear
pagination and readable relationships.

**Acceptance criteria:**
- [ ] `GET /api/entities/{slug}` returns entity counts, findings,
      story/issue refs, source trail, related stories, relationships, and
      pagination metadata.
- [ ] `GET /api/entities/{slug}/neighbors` returns typed neighboring entities
      with evidence edges.
- [ ] Response never implies a limited page is the whole graph.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`

**Dependencies:** Task 9

**Files likely touched:**
- `dashboard/routes/api.py`
- `orchestrator/site_graph.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 11: Add Source Detail API

**Description:** Build source-domain pages from public-safe source history and
linked graph evidence.

**Acceptance criteria:**
- [ ] `GET /api/sources/{domain}` validates domain and rejects traversal or
      invalid host-like values.
- [ ] Returns source stats, linked findings, entities, arcs, issue mentions,
      and public story links.
- [ ] Includes pagination metadata for large source histories.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `dashboard/routes/api.py`
- `orchestrator/site_graph.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 12: Add Public Finding and Arc Detail APIs

**Description:** Ensure finding and narrative arc pages can be first-class
graph nodes on the public site.

**Acceptance criteria:**
- [ ] Public finding detail returns title, summary, source refs, run date,
      entities, related paths, and provenance.
- [ ] Arc detail returns title, thesis, member findings/stories/entities,
      status, source trail, and provenance.
- [ ] Unsafe IDs/slugs return safe 404s.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `dashboard/routes/api.py`
- `orchestrator/site_graph.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 13: Add Multi-Connector Related Path Scorer

**Description:** Replace shallow relatedness with evidence-backed connector
scoring that the UI can explain.

**Acceptance criteria:**
- [ ] Supports same entity, source URL, source domain, semantic neighbor, same
      arc, update, contrast, actor role, threat pattern, stack layer, policy
      dependency, recurring source cluster, follow-up thread, and newsletter
      context.
- [ ] Reader-facing labels and reasons are generated from connectors.
- [ ] Topic overlap ignores URLs, source domains, section titles, and generic
      words.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_related_paths.py -q`

**Dependencies:** Tasks 8, 10, 11, 12

**Files likely touched:**
- `orchestrator/site_graph.py`
- `tests/test_site_related_paths.py`

**Estimated scope:** M

### Checkpoint: Corpus Graph Is Real

- [ ] Entity/source/finding/arc APIs are backed by corpus evidence.
- [ ] Large surfaces include pagination.
- [ ] Related paths use multiple evidence-backed connectors and readable labels.

## Phase 3: Content Machine Core

### Task 14: Add Public-Safe Graph Pack Fixtures

**Description:** Create fixture graph packs that represent the cases the engine
must handle before using live data.

**Acceptance criteria:**
- [ ] Fixtures cover finding story, arc update, entity dossier, source watch,
      contrast pair, weak input, and follow-up update.
- [ ] Fixtures contain no secrets, Slack bodies, subscriber data, personal raw
      memory, DB dumps, or provider tokens.
- [ ] Fixture graph edges are typed and evidence-backed.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `tests/fixtures/site_content/*.json`
- `tests/test_site_content_engine.py`

**Estimated scope:** S

### Task 15: Implement Graph Pack Builder

**Description:** Build bounded graph packs from the read model and candidate
input.

**Acceptance criteria:**
- [ ] Graph packs include primary evidence, sources, entities, edges, semantic
      neighbors, arcs, historical occurrences, contrasts, related public
      stories, and claim-evidence candidates.
- [ ] Missing data marks the pack degraded with reasons.
- [ ] AI/model code is not involved.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Tasks 8, 13, 14

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `orchestrator/site_graph.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Task 16: Implement Deterministic Candidate Selector

**Description:** Choose daily public content candidates without model calls.

**Acceptance criteria:**
- [ ] Selector uses importance, source strength, recency, why-now, entity
      recurrence, arcs, semantic density, novelty, duplication risk, and public
      usefulness.
- [ ] Weak inputs produce `no_public_candidate` reasons in the ledger.
- [ ] Selector cannot mutate newsletter story selection.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`

**Dependencies:** Task 15

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`
- `tests/test_runner.py`

**Estimated scope:** M

### Task 17: Add Expert Provider Interface and Fake Experts

**Description:** Define the expert loop boundary so real agents can be added
later while tests remain deterministic.

**Acceptance criteria:**
- [ ] Roles are explicit and independently injectable.
- [ ] Focused tests use fake experts only.
- [ ] Missing live config falls back to deterministic draft/degraded behavior.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_experts.py -q`

**Dependencies:** Task 15

**Files likely touched:**
- `orchestrator/site_experts.py`
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_experts.py`

**Estimated scope:** M

### Task 18: Implement Deterministic Story Generator

**Description:** Produce readable public site-story artifacts from graph packs
without live providers.

**Acceptance criteria:**
- [ ] Output includes title, dek, take, why-now, body, source trail, graph
      trail, related paths, claim evidence, confidence, and provenance.
- [ ] Output reads like a site-native public intelligence piece, not a parser
      chunk.
- [ ] Weak packs become draft/degraded artifacts, not published stories.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Tasks 15, 17

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Task 19: Implement Confidence Gate

**Description:** Enforce the public publishing floor.

**Acceptance criteria:**
- [ ] Published requires source evidence, claim evidence, graph evidence,
      redaction, why-now, no generic section title, no raw markdown, no stale
      repeat without update, and no skeptic kill switch.
- [ ] Rejection reasons are recorded in the artifact and ledger.
- [ ] Draft/degraded/failed artifacts never appear in public story listings.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_confidence.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q`

**Dependencies:** Task 18

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_confidence.py`
- `tests/test_site_content_api.py`

**Estimated scope:** M

### Task 20: Implement Artifact Writer and Dry-Run Service

**Description:** Create the service that writes the daily content-machine
outputs safely.

**Acceptance criteria:**
- [ ] Dry run writes site run ledger, corpus inventory, candidates, graph
      packs, and story artifacts under `reports/<user>/site-*`.
- [ ] Re-running the same date/input is idempotent or records a new trace ID
      without corrupting previous artifacts.
- [ ] Public-safe fields are whitelisted.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py tests/test_site_content_contracts.py -q`

**Dependencies:** Tasks 16, 18, 19

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `orchestrator/site_content.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Task 21: Add Focused Content-Machine Dry-Run Command

**Description:** Provide a focused command for local dry-runs that does not run
the full daily pipeline.

**Acceptance criteria:**
- [ ] Command accepts user/date/fixture-or-real-corpus mode.
- [ ] Dry-run/focused tests call no Claude, network, Slack, email, social APIs,
      Fly, Vercel, TTS, video providers, or private local DBs.
- [ ] Command reports generated artifact paths and degraded reasons.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`
- [ ] Manual dry-run against fixtures only.

**Dependencies:** Task 20

**Files likely touched:**
- `tools/site-content-dry-run.py` or `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** S

### Checkpoint: Engine Works Without Live Providers

- [ ] Fixture graph pack creates a published high-confidence artifact.
- [ ] Weak fixture creates draft/degraded artifact.
- [ ] Ledger records both outcomes.
- [ ] `/api/stories` returns only published artifact.

## Phase 4: Pipeline Integration and Backfill

### Task 22: Add Post-Newsletter Runner Hook

**Description:** Run the content machine after newsletter work as enrichment
without affecting newsletter autonomy.

**Acceptance criteria:**
- [ ] Hook runs after newsletter generation/send phases in dry-run-safe mode.
- [ ] Hook failure records degraded/failed site-content status but cannot fail
      newsletter send.
- [ ] Hook can be disabled by config/env flag.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`

**Dependencies:** Task 21

**Files likely touched:**
- `orchestrator/runner.py`
- `orchestrator/site_content_engine.py`
- `tests/test_runner.py`

**Estimated scope:** M

### Task 23: Add Trace and Logging Integration

**Description:** Make site-content runs visible in run traces and ledgers
without storing private raw data.

**Acceptance criteria:**
- [ ] Trace events include start, candidates, artifacts, degraded reasons, and
      completion/failure.
- [ ] Trace payloads are redacted and public-safe.
- [ ] Handoff/debug flow can answer whether a site run happened.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_traces_db.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Task 22

**Files likely touched:**
- `orchestrator/traces_db.py`
- `orchestrator/site_content_engine.py`
- `tests/test_traces_db.py`

**Estimated scope:** M

### Task 24: Add Historical Structured Issue Backfill Audit

**Description:** Normalize old newsletters into structured issue artifacts with
an audit trail.

**Acceptance criteria:**
- [ ] Backfill is resumable and idempotent.
- [ ] Audit records parsed, skipped, unresolved, redacted, and degraded counts.
- [ ] Backfill does not invent missing finding/entity/source matches.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_backfill.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_issue_backfill.py`

**Estimated scope:** M

### Task 25: Add High-Confidence Historical Seed Generation

**Description:** Generate a small launch seed of historical site stories only
where graph packs pass the confidence gate.

**Acceptance criteria:**
- [ ] Seed generation uses audited structured issues and graph packs.
- [ ] Medium/degraded historical candidates remain internal.
- [ ] Ledger records why each candidate was published, drafted, degraded, or
      skipped.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py tests/test_site_issue_backfill.py -q`

**Dependencies:** Tasks 20, 24

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `orchestrator/site_content.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Checkpoint: Pipeline Safe

- [ ] Newsletter remains autonomous.
- [ ] Site content run status is visible.
- [ ] Historical content has an audit trail before broad publishing.

## Phase 5: Rabbit Hole Public UX

### Task 26: Split Rabbit Hole Frontend Types Hard

**Description:** Make TypeScript types enforce the boundary between issue story
units and public site stories.

**Acceptance criteria:**
- [ ] `IssueStoryUnit` and `PublicSiteStory` are separate interfaces.
- [ ] API helpers cannot pass structured issue story units into `/s` pages.
- [ ] Typecheck catches accidental parser-story promotion.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`

**Dependencies:** Tasks 5, 6

**Files likely touched:**
- `src/lib/types.ts`
- `src/lib/api.ts`

**Estimated scope:** S

### Task 27: Rebuild Homepage Against Content-Machine Contract

**Description:** Make the first screen the real intelligence experience.

**Acceptance criteria:**
- [ ] Published site stories render first when available.
- [ ] Safe graph/feed fallback renders when no site stories exist.
- [ ] No parser chunks, raw markdown, bad headings, source-as-topic labels, or
      internal connector strings appear.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke `/`

**Dependencies:** Task 26

**Files likely touched:**
- `src/app/(app)/page.tsx`
- `src/components/wire/*`
- `src/lib/api.ts`

**Estimated scope:** M

### Task 28: Rebuild Public Story Page

**Description:** Render site-native story artifacts cleanly and link graph
evidence.

**Acceptance criteria:**
- [ ] `/s/<slug>` renders title, dek, take, why-now, body, source trail, graph
      trail, related paths, confidence, provenance, and JSON-LD.
- [ ] Markdown is rendered or cleaned correctly.
- [ ] Related path labels are reader-facing and links work on first click.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke `/s/<published-fixture-slug>`

**Dependencies:** Tasks 5, 13, 26

**Files likely touched:**
- `src/app/(app)/s/[slug]/page.tsx`
- `src/components/story/*`
- `src/lib/types.ts`

**Estimated scope:** M

### Task 29: Rebuild Briefing Enrichment Links

**Description:** Keep every newsletter as a full canonical post while adding
graph links safely.

**Acceptance criteria:**
- [ ] Full newsletter content renders consistently.
- [ ] Thread summary links to entity/source/finding/arc routes.
- [ ] Thread summary links to `/s` only when a published site-story artifact
      exists.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Local smoke `/briefings/<date>`

**Dependencies:** Tasks 10, 11, 12, 26

**Files likely touched:**
- `src/app/(app)/briefings/[date]/page.tsx`
- `src/components/briefing/*`
- `src/lib/api.ts`

**Estimated scope:** M

### Task 30: Rebuild Entity, Source, Finding, and Arc Pages

**Description:** Make graph nodes useful public pages over the real corpus.

**Acceptance criteria:**
- [ ] Entity and source pages show counts, pagination, public story links,
      source evidence, related entities/arcs/findings, and readable labels.
- [ ] Finding and arc pages expose public-safe evidence and graph navigation.
- [ ] Pages never imply a limited slice is the whole graph.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke `/e/<entity>`, `/source/<domain>`, `/f/<id>`, `/arc/<id>`

**Dependencies:** Tasks 9, 10, 11, 12, 13, 26

**Files likely touched:**
- `src/app/(app)/e/[slug]/page.tsx`
- `src/app/(app)/source/[domain]/page.tsx`
- `src/app/(app)/f/[id]/page.tsx`
- `src/app/(app)/arc/[id]/page.tsx`
- `src/components/graph/*`
- `src/lib/api.ts`
- `src/lib/types.ts`

**Estimated scope:** M

### Task 31: Disable or Ground Chat Primary Entry

**Description:** Ensure broken or ungrounded chat is not the public primary UX.

**Acceptance criteria:**
- [ ] Chat is hidden/disabled from the first-screen flow unless it uses public
      graph APIs.
- [ ] If visible, chat explains its grounded scope and cites graph evidence.
- [ ] No ungrounded chat route is promoted by homepage navigation.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Local smoke homepage and nav.

**Dependencies:** Task 27

**Files likely touched:**
- `src/app/(app)/page.tsx`
- `src/components/shell/site-nav.tsx`
- `src/components/chat/*`

**Estimated scope:** S

### Checkpoint: Public UX Coherent

- [ ] Homepage, story, briefing, entity, source, finding, and arc flows work.
- [ ] Raw markdown, bad headings, fake topics, and internal labels are gone.
- [ ] The site shows real content-machine artifacts when available.

## Phase 6: Verification, Commit, Merge, Release Gate

### Task 32: Run Backend Focused and Safety Tests

**Description:** Run the focused v3 suites that prove contracts, graph, content
machine, API safety, auth, and runner autonomy.

**Acceptance criteria:**
- [ ] All focused content-machine tests pass.
- [ ] API/auth contract tests pass.
- [ ] Runner dry-run tests prove newsletter autonomy.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py tests/test_site_content_engine.py tests/test_site_content_confidence.py tests/test_site_graph_api.py tests/test_site_content_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`

**Dependencies:** Tasks 3-25

**Files likely touched:**
- Test files only if failures expose missing coverage.

**Estimated scope:** S

### Task 33: Run Rabbit Hole Build Checks

**Description:** Verify the public site compiles and builds locally.

**Acceptance criteria:**
- [ ] Lint passes.
- [ ] Typecheck passes.
- [ ] Production build passes.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`

**Dependencies:** Tasks 26-31

**Files likely touched:**
- None unless fixing failures.

**Estimated scope:** S

### Task 34: Run Local Browser Smoke

**Description:** Prove the actual rendered product works before merge or
release.

**Acceptance criteria:**
- [ ] v3 local API and Rabbit Hole local server run together.
- [ ] Desktop and mobile smoke cover homepage, story, briefing, entity, source,
      finding, arc, and hidden/disabled chat.
- [ ] No console errors, no raw markdown, no bad headings, no internal
      connector labels, and links work on first click.

**Verification:**
- [ ] `.venv/bin/python3 -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8010`
- [ ] `BACKEND_API_URL=http://127.0.0.1:8010 pnpm start --hostname 127.0.0.1 --port 3010`
- [ ] Browser smoke with screenshots/HTTP evidence recorded in handoff.

**Dependencies:** Tasks 32, 33

**Files likely touched:**
- Handoff only unless smoke finds bugs.

**Estimated scope:** S

### Task 35: Run Graphify and Update Handoff/Docs

**Description:** Update machine and human documentation after verified backend
changes.

**Acceptance criteria:**
- [ ] Done table rows accurately updated with evidence.
- [ ] Handoff records tests, smoke, branches, commits, blockers, and deploy
      status.
- [ ] Graphify updated where required.

**Verification:**
- [ ] `graphify update .`
- [ ] `graphify check-update .`
- [ ] `git diff --check`

**Dependencies:** Task 34

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- This plan
- Graphify output files if tracked by repo

**Estimated scope:** S

### Task 36: Commit, Push, and Merge Readiness

**Description:** Package verified work without losing unrelated user changes.

**Acceptance criteria:**
- [ ] Commits are small and phase-based.
- [ ] Dirty files are clean or clearly explained.
- [ ] Branch is pushed and ready for PR/merge review.

**Verification:**
- [ ] `git status --short --branch` in both repos.
- [ ] `git log --oneline --decorate -n 8`

**Dependencies:** Task 35

**Files likely touched:**
- Git metadata only

**Estimated scope:** S

### Task 37: Production Release Gate

**Description:** Deploy only when local verification proves the MVP is better
than the broken chat-first experience and owner approval is explicit.

**Acceptance criteria:**
- [ ] Owner explicitly approves Vercel production deploy.
- [ ] Production deploy uses the verified branch/commit.
- [ ] Post-deploy smoke confirms public flows work.

**Verification:**
- [ ] Vercel deploy evidence after approval.
- [ ] Production HTTP/browser smoke evidence.

**Dependencies:** Task 36

**Files likely touched:**
- Handoff only unless release fixes are needed.

**Estimated scope:** S

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Parser chunks creep back into public stories | High | Keep `IssueStoryUnit` and `PublicSiteStory` separate in Python and TypeScript; tests reject bad headings/raw markdown. |
| Entity graph coverage is weaker than expected | High | Add corpus inventory and read model degradation states before UI claims full graph. |
| Related paths remain shallow | High | Implement connector scorer with evidence edges and reader labels before rebuilding UI related paths. |
| Live AI writes unsupported claims | High | Start with deterministic fake experts, graph packs, and confidence gate; live provider requires owner approval. |
| Newsletter quality is affected | High | Runner hook runs after newsletter work and cannot block or mutate selection/send. |
| Public APIs leak private data | High | Whitelist fields, validate paths, redact text, and test unsafe inputs. |
| Website ships before content exists | Med | Homepage must have safe graph/feed fallback and release gate requires browser smoke. |
| Historical backfill fabricates links | Med | Audit parsed/skipped/unresolved counts and never invent missing graph relationships. |
| Scope expands into full dashboard rebuild | Med | Keep MVP path: Wire -> story -> related graph -> briefing/entity/source/finding/arc. |

## Parallelization Opportunities

Safe after Phase 1 contracts:

- Backend graph API work in Phase 2 can run alongside Rabbit Hole type contract
  preparation if API response fixtures are pinned.
- Rabbit Hole visual components can be prepared against fixtures while backend
  content machine continues.
- Historical backfill audit can run separately from current-day content-machine
  dry-run once artifact contracts are stable.

Must be sequential:

- Artifact contracts before public API behavior.
- Corpus read model before graph pack builder.
- Confidence gate before public story listing and homepage promotion.
- Local build/smoke before release.

Needs coordination:

- Public story artifact fields between `dashboard/routes/api.py` and
  Rabbit Hole `src/lib/types.ts`.
- Related path labels between backend scorer and frontend graph components.
- Entity/source/finding/arc URL conventions.

## Open Questions For Owner Review

1. For launch, should the machine generate only current-day site stories, or
   also seed a small number of high-confidence historical stories?
2. Should entity dossiers be generated only for recurring/high-value entities
   while dynamic templates cover every valid entity?
3. Should `/s/<slug>` remain canonical, or should new site stories move to
   `/story/<slug>` with `/s` as compatibility?
4. Which live expert provider should be approved first after deterministic
   dry-run works?
5. Should high-confidence generated artifacts publish automatically to the
   public site once written, or should the first release use a manual publish
   command until trust is proven?

# Implementation Plan: Rabbit Hole Public Intelligence Content Engine

> Status: Corrective plan after owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-29
> Spec:
> `docs/runbooks/2026-06-29-rabbit-hole-content-engine-corrected-spec.md`
> Related repos:
> - v3/backend: `/Users/taylerramsay/Projects/mindpattern-v3`
> - public site: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`

## Overview

This plan corrects the Rabbit Hole MVP implementation direction.

The public site must not expose raw newsletter splitter output as product
stories. Structured newsletter story units are useful graph inputs and briefing
helpers, but public story pages must come from a dedicated site-content engine
that builds graph packs, runs editorial/expert generation, applies confidence
gates, and writes published artifacts.

The plan is ordered so the current bad UX is contained first, then the real
backend content engine and corpus graph are built, then Rabbit Hole consumes the
proper APIs.

## Architecture Decisions

- Keep dynamic templates. Do not hand-build entity/source/finding/arc pages.
- Keep JSON artifacts first. Do not add a graph database or schema changes
  without owner approval.
- Keep `/api/issues/{date}/structured` for newsletter decomposition.
- Move `/api/stories` to published site-story artifacts only.
- Use `reports/<user>/site-runs/YYYY-MM-DD.json` as the engine ledger.
- Use `reports/<user>/site-stories/YYYY-MM-DD/<slug>.json` for generated public
  story artifacts unless Task 4 proves the flat path is safer for compatibility.
- Treat the existing parser-first Wire and `/s` usage as rollback/stabilization
  work, not as MVP completion.
- Keep Vercel release gated by explicit owner approval.

## Dependency Graph

```text
contain bad public UX
    |
    +-- public story artifact contract
    |       |
    |       +-- artifact-backed /api/stories
    |
    +-- corpus graph inventory/index
    |       |
    |       +-- entity/source/finding dynamic APIs with pagination
    |       |
    |       +-- graph pack builder
    |
    +-- deterministic content engine
            |
            +-- confidence gate
            |
            +-- site run ledger
            |
            +-- optional runner post-newsletter hook
                    |
                    +-- Rabbit Hole story/entity/source UX
                            |
                            +-- browser smoke and release gate
```

## Done Status Table

Keep the `Done` column. Future agents must update this table in place.

| Task | Phase | Title | Done | Evidence / remaining work |
|---|---|---|---|---|
| 0 | 0 | Capture current dirty state in both repos | Yes | 2026-06-29: recorded `git status --short --branch` in both repos before corrective edits. v3 had pre-existing dirty `data/ramsay/**`, `data/social-drafts/eic-topic.json`, `run-launchd.sh`, `tests/test_launchd_wrapper.py`, plus agent-touched API/parser/doc files. Rabbit Hole had pre-existing dirty `src/components/wire/wire-row.tsx` and untracked backend docs plus agent-touched story/entity/type files. |
| 1 | 0 | Mark previous parser-first story UX as failed smoke | Yes | 2026-06-29: appended handoff section `Rabbit Hole Corrective Product Boundary - 2026-06-29` documenting failed screenshot smoke, corrected source-of-truth docs, and the rule that structured issue story units are graph inputs, not public stories. |
| 2 | 0 | Disable parser-derived stories as primary Wire UX | Yes | 2026-06-29: Rabbit Hole homepage no longer imports `getStories()` or `StoryWireRow`; normal Wire views use `/api/feed`/finding fallback. Verification: `pnpm lint`, `pnpm exec tsc --noEmit --incremental false`, `pnpm build`; local smoke `/` -> 200 and `rg "Top 5 Stories Today|shared_source|SHARED SOURCE|\\*\\*|\\[.*\\]\\(" /tmp/rh-home.html` returned no matches. |
| 3 | 0 | Preserve structured issue parser for briefings only | Partial | 2026-06-29: `/api/issues/{date}/structured` still returns sections/story units/source trail and focused tests pass. `/api/stories` no longer reads structured issue story units. Remaining work: stronger frontend type split between `IssueStoryUnit` and `PublicStory`. |
| 4 | 1 | Define public site-story artifact contract | Partial | 2026-06-29: API contract fixture now includes a published high-confidence `reports/ramsay/site-stories/*.json` artifact and a draft artifact that must not publish. Remaining work: dedicated `tests/test_site_content_contracts.py` coverage for artifact path/writer/gate helpers. |
| 5 | 1 | Make `/api/stories` artifact-backed only | Yes | 2026-06-29: backend `/api/stories` and `/api/stories/{slug}` now read published high-confidence site-story JSON artifacts only, require source refs and claim evidence, whitelist/redact public output, and omit draft/degraded/parser chunks. Verification: `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py tests/test_site_issue_contracts.py -q` -> 49 passed, 1 Starlette/httpx warning; local smoke `/api/stories?user=ramsay&limit=5` -> 200 with empty `items` because no real published local artifacts exist. |
| 6 | 1 | Add site run ledger contract | No | `reports/<user>/site-runs/YYYY-MM-DD.json` records candidates, graph packs, generated artifacts, skipped/draft/degraded reasons. |
| 7 | 2 | Inventory corpus graph sources | No | Identify actual local tables/views/artifacts: `findings`, embeddings, sources, `kg_entities`, `kg_edges`, `entity_graph`, arcs, reports. No private data exposed. |
| 8 | 2 | Add paginated entity index API | No | `/api/entities` supports search/limit/offset or cursor and exposes totals where safe. Must support large entity set dynamically. |
| 9 | 2 | Harden entity detail API over full corpus | No | `/api/entities/{slug}` includes story units, findings, relationships, source trail, related entities, and pagination metadata. |
| 10 | 2 | Add source detail API | No | `/api/sources/{domain}` returns source history, linked findings/issues/entities, and safe provenance. |
| 11 | 2 | Add graph-pack builder | No | Builds bounded evidence pack for a candidate from findings, entities, sources, embeddings, arcs, and issue context. |
| 12 | 3 | Add deterministic candidate selector | No | Selects site candidates without model calls; weak input returns no public candidates and records why. Does not mutate newsletter selection. |
| 13 | 3 | Add deterministic site story generator | No | Produces title/dek/take/why-now/body/source trail/related paths/claim evidence from fixture graph packs. |
| 14 | 3 | Add confidence gate | No | Published requires high confidence, evidence, redaction pass, graph evidence, why-now, and no kill switches. Medium/degraded remain internal. |
| 15 | 3 | Add fake-provider expert loop boundary | No | Role interfaces for Assignment Editor, Graph Cartographer, Domain Expert, Skeptic, Narrative Editor, Source Librarian, GEO Editor. Tests use fakes. |
| 16 | 3 | Write site artifacts and run ledger | No | Engine writes published/draft/degraded/failed artifacts under gitignored `reports/` with public-safe fields only. |
| 17 | 4 | Add runner post-newsletter hook behind dry-run safe boundary | No | Hook records status and cannot block newsletter send. No full pipeline run without approval. |
| 18 | 4 | Add historical structured issue backfill audit | No | Backfill canonical newsletters into structured issue artifacts with parsed/skipped/unresolved/redacted ledger. Does not rewrite old takes. |
| 19 | 5 | Rework Rabbit Hole API helpers/types | No | Types distinguish `IssueStoryUnit` from `PublicStoryArtifact`; frontend cannot accidentally treat parser output as public story content. |
| 20 | 5 | Rebuild Wire against proper content contract | No | Homepage shows published site stories first, high-signal feed fallback second, no broken chat-first path. |
| 21 | 5 | Rebuild story page for site artifacts | No | `/s/<slug>` renders title/dek/take/why-now/body/source trail/graph trail/related/provenance cleanly. |
| 22 | 5 | Rebuild briefing page links | No | Briefing story units link to entity/source/finding/arc routes and only link `/s` when a published site story exists. |
| 23 | 5 | Rebuild entity/source pages for large graph | No | Pages show counts, pagination, real relationship labels, and source evidence without implying small slices are complete. |
| 24 | 6 | Browser smoke and link reliability | No | Desktop/mobile smoke for homepage, story, briefing, entity, source, finding, no raw markdown, links single-click. |
| 25 | 6 | Graphify, docs, handoff | No | Run Graphify where required, update handoff with evidence, mark Done rows accurately. |
| 26 | 6 | Merge/release gate | No | Only after tests/build/smoke. Vercel deploy requires explicit owner approval. |

## Phase 0: Stop the Wrong Public UX

### Task 0: Capture Current Dirty State

**Description:** Record both repos before making corrective edits.

**Acceptance criteria:**
- [ ] v3 dirty files listed and classified as user/agent/generated.
- [ ] Rabbit Hole dirty files listed and classified as user/agent/generated.
- [ ] Current branch names recorded.

**Verification:**
- [ ] `git status --short --branch` in v3.
- [ ] `git status --short --branch` in Rabbit Hole.

**Dependencies:** None

**Files likely touched:**
- Handoff doc only

**Estimated scope:** XS

### Task 1: Record Failed Smoke and Product Correction

**Description:** Update the handoff/runbook so future agents do not continue the
parser-first path.

**Acceptance criteria:**
- [ ] Handoff records that screenshots failed product smoke.
- [ ] Handoff states raw newsletter chunks must not be public story products.
- [ ] Handoff links this corrected spec and plan.

**Verification:**
- [ ] `rg -n "parser-first|failed smoke|corrected spec" .claude/handoffs docs/runbooks`
- [ ] `git diff --check`

**Dependencies:** Task 0

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- This plan

**Estimated scope:** S

### Task 2: Disable Parser-Derived Stories as Primary Wire UX

**Description:** Rabbit Hole should not show raw `/api/stories` parser-derived
rows on the homepage. Until `/api/stories` is artifact-backed, use the existing
feed/finding path or published site stories only.

**Acceptance criteria:**
- [ ] Homepage does not display `Top 5 Stories Today` or `Security` as story
      card titles.
- [ ] Homepage does not render raw markdown snippets.
- [ ] If no published site stories exist, homepage still has useful fallback
      rows from `/api/feed` or findings.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke: `/` returns 200 and does not show bad headings/raw markdown.

**Dependencies:** Task 0

**Files likely touched:**
- `src/app/(app)/page.tsx`
- `src/lib/api.ts`
- `src/lib/types.ts`

**Estimated scope:** S

### Task 3: Preserve Structured Issue Parser for Briefings Only

**Description:** Keep structured issue output, but prevent it from being treated
as public site-native story content.

**Acceptance criteria:**
- [ ] `/api/issues/{date}/structured` still returns sections/story units.
- [ ] Issue story units are typed/named separately from public story artifacts.
- [ ] Story-unit tests guard against bad section headings and raw markdown.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_contracts.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `orchestrator/site_content.py`
- `dashboard/routes/api.py`
- `tests/test_site_issue_contracts.py`
- `tests/test_api_contract.py`

**Estimated scope:** M

### Checkpoint: Direction Corrected

- [ ] Current branch no longer presents parser chunks as the main product.
- [ ] Docs say exactly what the corrected build is.
- [ ] Existing useful graph read APIs are preserved.

## Phase 1: Public Story Artifact API

### Task 4: Define Public Site-Story Artifact Contract

**Description:** Add pure contracts for published/draft/degraded/failed public
story artifacts.

**Acceptance criteria:**
- [ ] Artifact path validation prevents traversal.
- [ ] Published artifact requires title, dek, take, why-now, source refs, claim
      evidence, graph edges, confidence, and provenance.
- [ ] Draft/degraded/failed artifacts can be written but are not public.
- [ ] Private fields are rejected or redacted.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q`

**Dependencies:** Task 3

**Files likely touched:**
- `orchestrator/site_content.py` or `orchestrator/site_content_engine.py`
- `tests/test_site_content_contracts.py`

**Estimated scope:** M

### Task 5: Make `/api/stories` Artifact-Backed Only

**Description:** Replace story listing/detail behavior so it reads published
site-story artifacts, not structured issue story units.

**Acceptance criteria:**
- [ ] `GET /api/stories` lists published/high-confidence artifacts only.
- [ ] `GET /api/stories/{slug}` returns one published artifact or safe 404.
- [ ] Draft/degraded/parser-only content is not returned.
- [ ] Unsafe users/slugs return safe empty/404 responses.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_site_content_api.py`
- `tests/test_api_contract.py`
- `dashboard/auth.py`

**Estimated scope:** M

### Task 6: Add Site Run Ledger Contract

**Description:** Add a daily ledger describing site content generation outcomes.

**Acceptance criteria:**
- [ ] Ledger records candidates, graph packs, generated artifacts, skipped
      reasons, degraded reasons, redaction status, and trace IDs.
- [ ] Ledger path is safe and under gitignored `reports/`.
- [ ] Ledger does not expose private raw data.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_contracts.py`

**Estimated scope:** S

### Checkpoint: Story API Boundary

- [ ] `/api/stories` is no longer parser-backed.
- [ ] Public story artifacts have tests.
- [ ] Draft/degraded artifacts are safe and private by default.

## Phase 2: Full Corpus Graph Read Layer

### Task 7: Inventory Corpus Graph Sources

**Description:** Inspect current data model and record what tables/artifacts can
support the public graph.

**Acceptance criteria:**
- [ ] Document existing graph tables/views/artifacts.
- [ ] Document which have 14,000+ style coverage and which are partial.
- [ ] No database files or private data are committed.

**Verification:**
- [ ] Focused read-only local inspection.
- [ ] Handoff/runbook updated with exact tables/artifacts.

**Dependencies:** Task 0

**Files likely touched:**
- Handoff/runbook docs

**Estimated scope:** S

### Task 8: Add Paginated Entity Index API

**Description:** Add `/api/entities` so Rabbit Hole can discover corpus
entities dynamically without hand-building pages.

**Acceptance criteria:**
- [ ] Supports `q`, `limit`, `offset` or cursor.
- [ ] Returns safe public fields, total/has_more where safe.
- [ ] Uses real corpus entity sources, not only newsletter parser refs.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q`

**Dependencies:** Task 7

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 9: Harden Entity Detail API Over Full Corpus

**Description:** Expand `/api/entities/{slug}` with paginated story/finding and
relationship trails.

**Acceptance criteria:**
- [ ] Entity detail includes corpus findings, issue story refs, relationships,
      sources, related entities, counts, and pagination metadata.
- [ ] Relationship labels are typed and reader-readable.
- [ ] A small limit is clearly a page, not the full graph.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 10: Add Source Detail API

**Description:** Add source-domain pages from source history and linked graph
data.

**Acceptance criteria:**
- [ ] `GET /api/sources/{domain}` validates domain.
- [ ] Returns findings, issue mentions, entities/topics, counts, and
      provenance.
- [ ] Does not serve arbitrary files or private source data.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q`

**Dependencies:** Task 7

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_site_graph_api.py`

**Estimated scope:** M

### Task 11: Add Graph Pack Builder

**Description:** Build bounded public-safe evidence packs for candidate site
stories.

**Acceptance criteria:**
- [ ] Graph pack includes primary finding/story unit, semantic neighbors,
      entity relationships, source trail, arcs, historical occurrences, and
      claim evidence candidates.
- [ ] Graph pack has deterministic output for fixtures.
- [ ] Missing graph data degrades visibly.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Tasks 8, 9, 10

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Checkpoint: Corpus Graph Is Real

- [ ] Entity/source/finding APIs are not limited to newsletter-only parser
      data.
- [ ] Large corpus surfaces have pagination.
- [ ] Graph packs can be built from real evidence sources.

## Phase 3: Site Content Engine

### Task 12: Deterministic Candidate Selector

**Description:** Select site content candidates without model calls.

**Acceptance criteria:**
- [ ] Uses importance, source quality, recency, arcs, semantic relatedness, and
      entity recurrence.
- [ ] Does not alter newsletter selection.
- [ ] Weak input records `no_public_candidate` with reasons.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`

**Dependencies:** Task 11

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Task 13: Deterministic Site Story Generator

**Description:** Generate public story artifacts from fixture graph packs without
live providers.

**Acceptance criteria:**
- [ ] Generates headline, dek, take, why-now, body, source trail, related
      paths, claim evidence, confidence, and provenance.
- [ ] Fixture output reads like a public story, not a parser chunk.
- [ ] Weak graph packs create draft/degraded artifacts, not published stories.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Task 12

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Task 14: Confidence Gate

**Description:** Enforce public publish rules.

**Acceptance criteria:**
- [ ] Published requires source evidence, claim evidence, why-now, redaction
      pass, graph evidence, and no kill switches.
- [ ] Medium/degraded/failed artifacts are not public.
- [ ] Gate explains every rejection reason in the ledger.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_confidence.py -q`

**Dependencies:** Task 13

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_confidence.py`

**Estimated scope:** S

### Task 15: Fake-Provider Expert Loop Boundary

**Description:** Add role interfaces for future real expert agents while tests
use fake providers.

**Acceptance criteria:**
- [ ] Expert roles are explicit and independently injectable.
- [ ] Missing live config uses deterministic/draft behavior.
- [ ] Focused tests make no Claude/network/Slack/email/social/Fly/Vercel calls.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_experts.py -q`

**Dependencies:** Task 14

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `agents/rabbit-hole-*.md`
- `tests/test_site_content_experts.py`

**Estimated scope:** M

### Task 16: Write Site Artifacts and Ledger

**Description:** Persist generated site content safely.

**Acceptance criteria:**
- [ ] Published stories, draft/degraded artifacts, and run ledgers write under
      gitignored `reports/<user>/`.
- [ ] Writes are idempotent for the same date/input hash.
- [ ] Public artifact content is whitelisted/redacted.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py tests/test_site_content_contracts.py -q`

**Dependencies:** Tasks 13, 14

**Files likely touched:**
- `orchestrator/site_content_engine.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Checkpoint: Engine Works Without Live Providers

- [ ] Fixture graph pack creates one published high-confidence artifact.
- [ ] Weak fixture creates draft/degraded artifact.
- [ ] Ledger records both outcomes.
- [ ] No live provider calls are needed.

## Phase 4: Pipeline Integration and Backfill

### Task 17: Post-Newsletter Runner Hook

**Description:** Add an optional enrichment phase after newsletter generation.

**Acceptance criteria:**
- [ ] Hook records ready/degraded/failed site-content status.
- [ ] Hook failure cannot fail newsletter send.
- [ ] Dry-run tests prove control flow without full pipeline execution.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_traces_db.py -q`

**Dependencies:** Task 16

**Files likely touched:**
- `orchestrator/runner.py`
- `orchestrator/site_content_engine.py`
- `tests/test_runner.py`
- `tests/test_traces_db.py`

**Estimated scope:** M

### Task 18: Historical Structured Issue Backfill Audit

**Description:** Normalize old newsletters into structured issue artifacts and
audit the result.

**Acceptance criteria:**
- [ ] Backfill is resumable and idempotent.
- [ ] Ledger records parsed/skipped/unresolved/redacted/degraded counts.
- [ ] Canonical newsletter meaning is preserved.
- [ ] Backfill does not invent missing finding/entity/source matches.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_backfill.py -q`

**Dependencies:** Task 3

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_issue_backfill.py`

**Estimated scope:** M

### Checkpoint: Pipeline Safe

- [ ] Newsletter autonomy remains intact.
- [ ] Site content can be generated after newsletter work.
- [ ] Historical issues can be normalized with an audit trail.

## Phase 5: Rabbit Hole Public UX

### Task 19: Rework API Helpers and Types

**Description:** Make frontend types enforce the distinction between issue story
units and public story artifacts.

**Acceptance criteria:**
- [ ] `IssueStoryUnit` and `PublicStory` are separate interfaces.
- [ ] `getStories()` reads published site stories only.
- [ ] `getStructuredIssue()` returns briefing graph input only.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`

**Dependencies:** Task 5

**Files likely touched:**
- `src/lib/types.ts`
- `src/lib/api.ts`

**Estimated scope:** S

### Task 20: Rebuild Wire Against Proper Contract

**Description:** Homepage becomes a content-first intelligence feed without
broken chat-first UX.

**Acceptance criteria:**
- [ ] Published site stories render first when available.
- [ ] Safe finding/feed fallback renders when no published stories exist.
- [ ] No bad parser headings, raw markdown, or internal connector labels.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke `/`

**Dependencies:** Task 19

**Files likely touched:**
- `src/app/(app)/page.tsx`
- `src/components/wire/*`

**Estimated scope:** M

### Task 21: Rebuild Story Page for Site Artifacts

**Description:** Render site-native public story artifacts.

**Acceptance criteria:**
- [ ] Story page renders headline, dek, take, why-now, body, sources, graph
      trail, related paths, provenance, and JSON-LD.
- [ ] Missing/degraded stories return clean not-found/degraded state.
- [ ] Links work on first click in local smoke.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke `/s/<published-fixture-slug>`

**Dependencies:** Tasks 5, 19

**Files likely touched:**
- `src/app/(app)/s/[slug]/page.tsx`
- `src/components/story/*`

**Estimated scope:** M

### Task 22: Rebuild Briefing Page Links

**Description:** Keep canonical newsletter pages complete and link their graph
structure correctly.

**Acceptance criteria:**
- [ ] Full newsletter renders consistently.
- [ ] Thread summary links to entity/source/finding/arc routes.
- [ ] Thread summary links to `/s` only when published story artifact exists.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Local smoke `/briefings/<date>`

**Dependencies:** Tasks 3, 19

**Files likely touched:**
- `src/app/(app)/briefings/[date]/page.tsx`
- `src/components/briefing/*`

**Estimated scope:** M

### Task 23: Rebuild Entity and Source Pages for Large Graph

**Description:** Render dynamic graph templates with counts, pagination, and
reader-readable relationships.

**Acceptance criteria:**
- [ ] Entity page shows corpus counts, findings, related entities, story units,
      source trail, and pagination.
- [ ] Source page shows source history and linked graph data.
- [ ] UI does not imply a limited page is the entire graph.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] `pnpm build`
- [ ] Local smoke `/e/<entity>` and `/source/<domain>`

**Dependencies:** Tasks 8, 9, 10, 19

**Files likely touched:**
- `src/app/(app)/e/[slug]/page.tsx`
- `src/app/(app)/source/[domain]/page.tsx`
- `src/components/entity/*`
- `src/components/source/*`

**Estimated scope:** M

### Checkpoint: Public UX Is Coherent

- [ ] Homepage, story, briefing, entity, source, and finding flows work.
- [ ] Raw markdown/bad headings/internal labels are gone.
- [ ] Content is readable and evidence-backed.

## Phase 6: Verification, Merge, Release Gate

### Task 24: Browser Smoke and Link Reliability

**Description:** Verify the actual rendered product.

**Acceptance criteria:**
- [ ] Desktop and mobile smoke cover homepage, story, briefing, entity, source,
      finding, and disabled/hidden chat.
- [ ] Links work on first click.
- [ ] No console errors.
- [ ] No raw markdown syntax visible where rendered prose is expected.

**Verification:**
- [ ] Local v3 server.
- [ ] Local Rabbit Hole server.
- [ ] HTTP/browser smoke evidence in handoff.

**Dependencies:** Tasks 20, 21, 22, 23

**Files likely touched:**
- Handoff docs

**Estimated scope:** S

### Task 25: Graphify, Docs, Handoff

**Description:** Update machine/human handoff evidence.

**Acceptance criteria:**
- [ ] Done table updated accurately.
- [ ] Handoff records tests, smoke, branches, commits, blockers.
- [ ] Graphify run completed where required.

**Verification:**
- [ ] `graphify update .`
- [ ] `graphify check-update .`
- [ ] `git diff --check`

**Dependencies:** Task 24

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- This plan

**Estimated scope:** S

### Task 26: Merge and Release Gate

**Description:** Prepare for merge and optional Vercel release.

**Acceptance criteria:**
- [ ] v3 tests pass.
- [ ] Rabbit Hole lint/typecheck/build pass.
- [ ] Dirty files are explained or clean.
- [ ] Owner explicitly approves production Vercel deploy.
- [ ] Production release smoke is run only after approval.

**Verification:**
- [ ] `git status --short --branch` in both repos.
- [ ] Commit log / PR evidence.
- [ ] Vercel deploy URL only after owner approval.

**Dependencies:** Task 25

**Files likely touched:**
- None unless release docs are updated

**Estimated scope:** S

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Agents continue parser-first work | Public site stays wrong | Phase 0 explicitly disables parser-derived story UX and updates handoff. |
| Corpus graph tables differ across local/Fly | Entity pages break | Task 7 inventories available graph sources and APIs degrade explicitly. |
| `limit=40` gets mistaken for whole corpus | User sees fake-small graph | Add pagination/count metadata and UI labels. |
| Content engine writes generic prose | Site feels bland | Require graph packs, role boundary, skeptic, why-now, and source evidence. |
| Site engine hurts newsletter | Core product quality drops | Run post-newsletter, fail independently, dry-run tests prove no blocking. |
| Public artifacts leak private data | Trust/security issue | Whitelist fields, redaction tests, no raw Slack/subscriber/personal memory. |
| Deploy happens too early | Broken site goes public | Release gate requires owner approval after local build and smoke. |

## Parallelization Opportunities

Safe to parallelize after Phase 1:

- Entity/source API tests and Rabbit Hole type definitions, if contracts are
  stable.
- Browser smoke checklist writing and backend content-engine tests.
- Briefing template polish and graph-pack builder, if route contracts do not
  change.

Must be sequential:

- Phase 0 before frontend expansion.
- Artifact contract before `/api/stories`.
- Graph pack builder before content generator.
- Content generator before story page promotion.
- Browser smoke before release gate.

## Open Questions

1. Use nested `reports/<user>/site-stories/YYYY-MM-DD/<slug>.json` or preserve
   the current flat `reports/<user>/site-stories/<slug>.json` helper until a
   migration task?
2. Should `/s/<slug>` remain the final public story URL or become
   `/story/<slug>` after the content engine is real?
3. Should historical public story generation backfill only selected best
   stories first, or attempt every old issue after structured issue backfill?
4. Should entity index totals expose exact counts or rounded counts publicly?

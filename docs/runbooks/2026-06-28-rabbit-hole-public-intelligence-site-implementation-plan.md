# Implementation Plan: Rabbit Hole Public Intelligence Site and Daily Content Engine

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-28
> Spec: `docs/runbooks/2026-06-28-rabbit-hole-public-intelligence-site-spec.md`
> Repos:
> - v3/backend: `/Users/taylerramsay/Projects/mindpattern-v3`
> - public site: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`

## Overview

This plan turns Rabbit Hole into the public MindPattern intelligence product.
The first implementation slice proves the hard part: real source-backed graph
connections and high-confidence auto-published public story artifacts. The site
then renders those artifacts as canonical story pages that newsletters and
social posts can link to.

Correction from owner review: the newsletter itself must also be decomposed
into structured graph data. The system should not treat newsletters as one
markdown blob. Each issue needs sections, story units, entities, sources,
finding links, and arc links so the public site can connect every daily issue
into dynamic graph template pages.

Second owner correction: every newsletter still needs to render as a complete,
polished blog-style briefing page. The structured graph is extracted from the
issue; it does not replace the full post. Historical issues and future issues
should use the same formatting, section structure, thread summaries, source
treatment, and reading experience.

The plan is ordered so backend contracts and graph quality are proven before
frontend polish. No website deploy, Fly deploy, full daily pipeline run, schema
change, dependency install, or live provider enablement happens without explicit
owner approval.

## Architecture Decisions

- Use artifact-first storage for MVP: `reports/<user>/site-stories/YYYY-MM-DD/`
  and `reports/<user>/site-runs/YYYY-MM-DD.json`. This avoids a schema change
  until the data model proves itself.
- Use JSON artifacts with JSON-LD-ready fields for MVP semantic publishing.
  Do not introduce Neo4j, RDF storage, or another graph database until the
  contracts and product behavior are proven.
- Use `/s/<slug>` for public story pages. Keep `/f/<id>` as raw finding detail
  or fallback, because public stories may aggregate multiple findings.
- Separate linkable graph templates from AI editorial content. Dynamic finding,
  entity, source, issue-story, and arc pages should render from structured data
  even when no AI-written story/dossier exists.
- Split daily newsletters into structured issue artifacts before relying on
  them for public graph navigation.
- Backfill historical newsletters through the same issue splitter/normalizer as
  future newsletters. Backfill adds structure and links; it must not rewrite the
  original canonical post meaning.
- Keep canonical newsletter issue pages as first-class public posts. All
  historical and future issues should render through one consistent briefing
  template.
- Treat raw findings, source URLs, and canonical newsletters as source of
  truth. AI-generated public stories are derived/explanatory artifacts and must
  carry source evidence, confidence, and provenance.
- Build real relatedness before public story UI: `/api/finding/{id}` and
  `/api/related/{id}` are required before replacing placeholder rabbit-hole
  behavior.
- Daily site content generation runs after newsletter synthesis/send or as a
  post-run enrichment phase. Failure must not block the newsletter.
- High-confidence public story artifacts can auto-publish. Medium/degraded
  artifacts remain drafts or internal diagnostics.
- The first public graph UI should be readable relationship trails and source
  evidence, not a complex node-map visualization.
- Keep social posting in Slack. The public site can display story/media
  metadata, but it does not approve or post to social platforms.

## Dependency Graph

```text
baseline / dirty state
    |
    +-- v3 public finding contract
    |       |
    |       +-- semantic related API
    |               |
    |               +-- structured issue/entity/source contracts
    |                       |
    |                       +-- newsletter splitter and entity linker
    |                       |       |
    |                       |       +-- historical newsletter backfill
    |                       |
    |                       +-- provenance / JSON-LD-ready graph metadata
    |                               |
    |                               +-- issue/entity/source APIs
    |                                       |
    |                                       +-- dynamic /e and /source templates
    |                       |
    |                       +-- story artifact contracts
    |                       |
    |                       +-- deterministic site content engine
    |                               |
    |                               +-- runner post-newsletter hook
    |                               +-- public story APIs
    |                                       |
    |                                       +-- Rabbit Hole API client/types
    |                                               |
    |                                               +-- /s/<slug> story page
    |                                               +-- /f/<id> real related
    |                                               +-- Wire story feed
    |                                               +-- Briefing deep links
    |
    +-- narrative arcs API already exists
            |
            +-- arc modules/pages on Rabbit Hole
```

## Done Status Table

Keep the `Done` column. Future agents should update this table in place.

| Task | Phase | Title | Done | Evidence / remaining work |
|---|---|---|---|---|
| 0 | 0 | Capture dirty state and owner choices | Yes | 2026-06-28 baseline recorded. v3 dirty: `data/ramsay/**`, `data/social-drafts/eic-topic.json`, `run-launchd.sh`, `tests/test_launchd_wrapper.py`, plus this new spec/plan. Rabbit Hole dirty: `src/components/story/rabbit-hole.tsx`, `src/components/wire/wire-row.tsx`, `src/lib/sections.ts`, untracked `docs/specs/2026-06-26-backend-*.md`. Baseline: v3 API contract 15 passed; v3 dry-run phases 4 passed; Rabbit Hole typecheck passed; lint 0 errors/2 pre-existing warnings. Defaults: artifact-first, `/s/<slug>`, no sitemap/deploy without owner approval. |
| 1 | 0 | Lock docs/source of truth | No | Not started. |
| 2 | 1 | Add `/api/finding/{id}` contract | Yes | Implemented public whitelisted single-finding endpoint with safe 404s. Verification: `.venv/bin/python3 -m pytest tests/test_api_contract.py -q` -> 18 passed. |
| 3 | 1 | Add semantic `/api/related/{id}` | Yes | Implemented stored-embedding semantic related endpoint with self-exclusion, score/reason fields, unsupported-mode 400, and missing-embedding empty result. Verification: `.venv/bin/python3 -m pytest tests/test_api_contract.py -q` -> 18 passed. |
| 4 | 1 | Add `/api/feed` compatibility wrapper | Yes | Implemented forward-compatible feed wrapper over public findings with `items`, `total`, `limit`, `offset`, `kind`, ranks, target URLs. Verification: `.venv/bin/python3 -m pytest tests/test_api_contract.py -q` -> 18 passed; auth allowlist verified with `tests/test_auth_middleware.py` -> 16 passed. |
| 5 | 2 | Add public story artifact contracts | No | Not started. |
| 5A | 2 | Add structured issue artifact contracts | No | Not started. |
| 5B | 2 | Add newsletter splitter and entity linker | No | Not started. |
| 5C | 2 | Add historical newsletter backfill normalizer | No | Not started. |
| 5D | 2 | Add provenance and JSON-LD-ready graph metadata contracts | No | Not started. |
| 6 | 2 | Add confidence gate and safety tests | No | Not started. |
| 7 | 2 | Add deterministic candidate selector | No | Not started. |
| 8 | 2 | Add deterministic story generator | No | Not started. |
| 9 | 2 | Add expert-agent provider boundary | No | Not started. |
| 10 | 2 | Add post-newsletter runner hook | No | Not started. |
| 11 | 3 | Expose public story APIs | No | Not started. |
| 12 | 3 | Add story API contract fixtures | No | Not started. |
| 12A | 3 | Expose structured issue/entity/source APIs | No | Not started. |
| 12B | 3 | Add structured public graph API fixtures | No | Not started. |
| 13 | 4 | Add Rabbit Hole story types/helpers | No | Not started. |
| 14 | 4 | Build `/s/[slug]` story page | No | Not started. |
| 14A | 4 | Build dynamic `/e/[slug]` and `/source/[domain]` pages | No | Not started. |
| 15 | 4 | Replace `/f/[id]` placeholder relatedness | No | Not started. |
| 16 | 4 | Upgrade Wire to story/feed rows | No | Not started. |
| 16A | 4 | Replace or hide broken chat-first entry points | No | Not started. |
| 17 | 4 | Add briefing-to-story modules | No | Not started. |
| 17A | 4 | Add structured issue graph modules | No | Not started. |
| 17B | 4 | Standardize canonical newsletter post template | No | Not started. |
| 18 | 5 | Add public arc modules/pages | No | Not started. |
| 19 | 5 | Add media/provenance cross-links | No | Not started. |
| 20 | 5 | Add SEO/GEO metadata pass | No | Not started. |
| 21 | 6 | Add browser smoke checks | No | Not started. |
| 22 | 6 | Run Graphify, docs, handoff | No | Not started. |
| 23 | 6 | Owner-approved live deploy/smoke | Deferred | Requires explicit owner approval. |

## Phase 0: Baseline and Product Guardrails

### Task 0: Capture Dirty State and Owner Choices

**Description:** Record current dirty files in both repos and lock the few
planning defaults needed for implementation: artifact-first storage, `/s/<slug>`
story URLs, and no sitemap inclusion without owner approval.

**Acceptance criteria:**
- [ ] v3 dirty files are listed and classified.
- [ ] Rabbit Hole dirty files are listed and classified.
- [ ] Plan records defaults for storage, URL shape, and sitemap behavior.

**Verification:**
- [ ] `git status --short --branch` in v3.
- [ ] `git status --short --branch` in Rabbit Hole.

**Dependencies:** None

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- This plan

**Estimated scope:** S

### Task 1: Lock Docs and Source of Truth

**Description:** Update docs so the Rabbit Hole rebuild spec becomes the visual
and product source of truth: Signal light/cobalt, content-first, archive-first,
not dashboard/chat-first.

**Acceptance criteria:**
- [ ] `PRODUCT.md`, `CLAUDE.md`, or a short ADR no longer contradicts the
      Signal/archive-first direction.
- [ ] The new public intelligence spec and plan are linked from the relevant
      handoff/runbook.
- [ ] No product code changes are included in this docs task.

**Verification:**
- [ ] `rg -n "charcoal|manila|chat-first|archive-first|Signal" PRODUCT.md CLAUDE.md docs`
- [ ] `git diff --check`

**Dependencies:** Task 0

**Files likely touched:**
- `PRODUCT.md` in Rabbit Hole
- `CLAUDE.md` in Rabbit Hole
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`

**Estimated scope:** S

### Checkpoint: Baseline

- [ ] Dirty state is recorded in both repos.
- [ ] Owner has accepted or changed artifact-first and `/s/<slug>` defaults.
- [ ] No code behavior has changed.

## Phase 1: Prove the Real Graph Read Path

### Task 2: Add `/api/finding/{id}` Contract

**Description:** Add a public single-finding JSON endpoint in v3 so Rabbit Hole
does not fetch the latest 300 findings and search locally.

**Acceptance criteria:**
- [ ] Valid finding ID returns the same public fields as `/api/findings`.
- [ ] Invalid or missing ID returns 404/empty safe response.
- [ ] User/date/path input cannot traverse local files or expose private data.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q`

**Dependencies:** Task 0

**Files likely touched:**
- `dashboard/routes/api.py`
- `dashboard/auth.py`
- `tests/test_api_contract.py`
- `tests/test_auth_middleware.py`

**Estimated scope:** M

### Task 3: Add Semantic `/api/related/{id}`

**Description:** Add real semantic related findings over existing
`findings_embeddings`, returning ranked neighbors with scores and relationship
reasons. This replaces the same-section placeholder as the backend truth.

**Acceptance criteria:**
- [ ] Endpoint excludes the source finding.
- [ ] Endpoint returns ranked related findings with `score`, `mode`, and
      human-readable `reason`.
- [ ] Missing embeddings degrade cleanly instead of crashing.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_related_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_related_api.py`
- `tests/fixtures/`

**Estimated scope:** M

### Task 4: Add `/api/feed` Compatibility Wrapper

**Description:** Add a public feed endpoint that returns ranked rows for the
Wire. The first version may wrap findings and later story artifacts, but the
contract should be forward-compatible with story/cluster rows.

**Acceptance criteria:**
- [ ] Feed response includes `items`, `total`, `limit`, `offset`, and `kind`.
- [ ] Current backend can return high-signal finding-backed rows.
- [ ] Response can later include story-backed rows without breaking the site.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_feed_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_feed_api.py`
- `tests/test_api_contract.py`

**Estimated scope:** M

### Checkpoint: Real Graph Read Path

- [ ] `/api/finding/{id}` works on fixture data.
- [ ] `/api/related/{id}?mode=semantic` returns real ranked neighbors.
- [ ] `/api/feed` has a stable shape for Rabbit Hole.
- [ ] No Rabbit Hole placeholder UI has been replaced before these contracts
      are proven.

## Phase 2: Daily Rabbit Hole Content Engine in v3

### Task 5: Add Public Story Artifact Contracts

**Description:** Add pure Python contracts and safe path helpers for public
story artifacts under `reports/<user>/site-stories/YYYY-MM-DD/`.

**Acceptance criteria:**
- [ ] Story slug/date/user validation prevents traversal.
- [ ] Public story output is whitelisted and redacted.
- [ ] Artifact paths stay under gitignored `reports/`.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_content_contracts.py`

**Estimated scope:** S

### Task 5A: Add Structured Issue Artifact Contracts

**Description:** Add pure contracts for decomposed newsletters:
`PublicIssue`, `IssueSection`, `IssueStoryUnit`, `PublicEntity`, source refs,
and relationship refs. This makes newsletters first-class graph inputs instead
of single markdown blobs.

**Acceptance criteria:**
- [ ] Structured issue artifacts include sections, story units, entities,
      source refs, finding IDs, arc IDs, and provenance.
- [ ] Entity slugs and source domains are normalized safely.
- [ ] Public issue artifacts are redacted and stored under gitignored
      `reports/<user>/site-issues/`.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_contracts.py -q`

**Dependencies:** Tasks 2, 5

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_issue_contracts.py`

**Estimated scope:** S

### Task 5B: Add Newsletter Splitter and Entity Linker

**Description:** Parse newsletter markdown into issue sections and story units,
then link those units to entities, findings, sources, and arcs. This should be
deterministic first; model-assisted cleanup can come later behind a provider
boundary.

**Acceptance criteria:**
- [ ] Newsletter headings produce stable issue sections.
- [ ] Story units preserve title, summary/excerpt, source links, and issue
      location.
- [ ] Entities from newsletter text are linked to matching findings/sources
      when possible and marked unresolved when not.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_parser.py -q`

**Dependencies:** Task 5A

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_issue_parser.py`
- `tests/fixtures/`

**Estimated scope:** M

### Task 5C: Add Historical Newsletter Backfill Normalizer

**Description:** Add a resumable backfill path that runs the same structured
issue splitter/normalizer over historical newsletter reports. Backfill must
preserve the original canonical post content and only add structure, links, and
metadata.

**Acceptance criteria:**
- [ ] Historical issues and new issues use the same `PublicIssue` and
      `IssueStoryUnit` contracts.
- [ ] Backfill writes an audit ledger with parsed, skipped, unresolved,
      redacted, and degraded counts.
- [ ] Backfill is idempotent and can resume without duplicating artifacts.
- [ ] Unresolved entity/source/finding links are marked unresolved; the
      backfill does not invent matches.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_backfill.py -q`

**Dependencies:** Task 5B

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_issue_backfill.py`
- `tests/fixtures/`

**Estimated scope:** M

### Task 5D: Add Provenance and JSON-LD-Ready Graph Metadata Contracts

**Description:** Add shared provenance, claim evidence, source refs, entity
refs, and JSON-LD-ready metadata fields used by issues, story units, public
stories, entity pages, source pages, and arc pages.

**Acceptance criteria:**
- [ ] Public artifacts include provenance with generator, generated time,
      input artifacts, source finding IDs, source issue dates, redaction
      status, AI-generated flag, and human-approved flag.
- [ ] Public artifacts include claim-to-source evidence where claims are
      synthesized or explained.
- [ ] JSON-LD-ready fields are present without exposing private trace rows,
      Slack message bodies, subscriber data, local paths, or secrets.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_graph_metadata.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q`

**Dependencies:** Tasks 5, 5A

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_graph_metadata.py`
- `tests/test_site_content_contracts.py`

**Estimated scope:** S

### Task 6: Add Confidence Gate and Safety Tests

**Description:** Implement the high/medium/degraded publish gate. High
confidence can publish; everything else is draft/degraded/failed.

**Acceptance criteria:**
- [ ] High confidence requires source diversity, claim-to-source evidence,
      non-empty related evidence, no kill switches, and a why-now reason.
- [ ] Medium/degraded stories are never marked `published`.
- [ ] Private data, secrets, raw Slack bodies, subscriber data, and local DB
      paths are redacted or rejected.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_confidence.py -q`

**Dependencies:** Tasks 5, 5D

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_content_confidence.py`

**Estimated scope:** S

### Task 7: Add Deterministic Candidate Selector

**Description:** Select candidate findings/arcs for public stories from current
research without calling a model. This is the Assignment Editor dry path.

**Acceptance criteria:**
- [ ] Selector uses importance, source quality, recency, arcs, and relatedness
      evidence.
- [ ] Selector does not mutate newsletter candidates or story selection.
- [ ] Empty/weak input returns no public candidates and records why.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis -q`

**Dependencies:** Tasks 3, 6

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_content_engine.py`
- `tests/test_runner.py`

**Estimated scope:** M

### Task 8: Add Deterministic Story Generator

**Description:** Generate structured public story artifacts from fixture
findings and related evidence without live model calls. This proves the artifact
shape and public API can work before the real expert loop is enabled.

**Acceptance criteria:**
- [ ] Generates title, dek, take, why-now, source trail, related links,
      confidence, and provenance.
- [ ] High-confidence fixture publishes automatically.
- [ ] Weak fixture creates draft/degraded artifact, not a public story.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q`

**Dependencies:** Tasks 5D, 7

**Files likely touched:**
- `orchestrator/site_content.py`
- `tests/test_site_content_engine.py`

**Estimated scope:** M

### Task 9: Add Expert-Agent Provider Boundary

**Description:** Add the real-AI expert loop interface with injectable providers
for Assignment Editor, Graph Cartographer, Domain Experts, Skeptic, Narrative
Editor, Source Librarian, GEO Editor, and Media Producer. Tests use fakes; live
model calls remain disabled until owner approval.

**Acceptance criteria:**
- [ ] Expert roles are explicit and independently testable.
- [ ] Missing provider config falls back to deterministic/draft behavior.
- [ ] Focused tests make no Claude, network, Slack, email, Fly, or Vercel calls.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_experts.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_media_feature_safety.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `orchestrator/site_content.py`
- `agents/rabbit-hole-*.md`
- `tests/test_site_content_experts.py`

**Estimated scope:** M

### Task 10: Add Post-Newsletter Runner Hook

**Description:** Wire the content engine as a post-newsletter enrichment phase
that can fail independently and records trace evidence. It must not block the
newsletter.

**Acceptance criteria:**
- [ ] Runner records site-content status as ready/degraded/failed.
- [ ] Content-engine failure does not fail newsletter send.
- [ ] Full pipeline is not run during tests; focused dry-run phase tests prove
      control flow.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_traces_db.py -q`

**Dependencies:** Tasks 8, 9

**Files likely touched:**
- `orchestrator/runner.py`
- `orchestrator/site_content.py`
- `tests/test_runner.py`
- `tests/test_traces_db.py`

**Estimated scope:** M

### Checkpoint: Content Engine

- [ ] Deterministic engine can create at least one high-confidence public story
      artifact from fixtures.
- [ ] Medium/degraded stories do not publish.
- [ ] Runner hook cannot block newsletter delivery.
- [ ] No live model/provider calls are required for tests.

## Phase 3: Public Story APIs

### Task 11: Expose Public Story APIs

**Description:** Add public read-only APIs for story listing and story detail,
backed by public story artifacts.

**Acceptance criteria:**
- [ ] `GET /api/stories` lists published stories only by default.
- [ ] `GET /api/stories/{slug}` returns one public story or safe 404.
- [ ] Draft/degraded/private artifacts are not exposed as normal published
      stories.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_content_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `dashboard/routes/api.py`
- `dashboard/auth.py`
- `tests/test_site_content_api.py`

**Estimated scope:** M

### Task 12: Add Story API Contract Fixtures

**Description:** Add public API contract fixtures so Rabbit Hole cannot silently
break when v3 response shapes change.

**Acceptance criteria:**
- [ ] Fixture covers list and detail response.
- [ ] Shape tests allow additive fields but reject removed/type-changed fields.
- [ ] Live-contract mode can be extended later after deploy approval.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`

**Dependencies:** Task 11

**Files likely touched:**
- `tests/test_api_contract.py`
- `tests/fixtures/api/`

**Estimated scope:** S

### Task 12A: Expose Structured Issue, Entity, and Source APIs

**Description:** Add public read-only APIs for structured newsletter issues,
entities, and sources. These power dynamic graph template pages without
requiring AI-written editorial content.

**Acceptance criteria:**
- [ ] `GET /api/issues/{date}/structured` returns safe issue sections, story
      units, entity links, source refs, finding IDs, and arc IDs.
- [ ] `GET /api/entities` and `GET /api/entities/{slug}` return structured
      entity data from issue/finding mentions.
- [ ] `GET /api/sources/{domain}` returns source history without exposing
      private data.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_api.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_auth_middleware.py -q`

**Dependencies:** Tasks 5A, 5B, 5C, 5D

**Files likely touched:**
- `dashboard/routes/api.py`
- `dashboard/auth.py`
- `tests/test_site_issue_api.py`

**Estimated scope:** M

### Task 12B: Add Structured Public Graph API Fixtures

**Description:** Add API fixtures for issues, issue story units, entities,
sources, stories, arcs, provenance, claim evidence, and JSON-LD-ready metadata
so Rabbit Hole can validate public graph responses without live data.

**Acceptance criteria:**
- [ ] Fixtures include one canonical briefing issue, one story unit, one
      entity, one source, one story, one related trail, and one provenance
      record.
- [ ] Fixture tests reject missing provenance, missing source evidence, and
      private fields.
- [ ] Fixtures cover both high-confidence public content and degraded/draft
      content that must not be publicly exposed as published.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_site_issue_api.py -q`

**Dependencies:** Tasks 11, 12, 12A

**Files likely touched:**
- `tests/test_api_contract.py`
- `tests/fixtures/api/`

**Estimated scope:** S

### Checkpoint: Public API Contract

- [ ] v3 exposes finding, related, feed, and story endpoints.
- [ ] v3 exposes structured issue, entity, and source endpoints.
- [ ] Public graph fixtures cover story, issue, entity, source, provenance,
      claim evidence, and JSON-LD-ready fields.
- [ ] All public routes are allowlisted intentionally.
- [ ] Public API tests pass locally.

## Phase 4: Rabbit Hole Frontend Slices

### Task 13: Add Rabbit Hole Story Types and Helpers

**Description:** Add TypeScript types and API helpers for story, feed, finding,
related, structured issue, entity, and source endpoints.

**Acceptance criteria:**
- [ ] `PublicStory`, `FeedResponse`, `RelatedFinding`, and `FindingDetail`
      types exist.
- [ ] `PublicIssue`, `IssueStoryUnit`, `PublicEntity`, and `PublicSource`
      types exist.
- [ ] `getStory()`, `getStories()`, `getFindingById()`, `getRelated()`, and
      `getFeed()` helpers exist.
- [ ] `getStructuredIssue()`, `getEntity()`, and `getSource()` helpers exist.
- [ ] Existing audio/report helpers keep working.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`

**Dependencies:** Tasks 2, 3, 4, 11, 12A, 12B

**Files likely touched:**
- `src/lib/types.ts`
- `src/lib/api.ts`

**Estimated scope:** S

### Task 14: Build `/s/[slug]` Story Page

**Description:** Add the canonical public story page with take, why-now,
source trail, related paths, confidence/provenance, and media links.

**Acceptance criteria:**
- [ ] Valid story slug renders public story content.
- [ ] Missing story returns a clean not-found state.
- [ ] Related/story/source links render without exposing private data.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: `/s/<fixture-slug>`

**Dependencies:** Task 13

**Files likely touched:**
- `src/app/(app)/s/[slug]/page.tsx`
- `src/components/story/public-story.tsx`
- `src/components/story/source-trail.tsx`
- `src/components/story/related-trail.tsx`

**Estimated scope:** M

### Task 14A: Build Dynamic `/e/[slug]` and `/source/[domain]` Pages

**Description:** Add dynamic template pages for entities and sources. These
pages render from structured graph data and do not require AI-written dossiers
to exist.

**Acceptance criteria:**
- [ ] `/e/<slug>` renders entity name, type, mention count, first/last seen,
      related findings, issue story links, sources, and related entities.
- [ ] `/source/<domain>` renders source history, related findings/issues, and
      recurring topics/entities.
- [ ] Missing or weak data returns a clean not-found/degraded state, not a
      fabricated AI page.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: one entity page and one source page

**Dependencies:** Tasks 12A, 13

**Files likely touched:**
- `src/app/(app)/e/[slug]/page.tsx`
- `src/app/(app)/source/[domain]/page.tsx`
- `src/components/entity/entity-page.tsx`
- `src/components/source/source-page.tsx`

**Estimated scope:** M

### Task 15: Replace `/f/[id]` Placeholder Relatedness

**Description:** Update finding pages to fetch the single finding and real
related results from v3 instead of local latest-300/same-section matching.

**Acceptance criteria:**
- [ ] Older finding IDs can render if the backend has them.
- [ ] Related items come from `/api/related/{id}`.
- [ ] Placeholder same-section related code is removed or explicitly isolated
      as a degraded fallback.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: `/f/<known-id>`

**Dependencies:** Tasks 3, 13

**Files likely touched:**
- `src/app/(app)/f/[id]/page.tsx`
- `src/components/story/rabbit-hole.tsx`
- `src/lib/api.ts`
- `src/lib/types.ts`

**Estimated scope:** M

### Task 16: Upgrade Wire to Story/Feed Rows

**Description:** Move the homepage Wire from raw finding slices to the new
`/api/feed` shape, preferring story rows when published stories exist.

**Acceptance criteria:**
- [ ] Wire renders story-backed rows with title, dek/take, source count, and
      confidence.
- [ ] Finding-backed rows still work as fallback.
- [ ] No layout shift or text overflow on mobile row cards.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: desktop/mobile Wire

**Dependencies:** Tasks 4, 13

**Files likely touched:**
- `src/app/(app)/page.tsx`
- `src/components/wire/wire-row.tsx`
- `src/components/wire/story-wire-row.tsx`
- `src/lib/types.ts`

**Estimated scope:** M

### Task 16A: Replace or Hide Broken Chat-First Entry Points

**Description:** Audit Rabbit Hole for chat-first navigation or broken chat
surfaces. The release should make Wire, briefings, stories, entities, sources,
and arcs the useful primary experience. Ungrounded chat should be hidden,
removed, or clearly marked unavailable until it can answer from public graph
data.

**Acceptance criteria:**
- [ ] Primary navigation and first viewport do not send users into a broken or
      ungrounded chat flow.
- [ ] Any remaining chat entry point is either hidden, disabled with a clean
      state, or explicitly grounded in public graph APIs.
- [ ] No useful story/briefing/entity/source route depends on chat to work.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: homepage, main nav, mobile nav, and any chat route

**Dependencies:** Tasks 13, 16

**Files likely touched:**
- `src/app/(app)/page.tsx`
- `src/components/nav/*`
- `src/app/(app)/chat/**` if present
- `src/components/chat/**` if present

**Estimated scope:** S

### Task 17: Add Briefing-to-Story Modules

**Description:** Add a non-invasive "go deeper" module to briefing pages that
shows public stories for the same date. This avoids rewriting newsletter
markdown while proving newsletter-to-site navigation.

**Acceptance criteria:**
- [ ] `/briefings/[date]` fetches stories for that date.
- [ ] Published stories render below the briefing header or after the audio
      player.
- [ ] Dates without stories render normally with no broken controls.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: `/briefings/<date>`

**Dependencies:** Tasks 13, 14

**Files likely touched:**
- `src/app/(app)/briefings/[date]/page.tsx`
- `src/components/briefing/story-links.tsx`
- `src/lib/api.ts`

**Estimated scope:** M

### Task 17A: Add Structured Issue Graph Modules

**Description:** Render the structured issue graph on briefing pages: section
thread summaries, entity links, source links, story-unit links, and arc links.
This makes the newsletter feel like a connected public post without losing the
full issue.

**Acceptance criteria:**
- [ ] `/briefings/[date]` can load structured issue data when available.
- [ ] Section/thread summaries link to entities, sources, findings, arcs, and
      public stories.
- [ ] Missing structured issue data falls back to the full formatted briefing
      without broken UI.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: historical issue and newest issue

**Dependencies:** Tasks 5A, 5B, 12A, 13

**Files likely touched:**
- `src/app/(app)/briefings/[date]/page.tsx`
- `src/components/briefing/issue-thread-summary.tsx`
- `src/components/briefing/entity-links.tsx`
- `src/lib/api.ts`

**Estimated scope:** M

### Task 17B: Standardize Canonical Newsletter Post Template

**Description:** Make every historical and future newsletter render through one
consistent blog-style post template with matching section typography, thread
summaries, source treatment, audio placement, and "go deeper" modules.

**Acceptance criteria:**
- [ ] All existing `/briefings/[date]` pages use the same canonical template.
- [ ] Historical markdown differences do not break layout or reading flow.
- [ ] New future issues can render without special-case UI work.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual browser check: newest issue, a mid-archive issue, and oldest
      available issue

**Dependencies:** Tasks 13, 17A

**Files likely touched:**
- `src/app/(app)/briefings/[date]/page.tsx`
- `src/components/briefing/report-markdown.tsx`
- `src/components/briefing/briefing-post.tsx`
- `src/components/briefing/issue-thread-summary.tsx`

**Estimated scope:** M

### Checkpoint: Website MVP Flow

- [ ] Wire can link to `/s/<slug>`.
- [ ] `/s/<slug>` renders a source-backed story.
- [ ] `/f/<id>` uses real related results.
- [ ] Broken/ungrounded chat is not the primary user path.
- [ ] Briefing page renders as a consistent canonical post and can lead
      readers into public stories/entities/arcs/sources.
- [ ] Rabbit Hole compile/lint pass.

## Phase 5: Public Arcs, Media, and GEO

### Task 18: Add Public Arc Modules and Pages

**Description:** Surface existing narrative arc artifacts as readable public
modules and optional arc pages.

**Acceptance criteria:**
- [ ] Story pages show relevant arcs when linked in story artifacts.
- [ ] Arc detail page/module shows summary, timeline, evidence count, and
      source domains.
- [ ] Weak/stale arcs do not appear as authoritative public context.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`

**Dependencies:** Tasks 13, 14

**Files likely touched:**
- `src/lib/types.ts`
- `src/lib/api.ts`
- `src/components/story/arc-module.tsx`
- `src/app/(app)/arcs/[slug]/page.tsx`

**Estimated scope:** M

### Task 19: Add Media and Provenance Cross-Links

**Description:** Link story pages to audio briefing metadata and video-script
metadata when public-safe artifacts reference the same story/finding/arc.

**Acceptance criteria:**
- [ ] Audio modules link back to the source briefing/story when metadata exists.
- [ ] Video/script metadata is labeled manual-publish/AI-assisted and does not
      imply live social posting.
- [ ] Missing media does not render broken controls.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`

**Dependencies:** Tasks 14, 18

**Files likely touched:**
- `src/components/story/media-module.tsx`
- `src/components/briefing/audio-briefing-player.tsx`
- `src/lib/types.ts`

**Estimated scope:** M

### Task 20: Add SEO/GEO Metadata Pass

**Description:** Add JSON-LD and agent-readable metadata for public story and
arc pages. Sitemap inclusion remains owner-approved because it affects public
indexing.

**Acceptance criteria:**
- [ ] Story pages emit Article/CreativeWork JSON-LD with source/provenance.
- [ ] Arc pages emit collection/timeline metadata.
- [ ] Sitemap changes are either owner-approved or explicitly deferred.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm exec tsc --noEmit --incremental false`
- [ ] Manual page-source check for JSON-LD

**Dependencies:** Tasks 14, 18

**Files likely touched:**
- `src/app/(app)/s/[slug]/page.tsx`
- `src/app/(app)/arcs/[slug]/page.tsx`
- `src/components/json-ld.tsx`
- `src/app/sitemap.ts` only with owner approval

**Estimated scope:** M

### Checkpoint: Public Intelligence Layer

- [ ] Stories, arcs, sources, related trails, and media metadata are connected.
- [ ] Public pages carry confidence/provenance.
- [ ] No private dashboard/Slack/subscriber data is exposed.

## Phase 6: Verification, Docs, and Release Hygiene

### Task 21: Add Browser Smoke Checks

**Description:** Verify the website in a real browser locally. If adding
Playwright would require dependencies, ask owner first; otherwise perform manual
browser checks and record evidence.

**Acceptance criteria:**
- [ ] Wire -> story -> related path works.
- [ ] Briefing -> story -> arc path works.
- [ ] Audio/no-audio pages render cleanly.
- [ ] Mobile viewport has no obvious overlap or text overflow.

**Verification:**
- [ ] `pnpm dev`
- [ ] Browser smoke evidence recorded in handoff
- [ ] `pnpm build`

**Dependencies:** Tasks 14-20

**Files likely touched:**
- Handoff/runbook only, unless owner approves e2e tooling.

**Estimated scope:** S

### Task 22: Run Graphify, Docs, and Handoff

**Description:** Update runbooks, handoff, and architecture graph evidence after
implementation.

**Acceptance criteria:**
- [ ] Done columns are updated with verification evidence.
- [ ] Handoff explains what is live, local-only, deferred, or blocked.
- [ ] Graphify is refreshed for v3 changes.
- [ ] Rabbit Hole dirty state is recorded.

**Verification:**
- [ ] `git diff --check`
- [ ] `graphify update .`
- [ ] `graphify check-update .`
- [ ] `git status --short --branch` in both repos

**Dependencies:** Tasks 0-21

**Files likely touched:**
- This plan
- Spec
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- `graphify-out/` if generated

**Estimated scope:** S

### Task 23: Owner-Approved Live Deploy and Smoke

**Description:** Only with explicit owner approval, deploy/smoke v3 and Rabbit
Hole. This task stays deferred until the owner approves each live action.

**Acceptance criteria:**
- [ ] Owner approves Fly action before Fly deploy/smoke.
- [ ] Owner approves Vercel action before Vercel deploy/smoke.
- [ ] Owner approves any full daily run or live content-engine run.
- [ ] Production smoke proves no live social posting occurred.

**Verification:**
- [ ] Owner-approved command evidence recorded.
- [ ] Live URLs checked.
- [ ] Rollback path documented.

**Dependencies:** Tasks 0-22

**Files likely touched:**
- Handoff/runbook only unless deploy reveals a bug.

**Estimated scope:** M

## Parallelization Opportunities

Safe after Task 12:

- Rabbit Hole story page work and arc module work can proceed in parallel if
  the API contract is frozen.
- SEO/GEO metadata can be drafted in parallel with frontend components after
  story types are stable.
- Docs/handoff updates can be handled in parallel with final browser smoke.

Must be sequential:

- `/api/finding/{id}` before Rabbit Hole removes latest-300 fallback.
- `/api/related/{id}` before replacing placeholder relatedness.
- Public story contracts before story generator, APIs, or frontend page work.
- Owner approval before deploys, schema changes, dependency installs, or live
  provider enablement.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Existing embeddings are not enough for good relatedness | High | Prove `/api/related` early with fixtures and spot checks before UI work. |
| Public story artifacts become generic AI prose | High | Require why-now, source trail, skeptic checks, and expert-role provenance. |
| Auto-publish creates bad public pages | High | Publish only high-confidence artifacts; draft/degrade everything else. |
| Site content job weakens the newsletter | High | Run after newsletter path and test failure independence. |
| Frontend ships placeholders again | Medium | Do not replace UI until real backend contracts pass. |
| Artifact storage becomes hard to query | Medium | Use artifacts for MVP; revisit schema only after shape proves useful. |
| Dashboard/private data leaks public | High | Redaction tests and explicit public/private feature classification. |
| Vercel deploy exposes unfinished pages | Medium | No deploy without owner approval and local browser smoke. |

## Open Questions for Owner

1. Confirm `/s/<slug>` for public story URLs.
2. Confirm artifact-first storage for MVP instead of a schema change.
3. Pick the first public dashboard-style feature after stories/arcs:
   Trend Radar, Best Story Archive, Dossiers, Collections, or Knowledge Graph
   Explorer.
4. Decide whether high-confidence stories enter sitemap immediately or after a
   one-day delay.
5. Decide whether social/newsletter links should prefer story pages always, or
   arc pages when the story is clearly part of a larger arc.

## Definition of Done

- Real graph read APIs exist and are tested.
- Rabbit Hole content engine creates high-confidence public story artifacts and
  does not block the newsletter.
- Public story APIs expose only safe published artifacts.
- Rabbit Hole renders Wire -> story -> related -> briefing/arc flow.
- Same-section placeholder relatedness is removed or isolated as a degraded
  fallback.
- Public pages include source evidence, confidence, and provenance.
- Tests, lint, typecheck, docs, handoff, and Graphify evidence are current.
- Website deploy remains deferred until owner approval.

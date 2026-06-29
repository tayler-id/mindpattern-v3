# Spec: Rabbit Hole Public Intelligence Content Engine

> Status: Corrective spec after owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-29
> Supersedes: parser-first interpretation in
> `docs/runbooks/2026-06-28-rabbit-hole-public-intelligence-site-spec.md`
> Related repos:
> - v3/backend: `/Users/taylerramsay/Projects/mindpattern-v3`
> - public site: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`

## Why This Spec Exists

The previous implementation path exposed deterministic newsletter splitter
output as public story pages. That was wrong.

The public site cannot treat `## Top 5 Stories Today`, `## Security`, or other
newsletter section headings as product pages. It also cannot show raw markdown,
source URLs as topics, generic same-issue links, or a tiny slice of the corpus
as if it were the knowledge graph.

The corrected product is a public intelligence site powered by a real v3
content engine and corpus graph:

```text
daily research + historical corpus + sources + entity graph + embeddings + arcs
    -> graph packs and candidate clusters
    -> expert/editorial site-content engine
    -> high-confidence public artifacts
    -> Rabbit Hole templates and graph navigation
```

Newsletter splitting is still useful, but only as structured input to the
graph. It is not the public story-writing engine.

## Objective

Build Rabbit Hole into the public MindPattern intelligence product that
newsletter and social readers land on.

The site should publish:

- Complete canonical newsletter briefings, formatted consistently all the way
  back through the archive and for every future issue.
- Dynamic entity, source, finding, issue, story-unit, and arc templates backed
  by the real corpus graph.
- High-confidence site-native stories, dossiers, collections, and relationship
  paths written by a dedicated site-content engine.
- Public graph pages that explain why two things connect: entity overlap,
  semantic similarity, source trail, narrative arc, update relationship,
  contrast relationship, finding provenance, or historical recurrence.

The site should not publish raw parser chunks as stories. AI writes the
connective/editorial layer. Source artifacts, findings, entities, sources,
arcs, and newsletters remain the factual source of truth.

## Product Requirements

### Required User Experience

1. The homepage is the actual intelligence experience, not a landing page and
   not broken chat.
2. The Wire should show readable, interesting public intelligence rows:
   site-native story artifacts first, then high-signal finding/arc fallback if
   no published site story exists.
3. Story pages must have a real headline, dek, take, why-now, source trail,
   graph trail, related paths, provenance, and confidence.
4. Story pages must not use newsletter section titles as headlines.
5. Story pages must not render raw markdown syntax as visible text.
6. Briefing pages must remain full canonical blog-style newsletter posts.
7. Briefing pages may show a thread summary and graph links, but the complete
   newsletter remains readable below it.
8. Entity pages are dynamic templates over the corpus graph, not hand-built
   pages. They must support all valid corpus entities, including the existing
   large entity set.
9. Entity/source/finding/arc pages must use pagination or cursoring instead of
   pretending a `limit=40` slice is the whole graph.
10. Related paths must be evidence-backed and reader-readable, not internal
    labels such as `shared_source_domain+shared_entity`.
11. If high-confidence site content is unavailable, the site degrades to
    canonical briefings, findings, and graph templates. It does not promote weak
    parser output into public story pages.
12. Chat remains hidden or disabled until it is grounded in the public graph
    APIs.

### Explicit Non-Goals

- Do not hand-build 14,000+ entity pages.
- Do not use a generic blog CMS as the source of truth.
- Do not use newsletter section extraction as the public story engine.
- Do not publish medium/degraded content as normal public content.
- Do not make Rabbit Hole work block, shrink, gate, or rewrite the daily
  newsletter.
- Do not deploy the website until local build, typecheck, lint, and browser
  smoke show the public experience is materially better than the current broken
  chat.

## Tech Stack

MindPattern v3:

- Python/FastAPI public API in `dashboard/routes/api.py`
- Daily orchestration in `orchestrator/runner.py`
- Site content engine under `orchestrator/site_content.py` or a new
  `orchestrator/site_content_engine.py`
- SQLite memory data under `data/<user>/`
- Public generated artifacts under gitignored `reports/<user>/`
- Tests via `pytest`

Rabbit Hole:

- Next.js App Router
- React
- TypeScript
- Tailwind
- Public deployment target: Vercel

## Commands

v3 focused checks:

```bash
.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q
.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q
.venv/bin/python3 -m pytest tests/test_site_content_api.py -q
.venv/bin/python3 -m pytest tests/test_site_issue_contracts.py -q
.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q
```

v3 broader checks before merge:

```bash
.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q
graphify update .
graphify check-update .
```

Rabbit Hole checks:

```bash
pnpm lint
pnpm exec tsc --noEmit --incremental false
pnpm build
```

Local smoke:

```bash
.venv/bin/python3 -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8010
BACKEND_API_URL=http://127.0.0.1:8010 pnpm start --hostname 127.0.0.1 --port 3010
```

Do not run full daily pipeline, send newsletters, deploy Fly, deploy Vercel,
add dependencies, change schema, or enable live providers without explicit
owner approval.

## Data Architecture

### Source-of-Truth Inputs

- `findings`: atomic research findings.
- `findings_embeddings`: semantic recall for findings.
- `kg_entities` and `kg_edges` where available.
- `entity_graph` where available.
- `sources`: source recurrence and quality signals.
- `reports/<user>/YYYY-MM-DD.md`: canonical newsletter posts.
- `reports/<user>/arcs/`: narrative arc artifacts.
- `reports/<user>/audio/`: audio artifacts.
- `reports/<user>/video-scripts/`: video script artifacts.

### Derived Graph Artifacts

Structured issue artifacts:

```text
reports/<user>/site-issues/YYYY-MM-DD.json
```

These preserve the complete newsletter and expose sections, story units,
sources, entities, findings, arcs, and provenance. They are graph inputs and
briefing-page helpers. They are not public story artifacts by themselves.

Site story artifacts:

```text
reports/<user>/site-stories/YYYY-MM-DD/<slug>.json
```

These are written by the content engine after graph-packing and editorial
generation. Only high-confidence published artifacts are exposed through
`/api/stories`.

Site run ledger:

```text
reports/<user>/site-runs/YYYY-MM-DD.json
```

This records candidates considered, graph packs built, generated artifacts,
draft/degraded/failed outcomes, confidence reasons, redactions, and trace IDs.

Future artifact classes:

```text
reports/<user>/site-dossiers/<entity-slug>.json
reports/<user>/site-collections/YYYY-MM-DD/<slug>.json
reports/<user>/site-graph/YYYY-MM-DD.json
```

### Public Story Contract

```ts
type PublicStory = {
  kind: 'story'
  id: string
  slug: string
  status: 'published' | 'draft' | 'degraded' | 'failed'
  confidence: 'high' | 'medium' | 'degraded'
  issue_date: string
  title: string
  dek: string
  take: string
  why_now: string
  body_markdown: string
  source_refs: SourceRef[]
  entity_refs: EntityRef[]
  primary_finding_ids: number[]
  supporting_finding_ids: number[]
  arc_ids: string[]
  graph_edges: GraphEdge[]
  related_paths: RelatedPath[]
  claim_evidence: ClaimEvidence[]
  labels: string[]
  target_url: string
  json_ld_ready: boolean
  provenance: Provenance
}
```

### Relationship Contract

```ts
type RelatedPath = {
  target_type: 'story' | 'finding' | 'entity' | 'source' | 'arc' | 'briefing'
  target_id: string
  target_url: string
  title: string
  relationship: string
  reason: string
  score: number
  evidence_edges: GraphEdge[]
}
```

Reader-facing relationship labels should be plain language:

- "Same company"
- "Same source trail"
- "Part of the same narrative arc"
- "Updates an earlier finding"
- "Contrasts with this finding"
- "Often appears with this entity"
- "Semantically similar research"

Internal connector names can exist in JSON, but they should not be the visible
heading text.

## Site Content Engine

The content engine is a post-newsletter enrichment job. It can also run
standalone against a date or corpus slice. It must never block or weaken the
newsletter.

### Pipeline

```text
candidate selection
    -> graph pack builder
    -> expert/editorial loop
    -> skeptic/fact check
    -> confidence gate
    -> artifact writer
    -> public API reads published artifacts
```

### Candidate Selection

Select candidates from:

- Current-day findings.
- High-importance findings.
- New or updated narrative arcs.
- Entity clusters with meaningful recurrence.
- Sources with strong new signals.
- Newsletter story units as context only.
- Existing corpus graph neighbors.

The selector must not mutate newsletter story selection.

### Graph Pack Builder

For each candidate, build a bounded graph pack:

- Primary finding or issue story unit.
- Related findings from embeddings.
- Related entities from `kg_entities`, `kg_edges`, and `entity_graph`.
- Source trail.
- Narrative arc links.
- Historical occurrences.
- Contradicting or contrasting evidence when available.
- Claim-to-source evidence candidates.

Graph packs are the main input to AI/editorial generation. AI does not invent
edges.

### Expert Loop

The first implementation must support deterministic dry-run output and fake
providers in tests. Live model calls require owner approval.

Roles:

- Assignment Editor: chooses whether the graph pack deserves a public page.
- Graph Cartographer: explains the typed graph relationships.
- Domain Expert: adds technical, product, market, policy, or research context.
- Skeptic: removes unsupported claims, fake trend language, and weak causal
  leaps.
- Narrative Editor: writes headline, dek, take, why-now, and follow-the-thread
  language.
- Source Librarian: verifies source URLs, source labels, dates, and claim
  evidence.
- GEO/Agent-Web Editor: prepares JSON-LD-ready metadata.

### Confidence Gate

Published requires all of:

- Public-safe redaction passed.
- At least one primary authoritative source or two independent source domains.
- Non-empty claim evidence for every synthesized claim.
- Non-empty related graph evidence unless the artifact is explicitly a single
  source explainer.
- No skeptic kill-switch.
- A clear why-now reason.
- No raw Slack bodies, subscriber data, personal memory, secrets, local paths,
  or private DB contents.

Medium/degraded/failed artifacts stay internal and are not returned by
`/api/stories` default listing.

## Public API Requirements

Backend APIs:

- `GET /api/feed`: story/cluster/finding feed with safe fallback.
- `GET /api/stories`: published site-story artifacts only.
- `GET /api/stories/{slug}`: one published site-story artifact.
- `GET /api/issues`: briefing index.
- `GET /api/issues/{date}/structured`: complete structured issue artifact or
  deterministic parser output.
- `GET /api/entities`: paginated/searchable entity index over the full corpus.
- `GET /api/entities/{slug}`: entity detail with story units, findings,
  relationships, source trail, and pagination/cursor metadata.
- `GET /api/entities/{slug}/neighbors`: typed related entities.
- `GET /api/sources/{domain}`: source detail.
- `GET /api/finding/{id}`: public finding detail.
- `GET /api/related/{id}`: semantic/entity/arc related findings.
- `GET /api/narrative-arcs` and `/api/narrative-arcs/{id}`: public arcs.

API rules:

- Validate user/date/slug/domain/id inputs.
- Never serve arbitrary files.
- Whitelist output fields.
- Include provenance and confidence on public artifacts.
- Include pagination metadata for large corpus endpoints.
- Expose totals where safe so the UI does not imply a small slice is the whole
  graph.

## Rabbit Hole Frontend Requirements

Homepage:

- Prefer published site stories from `/api/stories`.
- If no site stories exist, render high-signal finding/feed rows with a clear
  source-backed fallback, not parser-derived public stories.
- Do not make chat primary.

Story page:

- Render `title`, `dek`, `take`, `why_now`, `body_markdown`, sources, graph
  trail, related paths, provenance, and JSON-LD.
- Never render raw markdown syntax as plain text.
- Never show internal connector strings as section headings.

Briefing page:

- Render complete newsletter as canonical post.
- Add structured thread summary only when parser output is clean.
- Link issue story units to entity/source/finding/arc routes, not automatically
  to `/s` unless a published site story artifact exists.

Entity page:

- Dynamic route for all valid entities.
- Show mention counts, first/last seen, related findings, related stories,
  source trail, related entities, and pagination.
- Do not imply `limit=40` is the whole corpus.

Source page:

- Show source history, findings, issue mentions, related entities/topics, and
  source confidence.

## Code Style

Prefer typed contracts, explicit status, and whitelisted public output.

```python
def public_story_is_publishable(story: dict) -> bool:
    return (
        story.get("status") == "published"
        and story.get("confidence") == "high"
        and bool(story.get("source_refs"))
        and bool(story.get("claim_evidence"))
        and story.get("provenance", {}).get("redaction_status") == "passed"
    )
```

Avoid ambiguous names:

- Good: `IssueStoryUnit`, `PublicStoryArtifact`, `GraphPack`,
  `PublishedStory`.
- Bad: `Story` when it might mean newsletter section, parser chunk, or public
  editorial page.

## Testing Strategy

v3:

- Unit tests for safe artifact paths and redaction.
- Unit tests for structured issue splitting, with guards against section titles
  becoming public stories.
- Unit tests for graph pack construction over fixture findings/entities/arcs.
- Unit tests for candidate selection and weak-input degradation.
- Unit tests for deterministic story generation.
- Unit tests for confidence gates.
- API tests proving `/api/stories` returns published site artifacts only.
- API tests proving draft/degraded/parser-only artifacts are not public stories.
- API tests proving entity indexes/details can page through corpus data.
- Runner dry-run tests proving the content engine cannot block newsletter send.

Rabbit Hole:

- Lint, typecheck, build.
- Browser smoke for homepage, story, briefing, entity, source, finding, and no
  broken chat entry.
- Visual checks on mobile and desktop for raw markdown, bad headings, link
  click behavior, and related path readability.

## Boundaries

Always:

- Keep newsletter autonomous.
- Keep public site content source-backed.
- Keep parser output separate from site-native story artifacts.
- Keep large-corpus pages dynamic and paginated.
- Keep `reports/` generated artifacts out of git unless they are fixtures.
- Update handoff/runbooks after verified work.

Ask first:

- Vercel deploy.
- Fly deploy.
- Full daily pipeline run.
- Live provider/model calls.
- Schema changes.
- Dependencies.
- Sitemap/indexing changes.

Never:

- Publish raw newsletter section chunks as public stories.
- Show low-confidence/degraded content as normal public pages.
- Expose private data, secrets, Slack bodies, subscriber data, DB files,
  personal memory, or provider tokens.
- Make Slack approval required for newsletter send.
- Auto-post live social content without Slack owner approval.
- Claim the 14,000+ entity graph is working from a small limited slice.

## Success Criteria

MVP:

- Current bad story-first Wire is disabled or replaced with safe fallback.
- `/api/stories` is backed by published site-story artifacts only.
- Structured issue/story-unit parser remains available for briefings and graph
  input, but not as the public story feed.
- A deterministic content-engine dry run can write at least one high-confidence
  public story artifact from fixture graph data.
- Draft/degraded artifacts are not publicly listed.
- Entity/source/finding routes are dynamic, paginated where needed, and backed
  by the real corpus graph.
- Briefing pages render complete canonical newsletters with clean formatting.
- Rabbit Hole pages no longer show raw markdown syntax, bad section headings,
  source-as-topic noise, or internal connector labels.
- Local v3 tests pass.
- Rabbit Hole lint/typecheck/build pass.
- Browser smoke passes on desktop and mobile.
- No production deploy occurs before owner approval.

Release-ready:

- Website is materially better than the broken chat-first experience.
- Homepage -> story -> related graph -> entity/source/finding flow works.
- Full old newsletter archive can be normalized or clearly staged with an audit
  ledger.
- Handoff and runbooks are current.
- Both repos are clean or dirty files are clearly explained.

## Open Questions

1. Should the first content-engine artifacts live at
   `reports/<user>/site-stories/YYYY-MM-DD/<slug>.json` or the existing flat
   `reports/<user>/site-stories/<slug>.json` path for compatibility?
2. Should entity indexes expose all public entity names immediately, or require
   search/query first to avoid huge responses?
3. Should site-native public stories be generated for only the top candidates
   daily, or also backfilled for the historical archive?
4. Should `/s/<slug>` stay the canonical public story URL, or should the public
   story URL become `/story/<slug>` while `/s` remains compatibility?

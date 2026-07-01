# Spec: Rabbit Hole Real Content Machine

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-30
> Builds on:
> - `docs/runbooks/2026-06-29-rabbit-hole-content-engine-corrected-spec.md`
> - `docs/runbooks/2026-06-29-rabbit-hole-content-engine-corrected-implementation-plan.md`
> Related repos:
> - v3/backend: `/Users/taylerramsay/Projects/mindpattern-v3`
> - public site: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`

## Objective

Build the real Rabbit Hole content machine: a v3 backend pipeline that turns the
MindPattern research corpus into source-backed public intelligence pages for the
Rabbit Hole website.

The content machine is not the website UI by itself. The backend creates public
artifacts, graph packs, relationship trails, and canonical indexes. Rabbit Hole
renders those artifacts with dynamic templates.

The daily shape is:

```text
daily research + historical newsletters + findings + entity graph + embeddings + arcs
    -> corpus inventory
    -> candidate clusters
    -> graph packs
    -> expert editorial pipeline
    -> confidence gate
    -> public artifacts
    -> Rabbit Hole APIs and pages
```

The previous parser-first approach failed because it promoted newsletter
sections such as `Top 5 Stories Today` and `Security` into public story cards.
That must not happen again. Newsletter splitting is an input to the graph, not
the public writing engine.

## Core Product Model

Rabbit Hole should feel like a living public intelligence system:

- Every newsletter remains a complete canonical briefing page.
- Every valid entity, source, finding, narrative arc, issue, and public story is
  linkable through dynamic templates.
- Related content is connected by real evidence, not just same newsletter date.
- Public story pages are written as site-native pieces with headline, dek,
  sharp take, why-now, source trail, graph trail, and follow-the-thread links.
- AI explains and writes from the graph. AI does not become the source of truth.
- Weak, medium, or degraded artifacts stay internal or visibly degraded. They do
  not appear as normal public site content.

## Source Of Truth

The factual source of truth is existing MindPattern data:

- `findings`: atomic research findings from the daily agent pipeline.
- `findings_embeddings`: semantic relatedness between findings.
- `kg_entities`, `kg_entity_aliases`, `kg_edges`, and `kg_communities` where
  available.
- `entity_graph`: legacy entity relationship/provenance table.
- `sources`: source quality and recurrence signals where available.
- `reports/<user>/*.md`: canonical newsletter markdown.
- `reports/<user>/arcs/`: narrative arc artifacts.
- `reports/<user>/followups/`: owner-triggered follow-up research artifacts.
- `reports/<user>/audio/` and `reports/<user>/video-scripts/`: future media
  artifacts that may attach to public stories.

Generated public content is derived from those inputs and written under
gitignored `reports/<user>/site-*` directories. No database schema change is
required for the MVP unless explicitly approved.

## Required Outputs

### Site Run Ledger

Path:

```text
reports/<user>/site-runs/YYYY-MM-DD.json
```

Purpose:

- Records the content-machine run without exposing private raw data.
- Lists inputs scanned, candidates considered, graph packs built, artifacts
  written, confidence outcomes, rejection reasons, redaction status, and trace
  IDs.
- Makes it obvious why a day produced public content, draft content, or no
  publishable content.

### Corpus Inventory

Path:

```text
reports/<user>/site-corpus/YYYY-MM-DD.json
```

Purpose:

- Records public-safe counts and coverage for the corpus on that day.
- Includes counts for findings, entities, edges, sources, embeddings, issues,
  arcs, and publishable artifacts.
- Must distinguish "full corpus total" from "current page limit" so the UI
  never implies that 40 rows are the whole graph.

### Structured Issues

Path:

```text
reports/<user>/site-issues/YYYY-MM-DD.json
```

Purpose:

- Normalizes every newsletter into sections, story units, source refs, entity
  refs, finding refs, and provenance.
- Preserves the complete canonical newsletter.
- Feeds the graph and briefing pages.

Rules:

- Structured issue story units are not public stories.
- Section headings are never public story titles.
- Raw markdown syntax must be rendered or cleaned before public display.

### Candidate Clusters

Path:

```text
reports/<user>/site-candidates/YYYY-MM-DD/<candidate-id>.json
```

Purpose:

- Describes potential public content before AI writing.
- Candidate types include:
  - `finding_story`
  - `arc_update`
  - `entity_dossier`
  - `source_watch`
  - `briefing_thread`
  - `trend_cluster`
  - `contrast_pair`
  - `followup_update`
  - `collection`

Each candidate must include why it exists, which evidence supports it, and what
public page type it could become.

### Graph Packs

Path:

```text
reports/<user>/site-graph-packs/YYYY-MM-DD/<candidate-id>.json
```

Purpose:

- Provides the bounded evidence packet the expert pipeline writes from.
- Prevents the model from inventing relationships.

Graph pack contents:

- Primary findings or issue story units.
- Source refs with domains, dates, titles, and URLs.
- Entity refs and aliases.
- Typed edges from `kg_edges` and `entity_graph`.
- Semantic neighbors from embeddings.
- Narrative arcs.
- Historical occurrences.
- Related previous public stories.
- Contrasts, corrections, or stale/repeated-story warnings.
- Claim-evidence candidates.
- Redaction report.

### Public Site Stories

Path:

```text
reports/<user>/site-stories/YYYY-MM-DD/<slug>.json
```

Purpose:

- Site-native written public intelligence pages.
- These are what `/api/stories` and `/s/<slug>` should expose.

Required fields:

```ts
type PublicSiteStory = {
  kind: 'site_story'
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
  provenance: Provenance
  json_ld_ready: boolean
}
```

Writing rules:

- The title must be written for the site, not copied from a generic newsletter
  section.
- The body must be readable public prose, not a truncated parser chunk.
- Claims must map to evidence.
- Related paths must explain the connection in reader-facing language.
- Published stories require `status=published` and `confidence=high`.

### Entity Dossiers

Path:

```text
reports/<user>/site-dossiers/entities/<entity-slug>.json
```

Purpose:

- Optional generated editorial layer on top of dynamic entity pages.
- Useful for high-value recurring entities.

Rules:

- Do not hand-build 14,000+ pages.
- The dynamic `/e/<slug>` route must work from the graph even when no generated
  dossier exists.
- Generated dossier content is enrichment only.

### Source Pages

Path:

```text
reports/<user>/site-dossiers/sources/<domain-slug>.json
```

Purpose:

- Optional generated editorial layer on top of dynamic source pages.
- Shows what a source has been useful for, where it recurs, and which entities
  or arcs it connects.

### Collections

Path:

```text
reports/<user>/site-collections/YYYY-MM-DD/<slug>.json
```

Purpose:

- Curated public packages such as "AI model supply-chain risk", "agent coding
  reliability", or "new builder workflow".
- Built from multiple candidates and graph packs.

Collections are not required for the first MVP but should fit the same artifact
and confidence model.

## Relationship System

Related paths must use multiple connectors. Same-newsletter relatedness is only
one weak signal and cannot be the whole graph.

Supported connector classes:

| Connector | Meaning | Public label example |
|---|---|---|
| `same_entity` | Same canonical entity or alias appears in both items. | "Same company: Anthropic" |
| `same_source_url` | Both cite the exact same URL. | "Same source article" |
| `same_source_domain` | Both cite the same source domain. | "Same source trail: anthropic.com" |
| `semantic_neighbor` | Embeddings show strong semantic relatedness. | "Semantically close research" |
| `same_arc` | Both belong to the same narrative arc. | "Part of the same narrative arc" |
| `updates_finding` | New item updates an older finding. | "Updates earlier coverage" |
| `contrasts_with` | New item meaningfully contradicts or contrasts another. | "Contrasts with earlier signal" |
| `same_actor_role` | Same entity role, such as vendor, regulator, model provider. | "Same market actor" |
| `same_threat_pattern` | Security or risk pattern repeats. | "Same threat pattern" |
| `same_stack_layer` | Items touch the same technical layer. | "Same stack layer" |
| `same_policy_dependency` | Items depend on the same policy/regulatory force. | "Same policy dependency" |
| `recurring_source_cluster` | Source repeatedly covers a topic/entity cluster. | "Recurring source cluster" |
| `followup_thread` | Follow-up research extends a previous item. | "Follow-up to earlier research" |
| `newsletter_context` | Same issue context only. | "Appeared in the same briefing" |

Scoring rules:

- Exact source URL, same entity, same arc, and update relationships score above
  same date or loose topic overlap.
- Topic overlap must use at least two meaningful terms and cannot be built from
  URLs, section titles, or generic words.
- The UI must show readable labels and reasons, not internal connector keys.
- Every related path must include evidence edges.

## Candidate Selection

The selector runs without model calls first. It should identify public content
candidates from:

- New high-importance findings.
- Dense entity clusters.
- New or changed narrative arcs.
- Strong source clusters.
- Follow-up research artifacts.
- Newsletter story units as context only.
- Historical recurrence in the graph.
- Semantic clusters from embeddings.
- High-signal contrasts or reversals.

Candidate ranking signals:

- Source strength and independence.
- Finding importance.
- Recency and why-now.
- Entity recurrence.
- Arc momentum.
- Semantic density.
- Novelty against recent public stories and newsletters.
- Risk of duplication or stale resurfacing.
- Public usefulness.

Candidate selection must never mutate newsletter story selection.

## Expert Editorial Pipeline

The first implementation must support deterministic fake providers in tests and
dry-runs. Live model calls require explicit owner approval.

Roles:

- Assignment Editor: decides whether a candidate deserves a public artifact and
  chooses the artifact type.
- Graph Cartographer: verifies relationships, connector classes, and graph
  trail clarity.
- Domain Expert: adds technical, product, market, policy, or research context
  using only graph-pack evidence.
- Skeptic and Fact Checker: removes unsupported claims, hype, fake causality,
  duplicate angles, and stale repeats.
- Narrative Editor: writes the headline, dek, take, why-now, body, and
  follow-the-thread copy.
- Source Librarian: checks source labels, URLs, dates, domains, and evidence
  coverage.
- GEO and Agent-Web Editor: prepares structured metadata, JSON-LD-ready fields,
  and machine-readable summaries.
- Website Publisher: writes only public-safe artifacts that passed the gate.

Provider boundary:

```python
class SiteContentExpert:
    role: str

    def run(self, graph_pack: GraphPack, context: RunContext) -> ExpertResult:
        ...
```

Implementation requirements:

- Tests use fake experts.
- Missing live provider config falls back to deterministic draft/degraded
  output.
- The expert loop cannot call Slack, email, social APIs, Fly, Vercel, or the
  full daily pipeline.
- The expert loop cannot approve or post social content.

## Confidence Gate

Published public content requires:

- Redaction passed.
- At least one authoritative primary source or two independent source domains.
- Claim evidence for each synthesized claim.
- Graph evidence for every related path.
- A clear why-now.
- No private data, secrets, Slack message bodies, subscriber data, personal
  memory, provider tokens, local paths, or raw database dumps.
- No generic newsletter section title as the public title.
- No raw markdown syntax visible in fields intended for rendered prose.
- No stale repeat unless the new artifact explains what changed.
- Skeptic result does not contain a kill switch.

Medium, degraded, failed, and draft artifacts may be written internally but are
not returned from the public story listing.

## Website Contract

Rabbit Hole should consume public APIs and artifacts. It should not generate
the intelligence itself.

Homepage:

- Show published site stories first.
- Show high-signal feed/finding/arc fallback if no site stories exist.
- Never show parser-derived story chunks as the main product.
- Never make chat the primary UX until chat is grounded in public graph APIs.

Story pages:

- Render site-native story artifacts from `/api/stories/{slug}`.
- Show title, dek, take, why-now, body, source trail, graph trail, related
  paths, confidence, provenance, and JSON-LD-ready metadata.
- Links must work on first click.

Briefing pages:

- Render every old and future newsletter as a complete canonical blog-style
  post.
- Add thread summaries and graph links only as enrichment.
- Link to `/s/<slug>` only when a published site-story artifact exists.

Entity pages:

- `/e/<slug>` must support every valid public entity dynamically.
- Show full-corpus counts, page/cursor metadata, related findings, related
  entities, source trail, arcs, and public stories.
- Never imply a small page is the whole graph.

Source pages:

- `/source/<domain>` shows source history, linked findings, entities, arcs,
  issue mentions, and confidence/provenance.

Finding and arc pages:

- `/f/<id>` and `/arc/<id>` expose public-safe evidence, sources, related
  entities, and public story links.

## API Requirements

Backend endpoints:

- `GET /api/stories`
- `GET /api/stories/{slug}`
- `GET /api/issues`
- `GET /api/issues/{date}/structured`
- `GET /api/entities?q=&limit=&offset=`
- `GET /api/entities/{slug}?limit=&offset=`
- `GET /api/entities/{slug}/neighbors`
- `GET /api/sources/{domain}?limit=&offset=`
- `GET /api/findings/{id}`
- `GET /api/related/{id}`
- `GET /api/narrative-arcs`
- `GET /api/narrative-arcs/{id}`
- `GET /api/site/runs/{date}`
- `GET /api/site/corpus/{date}`

API rules:

- Validate user, date, slug, domain, and integer IDs.
- Never serve arbitrary files.
- Whitelist public fields.
- Return pagination metadata for large corpus endpoints.
- Return public-safe totals where possible.
- Return explicit degraded/empty states instead of pretending unavailable data
  is complete.

## Tech Stack

MindPattern v3:

- Python
- FastAPI route layer in `dashboard/routes/api.py`
- Existing memory SQLite and report artifacts
- Content contracts under `orchestrator/site_content.py`
- New content machine under `orchestrator/site_content_engine.py`
- Tests with `pytest`

Rabbit Hole:

- Next.js App Router
- React
- TypeScript
- Tailwind
- Vercel target, with production deploy gated by owner approval

## Commands

v3 focused checks:

```bash
.venv/bin/python3 -m pytest tests/test_site_content_contracts.py -q
.venv/bin/python3 -m pytest tests/test_site_content_engine.py -q
.venv/bin/python3 -m pytest tests/test_site_content_confidence.py -q
.venv/bin/python3 -m pytest tests/test_site_graph_api.py -q
.venv/bin/python3 -m pytest tests/test_site_content_api.py -q
```

v3 safety checks:

```bash
.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_auth_middleware.py -q
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

## Project Structure

New or expanded backend files:

```text
orchestrator/site_content.py
orchestrator/site_content_engine.py
orchestrator/site_graph.py
orchestrator/site_experts.py
dashboard/routes/api.py
tests/test_site_content_contracts.py
tests/test_site_content_engine.py
tests/test_site_content_confidence.py
tests/test_site_graph_api.py
tests/test_site_content_api.py
```

Generated artifacts:

```text
reports/<user>/site-runs/
reports/<user>/site-corpus/
reports/<user>/site-issues/
reports/<user>/site-candidates/
reports/<user>/site-graph-packs/
reports/<user>/site-stories/
reports/<user>/site-dossiers/
reports/<user>/site-collections/
```

Rabbit Hole areas:

```text
src/lib/api.ts
src/lib/types.ts
src/app/(app)/page.tsx
src/app/(app)/s/[slug]/page.tsx
src/app/(app)/briefings/[date]/page.tsx
src/app/(app)/e/[slug]/page.tsx
src/app/(app)/source/[domain]/page.tsx
src/app/(app)/f/[id]/page.tsx
src/app/(app)/arc/[id]/page.tsx
src/components/wire/
src/components/story/
src/components/briefing/
src/components/graph/
```

## Code Style

Use explicit contracts and names that prevent parser chunks from being confused
with written public stories.

Good names:

- `StructuredIssue`
- `IssueStoryUnit`
- `ContentCandidate`
- `GraphPack`
- `PublicSiteStory`
- `EntityDossier`
- `RelatedPath`
- `SiteRunLedger`

Bad names:

- `Story` for everything.
- `Topic` for source domains.
- `Related` without evidence or connector type.

Example gate:

```python
def is_publishable_site_story(story: dict) -> bool:
    return (
        story.get("kind") == "site_story"
        and story.get("status") == "published"
        and story.get("confidence") == "high"
        and bool(story.get("source_refs"))
        and bool(story.get("claim_evidence"))
        and bool(story.get("graph_edges"))
        and story.get("provenance", {}).get("redaction_status") == "passed"
    )
```

## Testing Strategy

Unit tests:

- Artifact path validation.
- Redaction.
- Structured issue parsing.
- Candidate selection.
- Graph pack construction.
- Related path scoring and labels.
- Expert provider fake boundary.
- Confidence gate publish/reject behavior.
- Ledger writing.

API tests:

- `/api/stories` returns only published high-confidence site-story artifacts.
- Draft/degraded/parser artifacts are not public.
- Entity index supports search and pagination over corpus fixtures.
- Entity detail includes counts and pagination metadata.
- Source detail validates domains and returns public-safe graph evidence.
- Related paths use evidence-backed connectors.
- Invalid users, slugs, dates, domains, and IDs fail safely.

Runner tests:

- Site content enrichment runs after newsletter work.
- Site content failure does not block newsletter send.
- Dry-run uses fake providers and no network.

Rabbit Hole tests/checks:

- Typecheck enforces separate issue story and public story types.
- Build passes.
- Browser smoke covers homepage, story, briefing, entity, source, finding, arc,
  and hidden/disabled chat flows.
- Smoke checks for no raw markdown, no bad section headings, no internal
  connector labels, and working first-click links.

## Boundaries

Always:

- Keep newsletter research, writing, and sending autonomous.
- Keep Rabbit Hole work enrichment-only relative to the newsletter.
- Keep public output source-backed and graph-backed.
- Keep parser output separate from site-native public stories.
- Keep all large corpus surfaces dynamic and paginated.
- Keep generated site artifacts under gitignored `reports/`.
- Update runbooks and handoff with evidence.

Ask first:

- Vercel deploy.
- Fly deploy.
- Full daily pipeline run.
- Live model/provider calls.
- New dependencies.
- Database schema changes.
- Public indexing/sitemap changes.

Never:

- Publish raw newsletter chunks as public site stories.
- Use generic section headings as story titles.
- Show source domains as topics.
- Claim a limited slice is the 14,000+ entity graph.
- Expose secrets, personal data, Slack bodies, subscriber data, private memory,
  databases, users.json, social-config.json, or provider tokens.
- Make Slack approval required for newsletter send.
- Auto-post live social content without explicit Slack owner approval.

## Success Criteria

MVP success:

- The backend can run a deterministic site-content dry run from fixtures and
  write a site run ledger, graph pack, and at least one high-confidence public
  site-story artifact.
- `/api/stories` serves only those artifacts.
- Entity/source/finding/arc APIs expose real corpus-backed graph data with
  pagination and public-safe totals.
- Related paths use multiple evidence-backed connectors and readable labels.
- Rabbit Hole homepage renders published site content first and safe graph/feed
  fallback second.
- Rabbit Hole story pages render readable site-native content, not truncated
  parser chunks.
- Briefing pages preserve complete canonical newsletters.
- Entity pages are dynamic and do not require hand-building 14,000+ pages.
- Local v3 tests pass.
- Rabbit Hole lint, typecheck, and build pass.
- Browser smoke proves the broken chat-first experience is no longer primary.

Release-ready success:

- A current-day site-content run produces publishable artifacts or an explicit
  degraded/no-public-content ledger.
- Historical backfill has an audit ledger and does not fabricate missing graph
  links.
- Handoff and runbooks are current.
- Both repos are clean or dirty files are clearly explained.
- Production Vercel deploy happens only after owner approval.

## Open Questions

1. Should the first public content machine generate only current-day site
   stories, or also backfill a small set of high-confidence historical stories
   for launch?
2. Should generated entity dossiers be limited to recurring/high-value entities
   at first while dynamic entity pages cover the full graph?
3. Should `/s/<slug>` remain the canonical story URL, or should new public
   story pages move to `/story/<slug>` with `/s` as compatibility?
4. Which live expert provider should be approved first when deterministic dry
   run is working: Claude CLI, another local agent runner, or a queue-based
   provider boundary?
5. Should high-confidence site artifacts publish automatically to the website
   once generated, or should the first production release require a manual
   "publish selected artifacts" command until trust is proven?

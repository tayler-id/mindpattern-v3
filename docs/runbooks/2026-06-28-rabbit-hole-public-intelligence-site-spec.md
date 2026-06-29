# Spec: Rabbit Hole Public Intelligence Site and Daily Content Engine

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-28
> Related repos:
> - v3/backend: `/Users/taylerramsay/Projects/mindpattern-v3`
> - public site: `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`

## Assumptions

1. Rabbit Hole becomes the primary public destination for MindPattern links from
   newsletters, social posts, audio, and video scripts.
2. The product is content-first and archive-first, not dashboard-first and not
   chat-first.
3. The current Signal light/cobalt design direction in the Rabbit Hole rebuild
   spec is the product source of truth unless the owner changes it.
4. The daily newsletter remains autonomous. The Rabbit Hole content engine may
   enrich and publish site-native content, but it must not block newsletter
   research, writing, or sending.
5. High-confidence public content can publish automatically. Medium-confidence,
   degraded, or weakly sourced content must be held as draft, marked degraded,
   or skipped.
6. The graph must be real: semantic relatedness, entities, narrative arcs,
   source trails, and typed relationships. Same-category placeholder links are
   not acceptable as the final product behavior.
7. AI writes the connective layer, but every public AI-written claim needs
   source evidence, confidence metadata, and a visible provenance trail.
8. Newsletters are not just markdown pages. Each daily newsletter should be
   split into structured issue sections, story units, entities, source
   references, and graph links so the site can connect from the email into the
   public knowledge graph.
9. Every newsletter, including the historical archive and every future issue,
   should also render as a consistent, polished blog-style briefing page with
   the same formatting, section treatment, thread summaries, source treatment,
   and reading experience.
10. The public graph should use web-native semantic publishing standards:
    Article/NewsArticle-style page metadata, JSON-LD for linked data,
    explicit provenance, and dereferenceable URLs for every public node.

## Objective

Build Rabbit Hole into the public MindPattern intelligence product: a
content-driven, AI-generated, source-backed site where newsletter and social
readers land to explore stories, arcs, sources, and graph connections produced
by a daily expert-agent editorial loop.

The daily newsletter remains a human-readable issue, but the website needs the
newsletter as structured data too. An issue is split into sections and story
units; each story unit links to entities, findings, sources, arcs, and related
site pages. The email becomes the daily narrative surface, while Rabbit Hole
becomes the entity/story/source graph that readers can continue exploring.

Do not split the newsletter in a way that loses the complete issue. The full
newsletter remains a canonical public post, like a high-quality blog article.
The structured issue graph is extracted from that post and used to power thread
summaries, entity links, story links, and rabbit-hole paths.

The site should answer, for every major story:

- What happened?
- Why does it matter now?
- What larger pattern or narrative arc does this connect to?
- Which sources prove it?
- Which related findings, people, companies, products, and concepts should the
  reader follow next?
- What media can be created from it: social angle, audio segment, video script,
  collection, or dossier?

Success means a reader can click a newsletter or social link and land on a
rich, public story/arc page rather than a raw finding row or generic archive
entry.

## Tech Stack

MindPattern v3:

- Python/FastAPI public API in `dashboard/routes/api.py`
- SQLite memory and trace stores under `data/<user>/`
- Existing embeddings in `findings_embeddings`
- Daily orchestration in `orchestrator/runner.py`
- Generated artifacts under gitignored `reports/<user>/`
- Tests via `pytest`

Rabbit Hole:

- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind v4
- shadcn/base-ui primitives where already used
- Motion for limited interaction polish
- Public deployment target: Vercel

## Commands

v3 backend:

```bash
.venv/bin/python3 -m pytest tests/test_api_contract.py -q
.venv/bin/python3 -m pytest tests/test_narrative_arcs.py tests/test_audio_briefing.py -q
.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q
graphify update .
graphify check-update .
```

Rabbit Hole site:

```bash
pnpm lint
pnpm exec tsc --noEmit --incremental false
pnpm build
pnpm dev
```

No Fly deploy, Vercel deploy, full daily pipeline run, live social post, live
newsletter send, schema change, dependency install, or provider credential
change should happen without explicit owner approval.

## Research-Backed Architecture Conclusions

The product should be built as a semantic publishing system with GraphRAG-style
retrieval, not as a normal blog, a dashboard, or a chat app.

The researched pattern is:

```text
raw research + sources
    -> canonical newsletter issue
    -> issue sections and story atoms
    -> entities, sources, findings, arcs, and typed relationships
    -> dynamic public templates
    -> high-confidence AI/editorial enrichment
```

Key decisions:

- Keep the full newsletter as the canonical human-readable article.
- Split the newsletter into structured issue/story atoms without losing the
  original post.
- Use dynamic templates for every valid entity, finding, source, issue story,
  and arc. Do not hand-build thousands of pages.
- Use embeddings for semantic recall and graph edges for explainable
  relationship trails.
- Store generated public content as JSON artifacts first, with JSON-LD-ready
  fields. Do not introduce a graph database until the contracts prove useful.
- Treat AI as an explainer, classifier, and editor over source-backed graph
  data. AI output must not become the source of truth for facts or edges.
- Preserve provenance for every public artifact: source URLs, first-seen dates,
  generation step, confidence, redaction status, and input artifact IDs.
- Backfill old newsletters through the same splitter/normalizer used for new
  issues, so old and future briefings share one public structure.

Research references to preserve for implementers:

- Google Search Central: Article/NewsArticle structured data for article pages.
- Schema.org: `NewsArticle`, `CreativeWork`, and entity `mentions`.
- IPTC media standards: rNews concepts were incorporated into schema.org news
  vocabularies.
- Reuters Institute News Atom: sentence/story atoms with entities,
  attribution, event dates, evidence, and archive reuse.
- Google Cloud GraphRAG: vector search plus graph traversal for connected
  retrieval.
- W3C PROV: provenance, attribution, derivation, versioning, and
  reproducibility.
- W3C JSON-LD: JSON-compatible linked-data graph representation.

## Product Structure

### Public Surfaces

- Wire: ranked public intelligence front page.
- Story pages: canonical public pages for story-level links.
- Arc pages: multi-day narrative arcs with source-backed timelines.
- Dossiers: entity/topic pages that explain a company, tool, protocol, model,
  category, or recurring concept.
- Briefings: canonical blog-style newsletter posts with consistent formatting
  across the full historical archive and all future issues.
- Issue graph: structured issue -> section -> story -> entity/source/finding
  decomposition of each newsletter.
- Collections: curated public packages such as "best AI agent tools this week"
  or "MCP security brief."
- Media modules: audio players, video-script previews, social-angle trails, and
  source-backed media provenance.

### Dynamic Template Pages

The site should generate public pages from structured graph data:

- `/briefings/<date>`: full canonical newsletter issue.
- `/s/<slug>`: high-confidence AI/editorial public story.
- `/i/<date>/<slug>`: optional issue story unit route if owner approves this
  URL shape; otherwise story units render inside `/briefings/<date>`.
- `/e/<slug>`: entity page generated from mentions, findings, issue stories,
  arcs, sources, and related entities.
- `/source/<domain>`: source page generated from source history and linked
  findings/issues.
- `/f/<id>`: individual finding page with source evidence and related graph
  trails.
- `/arc/<slug>`: narrative arc timeline generated from arc artifacts and
  linked story units.

Dynamic template pages may exist without AI-written prose. AI editorial pages
are an enrichment layer on top of the graph, not a requirement for linkability.

### Private / Ops Surfaces

- Source health, pipeline errors, trace logs, Slack approval state, subscriber
  data, social credentials, and personal memory remain private in v3, Slack, or
  the old dashboard.

## Daily Content Engine

The Rabbit Hole Content Engine runs after the research/newsletter pipeline, or
as an independent daily enrichment job over the same research corpus. It creates
site-native public artifacts.

The content engine has two distinct responsibilities:

1. Structured graph publishing
   - Always make valid structured nodes linkable through templates when source
     data exists: findings, entities, sources, issue sections, newsletter story
     units, and arcs.
   - These pages do not require AI-written editorial prose to exist.

2. Editorial enrichment
   - Write richer public stories, dossiers, collections, and narrative takes
     only when confidence gates pass.
   - High-confidence editorial content can auto-publish. Medium/degraded
     editorial content stays draft/internal.

### Historical Backfill Engine

The old newsletter archive must be normalized by the same structured issue
pipeline used for new issues.

Backfill requirements:

- Parse each historical newsletter into the canonical briefing template.
- Extract issue sections, story units, entities, source refs, finding links,
  arc links, and claim evidence when available.
- Preserve the original newsletter body as the canonical post content.
- Mark unresolved links explicitly instead of inventing entity/source matches.
- Write backfilled artifacts under `reports/<user>/site-issues/` or another
  owner-approved public artifact path that remains out of git.
- Produce an audit ledger listing parsed issues, skipped issues, unresolved
  links, redactions, and confidence/degraded reasons.
- Backfill must be resumable and idempotent.

Backfill must not rewrite old newsletter meaning. It normalizes structure and
adds links; it does not silently change the editorial take.

### Expert Agent Loop

1. Assignment Editor
   - Selects candidate findings, arcs, clusters, and briefing sections that
     deserve public pages.
   - Must not shrink, gate, or rewrite newsletter story selection.

2. Graph Cartographer
   - Builds semantic/entity/arc/source connections.
   - Produces related findings with scores and relationship reasons.

3. Domain Experts
   - Adds builder, technical, market, research, product, policy, and source
     context where relevant.
   - Experts must cite evidence and may return "no useful contribution."

4. Skeptic / Fact Checker
   - Cuts unsupported claims, weak causal language, fake trend framing, and
     source-thin conclusions.

5. Narrative Editor
   - Writes the public take, headline, dek, why-now, and follow-the-thread
     guidance.

6. Source Librarian
   - Verifies source URLs, dates, domains, source names, and claim-to-source
     mapping.

7. GEO / Agent-Web Editor
   - Produces structured metadata, JSON-LD, future OKF/llms output, and
     agent-readable summaries.

8. Media Producer
   - Suggests whether the page should spawn social angles, audio segments, or
     video script packages. Live social posting remains Slack approval-gated.

### Publish Rules

- High confidence: publish automatically to the public site artifact/API.
- Medium confidence: save as draft or internal artifact; do not publish.
- Degraded confidence: save degraded evidence for diagnosis; do not publish as
  a normal public story.
- Failed confidence: skip public artifact and record why.

High confidence requires:

- At least two independent source domains or one primary authoritative source
  plus strong cross-corpus evidence.
- A stable claim-to-source map for the public take.
- No unresolved fact-checker kill switches.
- Non-empty related graph evidence from semantic or entity matching.
- No private data, secrets, raw Slack bodies, subscriber data, or personal
  memory in public output.
- A clear "why now" reason tied to current findings or a recurring arc.

## Data Model

### Graph Principles

- Raw findings, source URLs, and canonical newsletter issues are source-of-truth
  inputs.
- Issue sections, story units, entities, arcs, related refs, and public stories
  are derived artifacts.
- Every public node needs a stable ID, a stable URL slug, a type, confidence,
  provenance, and safe public fields only.
- Relationships must be typed. Avoid generic `related_to` when a more specific
  relationship exists, such as `mentions`, `cites`, `same_arc`,
  `derived_from`, `source_for`, `contrasts_with`, or `updates`.
- Relationship reasons must be explainable to a reader and must point back to
  evidence finding IDs, issue story IDs, source URLs, or arc IDs.
- Backfilled historical issue artifacts and new daily issue artifacts must use
  the same schema.

### Existing Inputs

- `findings`: atomic research discoveries.
- `findings_embeddings`: semantic recall over findings.
- `sources`: source reputation and recurrence.
- `reports`: daily newsletter markdown.
- `narrative arcs`: current Feature 17 artifacts under `reports/<user>/arcs/`.
- `audio`: current Feature 20 artifacts under `reports/<user>/audio/`.
- `video scripts`: current Feature 21 artifacts under
  `reports/<user>/video-scripts/`.

### Shared Public Types

```ts
type SourceRef = {
  url: string
  domain: string
  title?: string
  published_at?: string
  retrieved_at?: string
  source_kind?: 'primary' | 'reporting' | 'community' | 'research' | 'unknown'
}
```

```ts
type EntityRef = {
  id: string
  slug: string
  name: string
  kind: 'company' | 'person' | 'tool' | 'model' | 'concept' | 'protocol' | 'source' | 'unknown'
}
```

```ts
type ClaimEvidence = {
  claim_id: string
  claim: string
  source_refs: SourceRef[]
  finding_ids: number[]
  issue_story_ids: string[]
  confidence: 'high' | 'medium' | 'degraded'
}
```

```ts
type Provenance = {
  generated_by: string
  generated_at: string
  input_artifacts: string[]
  source_finding_ids: number[]
  source_issue_dates: string[]
  model_provider?: string
  model_name?: string
  redaction_status: 'passed' | 'redacted' | 'failed'
  ai_generated: boolean
  human_approved: boolean
}
```

### New Structured Newsletter Artifacts

```ts
type PublicIssue = {
  date: string
  title: string
  slug: string
  sections: IssueSection[]
  entities: EntityRef[]
  story_units: IssueStoryUnit[]
  source_trail: SourceRef[]
  claim_evidence: ClaimEvidence[]
  generated_at: string
  provenance: Provenance
}
```

```ts
type IssueStoryUnit = {
  id: string
  slug: string
  issue_date: string
  section_id: string
  title: string
  summary: string
  body_excerpt: string
  finding_ids: number[]
  entity_ids: string[]
  source_refs: SourceRef[]
  arc_ids: string[]
  claim_evidence: ClaimEvidence[]
  public_story_slug?: string
}
```

```ts
type PublicEntity = {
  id: string
  slug: string
  name: string
  kind: 'company' | 'person' | 'tool' | 'model' | 'concept' | 'protocol' | 'source' | 'unknown'
  mention_count: number
  first_seen: string
  last_seen: string
  finding_ids: number[]
  issue_story_ids: string[]
  source_domains: string[]
  related_entities: RelatedRef[]
  provenance: Provenance
}
```

### New Public Artifacts

```ts
type PublicStory = {
  id: string
  slug: string
  date: string
  title: string
  dek: string
  take: string
  why_now: string
  status: 'published' | 'draft' | 'degraded' | 'failed'
  confidence: 'high' | 'medium' | 'degraded'
  primary_finding_ids: number[]
  source_trail: SourceRef[]
  entities: EntityRef[]
  narrative_arc_ids: string[]
  related: RelatedRef[]
  media: MediaRef[]
  claim_evidence: ClaimEvidence[]
  provenance: Provenance
}
```

```ts
type RelatedRef = {
  target_type: 'finding' | 'story' | 'arc' | 'entity' | 'source'
  target_id: string
  score: number
  relationship: string
  reason: string
  evidence_finding_ids: number[]
}
```

```ts
type PublicArcPage = {
  id: string
  slug: string
  title: string
  summary: string
  status: 'published' | 'draft' | 'degraded'
  first_seen: string
  last_seen: string
  evidence_count: number
  source_domain_count: number
  timeline: ArcTimelineItem[]
  related_stories: string[]
  source_trail: SourceRef[]
  confidence: 'high' | 'medium' | 'degraded'
}
```

## API Requirements

### v3 Public Read APIs

Required first:

- `GET /api/finding/{id}`: single public finding by ID.
- `GET /api/related/{id}?mode=semantic|graph|blended`: real related findings
  with scores and reasons.
- `GET /api/feed`: ranked public Wire feed. Early version can wrap findings;
  final version should return public stories/cluster-takes.
- `GET /api/topics`: topic/entity list with counts.
- `GET /api/issues`: public structured issue index.
- `GET /api/issues/{date}/structured`: structured newsletter issue with
  sections, story units, entities, findings, sources, and arc links.
- `GET /api/entities`: public entity index.
- `GET /api/entities/{slug}`: dynamic entity detail from structured mentions.
- `GET /api/sources/{domain}`: dynamic source detail from source/finding/issue
  references.
- `GET /api/stories`: published public stories.
- `GET /api/stories/{slug}`: public story detail.
- `GET /api/arcs` or continue `/api/narrative-arcs`: public arc summaries.
- `GET /api/arcs/{slug}`: public arc detail.

Public API responses that back indexable pages should include enough typed data
to render JSON-LD, but they should not expose private trace rows, raw Slack
bodies, subscriber records, local database paths, or secrets.

Later:

- `GET /api/dossiers/{entity}`
- `GET /api/collections/{slug}`
- `POST /api/event`: anonymous public analytics event ingest.
- `/llms.txt`
- `/okf/`
- WebMCP tools for agent-facing access.

## Rabbit Hole Frontend Requirements

- The homepage Wire must render public story/cluster-take rows, not only raw
  findings.
- Broken or ungrounded chat surfaces must not be the primary experience. If a
  chat entry point remains, it must be clearly grounded in public graph data or
  hidden until useful.
- The newsletter archive must render from or link to structured issue data, not
  only a single markdown blob.
- Story pages must be canonical landing pages for newsletter/social links.
- Entity pages must be dynamic template pages generated from structured entity
  data; they should work before AI-written dossiers exist.
- Source pages must be dynamic template pages generated from source and finding
  history.
- Rabbit-hole related paths must come from the real API, not same-section
  placeholders.
- Briefing pages must link sections/stories into story and arc pages.
- Narrative arc modules should show "this is part of a larger pattern" with
  evidence and timeline.
- Audio players should render when Feature 20 artifacts exist.
- Video/script packages should appear only as public metadata or embeds when
  explicitly public-safe; Slack remains the first workflow for video packages.
- The site should not expose private dashboard, Slack, trace, subscriber, or
  credential data.

## Code Style

Prefer typed data contracts and small adapters over ad hoc object use.

```ts
export async function getStory(slug: string): Promise<PublicStory | null> {
  try {
    return await backendFetch<PublicStory>(`/api/stories/${slug}`, {
      user: 'ramsay',
    })
  } catch {
    return null
  }
}

export function storyConfidenceLabel(story: PublicStory): string {
  if (story.status !== 'published') return 'Not public'
  return story.confidence === 'high' ? 'Source-backed' : 'Needs review'
}
```

Conventions:

- Use TypeScript interfaces for every public API shape.
- Public UI should say less when confidence is weak.
- Keep generated content as data plus provenance, not only markdown blobs.
- Split newsletter markdown into structured issue/story/entity artifacts before
  relying on it for graph navigation.
- Use source-backed language: "evidence suggests" when confidence is limited;
  direct claims only when source evidence supports them.
- Do not use in-app instructional text to explain the UI.

## Testing Strategy

v3:

- Unit tests for graph/related scoring, story artifact generation, confidence
  gates, redaction, and source validation.
- Unit tests for newsletter markdown splitting into issue sections, story units,
  entities, sources, and finding/arc references.
- Backfill tests proving historical newsletters normalize into the same
  structured issue contracts as new newsletters.
- JSON-LD/provenance tests proving public pages have machine-readable metadata
  without private fields.
- API contract tests for every public endpoint consumed by Rabbit Hole.
- Safety tests proving no private data enters public artifacts.
- Runner tests proving the site content engine does not block newsletter send.

Rabbit Hole:

- TypeScript compile and lint for every site change.
- Unit tests should be added before serious data-model work. The current site
  does not yet have a test runner; adding Vitest/Playwright requires owner
  approval because it adds dependencies.
- Browser smoke before deploy:
  - Wire -> story -> related story.
  - Briefing -> story link -> arc link.
  - Audio page with and without audio artifact.
  - Mobile layout.

## Boundaries

Always:

- Preserve newsletter autonomy.
- Publish high-confidence site content automatically only when confidence gates
  pass.
- Store generated public content as structured artifacts with provenance.
- Validate path/date/user/slug inputs on public APIs.
- Redact secrets, personal data, raw Slack bodies, subscriber data, DB paths,
  and tokens from public outputs.
- Keep generated media/content artifacts out of git unless they are explicit
  fixtures.
- Update specs/runbooks when architecture changes.

Ask first:

- Database schema changes.
- New dependencies.
- Fly deploys.
- Vercel deploys.
- Full daily pipeline runs.
- Live TTS/video provider setup.
- Public indexing of new content classes in sitemap.
- Exposing any private dashboard feature publicly.

Never:

- Make Slack approval required for newsletter research, writing, or sending.
- Auto-post live social content without explicit owner approval in Slack.
- Publish medium/degraded content as if it were high-confidence.
- Use placeholder same-section relatedness as final product behavior.
- Commit secrets, personal data, users files, databases, subscriber data, or
  generated media.
- Let the content engine shrink, gate, replace, or override newsletter story
  selection.

## Success Criteria

MVP success:

- A newsletter can be split into structured issue sections, story units,
  entities, sources, finding links, and arc links.
- A historical newsletter can be backfilled into the same structured issue
  format without changing the canonical post content.
- Every valid finding/entity/source/issue-story node can be linkable through a
  dynamic template route, even when no AI-written editorial story exists.
- A daily Rabbit Hole content job creates high-confidence public story artifacts
  from current research.
- At least one public story page can be generated from real findings with a
  source-backed take, source trail, entities, related findings, and provenance.
- `/api/finding/{id}` and `/api/related/{id}` exist and are consumed by the
  Rabbit Hole story experience.
- Rabbit-hole related links are real semantic/entity/arc connections, not
  same-section placeholders.
- The Wire can render site-native story/cluster rows.
- Briefing pages can link into story or arc pages.
- High-confidence stories publish automatically; medium/degraded candidates do
  not.
- Newsletter send remains independent if the Rabbit Hole content job fails.
- Structured issue/entity/source APIs expose only safe public graph data.
- Rabbit Hole renders dynamic `/e/<slug>` entity pages and `/source/<domain>`
  source pages from structured data.
- Public pages include JSON-LD-ready metadata, source evidence, confidence, and
  provenance.
- Public API tests and Rabbit Hole compile/lint pass.

v1 success:

- Narrative arcs have public pages or modules.
- Dossiers exist for at least one entity/topic type.
- Public collections can be generated from story/arcs.
- Audio and video/script metadata link back to canonical story/arc pages.
- Sitemap/JSON-LD/agent-readable metadata reflect public stories and briefings.
- Analytics/trending can influence ranking without exposing private data.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The graph is too weak at first | Public pages feel fake or repetitive | Require confidence gates and source-backed relationship reasons. |
| Site loop weakens newsletter | User loses the core daily product | Run site loop after newsletter; fail independently. |
| AI writes generic takes | Site feels bland | Use expert loop, skeptic cuts, and source-backed "why now" requirements. |
| Too much dashboard functionality moves public | Privacy/product confusion | Classify every feature as public content, private ops, or Slack workflow. |
| Auto-publish creates bad pages | Trust damage | Publish only high-confidence; draft/skip everything else. |
| Frontend ships before backend contracts | More placeholder UX | Build B1 APIs before replacing core Rabbit Hole UI. |

## Open Questions

1. Should public story artifacts live under `reports/<user>/site-stories/` first,
   or should we introduce a database table after owner-approved schema work?
2. Should the first public URL shape be `/s/<slug>`, `/story/<slug>`, or keep
   `/f/<id>` and layer story content onto it?
3. Should structured issue story units use `/i/<date>/<slug>` or remain nested
   only inside `/briefings/<date>` with links to entities/stories?
4. Which dashboard-style features should become public first: Trend Radar,
   Best Story Archive, Dossiers, Collections, or Knowledge Graph Explorer?
5. Should high-confidence auto-publish also update sitemap immediately, or
   should sitemap inclusion wait one day?
6. Should social/newsletter links point to story pages first, or arc pages when
   the story is clearly part of a larger arc?

# Spec: First-party analytics + trending front page + site search

**Status:** draft for review · **Date:** 2026-07-02
**Repos:** mindpattern-v3 (ingestion, scoring, dash, search API) +
mindpattern-rabbit-hole (event client, wire ranking, arrows, search UI)

## Objective

1. **Own the analytics.** Every event the site already fires (story views,
   related/entity/source/briefing/outbound clicks, scroll depth, subscribe)
   is also captured first-party, privacy-safe, so the product can use it.
2. **Popularity-aware front page.** Wire sections driven by real data:
   Trending (time-decayed blend of on-site reads + corpus signals),
   Most Read (all time), Latest. Stories carry an up/down/flat direction
   indicator (score now vs 24h ago).
3. **Internal dashboard.** A token-gated page in the v3 dashboard answering:
   which stories are popular (today / 7d / all time), what gets clicked,
   where readers come from, subscribe conversion.
4. **Real search.** A keyboard-first search page over stories, findings,
   entities, and sources with filters (type, section, date, source).

Success in one line: the wire reorders itself from real reader behavior,
you can see why on an internal dash, and anyone can find anything in
two keystrokes and a query.

## Tech stack

Existing only: FastAPI + SQLite (new `site_events.db`), numpy/fastembed
(search reuses stored embeddings), Next.js 16 site. No new dependencies.

## Architecture decisions

- **Storage: `/data/site_events.db` on Fly, separate from memory.db.**
  memory.db is overwritten by the daily local→Fly sync; events recorded in
  it would be destroyed every morning. site_events.db lives only on the
  volume, is never bundled, and is backed up by Fly volume snapshots.
- **Privacy contract:** store event type, target slug/path, referrer
  domain (not full URL), coarse timestamp, and optional client-random
  anon_id. Never IP, user agent, geo, or anything derived from them.
- **Ingestion:** `POST /api/event` (public, JSON, 1KB cap, allowlisted
  event types, 202 always — never block the page). The site's existing
  `trackEvent()` double-writes: Vercel Analytics (unchanged) + sendBeacon
  to `/api/proxy/event`.
- **Trending score** (computed in v3, cached 5 min):
  `onsite = Σ event_weight / (age_hours + 2)^1.4` (views 1, related 2,
  outbound 3, scroll-100 2) blended with `corpus = source recurrence of
  the story's domains (7d) + arc activity + log(HN points | stars) when
  present in the primary finding`.
  `score = 0.7 * normalized(onsite) + 0.3 * normalized(corpus)` — the
  corpus term answers "trending on the internet, not just on our site",
  using the research pipeline as the external sensor. Weights are config,
  not code (MP_TRENDING_* env).
- **Direction:** score vs the same score computed over events shifted 24h;
  ±15% band = flat. Exposed per story as `trend: up|down|flat`.
- **Endpoints:** `GET /api/trending?limit=` (ranked stories + trend field),
  `GET /api/popular?window=all|7d` (most read), both public + allowlisted;
  `GET /api/site-analytics/summary` (private, bearer) for the dash.
- **Search:** `GET /api/search/site?q=&types=&section=&from=&to=&domain=`
  → grouped results: stories (title/dek substring + recency boost),
  findings (semantic over stored embeddings), entities (name prefix),
  sources (domain match). One endpoint so the UI stays one round-trip.
- **Search UI:** `/search` page + ⌘K palette on every page; filters as
  chips; keyboard navigation; URL-addressable queries (shareable).
- **Wire integration:** Trending view calls /api/trending; Most Read tab
  added; arrows render via a small TrendIndicator component (none found
  hidden in the repo — will match the Signal aesthetic, mono glyphs
  ▲/▼/–, olive/red/faint).

## Project structure

```
v3: dashboard/routes/events.py        → POST /api/event, GET /api/trending|popular
    dashboard/routes/site_analytics.py→ private summary for the dash
    dashboard/templates/site_analytics.html → internal dash page
    orchestrator/trending.py          → score math (pure) + corpus signals
    memory/events_db.py               → site_events.db schema + writers
    tests/test_events_api.py, test_trending.py, test_search_site.py
site: src/lib/analytics.ts            → double-write via sendBeacon
    src/app/(app)/search/page.tsx     → search UI (+ cmd-k palette)
    src/components/wire/trend-indicator.tsx
    wire page: trending/most-read wired to new endpoints
```

## Testing strategy

pytest: event ingestion (allowlist, size cap, no-PII assertion on stored
rows), trending math (decay, blend, direction bands — pure function
tests), popular windows, search endpoint shapes/filters, dash auth.
FE: build + smoke via local backend. CI: added to the existing test job.

## Boundaries

- Always: events fail open (analytics can never 500 a page); scores
  cached; no PII at rest (test-enforced); search reuses stored embeddings.
- Ask first: any new dependency; storing anything about the reader beyond
  the privacy contract; exposing the dash outside the bearer token.
- Never: events in memory.db; blocking page render on analytics; buying
  an external trending/search service without a decision.

## Success criteria

1. `POST /api/event` stores an allowlisted event; a stored row contains
   no IP/UA (asserted by test reading the raw table).
2. `/api/trending` reorders when events are injected in a test, and its
   corpus term moves a story with zero on-site events (internet-only
   trending works).
3. Wire "Trending" and "Most Read" render from the new endpoints with
   up/down/flat indicators; sections update within the 5-min cache.
4. Internal dash shows per-story views/clicks for today/7d/all-time and
   subscribe conversion, behind auth.
5. `/search` answers a query across all four types in one request,
   filters work, ⌘K opens it from any page.
6. Events survive a daily sync (recorded on Fly before sync, still
   present after — integration-tested via the bundle-extract path).

## Decisions (review 2026-07-02)

1. anon_id: INCLUDED — random first-party, resettable, never identity-tied.
2. Most Read: own wire tab (Trending / Most Read / Latest / Topics).
3. Search results: grouped by type.

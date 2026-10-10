# orchestrator/threads.py

> Lead stories. Opus 5.5 reads every finding of the day and proposes original stories, each built from three to five findings that connect. The strongest take the Top slots ahead of single-finding picks.

## What It Does

A lead story is an angle that several findings support together and none supports alone. The newsletter's point is to retell real facts as stories no single source wrote, so the Top 5 open with these.

`find_threads` sends every finding of the day to the `thread_finder` route (Opus 5.5, high effort, no tools) with the Already Published list and a note per finding ("Also found by", already covered). The answer is checked against `contracts/threads.schema.json` one row at a time, so one bad row costs only itself.

Code then keeps a story only when it holds at least `min_members` findings from at least `min_agents` agents after three rules run, strongest first:

- A finding serves one lead story. A stronger story keeps a finding two stories both claim.
- A finding whose source URL a past issue already used can appear but does not count.
- No more lead stories than `newsletter.top_stories`.

Earlier coverage of a story's findings is attached from embeddings and knowledge-graph entities (`find_candidates`), so the writer can say what today adds.

## Key Functions

- `find_threads(conn, today, policy, notes, covered, published, runner)` returns the checked lead stories.
- `lead_block(leads)` is the writer's Lead stories section with each angle, the findings with links, and earlier coverage.
- `lead_positions(leads)` maps finding ids to their lead story. The runner marks those findings in All Findings so they get no section item.
- `deep_dives(leads)` gives [[orchestrator/deep_dive]] one story per lead, with its angle and every finding.
- `find_candidates(conn, today, policy)` finds today's findings that continue earlier stories. Deterministic.
- `save(...)` writes `reports/<user>/threads/<date>.json`.

## Behavior

In [[orchestrator/runner]], lead stories run before the selector. The selector is asked for the Top slots left and never sees lead-story findings. Five lead stories mean no selector call at all. Fewer than five, or none, and the selector fills the rest as before.

Fails open. A failed or empty answer means no lead stories and an issue picked by the selector alone. Skipped on dry runs.

Lead stories run 600 to 900 words (`newsletter.length.lead_story_words`), single-finding Top stories 300 to 500.

## Depends On

[[core/model_cli]], `core/contracts.py`, [[memory/embeddings]], the `kg_*` tables, `agents/thread-finder.md`, `policies/editorial.json` (`threads` section). Called by [[orchestrator/runner]].

## Last Updated

2026-10-10. Created.

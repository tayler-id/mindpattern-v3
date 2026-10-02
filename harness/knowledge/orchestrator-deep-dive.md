# orchestrator/deep_dive.py

> Evidence for the Top stories before the newsletter is written. One Sonnet 5.5 agent per picked story, three at a time.

## What It Does

After synthesis pass 1 picks the stories, `stories_from_selection` matches each pick to its finding. `run_deep_dives` gives each story an agent (task `story_deep_dive`) with WebSearch, WebFetch, and `mp`.

The agent stores the primary source, corroboration, numbers, a quote, and the strongest counterpoint with `mp evidence add`. `evidence_block` turns the stored items into one evidence pack per story for pass 2.

## Key Functions

Match the picks, run the agents, and turn what they stored into evidence packs.

- `picks(pass1_output)` reads the selector's JSON picks.
- `stories_from_selection(pass1_output, findings, limit)` matches picks to findings by agent and title overlap.
- `run_deep_dives(stories, evidence_dir, env, runner)` writes to `data/<user>/runs/<run_id>/deep-dive/`.
- `evidence_block(stories)` and `summary(stories)`.

## Behavior

Fails open: a story without a pack is written from its finding. Skipped on dry runs. The count comes from `deep_dive_stories` in `policies/editorial.json`.

Sep 30 replay: five deep dives at $0.12 to $0.27 each, 22 evidence items across the four that stored any.

## Depends On

[[core/model_cli]], [[mp/cli]], `agents/story-deep-dive.md`. Called by [[orchestrator/runner]].

## Last Updated

2026-10-02. Created with the models harness.

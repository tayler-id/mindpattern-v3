# orchestrator/runner.py

> Main pipeline state machine. 12 phases in fixed order. Python decides phase sequence, not LLM.

## What It Does

`ResearchPipeline` class orchestrates: INIT -> TREND_SCAN -> RESEARCH -> SYNTHESIS -> DELIVER -> SITE_CONTENT -> LEARN -> SOCIAL -> ENGAGEMENT -> IDENTITY -> MIRROR -> SYNC -> COMPLETED.

Handles resume-from-crash via [[orchestrator/checkpoint]]. Dispatches agents via [[orchestrator/agents]]. Scores output via [[orchestrator/evaluator]].

## Key Functions

One method per phase, plus the run loop and its resume path.

- `ResearchPipeline.__init__(user_id, date_str)` — opens memory.db + traces.db, creates pipeline_run
- `run() -> int` — entry point; checks for resumable run, else starts from INIT
- `_execute_from(start_phase)` — loop through PHASE_ORDER, call handler per phase, save checkpoint
- `_phase_init()` — load prefs, fetch feedback, detect prompt changes via [[orchestrator/prompt_tracker]]
- `_phase_research()` — dispatch 13 parallel agents via [[orchestrator/agents]], store findings in [[data/memory-db]]
- `_phase_synthesis()`: [[orchestrator/threads]] finds the lead stories (Opus 5.5), Pass 1 picks single stories for any Top slot left (Opus 5.5), [[orchestrator/deep_dive]] gathers evidence for each, Pass 2 writes the issue (Opus 5.5), [[orchestrator/newsletter_editor]] edits it, then the prose gate runs
- `_phase_deliver()` — validate + send via [[orchestrator/newsletter]], score via [[orchestrator/evaluator]]
- `_phase_learn()` checks the run's usage against the soft budget, prunes old raw traces ([[core/trace_store]]), checks for regressions, and runs [[orchestrator/analyzer]]
- `_phase_social()` — approval chain via [[social/approval]], posting via [[social/posting]]

## Depends On

[[orchestrator/agents]], [[core/trace_store]], [[orchestrator/threads]], [[orchestrator/deep_dive]], [[orchestrator/newsletter_editor]], [[orchestrator/checkpoint]], [[orchestrator/evaluator]], [[orchestrator/observability]], [[orchestrator/prompt_tracker]], [[orchestrator/traces_db]], [[memory/findings]], [[memory/db]]

## Known Fragile Points

Most phases fail open, so many failures surface only as warnings.

- CRITICAL_PHASES hardcoded to {RESEARCH, SYNTHESIS} — everything else is skippable, failures are silent warnings
- TREND_SCAN failure is silent — research runs without trends, no warning
- Finding dedup uses 0.90 similarity threshold — implementation-dependent on memory.search_findings()
- Preference loading failure is silent — continues with empty list
- Newsletter size not validated before sending — evaluator checks post-hoc but too late to re-synthesize
- max_workers=6 in dispatch_research_agents() is hardcoded
- Story counts come from `policies/editorial.json` ([[policies/files]]); the old env caps are gone
- `run-launchd.sh` skips a slot on battery without a full wake, or when api.anthropic.com does not answer, since Sep 28 and 29 runs crawled for 14 hours in a dark wake
- signal_context failure is silent — cross-pipeline signals skipped with no notification

## Last Modified By Harness

2026-10-02. Run context for tracing, deep dives and the Sol editor in SYNTHESIS, soft budget and trace pruning in LEARN.

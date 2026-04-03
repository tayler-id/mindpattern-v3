# orchestrator/runner.py

> Main pipeline state machine. 12 phases in fixed order. Python decides phase sequence, not LLM.

## What It Does

`ResearchPipeline` class orchestrates: INIT -> TREND_SCAN -> RESEARCH -> SYNTHESIS -> DELIVER -> LEARN -> SOCIAL -> ENGAGEMENT -> EVOLVE -> IDENTITY -> MIRROR -> SYNC -> COMPLETED.

Handles resume-from-crash via [[orchestrator/checkpoint]]. Dispatches agents via [[orchestrator/agents]]. Scores output via [[orchestrator/evaluator]].

## Key Functions

- `ResearchPipeline.__init__(user_id, date_str)` — opens memory.db + traces.db, creates pipeline_run
- `run() -> int` — entry point; checks for resumable run, else starts from INIT
- `_execute_from(start_phase)` — loop through PHASE_ORDER, call handler per phase, save checkpoint
- `_phase_init()` — load prefs, fetch feedback, detect prompt changes via [[orchestrator/prompt_tracker]]
- `_phase_research()` — dispatch 13 parallel agents via [[orchestrator/agents]], store findings in [[data/memory-db]]
- `_phase_synthesis()` — Pass 1: select 5 stories (Opus), Pass 2: write full newsletter
- `_phase_deliver()` — validate + send via [[orchestrator/newsletter]], score via [[orchestrator/evaluator]]
- `_phase_learn()` — check for regressions, run [[orchestrator/analyzer]] for self-optimization
- `_phase_social()` — approval chain via [[social/approval]], posting via [[social/posting]]

## Depends On

[[orchestrator/agents]], [[orchestrator/checkpoint]], [[orchestrator/evaluator]], [[orchestrator/observability]], [[orchestrator/prompt_tracker]], [[orchestrator/traces_db]], [[memory/findings]], [[memory/db]]

## Known Fragile Points

- CRITICAL_PHASES hardcoded to {RESEARCH, SYNTHESIS} — everything else is skippable, failures are silent warnings
- TREND_SCAN failure is silent — research runs without trends, no warning
- Finding dedup uses 0.90 similarity threshold — implementation-dependent on memory.search_findings()
- Preference loading failure is silent — continues with empty list
- Newsletter size not validated before sending — evaluator checks post-hoc but too late to re-synthesize
- max_workers=6 in dispatch_research_agents() is hardcoded
- signal_context failure is silent — cross-pipeline signals skipped with no notification

## Last Modified By Harness

Never — this file was created 2026-04-01 from codebase analysis.

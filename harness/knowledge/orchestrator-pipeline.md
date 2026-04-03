# orchestrator/pipeline.py

> Phase enum, state machine, transition validation. Strict forward-only.

## What It Does

Defines `Phase` enum (14 values), `PHASE_ORDER` list, `CRITICAL_PHASES`, `SKIPPABLE_PHASES`, `VALID_TRANSITIONS`. `PipelineRun` class manages state: transition(), complete_phase(), fail_phase().

## Key Facts

- CRITICAL_PHASES = {RESEARCH, SYNTHESIS} — failure stops pipeline
- SKIPPABLE_PHASES = everything else — failure logged as warning, continues
- Forward-only transitions — can't go back, can jump to FAILED/COMPLETED
- No timeout enforcement at state machine level — relies on caller

## Depends On

Nothing — leaf module. Used by [[orchestrator/runner]].

## Known Fragile Points

- CRITICAL_PHASES hardcoded, not configurable
- Warning accumulation unbounded — many skippable failures = large list
- _phase_start_time tracked but never read (dead code)

## Last Modified By Harness

Never — created 2026-04-01.

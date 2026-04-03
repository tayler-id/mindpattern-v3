# orchestrator/traces_db.py

> traces.db schema (15 tables) and CRUD helpers. WAL mode. Row factory.

## Tables

pipeline_runs, agent_runs, pipeline_phases, phase_tracking, events, checkpoints, alerts, cost_log, agent_metrics, daily_metrics, quality_scores, quality_history, prompt_versions, prompt_tracker, evolution_actions, proof_packages

## Key Functions

- `get_db(db_path)` / `init_db(db_path)` / `open_traces_db(db_path)` — connection management
- `create_pipeline_run()` / `complete_pipeline_run()` / `get_pipeline_run()` — pipeline lifecycle
- `create_agent_run()` / `complete_agent_run()` / `get_agent_run()` — agent lifecycle
- `log_event()` — structured event logging
- `log_evolution_action()` — self-improvement audit trail

## Depends On

Nothing. Core schema used by [[orchestrator/observability]], [[orchestrator/checkpoint]], [[orchestrator/runner]], [[orchestrator/newsletter]].

## Known Fragile Points

- Output truncation silent: MAX_OUTPUT_BYTES = 10,240 — no indicator that truncation occurred
- TRACES_DB_PATH hardcoded to "ramsay" — breaks for other users unless overridden
- No foreign key cascade deletes — orphaned rows accumulate
- UUID collision risk: only 6 hex chars (16M unique values)
- commit=True default — partial operations can commit unexpectedly in transactions

## Last Modified By Harness

Never — created 2026-04-01.

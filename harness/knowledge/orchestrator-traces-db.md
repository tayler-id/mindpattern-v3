# orchestrator/traces_db.py

> traces.db schema (17 tables) and CRUD helpers. WAL mode. Row factory.

## Tables

Seventeen tables, grouped by purpose in [[data/traces-db]].

pipeline_runs, agent_runs, pipeline_phases, phase_tracking, events, checkpoints, alerts, cost_log, agent_metrics, daily_metrics, quality_scores, quality_history, prompt_versions, prompt_tracker, evolution_actions, proof_packages, model_calls, model_call_steps

`model_calls` and `model_call_steps` come from [[core/trace_store]], which creates them itself because the runner opens traces.db without `init_db`.

## Key Functions

Connections, run and agent lifecycles, and event logging.

- `get_db(db_path)` / `init_db(db_path)` / `open_traces_db(db_path)` — connection management
- `create_pipeline_run()` / `complete_pipeline_run()` / `get_pipeline_run()` — pipeline lifecycle
- `create_agent_run()` / `complete_agent_run()` / `get_agent_run()` — agent lifecycle
- `log_event()` — structured event logging
- `log_evolution_action()` — self-improvement audit trail

## Depends On

Nothing. Core schema used by [[orchestrator/observability]], [[orchestrator/checkpoint]], [[orchestrator/runner]], [[orchestrator/newsletter]].

## Known Fragile Points

Silent truncation, a hardcoded user, and weak ids.

- Output truncation silent: MAX_OUTPUT_BYTES = 10,240 — no indicator that truncation occurred
- TRACES_DB_PATH hardcoded to "ramsay" — breaks for other users unless overridden
- No foreign key cascade deletes — orphaned rows accumulate
- UUID collision risk: only 6 hex chars (16M unique values)
- commit=True default — partial operations can commit unexpectedly in transactions

## Last Modified By Harness

2026-10-02. `init_db` also creates the model call tables.

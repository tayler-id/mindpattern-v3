# orchestrator/observability.py

> PipelineMonitor. Phase metrics, agent metrics, cost tracking, quality history.

## Key Class

`PipelineMonitor(traces_conn)` — creates/migrates 4 tables: phase_tracking, agent_metrics, cost_log, quality_history.

## Key Functions

- `start_phase(pipeline_run_id, phase_name)` — returns phase_id
- `end_phase(phase_id, status, tokens_used, cost, error)` — complete phase
- `record_agent_metrics(agent_name, run_date, findings_count, tokens_used, cost, duration_ms, model_used)` — upsert
- `log_cost(run_date, phase, model, input_tokens, output_tokens)` — calculates cost_usd from MODEL_PRICING

## Depends On

[[data/traces-db]]. MODEL_PRICING duplicated from [[orchestrator/router]].

## Known Fragile Points

- Schema migration is destructive — renames old table, copies via pivot, old data lost if INSERT fails
- Column detection catches all exceptions, returns None — hides corruption
- MODEL_PRICING duplicated — two sources of truth

## Last Modified By Harness

Never — created 2026-04-01.

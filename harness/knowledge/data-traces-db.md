# data/traces-db

> traces.db: 17 tables. Execution traces, every model call and tool step, cost, quality, evolution audit trail.

## Tables

### Execution
What ran, in what order, and every model call inside it.

- `pipeline_runs` — id, pipeline_type, status, started_at, completed_at, trigger, error, metadata
- `agent_runs` — id, pipeline_run_id (FK), agent_name, status, input/output tokens, latency_ms, quality_score, output (truncated 10KB)
- `pipeline_phases` — phase_name, status, started_at, completed_at, tokens_used, cost
- `phase_tracking` — mirror of pipeline_phases with index + cost_usd
- `events` — pipeline_run_id, event_type, payload (structured event log)
- `checkpoints` — pipeline_run_id, phase, state_data (crash recovery)
- `model_calls` holds one row per model call and per subagent (`parent_call_id`): run, phase, task, provider, model, outcome, tokens, cost. See [[core/trace_store]]
- `model_call_steps` holds one row per tool call inside a model call

### Cost & Performance
- `cost_log` — run_date, phase, model, input/output tokens, cost_usd
- `agent_metrics` — agent_name, run_date (UNIQUE), findings_count, tokens_used, cost_usd, duration_ms
- `daily_metrics` — date, metric_name, metric_value

### Quality
Per-agent and per-run quality scores, plus alerts.

- `quality_scores` — agent_run_id (FK), dimension, score, notes
- `quality_history` — run_date (UNIQUE), overall_score, coverage, dedup, sources, actionability, length_score, topic_balance
- `alerts` — run_date, alert_type, message, severity, acknowledged

### Prompt & Evolution
Prompt versions, rollbacks, and the self-improvement audit trail.

- `prompt_versions` — agent_name, git_hash (UNIQUE), file_path
- `prompt_tracker` — file_path, content_hash, git_hash, quality_snapshot, rolled_back
- `evolution_actions` — action_type, agents_affected, reasoning, date, metadata
- `proof_packages` — topic, quality_score, creative_brief, post_text, sources, post_results

## Connected To

Written by [[orchestrator/observability]], [[orchestrator/checkpoint]], [[orchestrator/runner]], [[orchestrator/newsletter]]. Schema defined in [[orchestrator/traces_db]].

## Last Modified By Harness

2026-10-02. Model call tables added.

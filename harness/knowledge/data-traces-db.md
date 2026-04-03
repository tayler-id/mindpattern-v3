# data/traces-db

> traces.db: 15 tables. Execution traces, cost, quality, evolution audit trail.

## Tables

### Execution
- `pipeline_runs` — id, pipeline_type, status, started_at, completed_at, trigger, error, metadata
- `agent_runs` — id, pipeline_run_id (FK), agent_name, status, input/output tokens, latency_ms, quality_score, output (truncated 10KB)
- `pipeline_phases` — phase_name, status, started_at, completed_at, tokens_used, cost
- `phase_tracking` — mirror of pipeline_phases with index + cost_usd
- `events` — pipeline_run_id, event_type, payload (structured event log)
- `checkpoints` — pipeline_run_id, phase, state_data (crash recovery)

### Cost & Performance
- `cost_log` — run_date, phase, model, input/output tokens, cost_usd
- `agent_metrics` — agent_name, run_date (UNIQUE), findings_count, tokens_used, cost_usd, duration_ms
- `daily_metrics` — date, metric_name, metric_value

### Quality
- `quality_scores` — agent_run_id (FK), dimension, score, notes
- `quality_history` — run_date (UNIQUE), overall_score, coverage, dedup, sources, actionability, length_score, topic_balance
- `alerts` — run_date, alert_type, message, severity, acknowledged

### Prompt & Evolution
- `prompt_versions` — agent_name, git_hash (UNIQUE), file_path
- `prompt_tracker` — file_path, content_hash, git_hash, quality_snapshot, rolled_back
- `evolution_actions` — action_type, agents_affected, reasoning, date, metadata
- `proof_packages` — topic, quality_score, creative_brief, post_text, sources, post_results

## Connected To

Written by [[orchestrator/observability]], [[orchestrator/checkpoint]], [[orchestrator/runner]], [[orchestrator/newsletter]]. Schema defined in [[orchestrator/traces_db]].

## Last Modified By Harness

Never — created 2026-04-01.

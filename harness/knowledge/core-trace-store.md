# core/trace_store.py

> Files every model call under its run. One row per call and per subagent in traces.db, one row per tool step, and the raw stream gzipped on disk.

## Storage

Two tables and two files per call.

- `model_calls`: run, phase, task, unit, provider, model, outcome, tokens, cost, turns, duration. A subagent is a child row linked by `parent_call_id`.
- `model_call_steps`: each tool call with its input summary, result size, and whether it failed.
- `data/<user>/traces/<date>/<run_id>/<call_id>.events.jsonl.gz` and `.prompt.md.gz`. Gitignored. Never synced to Fly.

`MP_TRACE_ROOT` moves all of it, and `tests/conftest.py` points it at a temp folder for every test.

## Key Functions

- `set_run_context(run_id=, run_date=, phase=, user_id=)` sets what later calls are filed under. [[orchestrator/runner]] sets it per run and per phase. A call outside a run is filed as `adhoc`.
- `record_call(request, route, result, raw_stdout)` writes the rows and the raw files.
- `prune_raw_traces(keep_days)` deletes day folders past the retention window.
- `run_totals(run_id)` and `over_budget(totals, policy)` feed the soft budget check in LEARN.

## Trace CLI

`python -m orchestrator.trace` reads it: `runs`, `show <run> --steps`, `call <id> --full` (the whole conversation, subagents included), `grep <run> <text>`, `usage --since N --by task,model`, `prune --keep-days N`.

## Policy

`policies/observability.json` keeps raw traces 90 days and sets a soft budget per run of 3M output tokens or $120 at API prices. Going over sends a Slack alert and never blocks a run. See [[policies/files]].

## Depends On

Nothing internal. Used by [[core/model_cli]], [[orchestrator/runner]], [[orchestrator/traces_db]].

## Last Updated

2026-10-02. Created with the models harness.

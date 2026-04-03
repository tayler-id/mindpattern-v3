# orchestrator/prompt_tracker.py

> Prompt change detection, quality regression check, auto-rollback.

## What It Does

SHA256 hashes skill files, compares against traces.db prompt_tracker table. If quality drops >15% after a prompt change, auto-rollbacks via git checkout or .bak restore.

## Key Functions

- `PromptTracker(traces_conn)` — init
- `scan_for_changes()` — compare current hashes vs stored, returns changed files
- `record_version(file_path, git_hash, quality_snapshot)` — store version
- `check_regression(run_date, threshold=0.15)` — flag >15% quality drops
- `auto_rollback(file_path, old_hash)` — git checkout or .bak restore

## Scans Directories

verticals/, agents/, verticals/ai-tech/agents/

## Depends On

[[data/traces-db]] prompt_tracker table, quality_history/run_quality tables. Used by [[orchestrator/runner]] (INIT + LEARN phases) and [[orchestrator/analyzer]].

## Known Fragile Points

- Regression baseline detection fragile — falls back to traces tables that may have stale data
- 15% threshold hardcoded, not configurable
- Git checkout rollback fails if file untracked or detached HEAD
- Hash mismatch after rollback still marked as success (with warning)
- PROMPT_DIRS hardcoded — no check directories exist

## Last Modified By Harness

Never — created 2026-04-01.

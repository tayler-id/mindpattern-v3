# orchestrator/checkpoint.py

## Purpose
Pipeline resume-on-failure mechanism. Saves completed phases to SQLite so crashed runs can restart from the last checkpoint.

## API
- `Checkpoint(conn)` — pass a `sqlite3.Connection` (traces.db or `:memory:` for tests)
- `save(run_id, phase, state_data=None, user_id=None)` — upsert checkpoint for a phase
- `load(run_id)` → `(Phase|None, dict|None)` — get latest checkpoint by `created_at`
- `get_completed_phases(run_id)` → `list[Phase]` — all phases in chronological order
- `resume_from(run_id)` → `Phase|None` — next phase after last completed, or None if done
- `find_resumable_run(user_id, run_date)` → `str|None` — find incomplete run for user+date
- `clear(run_id)` — delete all checkpoints for a run

## Schema
Table `checkpoints` with columns: id, pipeline_run_id, phase, state_data (JSON), user_id, created_at.
Unique constraint on (pipeline_run_id, phase). Indexes on pipeline_run_id and user_id.

## Known Issues
- `load()` orders by `created_at` which has second-level precision via SQLite `datetime('now')`. Multiple saves within the same second have non-deterministic ordering.
- Migration ordering: ALTER TABLE ADD COLUMN must come AFTER CREATE TABLE IF NOT EXISTS but the code already handles this correctly (CREATE TABLE includes user_id, ALTER is a no-op migration for old DBs).

## Test Coverage
- `tests/test_checkpoint.py` — 17 tests covering save, load, resume_from, find_resumable_run, clear, get_completed_phases

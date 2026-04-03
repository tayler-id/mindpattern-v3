# orchestrator/checkpoint.py

> Crash recovery. Saves phase completion to traces.db, resumes from last completed phase.

## Key Functions

- `Checkpoint(traces_conn)` — init checkpoints table
- `save(pipeline_run_id, phase, state_data, user_id)` — upsert checkpoint
- `load(pipeline_run_id)` — fetch last checkpoint
- `resume_from(pipeline_run_id)` — determine next phase
- `find_resumable_run(user_id, run_date)` — search for incomplete runs
- `clear(pipeline_run_id)` — delete checkpoints for run

## Depends On

[[orchestrator/pipeline]] (Phase enum). Stores in [[data/traces-db]] checkpoints table.

## Migration Pattern

`_ensure_table()` handles both fresh DBs and existing ones:
1. `CREATE TABLE IF NOT EXISTS` — includes all columns for fresh DBs
2. `ALTER TABLE ADD COLUMN` — adds missing columns for existing DBs
3. `CREATE INDEX IF NOT EXISTS` — must come AFTER alter table

**Critical:** Index creation on new columns must always come after the ALTER TABLE migration. Tests use in-memory SQLite (always fresh tables) so they cannot catch migration ordering bugs.

## Known Fragile Points

- Resume pattern uses LIKE `%-{run_date}-%` — fragile if ID format changes
- No cleanup of old checkpoints — accumulates forever
- state_data has no schema validation
- Migration ordering: indexes on new columns must be created after ALTER TABLE (bug found 2026-04-02)

## Last Modified

2026-04-02 — fixed migration ordering (user_id index before ALTER TABLE).

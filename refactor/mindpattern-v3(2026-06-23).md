# MindPattern v3 Refactor Progress - 2026-06-23

Branch: `refactor/mindpattern-v3-2026-06-23`

## Step 1 - Trace DB path boundary and sync-test repair

### Changes

- Added `orchestrator.traces_db.resolve_traces_db_path()` so traces DB path selection is centralized and can be resolved for an explicit user/data directory without baking `data/ramsay/traces.db` into helper call sites.
- Kept the existing default behavior as `data/ramsay/traces.db`.
- Updated `get_db()`, `init_db()`, and `open_traces_db()` to use the resolver.
- Fixed `capture_prompt_versions()` default Git working directory to the project root instead of `data/ramsay`.
- Added trace DB tests for non-default user path resolution and project-root prompt capture.
- Included the existing sync hardening in `orchestrator/sync.py`: fallback database uploads now verify remote byte size, retry once, fail loudly if Fly receives a truncated DB, and fail closed when the SFTP command itself fails.
- Added `write_synced_marker()` for confirmed sync-complete markers.
- Repaired sync tests to model the existing upload byte-size verification contract instead of returning empty `wc -c` output.
- Added direct tests for verified fallback SFTP retries and sync-marker writing.

### Verification

- `.venv/bin/python3 -m pytest tests/test_traces_db.py -q` - 8 passed.
- `.venv/bin/python3 -m pytest tests/test_traces_db.py tests/test_orchestrator.py -q` - 122 passed.
- `.venv/bin/python3 -m compileall -q orchestrator/traces_db.py` - passed.
- Runtime smoke: resolved `data/smoke/traces.db` for `user_id="smoke"` and confirmed `PROJECT_ROOT.name == "mindpattern-v3"`.
- `.venv/bin/python3 -m pytest tests/test_sync.py::TestSyncToFly::test_full_sync_success -q` - 1 passed.
- `.venv/bin/python3 -m pytest tests/test_sync.py -q` - 40 passed.
- `.venv/bin/python3 -m pytest tests/ -x -q` - 1086 passed, 1 FastAPI/Starlette deprecation warning.

### Auto Review

- `git diff --check -- orchestrator/sync.py orchestrator/traces_db.py tests/test_sync.py tests/test_traces_db.py 'refactor/mindpattern-v3(2026-06-23).md'` - passed.
- Five-axis review:
  - Correctness: explicit tests cover default-preserving path resolution, prompt capture cwd, and sync byte-size mock behavior.
  - Readability: resolver is small and call sites stay direct.
  - Architecture: path ownership moves behind one helper; prompt capture no longer depends on a user data path.
  - Security: no secrets or outbound operations added.
  - Performance: no new loops or I/O beyond existing DB path creation.

### Notes

- `graphify update .` could not run because `graphify` is not installed in this shell.
- The worktree had many unrelated pre-existing dirty files before this step; this commit should stage only the files listed above plus this progress log.

## Step 2 - Worktree preservation guardrails

### Changes

- Created a tracked-change recovery patch at `/private/tmp/mindpattern-v3-tracked-dirty-2026-06-23.patch` before cleanup work.
- Restored `.gitignore` protections for `*.db`, `*.db.*`, and `users.json`.
- Added ignore coverage for local-only state that should not enter commits: `.mlx-venv/`, `.understand-anything/`, and Claude backup files.

### Verification

- `git check-ignore -v users.json .mlx-venv .understand-anything .claude/settings.json.bak-pre-graphify` - confirmed all four are ignored.

### Auto Review

- `git diff --check -- .gitignore 'refactor/mindpattern-v3(2026-06-23).md'` - passed.
- Five-axis review:
  - Correctness: ignore rules now match the project convention that databases and PII config must not be committed.
  - Readability: rules stay in the existing `.gitignore` sections instead of adding a second footer block.
  - Architecture: cleanup separates local tool/runtime state from source-controlled project artifacts.
  - Security: `users.json` and SQLite files are protected from accidental staging.
  - Performance: no runtime behavior changed.

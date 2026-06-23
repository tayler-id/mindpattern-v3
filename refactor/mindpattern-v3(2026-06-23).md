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

## Step 3 - Research agent reliability and tool boundary

### Changes

- Added failure classification for research-agent CLI calls: `overloaded`, `rate_limit`, `server_error`, `timeout`, `parse_error`, `other`, and `success`.
- Retried transient Anthropic CLI failures with full-jitter exponential backoff while keeping calls on the `claude` CLI subscription path.
- Switched per-agent execution to process-group-aware `Popen` so timeouts kill the whole subprocess tree.
- Recorded the final classification on `AgentResult` so overloaded/rate-limit failures are no longer collapsed to "Non-zero exit code".
- Tightened research-agent allowed tools and explicitly denied `Skill`, `Bash`, `Agent`, `Write`, and `Edit`.
- Updated the research prompt to remove shell CLI and subagent instructions; Phase 2 now names only the allowed direct tools.
- Added policy `banned_entities` checks for research findings and social posts.
- Captured the source-tool install commands and the `xreach` vs current `twitter` CLI mismatch in `docs/spec-research-reliability.md`.

### Verification

- `.venv/bin/python3 -m pytest tests/test_agents.py::TestBuildAgentPromptToolBoundary -q` - 1 passed.
- `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_agent_defang.py tests/test_policies.py -q` - 66 passed.
- `.venv/bin/python3 -m pytest tests/ -x -q` - 1087 passed, 1 FastAPI/Starlette deprecation warning.
- `graphify update .` - failed because `graphify` is not installed in this shell.

### Auto Review

- `git diff --check -- orchestrator/agents.py tests/test_agents.py policies/engine.py policies/research.json policies/social.json tests/test_policies.py docs/spec-research-reliability.md 'refactor/mindpattern-v3(2026-06-23).md'` - passed.
- Five-axis review:
  - Correctness: retry behavior, no-retry paths, jitter bounds, prompt/tool boundary, and banned-entity policies are covered by tests.
  - Readability: retry classification is separated from subprocess execution; prompt instructions are now consistent with runtime tool permissions.
  - Architecture: dangerous tool access is denied in both command construction and prompt guidance, reducing prompt-injection blast radius for research agents.
  - Security: shell/subagent tools remain unavailable to research agents that process scraped external content; Synchrony bans gate both research and social output.
  - Performance: retry backoff only applies to transient failures and keeps normal 13-agent concurrency unchanged.

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

## Step 4 - Fly runtime and social posting hardening

### Changes

- Added environment-variable fallback for Slack and social secrets on non-macOS hosts while preserving macOS Keychain lookup locally.
- Guarded Slack harness commands when the bot is running in the Fly container that does not include `harness/`.
- Increased Slack approval wait time to 15 minutes and filtered Jina `SecurityCompromiseError` JSON bodies out of article reads.
- Updated Fly VM sizing and documented that the Fly machine runs both dashboard HTTP and Slack Socket Mode.
- Added LinkedIn API version normalization and version fallback for `/rest/` calls.
- Fixed the dirty LinkedIn fallback bug so a retired old configured version migrates forward to a recent supported default instead of retrying an even older retired version.
- Added a LinkedIn 3000-character commentary guard so posting fails closed instead of truncating.

### Verification

- `.venv/bin/python3 -m pytest tests/test_social.py::TestLinkedInClient::test_post_migrates_old_nonexistent_version_to_recent_default tests/test_social.py::TestLinkedInClient::test_post_steps_back_when_recent_default_is_rejected -q` - 2 passed after the fix.
- `.venv/bin/python3 -m pytest tests/test_social.py tests/test_slack_bot.py -q` - 52 passed.
- `.venv/bin/python3 -m pytest tests/ -x -q` - 1092 passed, 1 FastAPI/Starlette deprecation warning.
- `graphify update .` - ran after the Graphify reinstall; the committed graph artifacts will be refreshed in the next slice so their freshness marker points at this Step 4 commit.

### Auto Review

- `git diff --check -- CLAUDE.md fly.toml slack_bot/handlers/base.py slack_bot/handlers/harness.py slack_bot/registry.py social/posting.py tests/test_slack_bot.py tests/test_social.py 'refactor/mindpattern-v3(2026-06-23).md'` - passed.
- Five-axis review:
  - Correctness: tests cover env-var secret fallback, Fly harness absence, Jina security-compromise filtering, LinkedIn length limits, and LinkedIn version fallback from retired configured versions.
  - Readability: platform-specific secret lookup and LinkedIn retry behavior stay in small helpers instead of spreading conditionals across call sites.
  - Architecture: local macOS Keychain behavior remains the default while Fly/container runtime gets explicit environment-backed secrets and harness gating.
  - Security: the runtime fails closed for unavailable credentials, unsafe Jina bodies, and oversized LinkedIn commentary; no secret values are logged.
  - Performance: Slack command guards are constant-time checks, and LinkedIn version fallback is bounded by the existing retry loop.

## Step 5 - Graphify restoration and clean graph artifacts

### Changes

- Reinstalled Graphify as `graphifyy==0.8.46` through `uv tool install graphifyy`; `graphify` and `graphify-mcp` are now available from `~/.local/bin`.
- Moved the stale pre-clean `graphify-out/` aside intact to `/private/tmp/mindpattern-v3-graphify-out-preclean-2026-06-23` before regenerating artifacts; preserved the intermediate pre-`refactor/`-ignore graph at `/private/tmp/mindpattern-v3-graphify-out-pre-refactor-ignore-2026-06-23`.
- Added `.graphifyignore` so Graphify indexes project code/docs while excluding databases, personal data, `.claude/`, `.obsidian/`, generated reports, refactor progress logs, and transient `knowledge/state/` files.
- Added Graphify-local ignore rules for `.graphify_python`, cache, cost telemetry, generated HTML, and dated backup directories.
- Added a merge attribute for `graphify-out/graph.json`.
- Regenerated portable Graphify artifacts in `graphify-out/`: `graph.json`, `manifest.json`, `.graphify_labels.json`, `.graphify_root`, and `GRAPH_REPORT.md`.

### Verification

- `uv tool list` - confirmed `graphifyy v0.8.46` with `graphify` and `graphify-mcp`.
- `graphify update .` - rebuilt the graph from 387 files with 6242 nodes and 9395 edges, with freshness metadata against commit `1ae8fb8f`.
- `graphify explain "LinkedInClient"` - resolved `social/posting.py` `LinkedInClient` with 54 connections.
- `graphify path "Slack Approval Gateway" "LinkedInClient"` - found `gateway() -> ApprovalGateway <- pipeline.py -> LinkedInClient`.
- `graphify diagnose multigraph --json` - reported 6242 nodes, 9395 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.
- `rg -n "settings\\.local|\\\"source_file\\\": \\\"\\.claude/|knowledge/state|refactor/mindpattern" graphify-out/graph.json graphify-out/manifest.json graphify-out/GRAPH_REPORT.md graphify-out/.graphify_labels.json` - no matches.
- `git check-ignore -v graphify-out/.graphify_python graphify-out/cache/stat-index.json graphify-out/cost.json graphify-out/2026-06-23/graph.json` - confirmed local Graphify state/backups are ignored.

### Auto Review

- `git diff --check -- .gitignore .graphifyignore .gitattributes graphify-out 'refactor/mindpattern-v3(2026-06-23).md'` - passed.
- `rg -n "/Users/taylerramsay|/private/tmp|API_KEY|TOKEN|SECRET|PASSWORD|settings\\.local" graphify-out/graph.json graphify-out/manifest.json graphify-out/GRAPH_REPORT.md graphify-out/.graphify_labels.json` - no matches.
- Five-axis review:
  - Correctness: Graphify CLI resolves project symbols, paths between architecture nodes, and reports a structurally valid graph with no dangling endpoints or duplicate edges.
  - Readability: `.graphifyignore` separates repo knowledge from generated, personal, and local agent state; `.gitignore` keeps Graphify runtime debris out of status.
  - Architecture: the repo now has portable Graphify configuration plus committed graph artifacts for agents to inspect without depending on the local tool cache.
  - Security: personal data, local Claude state, DB files, env files, and cost/cache metadata are excluded from ingestion or commit.
  - Performance: the committed artifact set is about 5.6 MB, and Graphify intentionally skips `graph.html` for this 6000+ node graph unless the visualization limit is raised.

## Step 6 - Next-agent handoff

### Changes

- Added `.claude/handoffs/2026-06-23-mindpattern-v3-refactor-runtime-graphify.md` as the current handoff for the next agent.
- Captured the current branch, recent commits, verification status, Graphify state, dirty worktree classification, and safe next steps.
- Included the user's upgrade note by recording the observed current tool state: `uv tool list` still reports `graphifyy v0.8.46`.

### Verification

- `uv tool list` - confirmed current Graphify tool install state.
- `git status --short --untracked-files=normal` - reviewed remaining dirty files to document them accurately.
- `git diff --check -- .claude/handoffs/2026-06-23-mindpattern-v3-refactor-runtime-graphify.md 'refactor/mindpattern-v3(2026-06-23).md'` - passed.

### Auto Review

- `git diff --check -- .claude/handoffs/2026-06-23-mindpattern-v3-refactor-runtime-graphify.md 'refactor/mindpattern-v3(2026-06-23).md'` - passed.
- Secret scan found no credential values; the only scanner-term hit was the already-committed Step 5 command text that names patterns such as `TOKEN`.
- Five-axis review:
  - Correctness: handoff reflects the current branch, commit stack, Graphify state, verification history, and dirty worktree categories.
  - Readability: the next agent gets current facts first, then dirty-state triage and safe next steps.
  - Architecture: handoff points agents back to the progress log and committed Graphify report instead of stale May cleanup context.
  - Security: sensitive/user-generated directories are called out as do-not-stage-broadly; absolute repo and `/private/tmp` paths are intentional recovery context.
  - Performance: documentation-only change; no runtime impact.

## Step 7 - FastEmbed cache boundary hardening

### Changes

- Centralized fastembed model construction in `memory.embeddings.create_text_embedding()`.
- Added `FASTEMBED_CACHE_DIR` support with a persistent default at `~/.cache/mindpattern/fastembed` so macOS temp-dir cleanup does not break the RESEARCH embedding phase.
- Reused the shared `memory.embeddings` serializer and embedder from `dashboard/routes/api.py` instead of keeping a duplicate dashboard-local fastembed singleton.
- Updated the Docker build pre-download step to use the same `FASTEMBED_CACHE_DIR` path as runtime.
- Tightened the fastembed dependency floor to `fastembed>=0.7.3,<1.0`, the oldest locally verified version with `TextEmbedding(..., cache_dir=...)`.
- Added tests for cache-dir resolution and model construction without loading a real fastembed model.
- Verified current source-tool install state: `graphify` is installed, but `agent-reach`, `xreach`, `twitter`, `yt-dlp`, `mcporter`, and `exa-mcp-server` are still missing from PATH.

### Verification

- `.venv/bin/python3 -m pytest tests/test_embeddings.py -q` - 17 passed.
- `.venv/bin/python3 -m pytest tests/test_dashboard_findings.py tests/test_api_contract.py -q` - 17 passed, 1 FastAPI/Starlette deprecation warning.
- `.venv/bin/python3 -m pytest tests/test_embeddings.py tests/test_dashboard_findings.py tests/test_api_contract.py -q` - 34 passed after sharing the dashboard embedding path.
- `.venv/bin/python3 -m pytest tests/ -x -q` - 1094 passed, 1 FastAPI/Starlette deprecation warning.
- `.venv/bin/python3 -m pytest tests/test_embeddings.py tests/test_dashboard_findings.py tests/test_api_contract.py -q` - 34 passed after tightening the fastembed dependency floor.
- `.venv/bin/python3 -m compileall -q memory/embeddings.py dashboard/routes/api.py` - passed.
- `graphify update .` - refreshed graph artifacts to 6246 nodes and 9407 edges from 387 files; rerun after the requirements edit reported no topology changes.
- `graphify explain create_text_embedding` - resolved `memory/embeddings.py` with links to `_get_model()` and the cache tests.
- `graphify path api.py create_text_embedding` - found `api.py -> embeddings.py -> create_text_embedding()`.
- `graphify diagnose multigraph --json` - reported 6246 nodes, 9407 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.

### Auto Review

- `git diff --check -- Dockerfile dashboard/routes/api.py memory/embeddings.py tests/test_embeddings.py requirements.txt graphify-out 'refactor/mindpattern-v3(2026-06-23).md'` - passed before staging.
- Five-axis review:
  - Correctness: cache-dir behavior is tested with an environment override, and dashboard semantic search now uses the same embedding code path as memory storage.
  - Readability: fastembed construction lives behind one named factory instead of being duplicated in dashboard routes.
  - Architecture: source collection remains separate from semantic retrieval; missing X/Exa/YouTube tools still need installation before ingestion comes back.
  - Security: cache paths are local filesystem locations only; no personal data or generated `data/` files are included in this slice.
  - Performance: the model still lazy-loads once per process, and Docker pre-download uses the same persistent cache to avoid runtime cold fetches.

## Step 8 - Source tool restore and Twitter CLI fallback

### Changes

- Installed Agent Reach with `uv tool install "https://github.com/Panniantong/agent-reach/archive/main.zip"`; current installed version is `agent-reach v1.5.0`.
- Ran `agent-reach install --env=auto` and `agent-reach install --env=auto --channels=twitter`.
- Installed direct command tools needed by preflight:
  - `yt-dlp v2026.6.9`
  - `twitter-cli v0.8.5` exposing `twitter`
  - `mcporter v0.12.0`
- Confirmed legacy `xreach` cannot be installed from the package registry; `uv tool install xreach` reports the package is unavailable.
- Added a `preflight/twitter.py` command selector that prefers legacy `xreach` when present but falls back to current `twitter search -n ... --json`.
- Normalized both supported Twitter JSON shapes:
  - legacy `xreach`: `{"items": [...]}`
  - current `twitter-cli`: a top-level list of tweet objects with nested `metrics`
- Added tests for both Twitter/X CLI backends.

### Verification

- `.venv/bin/python3 -m pytest tests/test_preflight.py -q` - 27 passed.
- `.venv/bin/python3 -m compileall -q preflight/twitter.py tests/test_preflight.py` - passed.
- `git diff --check -- preflight/twitter.py tests/test_preflight.py` - passed.
- `agent-reach doctor` - reports 7/13 active channels; YouTube, RSS, Exa semantic search, web reader, V2EX, Twitter/X, and Bilibili basic are available; GitHub CLI is installed but not authenticated.
- `mcporter list exa --status` - reports Exa healthy with 2 tools.
- `mcporter call exa.web_search_exa query="AI agents" numResults=1` - returned a live Exa result.
- `yt-dlp --dump-json --flat-playlist --playlist-items 1:1 https://www.youtube.com/@Fireship/videos` - returned one live YouTube item.
- `preflight.exa.fetch(queries=["AI agents"], num_results=1)` - returned 1 item.
- `preflight.youtube.fetch(..., max_per_channel=1)` - returned 1 item.
- `twitter status` - authenticated successfully, and `twitter user-posts ... -n 1 --json` works.
- `twitter search "AI agents" -n 1 --json` - still fails upstream with HTTP 404, so query-based X search is installed but not healthy yet.
- `preflight.twitter.fetch(queries=["AI agents"], count=1)` - reaches `twitter-cli` but returns 0 because `twitter search` fails upstream.
- `graphify update .` - rebuilt graph artifacts to 6254 nodes and 9420 edges from 387 files.
- `graphify explain _search_command` - resolved `preflight/twitter.py`.
- `graphify path twitter.py _search_command` - found `twitter.py -> _search_command()`.
- `graphify diagnose multigraph --json` - reported 6254 nodes, 9420 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.

### Auto Review

- Five-axis review:
  - Correctness: unit tests cover both legacy and current CLI output formats; live Exa and YouTube preflight paths work end to end.
  - Readability: command selection and JSON normalization are isolated in named helpers instead of branching inside the fetch loop.
  - Architecture: the app no longer hard-depends on dead `xreach`, but the Twitter source remains query-search based and still depends on upstream `twitter-cli search` health.
  - Security: tool installs were outside the repo; no cookies, tokens, or personal data were committed. Twitter authentication is local machine state.
  - Performance: fallback command selection is a small PATH check; source fetch time remains dominated by external CLI/network calls.

## Step 9 - Real pipeline smoke and Learn-phase guard

### Changes

- Ran a real full pipeline smoke for `ramsay` on `2026-06-23` after restoring source tools.
- Confirmed newsletter delivery was not failing:
  - The earlier run sent the owner newsletter through Resend at `2026-06-23T11:31:12` and logged `Newsletter sent`.
  - The subscriber broadcast sent 1 message at `2026-06-23T11:31:13`.
  - The later full smoke skipped duplicate owner and subscriber sends because the `newsletter:2026-06-23` and broadcast receipts were already claimed.
- Fixed the Learn phase so a failed `learnings_update` Claude call cannot overwrite `data/<user>/learnings.md` with an error string such as `Error: Reached max turns (5)`.
- Added a regression test that preserves an existing learnings file when the updater exits nonzero.

### Real Pipeline Smoke Result

- Command: `.venv/bin/python3 run.py --user ramsay --date 2026-06-23`
- Exit: `0`
- Duration: `1211s`
- Final summary: `141 findings | 58 min | Quality: 0.86`
- Sync: `35609772 bytes uploaded`; Fly app restarted.
- Trend scan: 188 preflight items, 8 trends detected.
- Research: 13/13 agents succeeded, 181 raw findings, 82 stored after dedup.
- Synthesis: wrote `reports/ramsay/2026-06-23.md`, 6450 words; newsletter eval `overall=0.865`, `coverage=0.95`, `dedup=1.0`, `sources=0.846`.
- Deliver: report validated at 45281 bytes; duplicate-send receipts prevented resending today's newsletter during the smoke run.
- Learn: stored 20 entity relationships and backfilled 9 trend results; the old code then wrote failed updater output, which this step now guards against.
- Social/engagement: skipped because no social platforms are enabled in `social-config.json`.
- Identity: appended to decisions, but rejected an oversized `soul` update over the 3000-character guardrail.

### Remaining Gaps

- X/Twitter keyword search remains partially broken upstream: `twitter status` and `twitter user-posts` work, but `twitter search ... --json` returns HTTP 404, so thought-leader/topic X search still underperforms.
- Some research agents still came in below the 15-20 finding target on the full smoke run, especially thought-leaders, reddit, sources, agents, news, and GitHub pulse.
- Closed in Step 10: `_phase_sync` succeeded and restarted Fly but did not call the existing `orchestrator.sync.write_synced_marker()` helper; only the delivery ran-marker was written.
- Closed in Step 11: `learnings_update` needed prompt/runtime tuning because it hit max turns in both real runs today. The Step 9 guard prevented new corrupt writes, but did not repair existing corrupt learnings or guarantee a useful fallback.

### Verification

- RED reproduction: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn::test_learnings_update_failure_does_not_overwrite_existing_file -q` failed before the code guard because the file was overwritten with `Error: Reached max turns (5)`.
- GREEN regression: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn::test_learnings_update_failure_does_not_overwrite_existing_file -q` - 1 passed.
- Learn group: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn -q` - 4 passed.
- Full suite: `.venv/bin/python3 -m pytest -q` - 1097 passed, 1 FastAPI/Starlette deprecation warning.
- `graphify update .` - rebuilt graph artifacts to 6255 nodes and 9424 edges from 387 files; `graph.html` skipped because the graph exceeds the 5000-node viz limit.
- `graphify explain _phase_learn` - resolved `orchestrator/runner.py` line 984 with `ResearchPipeline`, `backfill_trend_results()`, and `log_event()` connections.
- `graphify diagnose multigraph --json` - reported 6255 nodes, 9424 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.

### Auto Review

- Five-axis review:
  - Correctness: the full live pipeline completed through sync with exit 0; the discovered Learn corruption path is now covered by a regression test.
  - Readability: the Learn updater write condition now makes the success criteria explicit: clean exit, non-empty output, and no error-prefix output.
  - Architecture: receipts are confirmed as the duplicate-send boundary for newsletters; source ingestion remains split from embeddings/semantic retrieval.
  - Security: no generated reports, personal `data/`, or recipient data are staged in this slice; delivery evidence is summarized from logs.
  - Performance: the guard adds only a string/exit-code check; Graphify and tests were refreshed after the code change.

## Step 10 - Sync marker and launchd retry boundary

### Changes

- Wired `_phase_sync()` to call `orchestrator.sync.write_synced_marker(self.date_str)` only after:
  - `sync_to_fly(...)` succeeds, and
  - `restart_app("mindpattern")` succeeds.
- Kept restart failure as a warning and deliberately did not write the sync marker on that path, so the morning backup window can retry instead of treating a stale dashboard as complete.
- Updated `run-launchd.sh` so it skips only when both markers exist:
  - `mindpattern-ran-<date>` for confirmed delivery
  - `mindpattern-synced-<date>` for confirmed Fly sync/restart
- Added a launchd wrapper guardrail test to catch regressions where delivered-but-not-synced days would be skipped.
- Added runner sync tests for marker write/no-write behavior across success, restart-failure, and sync-failure paths.

### Verification

- RED reproduction: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSync tests/test_launchd_wrapper.py -q` failed before implementation because `_phase_sync()` did not call `write_synced_marker()` and `run-launchd.sh` had no `SYNC_MARKER`.
- Focused tests: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSync tests/test_launchd_wrapper.py -q` - 4 passed.
- Shell syntax: `bash -n run-launchd.sh` - passed.
- Sync suite: `.venv/bin/python3 -m pytest tests/test_sync.py tests/test_runner.py::TestPhaseSync tests/test_launchd_wrapper.py -q` - 44 passed.
- Full suite: `.venv/bin/python3 -m pytest -q` - 1099 passed, 1 FastAPI/Starlette deprecation warning.
- Live marker smoke: `MP_RAN_MARKER_DIR=/private/tmp/mindpattern-sync-marker-smoke-2026-06-23 .venv/bin/python3 -c 'from orchestrator.sync import write_synced_marker; write_synced_marker("2026-06-23")'` wrote `/private/tmp/mindpattern-sync-marker-smoke-2026-06-23/mindpattern-synced-2026-06-23`.
- `graphify update .` - rebuilt graph artifacts to 6260 nodes and 9428 edges from 388 files; `graph.html` skipped because the graph exceeds the 5000-node viz limit.
- `graphify explain write_synced_marker` - resolved `orchestrator/sync.py` and now shows an incoming call from `_phase_sync()`.
- `graphify path _phase_sync write_synced_marker` - found `_phase_sync() --calls--> write_synced_marker()`.
- `graphify diagnose multigraph --json` - reported 6260 nodes, 9428 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.

### Auto Review

- Five-axis review:
  - Correctness: delivery and sync completion are now separate scheduler facts; duplicate-send receipts still make retrying a delivered-but-unsynced day safe.
  - Readability: marker names in the wrapper now distinguish delivery from sync instead of overloading `MARKER`.
  - Architecture: the existing sync marker helper is now connected to both the orchestrator and launchd guard, closing the stale-dashboard retry hole.
  - Security: no recipient data, reports, local settings, or personal data are staged; marker files contain no content.
  - Performance: the wrapper adds two filesystem checks, and `_phase_sync()` adds one marker write only after successful sync/restart.

## Step 11 - Learnings fallback and baseline repair

### Changes

- Added a deterministic `_build_learnings_fallback()` path for `learnings.md`.
- `_phase_learn()` now:
  - writes normal LLM output on clean success,
  - preserves a valid existing `learnings.md` if the LLM updater fails,
  - repairs missing or corrupt `learnings.md` files with deterministic run facts if the updater fails.
- Tightened `agents/learnings-updater.md` so the LLM uses only prompt-provided run data and stays under 500 words.
- Repaired the tracked `data/ramsay/learnings.md` baseline, which had contained only `Error: Reached max turns (5)` since the initial commit.

### Verification

- RED reproduction: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn::test_learnings_update_failure_repairs_corrupt_error_file -q` failed before implementation because the corrupt `Error:` file remained unchanged.
- Learn group: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn -q` - 5 passed.
- Runner suite: `.venv/bin/python3 -m pytest tests/test_runner.py -q` - 57 passed.
- Compile check: `.venv/bin/python3 -m compileall -q orchestrator/runner.py` - passed.
- Full suite: `.venv/bin/python3 -m pytest -q` - 1100 passed, 1 FastAPI/Starlette deprecation warning.
- `graphify update .` - rebuilt graph artifacts to 6263 nodes and 9433 edges from 388 files; `graph.html` skipped because the graph exceeds the 5000-node viz limit.
- `graphify explain _build_learnings_fallback` - resolved `orchestrator/runner.py` line 1115.
- `graphify path _phase_learn _build_learnings_fallback` - found `_phase_learn() --calls--> _build_learnings_fallback()`.
- `graphify diagnose multigraph --json` - reported 6263 nodes, 9433 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.

### Auto Review

- Five-axis review:
  - Correctness: updater failure can no longer leave agents reading raw CLI error text; tests cover both valid-file preservation and corrupt-file repair.
  - Readability: fallback output is a simple markdown summary with explicit latest-run and operating-note sections.
  - Architecture: Learn phase keeps the LLM summarizer as the preferred path but has a deterministic resilience path for runtime failures.
  - Security: the repaired baseline contains generic operating notes only, no recipient details or private source output.
  - Performance: fallback construction is in-process string formatting and only runs when the LLM updater fails or returns unusable output.

## Step 12 - Identity evolution length guard

### Changes

- Fixed the Identity phase gap found in the real smoke run where the LLM produced a `soul` section update over the 3000-character vault guardrail.
- Kept `apply_evolution_diff()` strict by default: direct oversized content is still rejected unless the caller explicitly opts into truncation.
- Added an identity-runtime opt-in path: `_phase_identity()` now calls `apply_evolution_diff(..., truncate_oversized=True)`, so overlong LLM content is sanitized, deterministically trimmed, warned about, and still applied when otherwise valid.
- Tightened the identity prompt with a 2600-character target budget, a 3000-character hard cap, and guidance to rewrite long identity sections as compact rolling summaries instead of appending unbounded history.
- Added regression coverage for both prompt budget text and runtime truncation, plus a runner assertion that the identity phase passes the opt-in flag.

### Verification

- RED reproduction: `.venv/bin/python3 -m pytest tests/test_identity_evolve.py -q` failed before implementation because the prompt lacked the 2600-character budget and `apply_evolution_diff()` did not accept `truncate_oversized`.
- Focused identity suite: `.venv/bin/python3 -m pytest tests/test_identity_evolve.py -q` - 31 passed.
- Runner identity suite: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseIdentity -q` - 2 passed.
- Compile check: `python3 -m compileall memory/identity_evolve.py orchestrator/runner.py` - passed.
- Full suite: `.venv/bin/python3 -m pytest -q` - 1102 passed, 1 FastAPI/Starlette deprecation warning.
- `graphify update .` - rebuilt graph artifacts to 6269 nodes and 9443 edges from 388 files; `graph.html` skipped because the graph exceeds the 5000-node viz limit.
- `graphify explain _fit_content_to_limit` - resolved `memory/identity_evolve.py` line 64 with an incoming call from `apply_evolution_diff()`.
- `graphify path _phase_identity _fit_content_to_limit` - found `_phase_identity() --calls--> apply_evolution_diff() --calls--> _fit_content_to_limit()`.
- `graphify diagnose multigraph --json` - reported 6269 nodes, 9443 edges, and zero missing endpoints, dangling endpoints, self-loops, or duplicate edges.

### Auto Review

- Five-axis review:
  - Correctness: the vault safety boundary remains fail-closed by default, while the runtime LLM path now repairs the specific overlong-output failure seen in the real run.
  - Readability: the new helper returns `(content, error, warning)`, keeping apply-time control flow explicit instead of hiding truncation in the vault writer.
  - Architecture: prompt constraints, diff validation, and runtime resilience now share one limit constant and one applier path.
  - Security: LLM content is still sanitized before length handling, and truncation is opt-in only; no personal vault data or social drafts are staged in this slice.
  - Performance: truncation is bounded string work on at most one content field per diff key and only runs when the LLM exceeds the cap.

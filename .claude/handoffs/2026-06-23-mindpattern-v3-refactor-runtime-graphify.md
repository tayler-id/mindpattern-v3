# Handoff: MindPattern v3 refactor, runtime hardening, and Graphify restoration

## Session Metadata

- Created: 2026-06-23
- Project: `/Users/taylerramsay/Projects/mindpattern-v3`
- Branch: `refactor/mindpattern-v3-2026-06-23`
- Code/graph state: session knowledge hook slice staged on top of `3271ce3 refactor: add knowledge graph schema`; run `git log --oneline -19` for the exact latest commit hash after it lands.
- Progress log: `refactor/mindpattern-v3(2026-06-23).md`
- User constraints: do not lose dirty changes; commit needed slices only; do not merge broken code; run live checks and auto review after significant steps.

## Current State Summary

This refactor branch now has nineteen save-point commits through the session knowledge hook slice once the current staged slice lands:

1. `db8a740 refactor: tighten data path and sync boundaries`
2. `2658c35 chore: restore worktree guardrails`
3. `6fd31a8 refactor: harden research agent dispatch`
4. `1ae8fb8 refactor: harden runtime social dispatch`
5. `2416fb4 chore: restore graphify artifacts`
6. `edef515 docs: add refactor handoff`
7. `333685e refactor: harden embedding cache boundary`
8. `1761aea refactor: restore preflight source tool fallback`
9. `36dbd4b fix: guard learnings updater failures`
10. `ca284bb fix: mark completed fly syncs`
11. `5506511 fix: add learnings fallback`
12. `4031fd6 fix: constrain identity evolution output`
13. `1048ebf fix: make dry-run skip claude and deploy`
14. `1ba1eaa refactor: kill claude prompt process groups`
15. `3c96abb refactor: share claude cli process runner`
16. `ee16f82 refactor: route all claude dispatch through runner`
17. `7058abe refactor: centralize claude command building`
18. `3271ce3 refactor: add knowledge graph schema`
19. latest `refactor: add session knowledge hooks`

This handoff was updated again after adding the interactive session knowledge hooks. Use `git log --oneline -19` for the exact latest commit hashes.

The main completed work is:

- Centralized trace DB path resolution and repaired sync/prompt-capture tests.
- Restored `.gitignore` guardrails for databases, `users.json`, local tool state, and Graphify-local runtime files.
- Hardened research-agent subprocess dispatch, retry classification, prompt/tool boundaries, and banned-entity policy checks.
- Hardened Fly/Slack/social runtime behavior, including environment secret fallback, Fly harness gating, Jina security-compromise filtering, LinkedIn version fallback, and LinkedIn 3000-character fail-closed guard.
- Restored Graphify as a working repo tool and committed portable graph artifacts.
- Centralized FastEmbed model construction and cache-dir handling so memory storage and dashboard semantic search share one persistent embedding path.
- Installed Agent Reach, direct `yt-dlp`, `mcporter`, and `twitter-cli`; patched `preflight/twitter.py` so it no longer hard-depends on unavailable legacy `xreach`.
- Smoke-tested the real research-to-sync pipeline for `ramsay` on `2026-06-23`; it completed with exit 0, wrote the newsletter report, skipped duplicate sends via receipts, uploaded sync data, and restarted Fly.
- Guarded `learnings.md` regeneration so a failed `learnings_update` Claude call cannot overwrite the file with CLI error text.
- Connected the sync marker boundary: `_phase_sync()` writes `mindpattern-synced-<date>` only after successful upload and Fly restart, and `run-launchd.sh` skips only when both delivery and sync markers exist.
- Added a deterministic Learn fallback: valid existing `learnings.md` is preserved on updater failure, while missing/corrupt files are repaired with a safe markdown summary. The tracked `data/ramsay/learnings.md` baseline no longer contains raw updater error text.
- Added an Identity phase length guard: `apply_evolution_diff()` remains strict by default, while `_phase_identity()` opts into deterministic truncation for oversized LLM content before writing vault files.
- Fixed the dry-run contract: `run.py --dry-run` now sets `MP_DRY_RUN=1`, Claude dispatch helpers return deterministic placeholders without subprocesses, and runner dry phases skip delivery, sync, mirror, identity, learn, social, research, and trend work.
- Hardened the Claude prompt subprocess boundary: `run_claude_prompt()` now uses `Popen(..., start_new_session=True)` and shares `_kill_process_group()` with research/file-agent dispatch so prompt timeouts cannot leave orphaned Claude child processes.
- Added `core.claude_cli` as the shared low-level Claude process primitive. `core.llm.run()` and `run_claude_prompt()` now delegate to `run_claude_process()`, while research/file-agent paths reuse the shared `kill_process_group()` helper and can migrate to the full helper in later slices.
- Finished the Claude dispatch migration: `run_single_agent()`, `_run_agent_attempt()`, `run_agent_with_files()`, `run_claude_prompt()`, and `core.llm.run()` now all execute Claude through `core.claude_cli.run_claude_process()`.
- Centralized Claude command construction in `_build_claude_command()` and named tool-policy constants so research, file-writing, and prompt dispatch share one CLI command shape while keeping distinct allowed/disallowed tool policies.
- Added `kg.schema` as the typed, bi-temporal KG schema foundation in `memory.db`, with idempotent `kg_*` tables, constrained vocabularies, and pure-SQLite regression tests.
- Added interactive session knowledge hooks and `.claude/settings.json` registration: session start injects compiled knowledge, session end/pre-compact spawn non-blocking flush work, and session capture writes tested conversation summaries.

## Verification Already Run

- Full suite after runtime/social changes: `.venv/bin/python3 -m pytest tests/ -x -q` -> `1092 passed, 1 FastAPI/Starlette warning`.
- Full suite after FastEmbed cache changes: `.venv/bin/python3 -m pytest tests/ -x -q` -> `1094 passed, 1 FastAPI/Starlette warning`.
- Targeted Slack/social suite: `.venv/bin/python3 -m pytest tests/test_social.py tests/test_slack_bot.py -q` -> `52 passed`.
- Targeted embedding/dashboard contract suite after the requirements floor change: `.venv/bin/python3 -m pytest tests/test_embeddings.py tests/test_dashboard_findings.py tests/test_api_contract.py -q` -> `34 passed, 1 FastAPI/Starlette warning`.
- Preflight source-tool suite after Twitter fallback: `.venv/bin/python3 -m pytest tests/test_preflight.py -q` -> `27 passed`.
- Learn-phase guard regression: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn::test_learnings_update_failure_does_not_overwrite_existing_file -q` -> first failed on the old overwrite behavior, then passed after the guard.
- Learn-phase group after guard: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn -q` -> `4 passed`.
- Full suite after Learn-phase guard: `.venv/bin/python3 -m pytest -q` -> `1097 passed, 1 FastAPI/Starlette warning`.
- Sync marker focused tests: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSync tests/test_launchd_wrapper.py -q` -> first failed on the old missing marker/wrapper behavior, then `4 passed`.
- Sync marker broad tests: `.venv/bin/python3 -m pytest tests/test_sync.py tests/test_runner.py::TestPhaseSync tests/test_launchd_wrapper.py -q` -> `44 passed`.
- Shell syntax: `bash -n run-launchd.sh` -> passed.
- Full suite after sync marker update: `.venv/bin/python3 -m pytest -q` -> `1099 passed, 1 FastAPI/Starlette warning`.
- Live marker smoke: `write_synced_marker("2026-06-23")` wrote `/private/tmp/mindpattern-sync-marker-smoke-2026-06-23/mindpattern-synced-2026-06-23`.
- Learn fallback RED regression: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn::test_learnings_update_failure_repairs_corrupt_error_file -q` -> failed before fallback because the corrupt `Error:` file remained unchanged.
- Learn fallback group: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseLearn -q` -> `5 passed`.
- Runner suite after fallback: `.venv/bin/python3 -m pytest tests/test_runner.py -q` -> `57 passed`.
- Compile after fallback: `.venv/bin/python3 -m compileall -q orchestrator/runner.py` -> passed.
- Full suite after fallback: `.venv/bin/python3 -m pytest -q` -> `1100 passed, 1 FastAPI/Starlette warning`.
- Identity length guard RED regression: `.venv/bin/python3 -m pytest tests/test_identity_evolve.py -q` -> failed before implementation because the prompt lacked the 2600-character budget and `apply_evolution_diff()` did not accept `truncate_oversized`.
- Identity length guard focused suite: `.venv/bin/python3 -m pytest tests/test_identity_evolve.py -q` -> `31 passed`.
- Runner identity suite after length guard: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseIdentity -q` -> `2 passed`.
- Compile after length guard: `python3 -m compileall memory/identity_evolve.py orchestrator/runner.py` -> passed.
- Full suite after length guard: `.venv/bin/python3 -m pytest -q` -> `1102 passed, 1 FastAPI/Starlette warning`.
- Dry-run RED regression: `.venv/bin/python3 -m pytest tests/test_agent_defang.py::TestDryRunKillSwitch tests/test_agents.py::TestDryRunClaudeDispatch tests/test_runner.py::TestDryRunPhases -q` -> failed before implementation because `MP_DRY_RUN` was not set, Claude subprocess helpers still ran, and dry-run sync could still reach Fly restart.
- Dry-run focused group: `.venv/bin/python3 -m pytest tests/test_agent_defang.py::TestDryRunKillSwitch tests/test_agents.py::TestDryRunClaudeDispatch tests/test_runner.py::TestDryRunPhases -q` -> `8 passed`.
- Dry-run expanded suites: `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_runner.py tests/test_agent_defang.py -q` -> `98 passed`.
- Compile after dry-run contract: `python3 -m compileall run.py orchestrator/agents.py orchestrator/runner.py` -> passed.
- Live dry-run CLI smoke: `.venv/bin/python3 run.py --dry-run --user ramsay --date 2099-01-01` -> exit `0`; all phases logged `DRY RUN`, deliver/sync were skipped, and only ignored `reports/ramsay/2099-01-01-dry-run.md` was written.
- Full suite after dry-run contract: `.venv/bin/python3 -m pytest -q` -> `1108 passed, 1 FastAPI/Starlette warning`.
- Claude prompt process-group RED regression: `.venv/bin/python3 -m pytest tests/test_agents.py::TestRunClaudePromptFailure::test_run_claude_prompt_timeout_kills_process_group -q` -> failed before implementation because `run_claude_prompt()` had no process group to kill.
- Claude prompt focused group: `.venv/bin/python3 -m pytest tests/test_agents.py::TestRunClaudePromptSuccess tests/test_agents.py::TestRunClaudePromptLargePromptUsesStdin tests/test_agents.py::TestRunClaudePromptFailure tests/test_agents.py::TestDryRunClaudeDispatch -q` -> `7 passed`.
- Feedback processing suite after prompt-boundary test update: `.venv/bin/python3 -m pytest tests/test_feedback_processing.py -q` -> `9 passed`.
- Broad affected suites after prompt-boundary update: `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_feedback_processing.py tests/test_orchestrator.py -q` -> `155 passed`.
- Compile after prompt-boundary update: `python3 -m compileall orchestrator/agents.py tests/test_agents.py tests/test_feedback_processing.py` -> passed.
- Local live prompt smoke: `run_claude_prompt()` exercised a temporary fake `claude` executable in `/tmp` through the real `Popen` path for both normal prompt mode and large-prompt stdin mode.
- Full suite after prompt-boundary update: `.venv/bin/python3 -m pytest -q` -> `1109 passed, 1 FastAPI/Starlette warning`.
- Shared Claude process primitive RED regression: `.venv/bin/python3 -m pytest tests/test_claude_cli.py -q` -> failed before implementation with `ModuleNotFoundError: No module named 'core.claude_cli'`.
- Shared boundary suite: `.venv/bin/python3 -m pytest tests/test_claude_cli.py -q` -> `4 passed`.
- Core LLM + shared boundary suite: `.venv/bin/python3 -m pytest tests/test_claude_cli.py tests/test_core_llm.py -q` -> `18 passed`.
- Focused prompt migration group: `.venv/bin/python3 -m pytest tests/test_claude_cli.py tests/test_core_llm.py tests/test_agents.py::TestRunClaudePromptSuccess tests/test_agents.py::TestRunClaudePromptLargePromptUsesStdin tests/test_agents.py::TestRunClaudePromptFailure tests/test_agents.py::TestDryRunClaudeDispatch -q` -> `25 passed`.
- Broad affected suites after shared primitive update: `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_core_llm.py tests/test_claude_cli.py tests/test_feedback_processing.py tests/test_orchestrator.py -q` -> `173 passed`.
- Compile after shared primitive update: `python3 -m compileall core/claude_cli.py core/llm.py orchestrator/agents.py tests/test_claude_cli.py tests/test_core_llm.py tests/test_agents.py` -> passed.
- Local live-safe shared-boundary smoke: `core.llm.run()` and `run_claude_prompt()` exercised a temporary fake `claude` executable in `/tmp`; normal prompt mode and large-prompt stdin mode passed through the shared helper without a real Claude/network call.
- Full suite after shared primitive update: `.venv/bin/python3 -m pytest -q` -> `1113 passed, 1 FastAPI/Starlette warning`.
- Full dispatch migration RED regression: `.venv/bin/python3 -m pytest tests/test_agents.py::TestRunSingleAgentSharedProcessRunner::test_run_single_agent_uses_shared_process_runner -q` -> failed before implementation because `run_single_agent()` still tried to execute `claude` directly.
- File-agent shared-runner RED regression: `.venv/bin/python3 -m pytest tests/test_orchestrator.py::TestRunAgentWithFiles::test_uses_shared_process_runner -q` -> failed before implementation because `run_agent_with_files()` still tried to execute `claude` directly.
- Affected dispatch group after full migration: `.venv/bin/python3 -m pytest tests/test_agents.py::TestRunSingleAgentSuccess tests/test_agents.py::TestRunSingleAgentSharedProcessRunner tests/test_agents.py::TestRunSingleAgentTimeout tests/test_agents.py::TestRunSingleAgentInvalidJson tests/test_agents.py::TestRunSingleAgentRetry tests/test_orchestrator.py::TestRunAgentWithFiles -q` -> `15 passed`.
- Broader affected suites after full migration: `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_orchestrator.py tests/test_core_llm.py tests/test_claude_cli.py -q` -> `166 passed`.
- Compile after full migration: `python3 -m compileall orchestrator/agents.py tests/test_agents.py tests/test_orchestrator.py` -> passed.
- Local live-safe full-dispatch smoke: `run_single_agent()`, `run_agent_with_files()`, and `run_claude_prompt()` exercised a temporary fake `claude` executable in `/tmp`; all three paths used the shared runner without a real Claude/network call.
- Full suite after full migration: `.venv/bin/python3 -m pytest -q` -> `1115 passed, 1 FastAPI/Starlette warning`.
- Shared command-builder RED regressions:
  - `.venv/bin/python3 -m pytest tests/test_agents.py::TestBuildClaudeCommand -q` failed before implementation because `_build_claude_command` did not exist.
  - `.venv/bin/python3 -m pytest tests/test_agent_defang.py::TestResearchAgentTools::test_dispatch_cmd_denies_dangerous_tools -q` failed before implementation for the same missing import.
- Shared command-builder tests: `.venv/bin/python3 -m pytest tests/test_agents.py::TestBuildClaudeCommand -q` -> `2 passed`.
- Defang command-policy test after command builder: `.venv/bin/python3 -m pytest tests/test_agent_defang.py::TestResearchAgentTools::test_dispatch_cmd_denies_dangerous_tools -q` -> `1 passed`.
- Command-shape caller group: `.venv/bin/python3 -m pytest tests/test_agents.py::TestRunSingleAgentSuccess tests/test_agents.py::TestRunClaudePromptSuccess tests/test_agents.py::TestRunClaudePromptLargePromptUsesStdin tests/test_orchestrator.py::TestRunAgentWithFiles::test_builds_correct_claude_command -q` -> `4 passed`.
- Compile after command builder: `python3 -m compileall orchestrator/agents.py tests/test_agents.py tests/test_agent_defang.py tests/test_orchestrator.py` -> passed.
- Broad affected suites before the identity-test repair: `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_agent_defang.py tests/test_orchestrator.py tests/test_core_llm.py tests/test_claude_cli.py -q` -> `176 passed`.
- First full suite after the command-builder code failed only in `tests/test_identity.py::test_skill_tool_blocked_in_run_single_agent`, because that test inspected source text instead of the built command. It was updated to assert `_build_claude_command()` output.
- Identity policy repair: `.venv/bin/python3 -m pytest tests/test_identity.py::test_skill_tool_blocked_in_run_single_agent -q` -> `1 passed`.
- Broad affected suites after the identity-test repair: `.venv/bin/python3 -m pytest tests/test_agents.py tests/test_agent_defang.py tests/test_identity.py tests/test_orchestrator.py tests/test_core_llm.py tests/test_claude_cli.py -q` -> `179 passed`.
- Compile after identity-test repair: `python3 -m compileall orchestrator/agents.py tests/test_agents.py tests/test_agent_defang.py tests/test_identity.py tests/test_orchestrator.py` -> passed.
- Local live-safe command-builder smoke: `run_single_agent()`, `run_agent_with_files()`, and `run_claude_prompt()` exercised a temporary fake `claude` executable in `/tmp`; output was `shared command builder smoke passed`.
- Full suite after command builder: `.venv/bin/python3 -m pytest -q` -> `1117 passed, 1 FastAPI/Starlette warning`.
- KG schema tests: `.venv/bin/python3 -m pytest tests/test_kg_schema.py -q` -> `8 passed`.
- Compile after KG schema: `python3 -m compileall kg/schema.py tests/test_kg_schema.py` -> passed.
- KG staged hygiene: `git diff --check -- kg/__init__.py kg/schema.py tests/test_kg_schema.py` -> passed.
- Graphify update attempts for KG: `graphify update .` and `graphify update . --force` both reported no topology changes because the graph artifacts already contained the KG topology.
- `graphify explain init_kg_schema` resolves `kg/schema.py` line 131 with incoming calls from `open_kg()`, `test_idempotent()`, and the schema test fixture.
- `graphify path open_kg init_kg_schema` finds `open_kg() --calls--> init_kg_schema()`.
- Session hook settings validation: `python3 -m json.tool .claude/settings.json` -> passed.
- Session hook suites: `.venv/bin/python3 -m pytest tests/test_session_capture.py tests/test_session_hook.py -q` -> `50 passed`.
- Compile after session hooks: `python3 -m compileall hooks/session_capture.py hooks/session_end.py hooks/session_start.py hooks/pre_compact.py tests/test_session_capture.py` -> passed.
- Session hook staged hygiene: `git diff --check -- .claude/settings.json hooks/__init__.py hooks/session_capture.py hooks/session_end.py hooks/session_start.py hooks/pre_compact.py tests/test_session_capture.py` -> passed.
- `graphify explain session_start.py` resolves `hooks/session_start.py` with `main()` contained.
- `graphify explain session_end.py` resolves `hooks/session_end.py` with `main()`, `_check_dedup()`, `_write_dedup()`, and `_extract_context()`.
- `graphify explain pre_compact.py` resolves `hooks/pre_compact.py` with the same dedup/context helpers.
- `graphify explain _update_sessions_index` resolves `hooks/session_capture.py` line 389 with an incoming call from `main()`.
- Real full pipeline smoke: `.venv/bin/python3 run.py --user ramsay --date 2026-06-23` -> exit `0`, `1211s`, `141 findings | 58 min | Quality: 0.86`, `35609772 bytes uploaded`, Fly restarted.
- Newsletter delivery evidence:
  - Earlier run at `2026-06-23T11:31:12` sent the owner newsletter via Resend and wrote the ran-marker.
  - Subscriber broadcast at `2026-06-23T11:31:13` sent 1 message.
  - Later full smoke at `2026-06-23T14:26:18` skipped owner/subscriber sends because receipts were already claimed, so duplicate-send protection worked.
- Live source-tool checks:
  - `agent-reach doctor` -> `7/13` active channels.
  - `mcporter list exa --status` -> Exa healthy with 2 tools.
  - `mcporter call exa.web_search_exa query="AI agents" numResults=1` -> returned a live result.
  - `yt-dlp --dump-json --flat-playlist --playlist-items 1:1 https://www.youtube.com/@Fireship/videos` -> returned one live item.
  - `preflight.exa.fetch(...)` and `preflight.youtube.fetch(...)` each returned 1 live item.
  - `twitter status` authenticates and `twitter user-posts ... -n 1 --json` works.
  - `twitter search "AI agents" -n 1 --json` still fails upstream with HTTP 404; query-based X search is installed but not healthy yet.
- Graphify:
  - `uv tool list` showed `graphifyy v0.8.46` with `graphify` and `graphify-mcp`.
  - `graphify update .` rebuilt clean artifacts from 390 files; current report shows 6320 nodes and 9624 edges.
  - `graphify explain "LinkedInClient"` resolves `social/posting.py` with 54 connections.
  - `graphify path "Slack Approval Gateway" "LinkedInClient"` finds `gateway() -> ApprovalGateway <- pipeline.py -> LinkedInClient`.
  - `graphify explain create_text_embedding` resolves `memory/embeddings.py` with links to `_get_model()` and cache tests.
  - `graphify path api.py create_text_embedding` finds `api.py -> embeddings.py -> create_text_embedding()`.
  - `graphify explain _search_command` resolves `preflight/twitter.py`.
  - `graphify path twitter.py _search_command` finds `twitter.py -> _search_command()`.
  - `graphify explain _phase_learn` resolves `orchestrator/runner.py` line 984.
  - `graphify explain write_synced_marker` resolves `orchestrator/sync.py` and shows `_phase_sync()` as an incoming caller.
  - `graphify path _phase_sync write_synced_marker` finds `_phase_sync() --calls--> write_synced_marker()`.
  - `graphify explain _build_learnings_fallback` resolves `orchestrator/runner.py` line 1115.
  - `graphify path _phase_learn _build_learnings_fallback` finds `_phase_learn() --calls--> _build_learnings_fallback()`.
  - `graphify explain _fit_content_to_limit` resolves `memory/identity_evolve.py` line 64 with an incoming call from `apply_evolution_diff()`.
  - `graphify path _phase_identity _fit_content_to_limit` finds `_phase_identity() --calls--> apply_evolution_diff() --calls--> _fit_content_to_limit()`.
  - `graphify explain _dry_run_enabled` resolves `orchestrator/agents.py` line 31 with incoming calls from `run_claude_prompt()`, `run_single_agent()`, and `run_agent_with_files()`.
  - `graphify explain _phase_synthesis_dry_run` resolves `orchestrator/runner.py` line 254.
  - `graphify path _get_phase_handler _phase_synthesis_dry_run` finds `_get_phase_handler() <--method-- ResearchPipeline --method--> _phase_synthesis_dry_run()`.
  - `graphify explain _kill_process_group` resolves `orchestrator/agents.py` line 78 with incoming calls from all three Claude dispatch paths.
  - `graphify path run_claude_prompt _kill_process_group` finds `run_claude_prompt() --calls--> _kill_process_group()`.
  - `graphify explain run_claude_process` resolves `core/claude_cli.py` line 36 with incoming calls from `core.llm.run()` and `run_claude_prompt()`.
  - `graphify path run_claude_prompt run_claude_process` finds `run_claude_prompt() --calls--> run_claude_process()`.
  - `graphify path run run_claude_process` finds `run() --calls--> run_claude_process()`; Graphify noted the `run` source name is ambiguous, but selected the core LLM helper.
  - `graphify explain run_claude_process` now also shows incoming calls from `run_agent_with_files()` and `_run_agent_attempt()`.
  - `graphify path run_single_agent run_claude_process` finds `run_single_agent() --calls--> _run_agent_attempt() --calls--> run_claude_process()`.
  - `graphify path run_agent_with_files run_claude_process` finds `run_agent_with_files() --calls--> run_claude_process()`.
  - `graphify explain _build_claude_command` resolves `orchestrator/agents.py` line 111 and shows incoming calls from `run_single_agent()`, `run_agent_with_files()`, `run_claude_prompt()`, and related tests.
  - `graphify path run_single_agent _build_claude_command` finds a direct one-hop path.
  - `graphify path run_agent_with_files _build_claude_command` finds a direct one-hop path.
  - `graphify path run_claude_prompt _build_claude_command` finds a direct one-hop path.
  - `graphify explain init_kg_schema` resolves `kg/schema.py` line 131 with incoming calls from `open_kg()` and the schema tests.
  - `graphify path open_kg init_kg_schema` finds `open_kg() --calls--> init_kg_schema()`.
  - `graphify explain session_start.py`, `graphify explain session_end.py`, `graphify explain pre_compact.py`, and `graphify explain _update_sessions_index` all resolve the session hook entry points/helpers.
  - `graphify diagnose multigraph --json` reports 6320 nodes, 9624 edges, and zero duplicate/missing/dangling/self-loop edges.
  - `graphify check-update .` exited cleanly with no output.

## Graphify Notes

- Graphify was reinstalled through `uv tool install graphifyy`.
- Current observed install state includes `graphifyy v0.8.46`, `agent-reach v1.5.0`, `twitter-cli v0.8.5`, and `yt-dlp v2026.6.9`.
- `graphify-out/GRAPH_REPORT.md` currently reports:
  - 390 files
  - 6320 nodes
  - 9624 edges
  - freshness marker `ee16f827`
- The freshness marker points at the current HEAD used for graph generation. `refactor/`, `.claude/`, and `graphify-out/` are excluded from ingestion, so docs-only commits can still be the recorded build commit even when the graph content comes from source files.
- `.graphifyignore` excludes `.claude/`, `.obsidian/`, `data/`, `reports/`, `refactor/`, `knowledge/state/`, DBs, env files, logs, and runtime caches.
- `.gitignore` keeps `graphify-out/.graphify_python`, `graphify-out/cache/`, `graphify-out/cost.json`, generated HTML, and dated backups out of git.
- Preserved local backup copies:
  - `/private/tmp/mindpattern-v3-graphify-out-preclean-2026-06-23`
  - `/private/tmp/mindpattern-v3-graphify-out-pre-refactor-ignore-2026-06-23`

## Dirty Worktree At Handoff

Do not reset or clean blindly. Some of this is likely user/personal/generated state.

Tracked dirty files after the session hook slice is committed should still mostly be user/generated state:

- Local/editor state: `.obsidian/app.json`, `.obsidian/workspace.json`
- Personal/generated data: `data/ramsay/mindpattern/**`, `data/social-drafts/**`
- Source/doc candidates: `docs/spec-v4.md`, plus the unrelated `requirements.txt` Pillow hunk if it remains unstaged.

Untracked notable directories/files:

- Agent/local config: `.claude/agents/`, `.claude/commands/`, `.claude/references/`, `.claude/skills/**`
- Handoffs: `.claude/handoffs/2026-05-07-114034-skills-cleanup-and-agentic-research.md`, plus this June 23 handoff
- Possible source feature slices: `knowledge/`, `docs/agents/`
- Research/spec/docs: `SAAS-AGENT-TECH.md`, `SPEC.md`, `V4-SPEC.md`, `v4/`, `research/`, `concepts/`, `tasks/`
- Runtime/user data: `data/ramsay/journal.offset`, `data/ramsay/mindpattern/knowledge/`, `data/testuser/`

There is also a tracked-change recovery patch from earlier in the run:

- `/private/tmp/mindpattern-v3-tracked-dirty-2026-06-23.patch`

## Recommended Next Steps

1. Re-check dirty status with `git status --short --untracked-files=normal`.
2. Classify remaining changes into small commit slices. Do not stage broad directories like `data/` or `.claude/` without inspecting content.
3. Likely next source slices to inspect:
   - `kg/` plus `tests/test_kg_schema.py`
   - `hooks/session_capture.py` plus `tests/test_session_capture.py`
   - `docs/spec-v4.md`, `v4/`, and top-level spec docs
   - X/Twitter query-search recovery: `twitter search` currently returns HTTP 404 even though auth and `user-posts` work.
4. Treat `data/ramsay/mindpattern/**` and `data/social-drafts/**` as personal/generated output until the user explicitly says to commit them.
5. After any code/doc slice:
   - run targeted tests first
   - run `.venv/bin/python3 -m pytest tests/ -x -q` before commit if the slice touches shared behavior
   - update `refactor/mindpattern-v3(2026-06-23).md`
   - run `graphify update .` if the slice changes code/docs that Graphify indexes
   - stage explicit paths only
   - commit with a narrow message

## Tool Install Context

Current installed command state:

- `graphify`: `/Users/taylerramsay/.local/bin/graphify`
- `agent-reach`: `/Users/taylerramsay/.local/bin/agent-reach`
- `twitter`: `/Users/taylerramsay/.local/bin/twitter`
- `yt-dlp`: `/Users/taylerramsay/.local/bin/yt-dlp`
- `mcporter`: `/Users/taylerramsay/.local/node/bin/mcporter`
- `gh`: `/opt/homebrew/bin/gh`
- `xreach`: still missing; `uv tool install xreach` failed because the package is not in the registry.
- `exa-mcp-server`: not installed as a direct binary, but Exa is configured through hosted MCP and reachable via `mcporter`.

Current tool versions from `uv tool list`:

- `agent-reach v1.5.0`
- `graphifyy v0.8.46`
- `twitter-cli v0.8.5`
- `yt-dlp v2026.6.9`

Agent Reach installed `mcporter v0.12.0` under the local Node tool path. Exa and YouTube are live-green. Twitter/X is partially restored: auth and account reads work, but topic search still fails with upstream HTTP 404.

Newsletter delivery is live-green at the app/API level: Resend accepted the earlier owner send and subscriber broadcast. The later smoke run intentionally skipped duplicate sends because receipts were already claimed.

## Embedding Context

Embeddings are semantic retrieval infrastructure, not source collection. They let the app compare meaning, find related memory records, and dedupe near-duplicate findings/posts. They do not fetch X, YouTube, or Exa content; those require the missing source/search tools above.

## Gotchas

- Do not rely on the old May 7 handoff as current. It says branch `main` and discusses stale skill/plugin cleanup.
- The repo is intentionally not clean. That is expected; the user asked not to lose changes.
- `graphify update .` may need approval in some sandboxes; the approved prefix was saved earlier and it ran successfully in this session.
- Commit hooks may launch a Graphify background rebuild. Check `git status` afterward before assuming a commit is finished.
- The report may remain fresh against the last code commit rather than the Graphify artifact commit because `refactor/` and `graphify-out/` are excluded from ingestion.
- The full pipeline smoke surfaced quality warnings, low-count research agents, X search 404s, and an oversized identity `soul` update rejection. The identity rejection is now covered by the length guard; X search 404s, low-count research agents, and quality warnings remain open.
- `run-launchd.sh` now intentionally reruns delivered-but-not-synced days during backup windows. Newsletter receipts make this safe; the goal is to retry Fly sync/restart instead of leaving mindpattern.ai stale.
- `data/ramsay/learnings.md` is tracked and was repaired from raw updater error text to a generic safe baseline. Future updater failures now preserve valid content or write deterministic fallback content.

## Security Reminder

Before committing any new handoff or config file, scan the staged diff for secrets and local absolute paths.

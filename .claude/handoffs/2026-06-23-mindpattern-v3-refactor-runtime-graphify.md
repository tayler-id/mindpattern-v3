# Handoff: MindPattern v3 refactor, runtime hardening, and Graphify restoration

## Session Metadata

- Created: 2026-06-23
- Project: `/Users/taylerramsay/Projects/mindpattern-v3`
- Branch: `refactor/mindpattern-v3-2026-06-23`
- Code/graph HEAD before the sync-marker/launchd slice: `36dbd4b fix: guard learnings updater failures`
- Progress log: `refactor/mindpattern-v3(2026-06-23).md`
- User constraints: do not lose dirty changes; commit needed slices only; do not merge broken code; run live checks and auto review after significant steps.

## Current State Summary

This refactor branch had nine clean save-point commits before the sync-marker/launchd update:

1. `db8a740 refactor: tighten data path and sync boundaries`
2. `2658c35 chore: restore worktree guardrails`
3. `6fd31a8 refactor: harden research agent dispatch`
4. `1ae8fb8 refactor: harden runtime social dispatch`
5. `2416fb4 chore: restore graphify artifacts`
6. `edef515 docs: add refactor handoff`
7. `333685e refactor: harden embedding cache boundary`
8. `1761aea refactor: restore preflight source tool fallback`
9. `36dbd4b fix: guard learnings updater failures`

This handoff was updated again after wiring the sync marker into `_phase_sync()` and `run-launchd.sh`. Use `git log --oneline -12` for the exact latest commit hash after the commit lands.

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
  - `graphify update .` rebuilt clean artifacts from 388 files; current report shows 6260 nodes and 9428 edges.
  - `graphify explain "LinkedInClient"` resolves `social/posting.py` with 54 connections.
  - `graphify path "Slack Approval Gateway" "LinkedInClient"` finds `gateway() -> ApprovalGateway <- pipeline.py -> LinkedInClient`.
  - `graphify explain create_text_embedding` resolves `memory/embeddings.py` with links to `_get_model()` and cache tests.
  - `graphify path api.py create_text_embedding` finds `api.py -> embeddings.py -> create_text_embedding()`.
  - `graphify explain _search_command` resolves `preflight/twitter.py`.
  - `graphify path twitter.py _search_command` finds `twitter.py -> _search_command()`.
  - `graphify explain _phase_learn` resolves `orchestrator/runner.py` line 984.
  - `graphify explain write_synced_marker` resolves `orchestrator/sync.py` and shows `_phase_sync()` as an incoming caller.
  - `graphify path _phase_sync write_synced_marker` finds `_phase_sync() --calls--> write_synced_marker()`.
  - `graphify diagnose multigraph --json` reports 6260 nodes, 9428 edges, and zero duplicate/missing/dangling/self-loop edges.
  - `graphify check-update .` exited cleanly with no output.

## Graphify Notes

- Graphify was reinstalled through `uv tool install graphifyy`.
- Current observed install state includes `graphifyy v0.8.46`, `agent-reach v1.5.0`, `twitter-cli v0.8.5`, and `yt-dlp v2026.6.9`.
- `graphify-out/GRAPH_REPORT.md` currently reports:
  - 388 files
  - 6260 nodes
  - 9428 edges
  - freshness marker `36dbd4bd`
- The freshness marker points at the current HEAD used for graph generation. `refactor/`, `.claude/`, and `graphify-out/` are excluded from ingestion, so docs-only commits can still be the recorded build commit even when the graph content comes from source files.
- `.graphifyignore` excludes `.claude/`, `.obsidian/`, `data/`, `reports/`, `refactor/`, `knowledge/state/`, DBs, env files, logs, and runtime caches.
- `.gitignore` keeps `graphify-out/.graphify_python`, `graphify-out/cache/`, `graphify-out/cost.json`, generated HTML, and dated backups out of git.
- Preserved local backup copies:
  - `/private/tmp/mindpattern-v3-graphify-out-preclean-2026-06-23`
  - `/private/tmp/mindpattern-v3-graphify-out-pre-refactor-ignore-2026-06-23`

## Dirty Worktree At Handoff

Do not reset or clean blindly. Some of this is likely user/personal/generated state.

Tracked dirty files after the sync-marker slice is committed should still mostly be user/generated state:

- Local/editor state: `.claude/settings.json`, `.obsidian/app.json`, `.obsidian/workspace.json`
- Personal/generated data: `data/ramsay/mindpattern/**`, `data/social-drafts/**`
- Source/doc candidates: `docs/spec-v4.md`, plus the unrelated `requirements.txt` Pillow hunk if it remains unstaged.

Untracked notable directories/files:

- Agent/local config: `.claude/agents/`, `.claude/commands/`, `.claude/references/`, `.claude/skills/**`
- Handoffs: `.claude/handoffs/2026-05-07-114034-skills-cleanup-and-agentic-research.md`, plus this June 23 handoff
- Possible source feature slices: `hooks/`, `kg/`, `knowledge/`, `docs/agents/`, `tests/test_kg_schema.py`, `tests/test_session_capture.py`
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
   - Learn updater tuning: the new guard prevents bad writes, but `learnings_update` still hit max turns in both real runs today.
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
- The full pipeline smoke surfaced quality warnings, low-count research agents, X search 404s, and an oversized identity `soul` update rejection. These did not stop the run, but they are not fixed.
- `run-launchd.sh` now intentionally reruns delivered-but-not-synced days during backup windows. Newsletter receipts make this safe; the goal is to retry Fly sync/restart instead of leaving mindpattern.ai stale.

## Security Reminder

Before committing any new handoff or config file, scan the staged diff for secrets and local absolute paths.

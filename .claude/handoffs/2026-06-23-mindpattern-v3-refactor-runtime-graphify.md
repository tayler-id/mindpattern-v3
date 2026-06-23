# Handoff: MindPattern v3 refactor, runtime hardening, and Graphify restoration

## Session Metadata

- Created: 2026-06-23
- Project: `/Users/taylerramsay/Projects/mindpattern-v3`
- Branch: `refactor/mindpattern-v3-2026-06-23`
- Code/graph HEAD before this handoff-doc commit: `2416fb4 chore: restore graphify artifacts`
- Progress log: `refactor/mindpattern-v3(2026-06-23).md`
- User constraints: do not lose dirty changes; commit needed slices only; do not merge broken code; run live checks and auto review after significant steps.

## Current State Summary

This refactor branch has five clean implementation/tooling save-point commits before this handoff-doc commit:

1. `db8a740 refactor: tighten data path and sync boundaries`
2. `2658c35 chore: restore worktree guardrails`
3. `6fd31a8 refactor: harden research agent dispatch`
4. `1ae8fb8 refactor: harden runtime social dispatch`
5. `2416fb4 chore: restore graphify artifacts`

The main completed work is:

- Centralized trace DB path resolution and repaired sync/prompt-capture tests.
- Restored `.gitignore` guardrails for databases, `users.json`, local tool state, and Graphify-local runtime files.
- Hardened research-agent subprocess dispatch, retry classification, prompt/tool boundaries, and banned-entity policy checks.
- Hardened Fly/Slack/social runtime behavior, including environment secret fallback, Fly harness gating, Jina security-compromise filtering, LinkedIn version fallback, and LinkedIn 3000-character fail-closed guard.
- Restored Graphify as a working repo tool and committed portable graph artifacts.

## Verification Already Run

- Full suite after runtime/social changes: `.venv/bin/python3 -m pytest tests/ -x -q` -> `1092 passed, 1 FastAPI/Starlette warning`.
- Targeted Slack/social suite: `.venv/bin/python3 -m pytest tests/test_social.py tests/test_slack_bot.py -q` -> `52 passed`.
- Graphify:
  - `uv tool list` showed `graphifyy v0.8.46` with `graphify` and `graphify-mcp`.
  - `graphify update .` rebuilt clean artifacts from 387 files.
  - `graphify explain "LinkedInClient"` resolves `social/posting.py` with 54 connections.
  - `graphify path "Slack Approval Gateway" "LinkedInClient"` finds `gateway() -> ApprovalGateway <- pipeline.py -> LinkedInClient`.
  - `graphify diagnose multigraph --json` reports 6242 nodes, 9395 edges, and zero duplicate/missing/dangling/self-loop edges.
  - `graphify check-update .` exited cleanly with no output.

## Graphify Notes

- Graphify was reinstalled through `uv tool install graphifyy`.
- Current observed install after the user's "I upgraded" note: `uv tool list` still reports `graphifyy v0.8.46`.
- `graphify-out/GRAPH_REPORT.md` currently reports:
  - 387 files
  - 6242 nodes
  - 9395 edges
  - freshness marker `1ae8fb8f`
- The freshness marker intentionally points at the last code commit, not `2416fb4`, because `2416fb4` only adds Graphify config/artifacts and `refactor/` is excluded from Graphify ingestion.
- `.graphifyignore` excludes `.claude/`, `.obsidian/`, `data/`, `reports/`, `refactor/`, `knowledge/state/`, DBs, env files, logs, and runtime caches.
- `.gitignore` keeps `graphify-out/.graphify_python`, `graphify-out/cache/`, `graphify-out/cost.json`, generated HTML, and dated backups out of git.
- Preserved local backup copies:
  - `/private/tmp/mindpattern-v3-graphify-out-preclean-2026-06-23`
  - `/private/tmp/mindpattern-v3-graphify-out-pre-refactor-ignore-2026-06-23`

## Dirty Worktree At Handoff

Do not reset or clean blindly. Some of this is likely user/personal/generated state.

Tracked dirty files:

- Local/editor state: `.claude/settings.json`, `.obsidian/app.json`, `.obsidian/workspace.json`
- Personal/generated data: `data/ramsay/mindpattern/**`, `data/social-drafts/**`
- Source/doc candidates: `docs/spec-v4.md`, `memory/embeddings.py`, `requirements.txt`

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
   - `memory/embeddings.py` plus `requirements.txt`
   - `kg/` plus `tests/test_kg_schema.py`
   - `hooks/session_capture.py` plus `tests/test_session_capture.py`
   - `docs/spec-v4.md`, `v4/`, and top-level spec docs
4. Treat `data/ramsay/mindpattern/**` and `data/social-drafts/**` as personal/generated output until the user explicitly says to commit them.
5. After any code/doc slice:
   - run targeted tests first
   - run `.venv/bin/python3 -m pytest tests/ -x -q` before commit if the slice touches shared behavior
   - update `refactor/mindpattern-v3(2026-06-23).md`
   - run `graphify update .` if the slice changes code/docs that Graphify indexes
   - stage explicit paths only
   - commit with a narrow message

## Tool Install Context

Only Graphify was installed by this agent. Earlier, exact commands were provided for the user's requested tools, but they were not executed here:

- Agent Reach / X path: `uv tool install "https://github.com/Panniantong/agent-reach/archive/main.zip"` then `agent-reach install --env=auto`
- YouTube: `brew install yt-dlp`
- MCPorter: `brew install steipete/tap/mcporter`
- Legacy xreach check: `uv tool install xreach`

The Agent Reach docs currently favor the `twitter` CLI path; the repo still refers to legacy `xreach` in places. If the user says the upgrade completed, verify with `which`, `--version`, or a one-result dry run before changing code.

## Gotchas

- Do not rely on the old May 7 handoff as current. It says branch `main` and discusses stale skill/plugin cleanup.
- The repo is intentionally not clean. That is expected; the user asked not to lose changes.
- `graphify update .` needs unsandboxed approval in this environment; the approved prefix was saved earlier.
- Commit hooks may launch a Graphify background rebuild. Check `git status` afterward before assuming a commit is finished.
- The report may remain fresh against the last code commit rather than the Graphify artifact commit because `refactor/` and `graphify-out/` are excluded from ingestion.

## Security Reminder

Before committing any new handoff or config file, scan the staged diff for secrets and local absolute paths.

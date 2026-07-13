---
name: mindpattern-goal-lifecycle
description: Turn substantial MindPattern work into a durable, resumable lifecycle with a dated runbook, compact goal, verification record, and safe handoff. Use only when explicitly asked to start, resume, plan, hand off, or close a multi-session MindPattern goal. Do not use for small routine edits.
---

# MindPattern Goal Lifecycle

Keep state in the repository instead of relying on a long conversation.

## Establish current state

Run `git status --short --branch`, record the current HEAD and worktree, and inspect existing specs, goals, runbooks, and handoffs for the same objective. Current code, tests, runtime configuration, and live state outrank dated handoffs.

## Choose durable artifacts

- Use `docs/goals/YYYY-MM-DD-<slug>-goal.md` for the compact objective and definition of done.
- Use `docs/runbooks/YYYY-MM-DD-<slug>-runbook.md` for scope, ordered tasks, evidence, decisions, and state.
- Add a separate implementation plan only when the dependency graph genuinely needs one.
- Treat `.claude/handoffs/` as legacy input. Put new tool-neutral handoffs under `docs/runbooks/`.

## Run the lifecycle

1. Record the objective, success criteria, non-goals, Always/Ask/Never boundaries, branch, HEAD, and dirty state.
2. Reuse or update the existing durable artifact instead of creating a competing document.
3. Break work into dependency-ordered tasks with independent verification.
4. Start a compact goal that points to the durable file; never paste the entire plan into the goal.
5. After each task, record files or commits, exact verification, decisions, and remaining work.
6. At a major objective change or serious context drift, update the runbook and start a fresh thread.
7. Close only after verifying the actual definition of done and recording residual risks.

Use `git diff --stat`, `git diff --check`, `graphify update .`, and `graphify check-update .` when relevant. This workflow does not authorize deploys, live pipeline runs, dependency changes, schema changes, or outbound publishing.

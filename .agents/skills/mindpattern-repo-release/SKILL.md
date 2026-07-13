---
name: mindpattern-repo-release
description: Prepare and execute a MindPattern repository release across mindpattern-v3 and, when in scope, mindpattern-rabbit-hole by preserving dirty work, reconciling branches and worktrees, running surface-specific gates, publishing intentionally, and recording evidence. Use only when explicitly asked to ship, release, merge, deploy, publish local changes, or recover repository state.
---

# MindPattern Repo Release

Treat release as an explicit workflow, not a side effect of implementation.

## Inventory first

Run `git status --short --branch`, `git diff --stat`, `git diff --check`, `git worktree list`, `git branch -vv`, and a short decorated log. Preserve unrelated dirty work. Never delete branches, stashes, or worktrees because they merely look old.

Create worktrees sequentially to avoid `.git/config.lock` races. Never force-push without explicit authorization.

## Run the correct gates

For `mindpattern-v3`:

```sh
.venv/bin/python3 -m pytest tests/ -q
git diff --check
graphify update .
graphify check-update .
```

For `mindpattern-rabbit-hole`:

```sh
pnpm lint
pnpm exec tsc --noEmit --incremental false
pnpm build
```

Use the GitHub publication workflow for intentional commit, push, and draft-PR work. Require explicit approval for merge, production deploy, branch or stash deletion, force push, or external-service mutation. Record the final branch, commit, verification, deployment result when applicable, and residual risks in the handoff.

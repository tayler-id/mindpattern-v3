---
name: rabbit-hole-backfill
description: Operate the Rabbit Hole historical story backfill through the claim-based orchestrator.site_backfill workflow. Use only when the user explicitly asks to run, resume, monitor, release, or report the archive backfill. Do not use for code changes, daily site-content generation, site-quality work, or ordinary Rabbit Hole development.
---

# Rabbit Hole Backfill

Treat this as an operator workflow, never as authorization to develop or deploy code.

## Required source

Read `references/operator-goal.md` completely before taking any action. Treat `orchestrator/site_backfill.py` and `docs/specs/2026-07-02-backfill-harness-spec.md` as the implementation sources when the prose and code disagree.

## Select the operation

- For status or reporting, run only the status command and inspect the canonical notebook. Do not claim work.
- For resume or run, verify every precondition in the operator goal before claiming a batch.
- For release, release only the named claim after confirming ownership and reason.
- For monitor, follow the active claim and notebook without starting a second process.

## Preserve operator boundaries

- Use the canonical reports root even from a temporary worktree.
- Never edit repository files, run `run.py`, deploy, commit, or kill unrelated processes.
- Stop on quota or failure-streak aborts. Do not retry the same day.
- Treat `failed:*` story outcomes as normal critic refusals that auto-release.
- Declare completion only when both `remaining_unclaimed` and `in_progress` are zero.
- Report the claim ID, outcome JSON, abort reason, fresh status, and matching notebook lines.

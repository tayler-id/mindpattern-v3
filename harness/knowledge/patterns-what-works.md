# What Works

> Approaches that produce good results. Updated by harness from successful PRs and run outcomes.

## Pipeline

- **13 parallel agents with specialization** — Each agent has a focused domain. Produces 230-254 findings per run consistently (Runs 14-19).
- **TDD in harness fix agents** — Write failing tests first, then implement. Catches regressions before merge.
- **Deterministic quality scoring** — [[orchestrator/evaluator]] catches issues without burning LLM tokens.
- **WAL mode for SQLite** — Allows concurrent reads during writes. Critical for parallel agents.
- **Single-bundle sync** — [[orchestrator/sync]] reduced 30 connections to 1. Significant reliability improvement.

## Social

- **Three-actor convergence** — When 3+ named actors publish same signal, topic passes Gate 1 cleanly.
- **Counter-narrative injection** — Gate 1 'custom' behavior for compound narratives (e.g., AI labor displacement + counter-evidence).
- **Distribution confirmed working** — Run 19 resolved Runs 16-18 ambiguity. Posts confirmed to Bluesky + LinkedIn.

## Harness

- **Staggered worktree creation** — 5s delay between parallel agent launches prevents git config lock race.
- **15 max turns for fix agents** — Prevents token burn on complex tickets. Forces focus or fast fail.

## Last Updated

2026-04-04 22:14.

2026-04-01 19:19.

2026-04-01 19:10.

2026-04-01 — initial patterns from run history analysis.

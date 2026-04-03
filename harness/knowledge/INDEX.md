# MindPattern Knowledge Graph

> Auto-evolving codebase knowledge. Updated by harness after every run.
> Last updated: 2026-04-02

## Modules

- [[orchestrator/runner]] — Main pipeline state machine, 12 phases
- [[orchestrator/agents]] — Parallel Claude CLI dispatch for 13 research agents
- [[orchestrator/pipeline]] — Phase enum, transitions, critical/skippable sets
- [[orchestrator/evaluator]] — Newsletter quality scoring (no LLM), 6 dimensions
- [[orchestrator/newsletter]] — Report validation, HTML render, Resend email delivery
- [[orchestrator/traces_db]] — traces.db schema (15 tables), CRUD helpers
- [[orchestrator/checkpoint]] — Crash recovery, resume from last completed phase
- [[orchestrator/observability]] — PipelineMonitor: phase metrics, agent metrics, cost
- [[orchestrator/prompt_tracker]] — Prompt change detection, regression check, auto-rollback
- [[orchestrator/analyzer]] — Self-optimization: trace analysis, skill file diffs
- [[orchestrator/router]] — Model routing, max turns, timeouts, pricing per task type
- [[orchestrator/sync]] — Fly.io sync: bundle DBs + reports, SFTP upload
- [[social/pipeline]] — Social posting orchestration
- [[social/writers]] — Draft generation per platform
- [[social/approval]] — Gate 1 / Gate 2 / Expeditor approval chain
- [[social/posting]] — Platform API posting (Bluesky, LinkedIn)
- [[memory/findings]] — Findings CRUD, dedup, embeddings, FTS
- [[memory/db]] — memory.db connection, schema init (37 tables)
- [[slack_bot/main]] — Socket Mode daemon, channel handler pattern
- [[harness/run]] — Harness orchestrator: scout, research, parallel fix, review, health report
- [[harness/tickets]] — Ticket lifecycle: pick, mark, decay, archive
- [[harness/issues]] — Shared issue log: append-only, read by all agents before fixes
- [[harness/health-report]] — Daily Slack health report: tickets, pipeline, issues

## Data Stores

- [[data/memory-db]] — memory.db: 37 tables, findings + editorial + user + entity graph
- [[data/traces-db]] — traces.db: 15 tables, execution traces + cost + quality + evolution

## Agent Skills

- [[agents/research-agents]] — 13 specialized researchers, signal sources, learned patterns

## Known Issues

- [[issues/open]] — Current known bugs, fragile patterns, debt

## Patterns

- [[patterns/what-works]] — Approaches that produce good results
- [[patterns/what-fails]] — Anti-patterns, common failure modes

## Run History

- [[runs/latest]] — Last harness run outcomes, tickets processed, PRs created

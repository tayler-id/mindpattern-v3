# Known Issues

> Open bugs, fragile patterns, technical debt. Updated by harness after each run.

## Critical

- **Missing DB tables in memory/db.py** — claimed_topics, failure_lessons, editorial_corrections, entity_graph are referenced by code in [[memory/findings]], memory/claims.py, memory/failures.py, memory/corrections.py, memory/graph.py but NOT created in _init_schema(). Tests importing these modules will fail. This is likely why ALL harness fix agents fail tests.
- **Sources score regression** — Dropped to 0.333 on security topics (Run 19). Unresolved 7+ runs. See [[orchestrator/evaluator]].
- **Topic score stuck at 0** — 7+ consecutive runs. See decisions.md.
- **Gate 1 auto-approves on exception** — social/pipeline.py silently auto-approves topics if approval system fails.
- **Bot responds to ALL users if owner_user_id not set** — slack_bot/bot.py has no allowlist fallback. Security risk.

## Fragile Patterns

- **Git config lock race** — Fixed: deterministic worktrees in [[harness/run]]. Each ticket gets `.harness-worktrees/{ticket-id}`.
- **SFTP error detection** — Checks "bytes written" substring. Breaks across flyctl versions. See [[orchestrator/sync]].
- **Schema migration destructive** — quality_history migration renames old table, copies via pivot. Data loss if INSERT fails. See [[orchestrator/observability]].
- **Output truncation silent** — agent_runs.output capped at 10KB with no indicator. See [[orchestrator/traces_db]].
- **Thread safety in embeddings** — Module-level singleton `_model` in memory/embeddings.py not thread-safe. Concurrent imports race.
- **No transaction boundaries in findings** — memory/findings.py stores finding + embedding in separate statements. Crash between = orphaned row.
- **Silent fallbacks everywhere** — social/art.py, social/critics.py, social/writers.py all swallow agent errors and continue with degraded output.
- **Subprocess calls have no retry** — image-gen.py, curl (Jina), Keychain lookups all single-attempt.
- **Approval polling has no backoff** — 10s fixed interval in [[social/approval]].

## Technical Debt

- **MODEL_PRICING duplicated** — In [[orchestrator/router]] and [[orchestrator/observability]]. Source of truth confusion.
- **TRACES_DB_PATH hardcoded** — "ramsay" username in [[orchestrator/traces_db]].
- **CRITICAL_PHASES hardcoded** — Only {RESEARCH, SYNTHESIS} in [[orchestrator/pipeline]]. Not configurable.
- **Regression threshold hardcoded** — 15% in [[orchestrator/prompt_tracker]]. Not configurable.
- **Dead code** — _phase_start_time in [[orchestrator/pipeline]] tracked but never read. _acquire_mutex in slack_bot/bot.py defined but never called.
- **Hardcoded thresholds** — Embedding similarity: 0.75 (patterns), 0.80 (social dedup), 0.85 (preflight dedup), 0.90 (finding dedup). None configurable.
- **Voice guide loaded per-call** — social/critics.py loads voice.md on every review call. Should cache.

## Harness-Specific

- **Worktree reuse** — FIXED: replaced find_newest_worktree() with deterministic `.harness-worktrees/{ticket-id}`.
- **No mark_open()** — Can't reset tickets to open via CLI. Must edit JSON manually.
- **All fix agents fail tests** — 12/12 tickets failed tests on 2026-04-01 run. Root cause: likely missing DB tables + fix agents not understanding test infrastructure.

## Last Updated

2026-04-04 22:14 — scout added 1 findings.

2026-04-01 19:03 — scout added 5 findings.

2026-04-01 18:08 — updated with deep analysis findings.

## Scout Findings (2026-04-01 19:03)

- **[P2] 2026-04-01-R014** — Add quality-driven cascade model routing for research agents. Files: orchestrator/router.py, orchestrator/agents.py, orchestrator/traces_db.py, config.json
- **[P3] 2026-03-31-R001** — Evaluate promptfoo or inspect-ai for agent eval framework. Files: tests/prompts/promptfoo.yaml, orchestrator/evaluator.py
- **[P2] 2026-04-01-R013** — Add freshness-weighted time-decay to semantic dedup scoring. Files: preflight/run_all.py
- **[P2] 2026-04-01-011** — Greedy regex in _phase_trend_scan silently drops trends when LLM output contains brackets. Files: orchestrator/runner.py, orchestrator/agents.py
- **[P2] 2026-04-01-R012** — Add day-of-week aware social posting with platform-specific optimal time windows. Files: social/pipeline.py, social/eic.py, memory/db.py, agents/eic.md, social-config.json

## Scout Findings (2026-04-04 22:14)

- **[P1] test-001** — Test ticket. Files: test.py

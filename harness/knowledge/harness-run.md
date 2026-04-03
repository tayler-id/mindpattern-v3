# harness/run.sh

> Harness orchestrator. 7 stages: Health Report -> Scout -> Codex Review -> Research -> Fix (parallel) -> Review -> Summary.

## How It Works

1. **Guards** — Check for hold file, pipeline lock, existing harness lock
2. **Health report** — Posts daily health report to `#mp-harness` Slack channel (ticket stats, pipeline status, recent issues). See [[harness/health-report]].
3. **Scout** — `claude -p` with scout.md prompt, scans codebase for issues, creates tickets. Reads [[harness/issues]] (shared issue log) first. Must output `KNOWLEDGE CHECK:` confirmation.
4. **Codex adversarial review** — Reviews all new tickets. Checks if bug still exists, if ticket is achievable in 25 turns, if it's a duplicate, and if the fix could break something. Rejects bad tickets before they burn fix agent tokens.
5. **Research** — `claude -p` with research.md prompt, web search for ideas, creates research tickets
6. **Fix loop** — Picks N tickets, dispatches parallel fix agents (each in own worktree), tests in worktree, review agent creates PR. Failures logged to [[harness/issues]]. Must output `KNOWLEDGE CHECK:` confirmation.
7. **Summary** — Count done/failed/remaining, notify Slack

## Knowledge Check

All agents must print `KNOWLEDGE CHECK: Read N issues, N relevant: ...` after reading the shared issue log. The harness parses this from agent logs. Missing = warning in harness log.

## Prompt Caching

Fix agents use `--append-system-prompt` for the knowledge summary (ISSUES.md + INDEX + patterns). This is stable across all parallel agents in a round, so agents 2 and 3 get API-level cache hits on the system prompt prefix. Per-ticket content stays in the user prompt.

## Key Config (harness/config.json)

| Stage | Model | Max Turns | Timeout |
|-------|-------|-----------|---------|
| scout | opus | 15 | 900s |
| research | opus | 15 | 900s |
| fix | opus | 15 | 600s |
| review | opus | 25 | 900s |

Parallel agents: 3. Max tickets per run: 10.

## Worktree Strategy

Each fix agent gets its own worktree at `.harness-worktrees/{ticket-id}`. After fix, tests run in worktree (no LLM). If pass, review agent inspects diff and creates PR.

**Known issue:** Parallel worktree creation races on .git/config.lock. Mitigated with 3s stagger between launches.

## Failure Logging

Fix failures and review rejections are logged to [[harness/issues]] (shared issue log) so the scout and future fix agents see them. This prevents repeat mistakes.

## Depends On

[[harness/tickets]] for ticket lifecycle. [[harness/issues]] for shared issue log. [[harness/health-report]] for daily Slack report. Scout reads [[issues/open]] and [[patterns/what-fails]] for context.

## Last Modified

2026-04-02 — added health report, shared issue log, prompt caching, codex adversarial ticket gate, knowledge check confirmation.

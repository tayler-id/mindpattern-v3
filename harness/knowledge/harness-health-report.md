# harness/health_report.py

> Daily Slack health report. Deterministic (no LLM) — aggregates data from tickets, issues, logs, feedback.

## What It Reports

- **Pipeline status** — success/crashed/not started (checks marker file + stderr log)
- **Harness run stats** — processed, PRs created, failures (parsed from harness log)
- **Ticket backlog** — open count by priority (P1/P2/P3), by type (bug/improvement/feature/research)
- **Success rate** — done / (done + failed) lifetime
- **Stale tickets** — open > 3 days, shows top 3
- **Issues (last 24h)** — count + titles from ISSUES.md
- **PR outcomes** — merged/rejected/closed from feedback.json

## When It Runs

Posted to `#mp-harness` at the start of every harness run (before scout). Gives you the state of the world before the harness acts.

## CLI

```bash
python3 -m harness.health_report           # stdout
python3 -m harness.health_report --slack    # post to Slack
```

## Connected To

Reads [[harness/tickets]], [[harness/issues]], `feedback.json`, `reports/harness-*.log`, `reports/launchd-stderr.log`. Posted by [[harness/run]].

## Created

2026-04-02.

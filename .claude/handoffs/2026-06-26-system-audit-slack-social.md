# 2026-06-26 System Audit, Slack/Social Diagnosis, and Improvement Backlog

## Scope

Audit-only pass requested by Tayler. The task was to understand MindPattern v3
as it works today, diagnose why Slack/social posting has not worked for weeks,
and prepare prioritized recommendations. No production behavior or application
code was changed in this pass.

## Current Repo State

- Branch: `main`
- Remote tracking: `main...origin/main`
- HEAD when inspected: `44329ba03d07ce3495d61277711b1fa8a283613e`
- Worktree was clean before this handoff file was added.
- `graphify-out/GRAPH_REPORT.md` exists but is stale: built from `eb913fee`.

## System Map

MindPattern v3 is a Python 3.14 autonomous daily research pipeline.

- Schedule: macOS launchd runs `run-launchd.sh` in the 06:00-11:59 window.
- Entry point: `run.py` sets PATH, logging, lock, caffeinate, user iteration,
  and a local Slack summary.
- State machine: `orchestrator/runner.py` runs the pipeline phases.
- Research: `preflight/run_all.py` gathers 8 sources and routes items to 13
  Claude research agents through `orchestrator/agents.py`.
- Newsletter: synthesis and delivery run through `orchestrator/runner.py`,
  `orchestrator/newsletter.py`, receipts, and `reports/ramsay/*.md`.
- Memory: `data/ramsay/memory.db` stores findings, quality, receipts, social
  posts, identity, signals, and embeddings.
- Traces: `data/ramsay/traces.db` stores pipeline observability.
- Social: `orchestrator/runner.py` enters `social/pipeline.py` only if at least
  one platform in `social-config.json` has `enabled: true`.
- Slack approval: `social/approval.py` posts approval requests to
  `#mindpattern-approvals` and polls threaded owner replies.
- Slack bot daemon: `slack_bot/` is a separate Socket Mode command bot.
- Fly production: `start.sh` runs FastAPI dashboard and `python3 -m slack_bot`
  on the same Fly machine. `/healthz` checks database and bot heartbeat.
- Sync: runner syncs local data/reports to Fly; `start.sh` symlinks
  `/data/social-config.json` and `/data/users.json` into the app container.

## Slack / Social Diagnosis

Most likely root cause: daily social posting is not reaching Slack approval or
platform posting because both configured platforms are disabled.

Evidence:

- Local `social-config.json`:
  - `platforms.linkedin.enabled = false`
  - `platforms.bluesky.enabled = false`
  - `imessage.gate_timeout_seconds = null`
- Fly `/data/social-config.json` matched local:
  - `{'platforms': {'linkedin': False, 'bluesky': False}, ...}`
- `orchestrator/runner.py` `_phase_social()` returns early when
  `_enabled_platforms(social_config)` is empty and logs:
  `Social: no platforms enabled, skipping social phase`.
- Recent logs show that exact skip every day inspected:
  2026-06-20 through 2026-06-26.
- `data/ramsay/memory.db` `social_posts` has no successful social posts after
  2026-06-01.
- Fly is not currently down:
  - `flyctl status --app mindpattern`: machine started, one check passing.
  - `https://mindpattern.fly.dev/healthz`: `database=connected`, `bot=alive`.
  - Fly secrets exist for Slack, LinkedIn, Bluesky, and Claude.
  - `/data/bot-heartbeat` existed and was fresh during inspection.
- Local launchd Slack bot services were not registered:
  - `com.mindpattern.slackbot`: service not found.
  - `com.taylerramsay.slack-bot`: service not found.
- `reports/slack-bot.log` only showed local bot activity through 2026-06-08.

Interpretation:

- Production Slack bot daemon is alive on Fly.
- The old local Slack bot log stopping is not the same as the daily social
  pipeline stopping.
- Daily social posting is currently skipped by config before topic selection,
  Slack approval, or platform posting can run.
- A portability risk remains: `social/approval.py` reads the Slack bot token
  from macOS Keychain only, while Fly secrets expose `SLACK_BOT_TOKEN`. If the
  daily approval path ever runs on Fly, it should use env fallback too.

Safe fix path:

1. Decide which platform should resume first, preferably Bluesky before LinkedIn.
2. Enable exactly one platform in both local `social-config.json` and Fly
   `/data/social-config.json`.
3. Set a finite social approval timeout instead of `null`.
4. Add env fallback to `ApprovalGateway._get_slack_token()`.
5. Run a dry social smoke that proves Slack approval prompt creation without
   posting.
6. Run one approved live social post and verify:
   - Slack approval message appears in `#mindpattern-approvals`.
   - `social_posts` gets a posted row.
   - platform URL is captured.
   - Fly dashboard/health remain ok.

## Newsletter / Research Quality Evidence

Recent stored findings dropped versus early June:

- 2026-06-01: 135 findings, 13 agents.
- 2026-06-05: 140 findings, 13 agents.
- 2026-06-09: 141 findings, 13 agents.
- 2026-06-20: 51 findings, 7 agents.
- 2026-06-21: 35 findings, 6 agents.
- 2026-06-22: 37 findings, 9 agents.
- 2026-06-25: 57 findings, 8 agents.
- 2026-06-26: 68 findings, 13 agents.

Recent source/tool evidence:

- Logs 2026-06-20 through 2026-06-26 show RSS at 0 items.
- Logs repeatedly showed RSS failing because `feedparser` was missing.
- Current `.venv` can now import `feedparser` version `6.0.12`, so the missing
  dependency may have been corrected after the logged runs.
- YouTube and Exa were missing on early 2026-06-21/22 logs but recovered in
  later logs to 15 and 20-25 items.
- Twitter/X status/auth works, but query search still failed in local smoke:
  HTTP 404 / cookie extraction issue.
- `agent-reach doctor --json` currently reports GitHub, Twitter, YouTube, RSS,
  Exa, and web as available, but Reddit as off.
- Local source smoke under the sandbox returned 0 for RSS, HN, Reddit, and
  Twitter. Exa/YouTube smoke was not conclusive because local DNS failed in the
  restricted sandbox.

Newsletter delivery evidence:

- Receipts exist for newsletter and subscriber broadcast for 2026-06-20 through
  2026-06-26.
- Recent logs show `Newsletter sent` for the inspected days.
- Focused tests passed: `300 passed in 92.64s`.

Quality risks:

- Source diversity is low. For findings since 2026-06-20, `arXiv` was the top
  source with 99 findings.
- 2026-06-25 had only 29 unique sources from 57 findings and quality score
  `0.5688`.
- Exact duplicate titles were not found for 2026-06-20 onward, but unique URLs
  were lower than findings on multiple days, so near-duplicate and repeated
  story angles remain possible.
- CI currently ignores `tests/test_runner.py`, which is the main pipeline phase
  test suite.

## Commands Run

- `git status --short --branch`
- `git log --oneline --decorate -20`
- `sed` reads of `CLAUDE.md`, `docs/ARCHITECTURE.md`, `graphify-out/GRAPH_REPORT.md`
- `sed` reads of `run.py`, `run-launchd.sh`, `fly.toml`, `start.sh`
- `sed` and `rg` reads of `orchestrator/runner.py`, `social/approval.py`,
  `social/pipeline.py`, `social/posting.py`, `slack_bot/`, `preflight/`
- `sqlite3 data/ramsay/memory.db` queries for findings, run quality, receipts,
  duplicate titles, source counts, and social posts
- `flyctl status --app mindpattern`
- `curl -sS https://mindpattern.fly.dev/healthz`
- `flyctl secrets list --app mindpattern`
- `flyctl ssh console --app mindpattern` checks for `/data/social-config.json`
  and `/data/bot-heartbeat`
- `launchctl print` for local Slack bot service labels
- `tail -80 reports/slack-bot.log`
- `agent-reach doctor --json`
- `yt-dlp --version`
- `mcporter list exa --status`
- `twitter status`
- `twitter search "AI agents" -n 1 --json`
- `.venv/bin/python3 -m pytest tests/test_approval.py tests/test_approval_parsing.py tests/test_slack_bot.py tests/test_social.py tests/test_preflight.py tests/test_dedup_resurfacing.py tests/test_newsletter.py tests/test_newsletter_receipts.py tests/test_runner.py -q`

## Top Next Actions

1. Re-enable social posting intentionally, one platform at a time, with Slack
   approval verification and receipt checks.
2. Fix source-channel observability and alerts so RSS/HN/Reddit/Twitter zeros
   are visible before the newsletter is written.
3. Add a newsletter quality floor that retries or escalates when source count,
   agent count, unique URLs, or duplicate angles fall below thresholds.
4. Move `tests/test_runner.py` back into CI or split it so the critical runner
   suite runs reliably.
5. Make Slack/social runtime config visible in the dashboard: bot heartbeat,
   enabled platforms, approval token source, last social post, and last skip
   reason.

## Do Not Do Yet

- Do not refactor `orchestrator/runner.py` before the Slack/social config issue
  and source-health issues are fixed.
- Do not enable both LinkedIn and Bluesky at once.
- Do not rely on local sandbox source-smoke failures as proof of production
  network failure.
- Do not remove approval gates to force posting.
- Do not change dedup thresholds broadly until duplicate examples are measured
  with URLs, titles, and semantic similarity.

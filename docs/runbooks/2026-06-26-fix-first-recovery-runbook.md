# Spec and Runbook: Fix-First Recovery for Slack, Research, and Newsletter Quality

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-26
> Source evidence: `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
> Implementation plan: `docs/runbooks/2026-06-26-fix-first-recovery-implementation-plan.md`

This runbook turns the handoff section "Fix-First Table: Existing Things That
Are Broken or Not Proven Working" into an implementation-ready recovery plan.
It is deliberately scoped to existing broken or unproven behavior, not new
features.

## Assumptions

1. The product direction is Slack-bot-first: `#mp-posts`, `#mp-skills`,
   `#mp-tips`, `#mp-engagement`, `#mp-approvals`, `#mp-briefing`, and
   `#mp-harness` are the human control surface.
2. No daily social path should auto-post. Every outward post requires an
   explicit owner approval in the correct Slack thread.
3. Disabled platform APIs should not stop draft creation. Disabled means
   "do not publish live", not "do not format useful copy".
4. The newsletter must keep shipping daily, but weak-source days must retry,
   escalate, and leave an incident trail instead of silently sending bland or
   repetitive content.
5. Secrets, subscriber data, local databases, Slack message bodies, and
   `social-config.json` are not committed or printed unless the owner
   explicitly asks.
6. Implementation should happen in small commits with tests, with Graphify
   refreshed after code or architecture-doc changes.

## Objective

Restore the existing MindPattern v3 operating contract:

- Slack channel workflows produce drafts, accept edits, wait for strict owner
  approval, and either publish or provide manual-copy fallback.
- The daily pipeline can create Slack social candidates even when platform
  posting APIs are disabled.
- RSS, HN, Reddit, Twitter/X, Exa, and YouTube source health is visible and
  actionable before newsletter synthesis.
- Newsletter generation retries or escalates when sources, agents, unique URLs,
  or duplicate-angle checks are below the quality floor.
- CI and Graphify catch regressions before another agent merges or deploys.

Success means the fix-first table is no longer a list of guesses. Each row has
one of these statuses with evidence: fixed, intentionally disabled with alert,
or blocked by a named external credential/tool.

## Non-goals

- Do not add new product features from the "30 Pure New Feature Ideas" table.
- Do not turn on background auto-posting.
- Do not enable both live LinkedIn and Bluesky posting at once during smoke
  tests.
- Do not remove approval gates to force a test through.
- Do not broadly refactor `orchestrator/runner.py` before the Slack and source
  health bugs are isolated.
- Do not change newsletter voice, editorial strategy, or prompt personality as
  part of this repair pass unless a failing quality check proves that exact
  prompt is the cause.

## Tech Stack

- Python 3.14 locally through `.venv/bin/python3`.
- Python 3.11 in the Fly image.
- SQLite databases at `data/ramsay/memory.db` and `data/ramsay/traces.db`.
- Slack Socket Mode bot in `slack_bot/`, running on Fly through `start.sh`.
- Daily pipeline entry point: `run.py`.
- Pipeline state machine: `orchestrator/runner.py`.
- Source collection: `preflight/`.
- Social pipeline and posting clients: `social/`.
- Newsletter quality scoring: `orchestrator/evaluator.py`.
- Tests: pytest under `tests/`.
- Production app: Fly app `mindpattern`.
- Architecture graph: `graphify-out/`.

## Commands

Use these exact commands unless the implementation task states otherwise.

```bash
# Inspect repo state before touching anything.
git status --short --branch
git diff --stat
git diff --name-only

# Install/update Python dependencies in the existing venv.
.venv/bin/python3 -m pip install -r requirements.txt

# Fast targeted Slack/social safety checks.
.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q

# Source/newsletter quality checks.
.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_evaluator.py tests/test_dedup_resurfacing.py tests/test_newsletter.py -q

# Runner checks. This file is currently excluded from CI, so run it locally.
.venv/bin/python3 -m pytest tests/test_runner.py -q

# Full local suite.
.venv/bin/python3 -m pytest tests/ -x -q

# Current CI-equivalent command from .github/workflows/test.yml.
.venv/bin/python3 -m pytest tests/ -q --tb=short --ignore=tests/test_cors.py --ignore=tests/test_engagement_linkedin.py --ignore=tests/test_memory_cli.py --ignore=tests/test_runner.py -k "not test_blocked_when_at_limit and not test_get_model_research_agent"

# Source-tool smoke commands.
agent-reach doctor --json
twitter status
twitter search "AI agents" -n 1 --json
yt-dlp --version
mcporter list exa --status

# Fly health and logs.
curl -sS https://mindpattern.fly.dev/healthz
/Users/taylerramsay/.fly/bin/flyctl logs --app mindpattern --no-tail

# Deploy only after tests pass and the owner approves deploy.
/Users/taylerramsay/.fly/bin/flyctl deploy --app mindpattern

# Graphify after code or indexed docs change.
graphify update .
graphify check-update .
```

Live commands that can send email, post to social, or mutate production state
require explicit owner approval first:

```bash
.venv/bin/python3 run.py --user ramsay
/Users/taylerramsay/.fly/bin/flyctl deploy --app mindpattern
```

## Project Structure

```text
orchestrator/runner.py       Daily pipeline phases, social skip, quality gate, sync
orchestrator/evaluator.py    Deterministic newsletter quality scoring
preflight/                   RSS, arXiv, GitHub, HN, Reddit, Twitter/X, Exa, YouTube
social/                      Social pipeline, approval gateway, posting clients
slack_bot/                   Fly Socket Mode bot and channel handlers
memory/                      Findings, dedupe, embeddings, feedback, preferences
dashboard/                   FastAPI dashboard and health endpoint
tests/                       pytest tests; network/API calls mocked
docs/runbooks/               Living repair runbooks and operational specs
.claude/handoffs/            Session handoffs and evidence logs
graphify-out/                Generated architecture graph artifacts
```

## Code Style

Prefer small, testable helpers and fail-closed approval behavior. Approval text
must be explicit; unclear text, pasted edits, or partial skip commands must not
publish.

```python
def parse_platform_approval(reply: str, platforms: list[str]) -> list[str]:
    reply_lower = reply.lower().strip()
    if reply_lower in {"all", "yes", "y", "go", "post", "approve", "approved"}:
        return platforms

    tokens = [token for token in re.split(r"[\s,/+&]+", reply_lower) if token and token != "and"]
    platform_map = {platform.lower(): platform for platform in platforms}
    if tokens and all(token in platform_map for token in tokens):
        return list(dict.fromkeys(platform_map[token] for token in tokens))

    return []
```

Conventions:

- Use `logging.getLogger(__name__)`.
- Use `str | None`, not `Optional[str]`.
- Mock Slack, network, subprocess, and Claude CLI in tests.
- Use structured return dictionaries for source health and quality gates.
- Keep user-visible Slack replies plain and actionable.
- Add comments only where the reason is non-obvious.

## Testing Strategy

- Unit tests first for approval parsing, source diagnostics, quality thresholds,
  duplicate angle checks, and Graphify freshness checks.
- Integration-style tests for runner phase behavior with mocks, especially
  `_phase_social`, preflight source counts, and newsletter evaluation.
- No tests should require live Slack, live social APIs, network, secrets, or
  real Claude calls.
- Live Slack/Fly smoke comes after local tests and deploy approval.
- A fix is not complete until the exact failed path has both a local test and a
  live or production-equivalent verification note.

## Boundaries

Always:

- Preserve user work. Inspect dirty files before editing or committing.
- Keep outbound posting behind explicit owner approval.
- Make disabled platforms produce manual-copy drafts instead of silent skips.
- Store the reason for degraded runs in logs/traces/briefing.
- Run focused tests for the touched area, then broader tests before deploy.
- Update the handoff/runbook with what was fixed, what was verified, and what
  remains.

Ask first:

- Running the full daily pipeline.
- Deploying to Fly.
- Enabling live LinkedIn or Bluesky posting.
- Changing database schema or adding migrations.
- Adding dependencies.
- Reading or printing Slack message bodies, subscriber data, secrets, or
  personal data.
- Changing newsletter editorial voice or quality thresholds away from the
  owner-approved defaults.

Never:

- Commit secrets, `social-config.json`, `users.json`, `data/*.db`, or Slack
  token output.
- Treat heartbeat health as proof that every Slack channel works.
- Turn a failed source into an empty result without an alertable reason.
- Send a low-quality newsletter silently when the pipeline knows inputs are
  degraded.
- Delete tests or lower thresholds just to get green output.

## Current Known Status

- `#mp-posts` Fly image packaging for `core/` was fixed and deployed in commit
  `a847ddf`.
- `#mp-skills` and `#mp-tips` short-input no-response behavior was fixed and
  deployed in commit `5cebd02`.
- `#mp-skills` and `#mp-tips` still need strict approval parsing; current code
  can default unclear replies to all platforms.
- The daily social phase still skips entirely when all platform configs are
  disabled.
- RSS, HN, Reddit, and Twitter/X have unresolved zero-source or backend-health
  evidence from the handoff.
- `tests/test_runner.py` is still excluded from GitHub Actions.
- Graphify freshness must be rechecked after this runbook and after future
  code changes.

## Implementation Progress

### 2026-06-26 Task 1 Baseline

Dirty files at goal start were docs-only:

- Modified: `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- Untracked: `docs/runbooks/2026-06-26-fix-first-recovery-runbook.md`
- Untracked: `docs/runbooks/2026-06-26-fix-first-recovery-implementation-plan.md`

Baseline tests:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q` -> 172 passed in 3.27s.
- `.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_evaluator.py tests/test_dedup_resurfacing.py tests/test_newsletter.py -q` -> 66 passed in 88.43s.
- `.venv/bin/python3 -m pytest tests/test_runner.py -q` -> 61 passed in 0.61s.

No live Slack post, email send, Fly deploy, full pipeline run, schema change, or
dependency change was performed for the baseline.

### 2026-06-26 Task 2 Shared Slack Approval Parser

Implemented `slack_bot.approval.parse_platform_approval()` and switched
`#mp-posts` to use it. The parser is fail-closed: only explicit affirmative
tokens or replies composed entirely of platform names approve posting.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 39 passed in 0.02s.
- `.venv/bin/python3 -m pytest tests/test_approval_parsing.py -q` -> 53 passed in 3.10s.

### 2026-06-26 Task 3 Strict Skills/Tips Approval

Switched `#mp-skills` and `#mp-tips` to the shared fail-closed approval parser.
Unclear replies such as `wait`, `hold on`, `skip linkedin`, pasted edits, or
partial sentences now post nothing.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 57 passed in 0.03s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q` -> 219 passed in 3.25s.

### 2026-06-26 Task 4 Draft Edit Helpers

Added pure draft edit helpers for `edit platform: replacement` replies. Edit
commands parse separately from approval and `parse_platform_approval()` treats
edit commands as no approval.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 64 passed in 0.03s.

### 2026-06-26 Task 5 `#mp-posts` Edit Flow

Wired draft edit helpers into `#mp-posts`. An `edit platform: replacement`
reply updates that draft, re-previews it, and waits for a second explicit
approval before posting. Invalid edit commands return an error and wait again.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 67 passed in 0.03s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q` -> 229 passed in 3.24s.

### 2026-06-26 Task 6 `#mp-skills` and `#mp-tips` Edit Flow

Wired the same draft edit loop into `#mp-skills` and `#mp-tips`. Platform
edits now update only the named draft, re-preview updated copy, and require a
second explicit approval. Invalid edit commands return an error and keep
waiting. `skip` or unclear text after an edit posts nothing.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 73 passed in 0.04s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q` -> 235 passed in 3.27s.

### 2026-06-26 Task 7 Manual-Copy Fallback

Added a structured `manual_only` posting result and wired it into `#mp-posts`,
`#mp-skills`, and `#mp-tips`. Disabled platforms now return the final draft as
manual copy without initializing live API clients. Client failures in skills
and tips are no longer reported as successful posts.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 79 passed in 0.19s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_posting.py -q` -> 132 passed in 0.18s.

### 2026-06-26 Task 8 Slack Bot Doctor

Added a redacted registry build report and a `doctor` command in
`#mp-briefing`. The report shows registered handler names, configured channel
count, missing channel config names, owner configured/missing, token source
labels, and heartbeat freshness without printing tokens, owner IDs, channel IDs,
message bodies, or secrets.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 81 passed in 0.11s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q` -> 243 passed in 3.23s.

### 2026-06-26 Task 9 Platform Publish Modes

Centralized platform publish-mode resolution in `social.posting`. Platforms
with `enabled: true` are live-capable, configured platforms with
`enabled: false` remain `manual_only` by default, explicit
`draft_enabled: false` becomes `skipped`, and unknown/missing platforms become
`error`. Slack post/skills/tips handlers now use the same mode helper and
canonical result statuses.

Verification:

- `.venv/bin/python3 -m pytest tests/test_social.py tests/test_posting.py -q` -> 58 passed in 0.12s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 81 passed in 0.10s.

### 2026-06-26 Task 10 SocialPipeline Draft-Only Path

Updated `SocialPipeline` to target draft-capable platforms, not only live
clients. With all platforms configured as `enabled: false`, the pipeline now
selects a topic, creates a brief, writes/reviews/humanizes/expedites drafts,
requests approval, and returns `manual_copy` results without initializing or
calling live posting clients. Writer errors in draft-only mode now surface as
structured `Writing: ...` errors instead of the old `No enabled platforms`
early exit.

Verification:

- `.venv/bin/python3 -m pytest tests/test_social.py -q` -> 46 passed in 0.11s.
- `.venv/bin/python3 -m pytest tests/test_social.py tests/test_runner.py -q` -> 107 passed in 0.63s.

### 2026-06-26 Task 11 Runner Social Draft-Only Phase

Updated `_phase_social()` so it skips only when no platform is draft-capable.
Disabled-but-draft-capable platform config now runs `SocialPipeline` and can
return `manual_copy` results. Manual-only, skipped, and error results are no
longer stored as live `posted` engagement signals.

Verification:

- `.venv/bin/python3 -m pytest tests/test_runner.py -q` -> 62 passed in 0.48s.
- `.venv/bin/python3 -m pytest tests/test_social.py tests/test_runner.py -q` -> 108 passed in 0.53s.

### 2026-06-26 Task 12 Briefing Social Draft State

Updated `#mp-briefing` pipeline summaries to distinguish live posted,
manual-copy draft, skipped, error, kill-day, and no-post states. Manual-copy
summaries include only platform names and status, not draft bodies.

Verification:

- `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 84 passed in 0.10s.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_runner.py -q` -> 146 passed in 0.52s.

### 2026-06-26 Task 13 Structured Source Health

Added per-source `source_health` output to `preflight.run_all()` while
preserving existing `items`, `assignments`, and `source_counts` keys. Each
source records `status`, `count`, `duration_ms`, and `reason`. Success,
healthy-empty, exception, timeout, and missing-tool failures are classified
without throwing away the rest of the preflight result.

Verification:

- `.venv/bin/python3 -m pytest tests/test_preflight.py::test_source_health_success tests/test_preflight.py::test_source_health_empty tests/test_preflight.py::test_source_health_exception tests/test_preflight.py::test_source_health_timeout tests/test_preflight.py::test_source_health_missing_cli -q` -> 5 passed in 0.01s.
- `.venv/bin/python3 -m pytest tests/test_preflight.py -q` -> 32 passed in 88.34s.

### 2026-06-26 Task 14 RSS Diagnostics

Added `preflight.rss.fetch_with_diagnostics()` and wired `run_all()` to merge
RSS diagnostics into `source_health`. RSS now reports normal, empty, partial,
timeout, and failed states; partial failures include structured `feed_errors`
with bad feed context while preserving healthy feed items.

Verification:

- `.venv/bin/python3 -m pytest tests/test_preflight.py::test_rss_fetch_with_diagnostics_normal_feed tests/test_preflight.py::test_rss_fetch_with_diagnostics_empty_feed tests/test_preflight.py::test_rss_fetch_with_diagnostics_names_bad_feed tests/test_preflight.py::test_source_health_merges_rss_diagnostics -q` -> 4 passed in 0.01s.
- `.venv/bin/python3 -m pytest tests/test_preflight.py -q` -> 36 passed in 88.45s.

### 2026-06-26 Task 15 Twitter/X and HN Diagnostics

Added diagnostic fetchers for Twitter/X and HN and wired them into
`run_all()` source health. Twitter/X failures now include backend, query, exit
code, and a safe stderr snippet. HN empty results include query/hours/point
thresholds, and HN failures include structured stderr context.

Verification:

- `.venv/bin/python3 -m pytest tests/test_preflight.py::test_hn_fetch_with_diagnostics_empty tests/test_preflight.py::test_hn_fetch_with_diagnostics_failure tests/test_preflight.py::test_twitter_fetch_with_diagnostics_cli_failure tests/test_preflight.py::test_twitter_fetch_with_diagnostics_success_shape -q` -> 4 passed in 0.01s.
- `.venv/bin/python3 -m pytest tests/test_preflight.py -q` -> 40 passed in 88.42s.

### 2026-06-26 Task 16 Reddit, Exa, and YouTube Availability

Added diagnostic fetchers for Reddit, Exa, and YouTube and wired `run_all()` to
use them. Backend/tool-off states now report `unavailable` instead of looking
like normal empty research. Runtime failures and timeouts report `failed` or
`timeout` with safe backend/query/channel context. `run_all()` now also returns
`source_health_summary`, which excludes unavailable optional sources from the
expected-source denominator while keeping configured failures visible as
degraded sources.

Verification:

- `.venv/bin/python3 -m pytest tests/test_preflight.py -q` -> 46 passed in 88.37s.

### 2026-06-26 Task 17 Runner and Briefing Source Health

Added source-health summary propagation from trend scan into the
`preflight_complete` trace event. The trace payload now includes the run date,
source counts, compact per-source `status`/`count`/`reason`, and the
`source_health_summary` while avoiding nested tool stderr payloads.
`#mp-briefing status` now reads the latest matching preflight trace and shows
responsive source count, unavailable sources, and degraded source names/statuses
without printing raw backend errors or Slack/message content.

Verification:

- `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseTrendScan::test_logs_source_health_summary_to_trace tests/test_slack_bot.py::TestBriefingSocialState::test_status_reports_source_health_from_latest_trace -q` -> 2 passed in 0.07s.
- `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_slack_bot.py tests/test_preflight.py -q` -> 194 passed in 88.94s.

### 2026-06-26 Task 18 Deterministic Quality Floor Helper

Added `orchestrator.evaluator.assess_quality_floor()` and configurable
`QUALITY_FLOOR_THRESHOLDS`. The helper reports `pass`, `degraded`, or
`fail_retryable` with metrics, thresholds, and reasons, but it does not change
newsletter send behavior yet.

Default thresholds:

- Overall score: `0.60`; retryable below `0.50`.
- Coverage score: `0.60`; retryable below `0.45`.
- Duplicate score: `0.80`; retryable below `0.60`.
- Source citation score: `0.50`; retryable below `0.35`.
- Agent coverage: `11` of target `13`; retryable below `8`.
- Finding volume: `70`; retryable below `40`.
- Source diversity: `4` source classes; retryable below `2`.
- Responsive source ratio: `0.75`; retryable below `0.50`.
- Unique URL ratio: `0.80`; retryable below `0.65`.
- Single-source dominance ceiling: `0.35`; retryable above `0.60`.

Verification:

- `.venv/bin/python3 -m pytest tests/test_evaluator.py::test_assess_quality_floor_passes_good_synthetic_run tests/test_evaluator.py::test_assess_quality_floor_marks_degraded_synthetic_run tests/test_evaluator.py::test_assess_quality_floor_marks_retryable_bad_synthetic_run -q` -> 3 passed in 0.01s.
- `.venv/bin/python3 -m pytest tests/test_evaluator.py tests/test_runner.py -q` -> 72 passed in 0.48s.

### 2026-06-26 Task 19 Duplicate Story and Angle Checks

Added `detect_duplicate_story_risk()` and wired its risk metric into
`assess_quality_floor()` without changing delivery behavior. The detector
flags canonical repeated URLs, near-title repeats, and repeated story angles
against recent findings. Exact URL repeats ignore tracking query strings and
can be bypassed only when a finding carries an explicit new-angle/follow-up
field or a different source date is detectable. The quality floor now includes
`duplicate_story_risk` with default ceiling `0.0` and retryable ceiling `0.20`.

Verification:

- `.venv/bin/python3 -m pytest tests/test_dedup_resurfacing.py::TestNewsletterDuplicateAngleGate::test_repeated_adjacent_day_story_fails_duplicate_angle_check tests/test_evaluator.py::test_duplicate_story_risk_flags_repeated_url tests/test_evaluator.py::test_quality_floor_flags_repeated_adjacent_day_angle tests/test_evaluator.py::test_duplicate_story_risk_does_not_overblock_related_story -q` -> 4 passed in 0.06s.
- `.venv/bin/python3 -m pytest tests/test_dedup_resurfacing.py tests/test_evaluator.py -q` -> 25 passed in 0.07s.

### 2026-06-26 Task 20 Agent Coverage Floor

Added `_assess_agent_coverage()` in the runner and wired it into
`_phase_research()` before cross-agent dedup mutates result lists. The research
phase now returns `research_degraded` and an `agent_coverage` block with
contributing-agent count, zero-finding agents, failed agents, status, retryable
flag, and reasons. Degraded coverage is logged to the `research_agent_coverage`
trace event. An 8-of-13 contributing-agent run is degraded; a 6-of-13 run is
`fail_retryable`; zero-finding and failed agents are named in the reasons.

Verification:

- `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseResearch::test_research_marks_8_of_13_agents_degraded tests/test_runner.py::TestPhaseResearch::test_research_marks_6_of_13_agents_retryable -q` -> 2 passed in 0.23s.
- `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_agents.py -q` -> 102 passed in 0.59s.

## Implementation Plan

### Phase 0: Baseline and Safety

Goal: prove the current state, protect user data, and avoid making the system
more dangerous while repairing it.

Verification checkpoint:

- `git status --short --branch` recorded.
- Current failing/unproven rows copied into this runbook.
- Focused tests run once to establish baseline.
- No live post, email send, Fly deploy, or full pipeline run without approval.

### Phase 1: Slack Safety and Channel Proof

Goal: every Slack content channel can reply, draft, edit, and wait for strict
owner approval without accidental posting.

Includes fix-first rows:

- `#mp-skills` approval
- `#mp-tips` approval
- Slack edit flow
- `#mp-posts` live posting manual fallback
- Slack bot local visibility
- Slack channel health

Verification checkpoint:

- Targeted Slack/social tests pass.
- Fly `/healthz` is ok after deploy.
- From phone, `help` or short test messages in `#mp-posts`, `#mp-skills`,
  `#mp-tips`, and `status` in `#mp-briefing` each receive a reply.
- A controlled draft waits for owner approval and does not post on unclear
  reply text.

### Phase 2: Daily Social Draft Mode

Goal: daily social no longer disappears just because live platform APIs are
disabled.

Includes fix-first rows:

- Daily social phase
- Slack approval for daily social

Verification checkpoint:

- Disabled platforms create Slack/manual-copy candidates rather than returning
  `{"skipped": true, "reason": "no platforms enabled"}`.
- No live post is sent unless a platform is enabled and the owner approves in
  Slack.
- The briefing or traces explain whether the run was draft-only, posted, or
  skipped with reason.

### Phase 3: Source Health

Goal: source failures become visible before synthesis, and each source either
produces items or reports a specific reason.

Includes fix-first rows:

- RSS preflight
- Reddit preflight
- Twitter/X preflight
- HN preflight
- Exa preflight
- YouTube preflight

Verification checkpoint:

- `preflight/run_all.py` returns per-source counts and health reasons.
- RSS names bad feeds or missing parser/config issues.
- Reddit is either configured and nonzero, or explicitly marked unavailable.
- Twitter/X query search returns entries, or the backend failure is named.
- HN returns entries or logs per-query diagnostics.
- Exa and YouTube production health is reported daily; local sandbox DNS
  failure is not treated as production proof.

### Phase 4: Newsletter Quality Recovery

Goal: bad inputs cannot silently produce weak, repetitive newsletters.

Includes fix-first rows:

- Newsletter quality floor
- Duplicate story control
- Agent coverage
- Source balance

Verification checkpoint:

- Below-floor source or agent coverage triggers retry/escalation before
  synthesis.
- The system still produces a daily issue by deadline, but degraded runs leave
  a Slack/trace incident and use the strongest source-grounded fallback rather
  than bland filler.
- Duplicate URL and semantic angle checks compare against recent issues.
- Source dominance is capped so arXiv or any one source cannot overfill the
  issue.

### Phase 5: Developer Workflow Guardrails

Goal: prevent the same regressions from landing again.

Includes fix-first rows:

- CI coverage
- Graphify freshness

Verification checkpoint:

- A critical subset of `tests/test_runner.py` runs in GitHub Actions.
- Graphify artifacts are updated and `graphify check-update .` is clean.
- The handoff links to this runbook and names the last verified commit.

## Task Checklist

### 1. Fix `#mp-skills` strict approval parsing

- Acceptance: replies such as `wait`, `hold on`, pasted replacement text, and
  `skip linkedin` post nothing.
- Verify: add tests in `tests/test_slack_bot.py`; run
  `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`.
- Files: `slack_bot/handlers/skills.py`, shared parser if extracted, tests.

### 2. Fix `#mp-tips` strict approval parsing

- Acceptance: behavior matches `#mp-posts`; only `all`, exact platform names,
  or clear affirmative approval can post.
- Verify: add tests for unclear, skip, single-platform, and all-platform
  replies.
- Files: `slack_bot/handlers/tips.py`, shared parser if extracted, tests.

### 3. Implement real Slack edit flow

- Acceptance: owner can reply `edit bluesky: ...`, `edit linkedin: ...`, or a
  clearly parsed replacement; the bot re-previews and requires a second
  approval before posting.
- Verify: mocked Slack thread tests show edit, re-preview, approval, and no
  post on first edit.
- Files: `slack_bot/handlers/base.py`, `posts.py`, `skills.py`, `tips.py`,
  tests.

### 4. Add manual-copy fallback for disabled platforms

- Acceptance: disabled LinkedIn/Bluesky returns formatted copy with a clear
  manual-post result instead of raising or silently skipping.
- Verify: mocked disabled config test returns draft text and `manual_only`
  status.
- Files: `social/posting.py`, Slack handlers, tests.

### 5. Prove `#mp-posts` live draft workflow

- Acceptance: URL or idea creates platform drafts, waits for approval, and
  does not publish unless the owner explicitly approves.
- Verify: local tests plus one Fly Slack smoke after deploy. Do not approve a
  live post unless the owner asks.
- Files: `slack_bot/handlers/posts.py`, `social/`, tests, handoff notes.

### 6. Document Fly-only versus local Slack bot status

- Acceptance: docs explain that production Slack bot runs on Fly, local
  `reports/slack-bot.log` is stale by design unless local launchd is restored,
  and `/healthz` only proves heartbeat.
- Verify: doc diff only; no behavior change.
- Files: this runbook, handoff, optionally `docs/SYSTEM-OVERVIEW.md`.

### 7. Add Slack bot doctor/status command

- Acceptance: `status` or `doctor` reports registered handlers, channel IDs or
  names, owner configured, token source class, heartbeat age, and last handler
  error without printing secrets.
- Verify: mocked handler tests and live `status` in `#mp-briefing`.
- Files: `slack_bot/registry.py`, `slack_bot/bot.py`,
  `slack_bot/handlers/briefing.py`, tests.

### 8. Make daily social phase draft-capable

- Acceptance: platform APIs disabled no longer makes `_phase_social` exit
  before candidate creation; it creates Slack/manual-copy candidates in
  draft-only mode.
- Verify: runner test with both platforms disabled asserts draft path is called
  and no posting client is called.
- Files: `orchestrator/runner.py`, `social/pipeline.py`, config loading, tests.

### 9. Route daily social candidates to Slack approval/control

- Acceptance: daily pipeline can send candidates to the Slack bot/channel
  workflow without auto-posting.
- Verify: mocked Slack client test; run result records `draft_only`,
  `awaiting_approval`, or `manual_only`.
- Files: `orchestrator/runner.py`, `social/approval.py`, Slack bot handler or
  briefing integration, tests.

### 10. Add source-health reporting to preflight

- Acceptance: every preflight source returns count, duration, status, and
  failure reason; zero counts are distinguishable from healthy empty results.
- Verify: tests simulate success, empty, timeout, missing CLI, invalid JSON.
- Files: `preflight/run_all.py`, source modules, tests.

### 11. Repair RSS diagnostics

- Acceptance: RSS either returns items or identifies bad feeds/dependency
  problems with per-feed detail.
- Verify: tests for parser import, bad feed, empty feed, and normal feed.
- Files: `preflight/rss.py`, `verticals/ai-tech/rss-feeds.json`,
  `requirements.txt` if needed, tests.

### 12. Restore or explicitly disable Reddit backend

- Acceptance: Reddit preflight returns items with an authenticated backend, or
  the run records `reddit unavailable: backend not configured` and excludes it
  from expected healthy-source counts.
- Verify: `agent-reach doctor --json` plus mocked preflight tests.
- Files: Agent Reach/OpenCLI config notes, `preflight/reddit.py`, tests.

### 13. Repair Twitter/X query search

- Acceptance: `twitter search "AI agents" -n 1 --json` or supported fallback
  returns parseable entries; HTTP/cookie failures are named in source health.
- Verify: live CLI smoke plus mocked CLI-shape tests.
- Files: `preflight/twitter.py`, tests, setup docs if needed.

### 14. Diagnose HN zero-source behavior

- Acceptance: HN logs per-query/API diagnostics and returns relevant builder
  or startup items when available.
- Verify: tests cover threshold adjustment and healthy mocked API response.
- Files: `preflight/hn.py`, tests.

### 15. Add Exa and YouTube production health alerts

- Acceptance: Exa and YouTube source count, CLI/backend status, and errors are
  visible in daily run output and Slack briefing.
- Verify: mocked source-health tests and production log/briefing evidence.
- Files: `preflight/exa.py`, `preflight/youtube.py`, `preflight/run_all.py`,
  briefing handler, tests.

### 16. Add newsletter quality floor with retry/escalation

- Acceptance: low source diversity, low agent coverage, low unique URL ratio,
  or duplicate angle risk triggers retry/escalation before delivery.
- Verify: runner/evaluator tests show a bad synthetic run does not silently
  send the first weak synthesis.
- Files: `orchestrator/evaluator.py`, `orchestrator/runner.py`, tests.

### 17. Add duplicate story and duplicate angle control

- Acceptance: exact URL repeats, near-title repeats, and semantic angle repeats
  across recent issues are flagged before synthesis/delivery.
- Verify: tests with known repeated stories from adjacent days fail the gate.
- Files: `orchestrator/evaluator.py`, `memory/embeddings.py` or existing
  dedupe helpers, tests.

### 18. Add agent coverage floor

- Acceptance: zero-finding or failed agents are retried where appropriate; a
  run with fewer than the accepted coverage floor is marked degraded before
  synthesis.
- Verify: tests simulate 6 of 13 agents contributing and assert retry or
  degraded status.
- Files: `orchestrator/agents.py`, `orchestrator/runner.py`, tests.

### 19. Add source balance weighting

- Acceptance: no single source class can dominate the newsletter candidate set;
  underrepresented healthy sources are boosted.
- Verify: synthetic arXiv-heavy findings produce a more balanced selected set.
- Files: `preflight/run_all.py`, synthesis selection in `orchestrator/runner.py`,
  tests.

### 20. Put critical runner tests back in CI and refresh Graphify

- Acceptance: GitHub Actions runs the critical runner phase tests, and Graphify
  reports match the current code/doc state.
- Verify: local CI-equivalent command passes; `.github/workflows/test.yml`
  includes the selected runner subset; `graphify check-update .` is clean.
- Files: `.github/workflows/test.yml`, tests if split, `graphify-out/`, handoff.

## Production Smoke Runbook

Run this only after local tests pass and the owner approves deploy/smoke.

1. Confirm clean intended diff:
   `git status --short --branch`
2. Deploy:
   `/Users/taylerramsay/.fly/bin/flyctl deploy --app mindpattern`
3. Check health:
   `curl -sS https://mindpattern.fly.dev/healthz`
4. Tail logs:
   `/Users/taylerramsay/.fly/bin/flyctl logs --app mindpattern --no-tail`
5. From Slack phone/client:
   - Send `help` in `#mp-posts`.
   - Send a short test in `#mp-skills`; expect guidance, not silence.
   - Send a short test in `#mp-tips`; expect guidance, not silence.
   - Send `status` in `#mp-briefing`; expect bot/channel/source health.
6. For a controlled draft test, use a harmless draft idea and do not approve
   live posting unless the owner explicitly asks.
7. Record the commit, Fly deploy result, channel names, and pass/fail notes in
   the handoff.

## Proposed Quality Floor Defaults

These defaults should be calibrated against the last known good month before
enforcement:

- Agent coverage: at least 11 of 13 agents contribute, or retry/mark degraded.
- Source health: at least 6 of 8 source classes healthy, unless an unavailable
  source is explicitly removed from expected count.
- Finding volume: at least 70 percent of the trailing 14-day median, not a
  hardcoded one-day number.
- Unique URLs: at least 80 percent of cited story candidates have unique URLs
  unless a repeated URL has a new date or clearly new angle.
- Source balance: no single source class should exceed 35 percent of selected
  newsletter candidates without an explicit reason.
- Duplicate angle: compare against at least the previous 3 issues before
  delivery.

## Open Questions

1. Should daily social draft candidates go to `#mp-posts`, `#mp-briefing`, or
   both?
2. What exact quality-floor numbers does the owner want after we compare
   trailing good-run metrics?
3. Should Reddit be a required healthy source, or optional until a backend is
   configured?
4. Should a final degraded newsletter require owner approval, or should it send
   by deadline with a Slack incident summary because the newsletter must ship
   daily?
5. Should Slack edit flow support freeform pasted replacement text, or only
   explicit commands such as `edit bluesky: ...`?

## Implementation Goal Prompt

Use this with `/goal` after the owner approves the spec:

```text
/goal Implement the fix-first recovery runbook in docs/runbooks/2026-06-26-fix-first-recovery-runbook.md.

Follow the phases in order. Do not implement new features from the feature idea table. Keep Slack-bot-first behavior, no auto-posting, and no live outbound post without explicit owner approval. Work in small tested commits. For each task, add or update tests before behavior changes, run the focused verification command, update the runbook/handoff with evidence, and stop before any live pipeline run, Fly deploy, schema change, dependency add, or platform enablement unless the owner explicitly approves.
```

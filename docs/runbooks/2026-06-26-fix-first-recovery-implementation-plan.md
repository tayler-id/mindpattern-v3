# Implementation Plan: Fix-First Recovery

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-26
> Spec: `docs/runbooks/2026-06-26-fix-first-recovery-runbook.md`

This plan breaks the fix-first recovery spec into small, ordered tasks. It is
not implementation. Do not start code changes from this plan until the owner
approves the task order and any open decisions.

## Overview

The repair must restore existing behavior without adding surprise automation:
Slack remains the control surface, outbound posting remains owner-approved,
daily social can draft even when platforms are disabled, source failures are
visible before synthesis, newsletter quality failures retry or escalate, and
CI/Graphify catch regressions.

The work is intentionally ordered so risky behavior changes are built on safer
shared primitives first. The first implementation slice is Slack safety because
approval parsing and edit semantics affect every outward post.

## Architecture Decisions

- Shared Slack approval parsing comes before handler-specific fixes. `#mp-posts`
  already has the safest parser; `#mp-skills` and `#mp-tips` should reuse the
  same rule instead of keeping substring/default-to-all parsing.
- Edits are a separate state transition, not approval. A reply that changes copy
  should re-preview the draft and require a second explicit approval.
- Disabled platforms mean manual-copy or draft-only, not "dead workflow".
  Posting clients should only run for enabled platforms after approval.
- Source health gets a structured contract before individual source repairs.
  Without that, each source will keep inventing its own zero-count meaning.
- Newsletter quality floors should be deterministic and calibrated from recent
  good runs before any hard block. The newsletter must still ship daily, but
  degraded output must be visible and source-grounded.
- Runner/CI changes wait until Slack and source contracts are tested locally.

## Dependency Graph

```text
Shared Slack approval parser
    |
    +-- skills/tips strict approval
    |
    +-- edit command parser and approval loop
    |       |
    |       +-- posts edit flow
    |       +-- skills/tips edit flow
    |
    +-- manual-copy fallback
            |
            +-- daily social draft-only mode
                    |
                    +-- runner no-platform behavior
                    +-- Slack briefing/status visibility

Source health contract
    |
    +-- RSS diagnostics
    +-- Twitter/HN diagnostics
    +-- Reddit/Exa/YouTube availability reporting
            |
            +-- newsletter quality floor inputs

Newsletter quality floor inputs
    |
    +-- duplicate angle checks
    +-- agent coverage floor
    +-- source balance weighting
            |
            +-- CI runner subset
            +-- Graphify freshness
```

## Task List

### Phase 0: Baseline

#### Task 1: Capture Baseline State

**Description:** Record the repo state and current focused test baseline before
any behavior changes. This creates a known starting point and protects unrelated
dirty work.

**Acceptance criteria:**
- [ ] Dirty files are listed and classified as docs-only, user work, or planned
      implementation work.
- [ ] Focused Slack/social, preflight/newsletter, and runner test baselines are
      recorded in the handoff or runbook.
- [ ] No live Slack post, email send, Fly deploy, or full pipeline run occurs.

**Verification:**
- [ ] Run `git status --short --branch`.
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q`.
- [ ] Run `.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_evaluator.py tests/test_dedup_resurfacing.py tests/test_newsletter.py -q`.
- [ ] Run `.venv/bin/python3 -m pytest tests/test_runner.py -q`.

**Dependencies:** None

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- `docs/runbooks/2026-06-26-fix-first-recovery-runbook.md`

**Estimated scope:** S

### Checkpoint: Baseline

- [ ] Owner can see exactly what is dirty and what is planned.
- [ ] Any failing baseline tests are recorded as pre-existing or blocking.

### Phase 1: Slack Safety Foundation

#### Task 2: Extract Shared Slack Approval Parser

**Description:** Move the strict `#mp-posts` approval logic into a reusable
Slack bot helper so all content channels interpret approval the same way.

**Acceptance criteria:**
- [ ] `all`, `yes`, `go`, `post`, `approve`, exact platform names, and platform
      lists approve only the intended platforms.
- [ ] `skip`, `wait`, `hold on`, `skip linkedin`, and pasted prose approve
      nothing.
- [ ] `#mp-posts` behavior remains equivalent to the current strict parser.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`.
- [ ] Add direct unit tests for the shared parser.

**Dependencies:** Task 1

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `slack_bot/handlers/base.py` or a new `slack_bot/approval.py`
- `tests/test_slack_bot.py`

**Estimated scope:** S

#### Task 3: Apply Strict Approval to `#mp-skills` and `#mp-tips`

**Description:** Replace substring/default-to-all approval logic in the skills
and tips handlers with the shared fail-closed parser.

**Acceptance criteria:**
- [ ] Unclear replies post nothing in both channels.
- [ ] Exact `bluesky`, `linkedin`, and `all` approvals still work.
- [ ] The bot replies with "skipped/nothing posted" instead of silently doing
      the wrong thing.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`.
- [ ] Add tests for unclear, skip-one, single-platform, and all-platform
      replies for both handlers.

**Dependencies:** Task 2

**Files likely touched:**
- `slack_bot/handlers/skills.py`
- `slack_bot/handlers/tips.py`
- `tests/test_slack_bot.py`

**Estimated scope:** S

#### Task 4: Add Draft Edit State Helpers

**Description:** Add small shared helpers for parsing edit commands and applying
draft replacements without posting. This is the foundation for a real edit loop.

**Acceptance criteria:**
- [ ] `edit bluesky: ...` and `edit linkedin: ...` update only the named
      platform draft.
- [ ] A replacement draft is re-previewed and cannot be treated as approval.
- [ ] Unknown platform edits and empty edits are rejected with a clear message.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`.
- [ ] Add unit tests for edit parsing and draft replacement.

**Dependencies:** Task 2

**Files likely touched:**
- `slack_bot/handlers/base.py` or a new `slack_bot/drafts.py`
- `tests/test_slack_bot.py`

**Estimated scope:** S

#### Task 5: Wire Edit Flow into `#mp-posts`

**Description:** Use the edit helpers in `#mp-posts` so an edit reply updates
the draft, shows a new preview, and waits for explicit approval again.

**Acceptance criteria:**
- [ ] First edit reply never posts.
- [ ] Re-preview includes updated copy and char counts.
- [ ] Posting only happens after the second reply is explicit approval.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py -q`.
- [ ] Add mocked thread tests for edit then approve, edit then skip, and unclear
      reply after edit.

**Dependencies:** Task 4

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

#### Task 6: Wire Edit Flow into `#mp-skills` and `#mp-tips`

**Description:** Bring the skills and tips channels to the same edit semantics
as `#mp-posts`.

**Acceptance criteria:**
- [ ] Skills and tips support platform-specific edit commands.
- [ ] Edited drafts re-preview and require second approval.
- [ ] Freeform unclear text is not treated as approval.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`.
- [ ] Add mocked tests for edit then approve in both handlers.

**Dependencies:** Tasks 3, 4

**Files likely touched:**
- `slack_bot/handlers/skills.py`
- `slack_bot/handlers/tips.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

#### Task 7: Add Manual-Copy Fallback for Disabled Platforms

**Description:** Make Slack handlers return useful manual-copy results when a
platform is disabled, instead of attempting a live client or making the channel
feel broken.

**Acceptance criteria:**
- [ ] Disabled platform returns `manual_only` or equivalent status with final
      copy.
- [ ] Enabled platform still uses the posting client after approval.
- [ ] Missing credentials or disabled config never gets reported as a successful
      live post.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_posting.py -q`.
- [ ] Add tests for disabled LinkedIn and disabled Bluesky.

**Dependencies:** Tasks 2, 3

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `slack_bot/handlers/skills.py`
- `slack_bot/handlers/tips.py`
- `social/posting.py` or a small helper module
- `tests/test_slack_bot.py`

**Estimated scope:** M

#### Task 8: Add Slack Bot Doctor/Status Surface

**Description:** Add a safe bot health report so `#mp-briefing` can prove
handler registration, channel config, owner config, heartbeat age, and recent
errors without printing secrets.

**Acceptance criteria:**
- [ ] `status` or `doctor` reports registered handler names and configured
      channel count.
- [ ] The output indicates owner ID configured/unconfigured without exposing
      token values.
- [ ] Missing channel IDs and skipped handlers are visible.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`.
- [ ] After deploy approval, live smoke `status` in `#mp-briefing`.

**Dependencies:** Task 1

**Files likely touched:**
- `slack_bot/registry.py`
- `slack_bot/bot.py`
- `slack_bot/handlers/briefing.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

### Checkpoint: Slack Safety

- [ ] `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q` passes.
- [ ] No handler has default-to-all approval behavior.
- [ ] Manual-copy fallback works with disabled platform config.
- [ ] Owner approves before any Fly deploy or live Slack smoke.

### Phase 2: Daily Social Draft Mode

#### Task 9: Define Platform Publish Modes

**Description:** Centralize how the social system distinguishes live-enabled,
manual-only, disabled, and unknown platform states.

**Acceptance criteria:**
- [ ] A platform with `enabled: true` is live-capable.
- [ ] A platform with valid writer config but `enabled: false` can still be
      draft/manual-only.
- [ ] The result shape clearly separates `posted`, `manual_only`, `skipped`,
      and `error`.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social.py tests/test_posting.py -q`.
- [ ] Add unit tests for platform mode resolution.

**Dependencies:** Task 7

**Files likely touched:**
- `social/pipeline.py`
- `social/posting.py` or a new small helper
- `tests/test_social.py`

**Estimated scope:** S

#### Task 10: Add Draft-Only Path to `SocialPipeline`

**Description:** Allow the daily social pipeline to select a topic, create a
brief, and write drafts for manual-only platforms without initializing live
posting clients.

**Acceptance criteria:**
- [ ] With no live-enabled platforms but draft-capable platforms present,
      pipeline returns drafts/manual-copy state instead of `No enabled platforms`.
- [ ] Posting clients are not initialized or called in draft-only mode.
- [ ] Topic/brief/draft errors still return structured errors.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social.py tests/test_runner.py -q`.
- [ ] Add tests with both platforms disabled and mocked writer output.

**Dependencies:** Task 9

**Files likely touched:**
- `social/pipeline.py`
- `tests/test_social.py`
- `tests/test_runner.py`

**Estimated scope:** M

#### Task 11: Update Runner Social Phase to Use Draft-Only Mode

**Description:** Replace the current early skip in `_phase_social` with a call
to the draft-only path when platforms are disabled but draft generation is
allowed.

**Acceptance criteria:**
- [ ] `_phase_social` no longer returns `reason: no platforms enabled` when
      draft-only mode is available.
- [ ] Result records draft/manual/posted/skipped status.
- [ ] Signals are only stored as posted when a live post actually succeeds.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_runner.py -q`.
- [ ] Add or update runner tests for disabled platforms and draft-only result.

**Dependencies:** Task 10

**Files likely touched:**
- `orchestrator/runner.py`
- `tests/test_runner.py`

**Estimated scope:** S

#### Task 12: Surface Social Draft State in Briefing

**Description:** Make the Slack briefing show whether daily social was posted,
manual-only, awaiting approval, skipped, or errored.

**Acceptance criteria:**
- [ ] Briefing distinguishes "No posts" from "Draft/manual-only created".
- [ ] The status output includes the social skipped/degraded reason when no
      draft was created.
- [ ] No Slack token or sensitive copy is printed in logs/tests.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_runner.py -q`.
- [ ] Add briefing tests with social result variants.

**Dependencies:** Tasks 8, 11

**Files likely touched:**
- `slack_bot/handlers/briefing.py`
- `orchestrator/runner.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

### Checkpoint: Daily Social

- [ ] Disabled platform config produces drafts/manual-copy, not a dead skip.
- [ ] No live post can occur without enabled platform plus explicit approval.
- [ ] Handoff records whether live Fly smoke was run or deferred.

### Phase 3: Source Health

#### Task 13: Add Structured Preflight Source Health Contract

**Description:** Add a per-source health structure around current preflight
fetches while preserving existing `items`, `source_counts`, and `assignments`
return keys.

**Acceptance criteria:**
- [ ] Each source records `status`, `count`, `duration_ms`, and `reason`.
- [ ] Exceptions are classified as failed with reason, not just zero items.
- [ ] Healthy empty results are distinguishable from failed empty results.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_preflight.py -q`.
- [ ] Add tests for success, healthy-empty, exception, timeout, and missing CLI.

**Dependencies:** Task 1

**Files likely touched:**
- `preflight/run_all.py`
- `tests/test_preflight.py`

**Estimated scope:** M

#### Task 14: Repair RSS Diagnostics

**Description:** Make RSS expose per-feed failures and parser/config problems
so zero RSS days identify the bad feed or dependency.

**Acceptance criteria:**
- [ ] Bad feed URL is named in source health.
- [ ] Missing or malformed feed data does not hide healthy feeds.
- [ ] RSS zero count reports either healthy-empty or specific failure reasons.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_preflight.py -q`.
- [ ] Add tests for bad feed, empty feed, and normal feed.

**Dependencies:** Task 13

**Files likely touched:**
- `preflight/rss.py`
- `preflight/run_all.py`
- `tests/test_preflight.py`

**Estimated scope:** M

#### Task 15: Repair Twitter/X and HN Diagnostics

**Description:** Make Twitter/X query failures and HN zero-source behavior
diagnosable from source health rather than silent count zero.

**Acceptance criteria:**
- [ ] Twitter CLI failures include backend, exit code, and safe stderr snippet.
- [ ] Supported Twitter JSON shapes still parse.
- [ ] HN logs/query diagnostics explain zero results or API failures.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_preflight.py -q`.
- [ ] Live smoke later: `twitter search "AI agents" -n 1 --json`.

**Dependencies:** Task 13

**Files likely touched:**
- `preflight/twitter.py`
- `preflight/hn.py`
- `preflight/run_all.py`
- `tests/test_preflight.py`

**Estimated scope:** M

#### Task 16: Report Reddit, Exa, and YouTube Availability

**Description:** Make optional/backended sources explicitly available,
unavailable, or failed so the pipeline stops treating backend-off as normal
empty research.

**Acceptance criteria:**
- [ ] Reddit backend-off is reported as unavailable unless configured.
- [ ] Exa and YouTube tool errors/timeouts surface in source health.
- [ ] Expected healthy-source count can exclude explicitly unavailable sources.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_preflight.py -q`.
- [ ] Live smoke later: `agent-reach doctor --json`, `yt-dlp --version`,
      `mcporter list exa --status`.

**Dependencies:** Task 13

**Files likely touched:**
- `preflight/reddit.py`
- `preflight/exa.py`
- `preflight/youtube.py`
- `preflight/run_all.py`
- `tests/test_preflight.py`

**Estimated scope:** M

#### Task 17: Surface Source Health in Runner and Briefing

**Description:** Carry source health from trend scan into traces and Slack
briefing so degraded inputs are visible before the newsletter is judged.

**Acceptance criteria:**
- [ ] `preflight_complete` trace includes source health summary.
- [ ] `#mp-briefing status` includes major source failures or unavailable
      sources.
- [ ] Existing source count consumers remain compatible.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_slack_bot.py tests/test_preflight.py -q`.

**Dependencies:** Tasks 13, 14, 15, 16

**Files likely touched:**
- `orchestrator/runner.py`
- `slack_bot/handlers/briefing.py`
- `tests/test_runner.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

### Checkpoint: Source Health

- [ ] Source zero counts have reasons.
- [ ] Major source failures can be seen before synthesis.
- [ ] Local sandbox network failures are not recorded as production proof.

### Phase 4: Newsletter Quality Recovery

#### Task 18: Add Deterministic Quality Floor Helper

**Description:** Create a deterministic helper that evaluates source health,
agent coverage, finding volume, unique URL ratio, duplicate risk, and source
balance without changing send behavior yet.

**Acceptance criteria:**
- [ ] Helper returns `pass`, `degraded`, or `fail_retryable` with reasons.
- [ ] Thresholds are configurable constants and documented in the runbook.
- [ ] No newsletter send behavior changes in this task.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_evaluator.py tests/test_runner.py -q`.
- [ ] Add tests for good, degraded, and retryable-bad synthetic runs.

**Dependencies:** Task 17

**Files likely touched:**
- `orchestrator/evaluator.py` or a new small quality module
- `tests/test_evaluator.py`
- `tests/test_runner.py`

**Estimated scope:** M

#### Task 19: Add Duplicate Story and Angle Checks

**Description:** Extend dedupe beyond exact title overlap by checking recent
URLs, near-title overlap, and semantic angle similarity against recent issues.

**Acceptance criteria:**
- [ ] Repeated URLs across recent issues are flagged unless they have a new
      source date or explicit new angle.
- [ ] Known repeated adjacent-day stories fail duplicate-angle checks.
- [ ] Distinct related stories are not over-blocked.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_dedup_resurfacing.py tests/test_evaluator.py -q`.

**Dependencies:** Task 18

**Files likely touched:**
- `orchestrator/evaluator.py` or quality helper
- `memory/embeddings.py` or existing dedupe helpers if needed
- `tests/test_dedup_resurfacing.py`
- `tests/test_evaluator.py`

**Estimated scope:** M

#### Task 20: Add Agent Coverage Floor

**Description:** Mark runs degraded or retryable when too few agents contribute
or too many agents return zero findings.

**Acceptance criteria:**
- [ ] A 6-of-13 or 8-of-13 contributing-agent run is marked degraded/retryable
      according to thresholds.
- [ ] Zero-finding agents are named in the quality reasons.
- [ ] The run result distinguishes degraded research from normal low-volume
      days.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_agents.py -q`.

**Dependencies:** Task 18

**Files likely touched:**
- `orchestrator/runner.py`
- `orchestrator/agents.py` if retry logic is changed
- `tests/test_runner.py`
- `tests/test_agents.py`

**Estimated scope:** M

#### Task 21: Add Source Balance Weighting

**Description:** Prevent one source class, such as arXiv, from dominating the
candidate set when other healthy source classes exist.

**Acceptance criteria:**
- [ ] Selected newsletter candidates cap single-source dominance by configured
      threshold.
- [ ] Underrepresented healthy source classes receive a boost.
- [ ] If only one source is healthy, the run is marked degraded instead of
      fabricating diversity.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_runner.py -q`.

**Dependencies:** Tasks 17, 18

**Files likely touched:**
- `preflight/run_all.py`
- `orchestrator/runner.py`
- `tests/test_preflight.py`
- `tests/test_runner.py`

**Estimated scope:** M

#### Task 22: Integrate Quality Floor into Synthesis/Delivery

**Description:** Use the quality floor to retry, escalate, or mark degraded
before delivery. The newsletter should still ship daily unless the owner
chooses a hard approval gate.

**Acceptance criteria:**
- [ ] Retryable bad synthesis triggers a bounded retry or source-grounded
      fallback before delivery.
- [ ] Degraded issue sends with visible Slack/trace incident summary.
- [ ] Delivery receipts are preserved; retries do not double-send.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_newsletter.py tests/test_newsletter_receipts.py -q`.

**Dependencies:** Tasks 18, 19, 20, 21

**Files likely touched:**
- `orchestrator/runner.py`
- `orchestrator/newsletter.py`
- `tests/test_runner.py`
- `tests/test_newsletter.py`
- `tests/test_newsletter_receipts.py`

**Estimated scope:** M

### Checkpoint: Newsletter Recovery

- [ ] Weak inputs cannot silently produce a weak newsletter.
- [ ] Degraded send path is visible in logs/traces/Slack.
- [ ] Daily newsletter contract remains intact.

### Phase 5: Workflow Guardrails and Production Proof

#### Task 23: Put Critical Runner Tests Back in CI

**Description:** Add a stable subset of runner tests to GitHub Actions so social
skip behavior, source-health propagation, and quality floors are checked before
merge.

**Acceptance criteria:**
- [x] CI no longer ignores all of `tests/test_runner.py`.
- [x] The selected runner subset is deterministic and offline.
- [x] Local CI-equivalent command passes.

**Verification:**
- [x] Run the updated CI-equivalent pytest command locally.
  `.venv/bin/python3 -m pytest tests/ -q --tb=short --ignore=tests/test_cors.py --ignore=tests/test_engagement_linkedin.py --ignore=tests/test_memory_cli.py --ignore=tests/test_runner.py -k "not test_blocked_when_at_limit and not test_get_model_research_agent"` -> 1154 passed, 3 deselected, 1 warning in 93.93s.
- [x] Run `.venv/bin/python3 -m pytest tests/test_runner.py -q` locally.
  Result: 69 passed in 0.58s.
- [x] Run the selected CI runner subset locally.
  `.venv/bin/python3 -m pytest -q --tb=short tests/test_runner.py::TestPhaseTrendScan tests/test_runner.py::TestPhaseResearch tests/test_runner.py::TestPhaseSynthesis tests/test_runner.py::TestPhaseSocial` -> 23 passed in 0.40s.

**Dependencies:** Tasks 11, 17, 22

**Files likely touched:**
- `.github/workflows/test.yml`
- `tests/test_runner.py` if split/stabilized

**Estimated scope:** S

#### Task 24: Refresh Graphify and Handoff Evidence

**Description:** Update Graphify after code/docs changes and record final
verification evidence for the next agent.

**Acceptance criteria:**
- [ ] `graphify update .` has been run after indexed code/docs changes.
- [ ] `graphify check-update .` is clean or any limitation is recorded.
- [ ] Handoff lists commit IDs, tests run, deploy status, live smoke status, and
      unresolved blockers.

**Verification:**
- [ ] Run `graphify update .`.
- [ ] Run `graphify check-update .`.
- [ ] Run `git status --short --branch`.

**Dependencies:** Task 23

**Files likely touched:**
- `graphify-out/`
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- `docs/runbooks/2026-06-26-fix-first-recovery-runbook.md`

**Estimated scope:** S

#### Task 25: Owner-Approved Production Smoke

**Description:** After tests and deploy approval, deploy and prove the high-risk
paths from Slack/Fly without approving a live platform post unless the owner
explicitly asks.

**Acceptance criteria:**
- [ ] Fly `/healthz` is ok after deploy.
- [ ] `#mp-posts`, `#mp-skills`, `#mp-tips`, and `#mp-briefing` respond from
      live Slack.
- [ ] Controlled draft does not post on unclear reply and produces manual-copy
      when platforms are disabled.

**Verification:**
- [ ] Run `/Users/taylerramsay/.fly/bin/flyctl deploy --app mindpattern`.
- [ ] Run `curl -sS https://mindpattern.fly.dev/healthz`.
- [ ] Tail logs with `/Users/taylerramsay/.fly/bin/flyctl logs --app mindpattern --no-tail`.
- [ ] Record live smoke notes in the handoff.

**Dependencies:** Tasks 8, 12, 22, 24

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`

**Estimated scope:** S

### Checkpoint: Complete

- [ ] All fix-first rows are fixed, intentionally disabled with alert, or
      blocked by a named external dependency.
- [ ] Focused and full relevant tests pass.
- [ ] Owner-approved Fly smoke is recorded or explicitly deferred.
- [ ] Repo is clean except for intentional committed work.

## Parallelization Opportunities

Safe to parallelize after Task 13 defines the source-health contract:

- Task 14 RSS diagnostics
- Task 15 Twitter/X and HN diagnostics
- Task 16 Reddit, Exa, and YouTube availability

Safe to parallelize after Task 18 defines the quality floor helper:

- Task 19 duplicate angle checks
- Task 20 agent coverage floor
- Task 21 source balance weighting

Should remain sequential:

- Tasks 2 through 7, because they share Slack approval/edit/manual-copy
  primitives.
- Tasks 9 through 12, because runner behavior depends on social mode semantics.
- Task 22, because it depends on the source, duplicate, agent, and balance
  signals.
- Tasks 23 through 25, because CI, Graphify, deploy, and smoke should happen
  after implementation is stable.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Approval parser regression posts unexpectedly | High | Fail-closed parser, handler tests for unclear text, no live posting smoke without owner approval. |
| Daily social draft mode accidentally posts | High | Separate platform mode from client initialization; assert posting clients are not called in draft-only tests. |
| Quality floor blocks daily newsletter entirely | High | Start as degraded/retry/escalate, not hard block, until owner approves hard gating. |
| Source-health contract breaks existing consumers | Medium | Preserve existing `source_counts`, `items`, and `assignments` keys while adding new `source_health`. |
| CI becomes too slow or flaky | Medium | Add a stable runner subset first; keep network and Claude calls mocked. |
| Graphify artifacts churn unexpectedly | Low | Run Graphify only after implementation slices; record if no topology changes. |

## Open Questions

1. Should daily social draft candidates post to `#mp-posts`, `#mp-briefing`, or
   both?
2. Should degraded newsletters always send by deadline, or should a hard Slack
   approval gate be allowed for severe quality failures?
3. Is Reddit required for a healthy run, or optional until a backend is
   configured?
4. Should edit flow allow freeform pasted replacement text, or only explicit
   `edit platform: ...` commands?
5. What exact source/agent thresholds should be locked after comparing against
   last month's good runs?

## Implementation Goal Prompt

Use this after the owner approves the plan:

```text
/goal Implement docs/runbooks/2026-06-26-fix-first-recovery-implementation-plan.md task by task.

Follow dependency order. Do not add new product features. Keep Slack-bot-first behavior, fail-closed approval parsing, and no live outbound post without explicit owner approval. For each task: write/update tests first, implement the smallest change, run the task verification command, update the runbook/handoff with evidence, and stop before any Fly deploy, full daily pipeline run, live platform enablement, dependency add, or schema change unless the owner explicitly approves.
```

# Implementation Plan: Feature 24 - Ask Follow-Up Research

> Status: In progress
> Owner: Tayler
> Author: Codex
> Created: 2026-06-26
> Spec: `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md`

This plan breaks the Feature 24 runbook into small, ordered tasks. It is not
implementation. Do not start code changes from this plan until the owner
approves the task order and any open decisions.

## Overview

Build "Ask Follow-Up" first: an owner-only Slack command that runs scoped
follow-up research and returns findings in-thread without running the daily
pipeline, sending a newsletter, posting social content, syncing Fly, or changing
schema.

The optional Slack Social Ideas Desk is a later layer. It can help with social
post ideas and call the same follow-up research flow, but it must not review,
select, approve, block, write, or send newsletter stories. The scheduled daily
newsletter must continue to research, write, and send through the normal
quality-gated pipeline without waiting for Slack feedback.

## Architecture Decisions

- Implement Ask Follow-Up as a small service in `orchestrator/followup.py`, not
  as a new runner phase and not as a call to `run.py`.
- Keep Slack thread replies ignored in `slack_bot/bot.py`. Approval-thread
  follow-up must be intercepted inside the existing polling loops so approval
  replies do not start a second pipeline.
- Use deterministic dry-run behavior and mocks in tests. No focused test should
  require Slack tokens, Claude, network access, Fly, local browser cookies, or
  private `memory.db` contents.
- Use existing `orchestrator.traces_db.log_event()` for trace events. Do not add
  schema for the MVP unless the owner explicitly approves it.
- Store follow-up artifacts under `reports/ramsay/followups/` and social idea
  feedback under uncommitted `data/social-ideas/`. Do not commit generated
  artifacts, databases, Slack bodies, subscriber data, `users.json`, or
  `social-config.json`.
- MVP Social Ideas Desk should use an existing social channel command, likely
  `#mp-posts`, to avoid Slack app/channel configuration churn. A new
  `#mp-social-ideas` channel or Block Kit buttons require owner approval.

## Dependency Graph

```text
Follow-up parser contract
    |
    +-- dry-run follow-up service
    |       |
    |       +-- safe trace/artifact writer
    |       +-- live-agent adapter behind explicit runtime boundary
    |
    +-- #mp-briefing follow-up command
    |
    +-- approval-loop follow-up interceptor
            |
            +-- #mp-posts draft-thread follow-up
            +-- #mp-skills/#mp-tips draft-thread follow-up
            +-- no-post/no-send/no-runner regressions

Social idea parser/contract
    |
    +-- fixture-backed idea loader
    +-- safe feedback store
            |
            +-- social ideas Slack command
            +-- social idea actions
                    |
                    +-- draft/manual-copy handoff
                    +-- follow-up research handoff
                    +-- no-newsletter-gate regressions
```

## Done Status Table

Keep the `Done` column in this table. Future agents should update it in place
instead of deleting the column.

| Task | Title | Done | Evidence / remaining work |
|---|---|---|---|
| 1 | Capture baseline and guardrails | Yes | `git status --short --branch`, `git diff --stat`, Slack/social/approval baseline, and runner dry-run baseline passed before edits. |
| 2 | Follow-up parser and safe request contract | Yes | Added `parse_followup_request()` and parser/redaction tests. |
| 3 | Deterministic dry-run follow-up service | Yes | Added `run_followup_research(..., dry_run=True)` and dry-run no-agent-call test. |
| 4 | Live-agent adapter with degraded results | Yes | Added injected live-agent boundary with failed/degraded result test. |
| 5 | Safe trace and artifact writer | Yes | Added trace/artifact writing with redaction test using temp `traces.db`. |
| 6 | `#mp-briefing` follow-up command | Yes | `BriefingHandler` handles `follow up:` with acknowledgement/result replies and tests. |
| 7 | Approval-loop follow-up interceptor | Yes | Added `slack_bot/handlers/followup.py`; targeted Slack tests verify follow-up replies are consumed before edit/approval parsing. |
| 8 | `#mp-posts` draft-thread follow-up | Yes | `PostsHandler._run_and_approve()` handles `follow up:` then keeps waiting; test proves `_post_to_platforms()` is not called. |
| 9 | `#mp-skills` and `#mp-tips` draft-thread follow-up | Yes | `SkillsHandler` and `TipsHandler` handle `follow up:` then keep waiting; tests prove `_post()` is not called and `skip` still cancels. |
| 10 | Ask Follow-Up safety regression suite | Yes | Added import/token guards for runner/newsletter/social/Fly delivery paths and `MP_DISABLE_OUTBOUND=1` dry-run boundary test; Task 10 verification passed. |
| 11 | Social Ideas parser and idea contract | No | Social-only commands; newsletter commands rejected. |
| 12 | Fixture-backed social idea loader | No | CI does not depend on private DB data. |
| 13 | Safe social idea feedback store | No | JSON artifact contract; no schema. |
| 14 | Social Ideas Slack command | No | `social ideas` posts a numbered social idea list. |
| 15 | Social Ideas actions | No | `draft/save/revise/reject/follow up` are safe. |
| 16 | Social Ideas safety regression suite | No | Proves no live post and no newsletter gate. |
| 17 | Docs, handoff, and Done evidence | No | Runbook/handoff current for next agent. |
| 18 | Graphify, CI, commit, push | No | Graph fresh, tests pass, clean status. |
| 19 | Optional owner-approved live smoke | Deferred | Requires explicit deploy/live Slack approval. |

## Task List

### Phase 0: Baseline

#### Task 1: Capture Baseline and Guardrails

**Description:** Record the current repo state and focused test baseline before
any implementation. This protects unrelated user changes and establishes that
the new feature starts from a known-good `main`.

**Acceptance criteria:**
- [ ] Dirty files are listed and classified before edits.
- [ ] Focused Slack, approval, social, and runner safety tests are recorded.
- [ ] No live Slack command, email send, social post, Fly deploy, or full daily
      pipeline run occurs.

**Verification:**
- [ ] Run `git status --short --branch`.
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_approval.py tests/test_social.py -q`.
- [ ] Run `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`.

**Dependencies:** None

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md`

**Estimated scope:** S

### Checkpoint: Baseline

- [ ] Owner can see exactly what is dirty.
- [ ] Any pre-existing test failures are recorded before implementation.

### Phase 1: Ask Follow-Up Core

#### Task 2: Add Follow-Up Parser and Safe Request Contract

**Description:** Add a pure parser/normalizer for owner follow-up requests. It
should accept clear commands and produce a stable request object with safe
metadata for tracing and Slack formatting.

**Acceptance criteria:**
- [ ] Accepts `follow up:`, `follow-up:`, and `research this:`.
- [ ] Rejects empty, too-short, and vague commands with a helpful error.
- [ ] Produces a redacted preview and hashable query field without storing raw
      Slack user IDs or full message bodies.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py -q`.

**Dependencies:** Task 1

**Files likely touched:**
- `orchestrator/followup.py`
- `tests/test_followup_research.py`

**Estimated scope:** S

#### Task 3: Add Deterministic Dry-Run Follow-Up Service

**Description:** Implement the first service path around the parser. In dry-run
or outbound-disabled mode it returns deterministic findings and never calls
Claude, network helpers, Slack, email, social posting, Fly, or `run.py`.

**Acceptance criteria:**
- [ ] Dry-run returns 3-7 structured findings, `why_this_matters`, source fields
      where available, degraded status, and a recommended next action.
- [ ] `MP_DISABLE_OUTBOUND=1` prevents Claude/network execution.
- [ ] Unit tests prove no subprocess/agent/network boundary is called in dry-run.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py -q`.

**Dependencies:** Task 2

**Files likely touched:**
- `orchestrator/followup.py`
- `tests/test_followup_research.py`

**Estimated scope:** S

#### Task 4: Add Live-Agent Adapter with Degraded Results

**Description:** Add the mocked live execution adapter that can call existing
agent execution when outbound access is allowed. It should be easy to test by
injecting/mocking the runner boundary.

**Acceptance criteria:**
- [ ] The adapter uses existing agent execution patterns, not a new pipeline
      framework.
- [ ] Agent failures return a visible degraded/failed result instead of silent
      empty output.
- [ ] Tests mock the agent boundary and prove no live Claude call occurs.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py -q`.

**Dependencies:** Task 3

**Files likely touched:**
- `orchestrator/followup.py`
- `tests/test_followup_research.py`

**Estimated scope:** S

#### Task 5: Add Safe Trace and Artifact Writing

**Description:** Persist a safe trace event and optional markdown artifact for
completed/degraded follow-up runs. Use existing trace schema and test with temp
paths.

**Acceptance criteria:**
- [ ] Completion and failure paths can log `followup_research_complete` or
      `followup_research_failed` through existing `traces_db.log_event()`.
- [ ] Artifact paths live under `reports/ramsay/followups/`.
- [ ] Trace payloads and artifacts exclude raw Slack IDs, tokens, subscriber
      data, full Slack message bodies, `users.json`, and `social-config.json`.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_traces_db.py -q`.

**Dependencies:** Tasks 3-4

**Files likely touched:**
- `orchestrator/followup.py`
- `tests/test_followup_research.py`

**Estimated scope:** S

### Checkpoint: Follow-Up Core

- [ ] Follow-up service works in deterministic dry-run.
- [ ] Safe trace/artifact behavior is tested.
- [ ] No Slack handler code has been changed yet.

### Phase 2: Slack Ask Follow-Up Integration

#### Task 6: Wire `#mp-briefing` Follow-Up Command

**Description:** Add a command branch in `BriefingHandler` so the owner can send
`follow up: <topic>` and receive an acknowledgement plus the final result in the
same thread.

**Acceptance criteria:**
- [ ] `#mp-briefing` handles accepted follow-up commands and rejects vague ones.
- [ ] The handler posts a short acknowledgement before longer work.
- [ ] The handler formats completed/degraded/failed results for phone-readable
      Slack review.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_followup_research.py -q`.

**Dependencies:** Tasks 2-5

**Files likely touched:**
- `slack_bot/handlers/briefing.py`
- `tests/test_slack_bot.py`
- `tests/test_followup_research.py`

**Estimated scope:** S

#### Task 7: Add Approval-Loop Follow-Up Interceptor

**Description:** Add a shared helper that approval loops can call after
`wait_for_reply()`. It should detect `follow up:` replies, run follow-up
research, post the result, and tell the loop to keep waiting for edit/skip/live
posting approval.

**Acceptance criteria:**
- [ ] Non-follow-up replies pass through unchanged.
- [ ] Follow-up replies are handled without approving, skipping, posting, or
      losing the draft.
- [ ] The helper is unit-tested without Slack tokens or live agent calls.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_slack_bot.py -q`.

**Dependencies:** Tasks 2-6

**Files likely touched:**
- `slack_bot/handlers/base.py` or new `slack_bot/handlers/followup.py`
- `tests/test_slack_bot.py`
- `tests/test_followup_research.py`

**Estimated scope:** S

#### Task 8: Wire `#mp-posts` Draft-Thread Follow-Up

**Description:** Use the interceptor inside `PostsHandler._run_and_approve()` so
follow-up replies can enrich a draft thread without becoming approval text.

**Acceptance criteria:**
- [ ] `follow up:` in a `#mp-posts` approval thread posts a follow-up result and
      keeps waiting.
- [ ] After follow-up, explicit `skip` still cancels and explicit platform
      approval still works.
- [ ] `_post_to_platforms()` is not called because of the follow-up reply.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_followup_research.py tests/test_approval.py -q`.

**Dependencies:** Task 7

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `tests/test_slack_bot.py`

**Estimated scope:** S

#### Task 9: Wire `#mp-skills` and `#mp-tips` Draft-Thread Follow-Up

**Description:** Add the same interceptor to the skills and tips approval loops
so follow-up is consistent across existing Slack content channels.

**Acceptance criteria:**
- [ ] `follow up:` in `#mp-skills` and `#mp-tips` posts research and keeps
      waiting for a real edit/skip/approval reply.
- [ ] Follow-up replies do not call `_post()`.
- [ ] Existing edit and fail-closed approval tests still pass.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_approval.py tests/test_approval_parsing.py tests/test_followup_research.py -q`.

**Dependencies:** Task 8

**Files likely touched:**
- `slack_bot/handlers/skills.py`
- `slack_bot/handlers/tips.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

**Implementation evidence:**
- Added shared helper `slack_bot/handlers/followup.py`.
- Wired `PostsHandler`, `SkillsHandler`, and `TipsHandler` approval loops to
  consume `follow up:` before draft edit or approval parsing.
- Verification passed:
  `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsEditFlow::test_followup_reply_runs_research_and_keeps_waiting tests/test_slack_bot.py::TestSkillsTipsEditFlow::test_followup_reply_runs_research_and_keeps_waiting tests/test_followup_research.py -q`
  -> 9 passed.
- Verification passed:
  `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsEditFlow tests/test_slack_bot.py::TestSkillsTipsEditFlow tests/test_slack_bot.py::TestBriefingFollowupCommand -q`
  -> 14 passed.

#### Task 10: Add Ask Follow-Up Safety Regression Suite

**Description:** Add cross-boundary tests proving Ask Follow-Up cannot trigger
the daily runner, newsletter delivery, live social posting, Fly sync, or
surprise draft creation.

**Acceptance criteria:**
- [ ] Tests fail if follow-up calls `run.py`, runner phases, social posting, or
      sync helpers.
- [ ] Tests prove `MP_DISABLE_OUTBOUND=1` keeps the path deterministic.
- [ ] Newsletter quality gates and runner tests are unchanged.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q`.

**Dependencies:** Tasks 6-9

**Files likely touched:**
- `tests/test_followup_research.py`
- `tests/test_social.py` or `tests/test_runner.py`

**Estimated scope:** S

**Implementation evidence:**
- Added follow-up service guards proving no imports/references to daily runner,
  newsletter delivery, social posting, or Fly sync boundaries.
- Added `MP_DISABLE_OUTBOUND=1` regression proving the default agent runner is
  not called and deterministic dry-run is selected.
- Verification passed:
  `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q`
  -> 60 passed.

### Checkpoint: Ask Follow-Up MVP

- [ ] `#mp-briefing` follow-up is implemented and tested.
- [ ] Draft-thread follow-up is implemented in existing approval loops.
- [ ] No tests require Slack tokens, Claude, network, Fly, or private DB data.
- [ ] The daily newsletter path is not modified.

### Phase 3: Optional Social Ideas Desk

#### Task 11: Add Social Ideas Parser and Contract

**Description:** Define the Social Ideas Desk command grammar and stable idea
object. Keep it explicitly social-only.

**Acceptance criteria:**
- [ ] Accepts `social ideas`, `post ideas`, and `today's social ideas`.
- [ ] Accepts thread commands `draft <n>`, `save <n>`, `revise <n>: ...`,
      `reject <n>: ...`, `follow up <n>: ...`, and `status`.
- [ ] Rejects newsletter-control wording such as `approve story`,
      `send newsletter`, `exclude story`, or vague commands with no state
      change.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py -q`.

**Dependencies:** Task 10

**Files likely touched:**
- `orchestrator/social_ideas.py`
- `tests/test_social_ideas_desk.py`

**Estimated scope:** S

#### Task 12: Add Fixture-Backed Social Idea Loader

**Description:** Load ranked social ideas from deterministic fixtures first, then
from safe current-day artifacts or reports when available. Avoid CI dependence
on private `memory.db`.

**Acceptance criteria:**
- [ ] Fixture loader returns stable ranked ideas in tests.
- [ ] Real loader gracefully degrades when memory/report artifacts are missing.
- [ ] Loader does not expose private DB rows or raw Slack content in Slack text.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py -q`.

**Dependencies:** Task 11

**Files likely touched:**
- `orchestrator/social_ideas.py`
- `tests/test_social_ideas_desk.py`
- `tests/fixtures/` if a fixture is added

**Estimated scope:** S

#### Task 13: Add Safe Social Idea Feedback Store

**Description:** Persist Social Ideas Desk feedback to an uncommitted JSON
artifact without schema changes.

**Acceptance criteria:**
- [ ] `draft_requested`, `saved`, `rejected`, `revision_requested`, and
      `followup_requested` states are persisted with safe metadata only.
- [ ] Store path is configurable in tests and defaults under
      `data/social-ideas/`.
- [ ] Full Slack message bodies, user IDs, tokens, subscriber data, databases,
      `users.json`, and `social-config.json` are not written.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py -q`.

**Dependencies:** Task 12

**Files likely touched:**
- `orchestrator/social_ideas.py`
- `tests/test_social_ideas_desk.py`

**Estimated scope:** S

#### Task 14: Wire Social Ideas Slack Command

**Description:** Add the Slack command surface for listing ideas. MVP should use
the existing `#mp-posts` command path unless the owner approves a new channel.

**Acceptance criteria:**
- [ ] Owner message `social ideas` posts a numbered idea list in-thread.
- [ ] Empty/degraded idea lists return a clear degraded notice.
- [ ] No new Slack channel config is required for MVP.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_slack_bot.py -q`.

**Dependencies:** Tasks 11-13

**Files likely touched:**
- `slack_bot/handlers/posts.py` or `slack_bot/handlers/social_ideas.py`
- `orchestrator/social_ideas.py`
- `tests/test_social_ideas_desk.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

#### Task 15: Wire Social Ideas Actions

**Description:** Implement thread actions for social ideas. `draft <n>` should
create or prioritize a Slack draft/manual-copy candidate, not publish live.
`follow up <n>` should call the Ask Follow-Up service.

**Acceptance criteria:**
- [ ] `save`, `reject`, and `revise` update safe feedback state only.
- [ ] `follow up <n>` returns scoped research in the thread.
- [ ] `draft <n>` creates or prioritizes a Slack draft path but cannot publish
      live without the existing explicit approval flow.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_followup_research.py tests/test_social.py -q`.

**Dependencies:** Task 14

**Files likely touched:**
- `slack_bot/handlers/posts.py` or `slack_bot/handlers/social_ideas.py`
- `orchestrator/social_ideas.py`
- `tests/test_social_ideas_desk.py`

**Estimated scope:** M

#### Task 16: Add Social Ideas Safety Regression Suite

**Description:** Prove the optional Social Ideas Desk cannot block or alter the
newsletter and cannot post live on its own.

**Acceptance criteria:**
- [ ] Tests prove Social Ideas Desk does not call newsletter send, runner
      synthesis/delivery phases, Fly sync, or live social posting.
- [ ] Tests prove unclear social idea actions change no state.
- [ ] Existing `#mp-posts`, `#mp-skills`, and `#mp-tips` approval behavior still
      fails closed.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_slack_bot.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q`.

**Dependencies:** Task 15

**Files likely touched:**
- `tests/test_social_ideas_desk.py`
- `tests/test_slack_bot.py`
- `tests/test_social.py` or `tests/test_runner.py`

**Estimated scope:** S

### Checkpoint: Social Ideas MVP

- [ ] Social Ideas Desk is social-only.
- [ ] The newsletter pipeline still researches, writes, and sends without Slack
      feedback.
- [ ] No live social post happens without existing explicit owner approval.

### Phase 4: Documentation, Graph, and Release Hygiene

#### Task 17: Update Docs, Handoff, and Done Evidence

**Description:** Update the runbook task table, this implementation plan, and
the handoff with exact commands, results, blockers, and any deferred live smoke.

**Acceptance criteria:**
- [ ] Done columns are updated in place.
- [ ] Handoff summarizes what changed and what remains.
- [ ] Any blocked/deferred owner-approval work is named explicitly.

**Verification:**
- [ ] Run `git diff --check`.

**Dependencies:** Tasks 10 and optionally 16

**Files likely touched:**
- `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md`
- `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-implementation-plan.md`
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`

**Estimated scope:** S

#### Task 18: Refresh Graphify, Run CI-Equivalent Tests, Commit, and Push

**Description:** Complete local verification, refresh Graphify, make an atomic
commit or phase commits, push to `main`, and watch CI.

**Acceptance criteria:**
- [ ] Focused tests for changed areas pass.
- [ ] Critical runner phase suite still passes locally or in CI.
- [ ] `graphify update .` and `graphify check-update .` pass.
- [ ] Repo is clean or all dirty files are explained.

**Verification:**
- [ ] Run `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_slack_bot.py tests/test_approval.py tests/test_social.py -q`.
- [ ] Run `.venv/bin/python3 -m pytest -q --tb=short tests/test_runner.py::TestPhaseTrendScan tests/test_runner.py::TestPhaseResearch tests/test_runner.py::TestPhaseSynthesis tests/test_runner.py::TestPhaseSocial`.
- [ ] Run `graphify update .`.
- [ ] Run `graphify check-update .`.
- [ ] Run `gh run watch <run-id> --exit-status` after push.

**Dependencies:** Task 17

**Files likely touched:**
- `graphify-out/`
- changed code/tests/docs

**Estimated scope:** S

#### Task 19: Optional Owner-Approved Live Smoke

**Description:** Only after owner approval, deploy or use the live bot to smoke
test real Slack commands. This is not required for local implementation.

**Acceptance criteria:**
- [ ] Owner explicitly approves deploy/live Slack smoke.
- [ ] `follow up:` in `#mp-briefing` returns a result and triggers no forbidden
      side effects.
- [ ] `social ideas` returns social ideas and no live post.

**Verification:**
- [ ] Owner-approved Fly/Slack smoke checklist from the runbook.

**Dependencies:** Task 18

**Files likely touched:**
- None unless the smoke finds a bug.

**Estimated scope:** S

## Parallelization Opportunities

- Tasks 2-5 are mostly sequential because they define one service contract.
- After Task 5, Task 6 and Task 7 can be developed by different agents if they
  share the same `orchestrator.followup` API.
- Tasks 8 and 9 can be parallelized after Task 7 because they touch separate
  handlers.
- Tasks 11-13 can be parallelized after the social idea contract is agreed.
- Task 16 should be sequential after Tasks 14-15 because it tests the integrated
  behavior.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Follow-up thread reply is treated as approval | High | Intercept inside approval loops before approval parsing; keep global thread routing ignored. |
| Follow-up becomes a hidden daily pipeline | High | Service must not call `run.py` or runner phases; add regression tests. |
| Social Ideas Desk leaks into newsletter control | High | Social-only command names and tests for no newsletter phase calls. |
| Live tests call Claude/network in CI | Medium | Dry-run default, dependency injection, mocks around agent boundary. |
| Private local DB dependency breaks CI | Medium | Fixture-backed loaders and graceful missing-data behavior. |
| Raw Slack/personal data leaks to traces or docs | High | Store hashes/previews only and test artifact payloads. |
| Slack app config work expands scope | Medium | Use existing `#mp-posts` for MVP; require owner approval for new channels/buttons. |

## Open Questions

1. For MVP, should Social Ideas Desk be implemented in `#mp-posts` only, or is a
   new `#mp-social-ideas` channel approved?
2. Should `draft <n>` immediately run the existing social draft pipeline and
   wait for approval, or create a manual-copy artifact first?
3. Should live follow-up research be allowed in the first implementation, or
   should the first merged version ship dry-run/local-only until a separate
   owner-approved smoke?

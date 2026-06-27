# Spec and Runbook: Feature 24 - Ask Follow-Up Research

> Status: Draft for owner review
> Owner: Tayler
> Author: Codex
> Created: 2026-06-26
> Source evidence: `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
> Feature row: New Feature Ideas table, row 24

This runbook turns feature idea 24, `"Ask Follow-Up" Research Button`, into an
implementation-ready spec for a future `/goal` run. It does not implement the
feature yet.

## Assumptions

1. "24" means the new-feature table row 24, `"Ask Follow-Up" Research Button`,
   not the fix-first row 24, "Source balance weighting", which is already done.
2. The first version should be Slack-bot-first and command-first. A true Slack
   Block Kit button can be added only if the current Slack app interactivity
   wiring supports it or the owner approves that setup work.
3. A follow-up run is not a full daily pipeline run. It must not send a
   newsletter, sync Fly, create social drafts, post social content, or touch
   subscriber delivery.
4. Follow-up research is owner-triggered only. The bot must ignore non-owner
   requests and fail closed when owner identity is missing.
5. Follow-up output should return to Slack in the triggering thread and write a
   local artifact for auditability, but should not require a database schema
   change for the MVP.
6. The feature should reuse existing agent execution and tracing patterns where
   possible instead of creating a second pipeline framework.

If any of these are wrong, update this runbook before implementation starts.

## Objective

Build a controlled way for Tayler to ask, from Slack, "go deeper on this story"
without running the whole newsletter pipeline.

The user should be able to trigger follow-up research from:

- `#mp-briefing`, by sending `follow up: <topic, question, URL, or story>`.
- A Slack draft/review thread, by replying `follow up: <specific question>`.
- A newsletter story pasted into Slack, by including `follow up:` plus the story
  title, URL, or excerpt.

The bot should acknowledge the request, run a scoped research pass, and return a
concise result in the same Slack thread:

- 3-7 concrete findings.
- Source links where available.
- "Why this matters" summary.
- Suggested next action: cover tomorrow, turn into social angle, archive, or
  ignore.
- Clear degraded/error notice if sources or agent execution fail.

## Non-Goals

- Do not implement background auto-research based on every newsletter story.
- Do not auto-post to LinkedIn, Bluesky, X, or any other social platform.
- Do not send email or create a second daily newsletter.
- Do not run `run.py` as part of a Slack follow-up request.
- Do not add dependencies unless the owner explicitly approves.
- Do not change database schema for the MVP unless the implementation proves it
  cannot meet acceptance criteria with trace events and local artifacts.
- Do not expose Slack message bodies, secrets, subscriber data, `users.json`,
  `social-config.json`, `memory.db`, or `traces.db` in committed files.

## Tech Stack

- Python 3.14 locally through `.venv/bin/python3`.
- Python on Fly for the Slack Socket Mode bot.
- Slack bot entry point: `slack_bot/bot.py`.
- Slack handler registry: `slack_bot/registry.py`.
- Slack handlers: `slack_bot/handlers/`.
- Shared Slack helpers: `slack_bot/handlers/base.py`.
- Agent execution: `orchestrator/agents.py`.
- Pipeline tracing: `orchestrator/traces_db.py`.
- Current daily runner: `run.py` and `orchestrator/runner.py`.
- Tests: pytest under `tests/`.

## Commands

Use these exact commands unless a task says otherwise.

```bash
# Start state
git status --short --branch
git diff --stat

# Focused Slack bot tests
.venv/bin/python3 -m pytest tests/test_slack_bot.py -q

# Follow-up feature tests after adding them
.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_slack_bot.py -q

# Social/approval regression checks
.venv/bin/python3 -m pytest tests/test_approval.py tests/test_social.py -q

# Runner safety regression checks
.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q

# CI-equivalent local suite
.venv/bin/python3 -m pytest tests/ -q --tb=short --ignore=tests/test_cors.py --ignore=tests/test_engagement_linkedin.py --ignore=tests/test_memory_cli.py --ignore=tests/test_runner.py -k "not test_blocked_when_at_limit and not test_get_model_research_agent"

# Critical runner phase suite from CI
.venv/bin/python3 -m pytest -q --tb=short tests/test_runner.py::TestPhaseTrendScan tests/test_runner.py::TestPhaseResearch tests/test_runner.py::TestPhaseSynthesis tests/test_runner.py::TestPhaseSocial

# Formatting/sanity
git diff --check

# Graph after code or indexed docs changes
graphify update .
graphify check-update .
```

Commands requiring explicit owner approval:

```bash
# Live Slack/Fly smoke
/Users/taylerramsay/.fly/bin/flyctl deploy --app mindpattern
/Users/taylerramsay/.fly/bin/flyctl logs --app mindpattern --no-tail

# Any real follow-up command from Slack that invokes Claude/network access
# while the bot is connected to production Slack.
```

## Project Structure

```text
slack_bot/bot.py                 Socket Mode routing and owner filtering
slack_bot/registry.py            Channel -> handler mapping and doctor status
slack_bot/handlers/base.py       reply/react/thread helpers and URL reader
slack_bot/handlers/briefing.py   #mp-briefing status commands
slack_bot/handlers/posts.py      #mp-posts social draft workflow
slack_bot/handlers/skills.py     #mp-skills draft workflow
slack_bot/handlers/tips.py       #mp-tips draft workflow
orchestrator/agents.py           run_single_agent and run_claude_prompt
orchestrator/traces_db.py        pipeline_runs, agent_runs, events
reports/ramsay/followups/        proposed local follow-up markdown artifacts
tests/test_slack_bot.py          Slack handler and bot behavior tests
tests/test_followup_research.py  proposed focused follow-up tests
docs/runbooks/                   this runbook and future implementation notes
```

## Code Style

Prefer small helpers with explicit structured results. The feature should be
testable without Slack, Claude, network access, or Fly.

Example style:

```python
def parse_followup_request(text: str) -> dict | None:
    text = text.strip()
    lower = text.lower()
    if not lower.startswith(("follow up:", "follow-up:", "research this:")):
        return None

    _, _, query = text.partition(":")
    query = query.strip()
    if len(query) < 8:
        return {"error": "follow-up request needs a more specific topic"}

    return {"query": query, "source": "slack"}
```

Conventions:

- Use `logging.getLogger(__name__)`.
- Return dictionaries with stable keys for Slack formatting and tests.
- Fail closed on unclear commands.
- Keep Slack responses short enough for phone review.
- Mock `subprocess`, Slack SDK calls, Claude calls, filesystem writes, and time
  in tests.
- Do not put raw secrets, channel IDs, full Slack message bodies, or private DB
  content into logs or docs.

## Testing Strategy

Unit tests must cover:

- Parser accepts `follow up:`, `follow-up:`, and `research this:`.
- Parser rejects empty or too-short requests with a helpful message.
- Non-owner Slack messages are still ignored by the bot.
- `MP_DISABLE_OUTBOUND=1` or dry-run mode does not call Claude/network helpers.
- Follow-up service returns deterministic fake findings in dry-run.
- Follow-up service logs a trace event without exposing full Slack body.
- `#mp-briefing` command posts an acknowledgement and final result.
- Draft-thread follow-up does not approve or post any social draft.
- Existing approval parsing remains fail-closed.

Integration-style tests should mock Slack and Claude but exercise real handler
methods. No test should require a real Slack token, live network, real browser
cookies, or the owner's local `memory.db`.

Manual smoke, only after owner approval:

1. Deploy to Fly.
2. In `#mp-briefing`, send `follow up: agent-reach social search reliability`.
3. Confirm the bot replies in-thread with an acknowledgement.
4. Confirm it returns scoped findings, sources, and next action.
5. Confirm no newsletter email, social post, Fly sync, or daily pipeline run was
   triggered.
6. Confirm traces/logs contain a follow-up event without secret or raw Slack body
   leakage.

## Boundaries

- Always: keep Slack-bot-first behavior.
- Always: use owner-only command handling.
- Always: test parser, dry-run, handler, and approval-regression behavior before
  committing.
- Always: update this runbook and handoff with evidence after implementation.
- Always: keep follow-up runs scoped and visibly degraded when source/agent
  inputs fail.
- Ask first: adding Slack Block Kit interactivity or changing Slack app settings.
- Ask first: database schema changes.
- Ask first: adding dependencies.
- Ask first: deploying to Fly or running a live Slack smoke.
- Ask first: storing follow-up outputs in `memory.db` as permanent findings.
- Never: run the full daily pipeline from the follow-up command.
- Never: auto-send a newsletter from this feature.
- Never: auto-post social content from this feature.
- Never: commit local databases, secrets, Slack message bodies, subscriber data,
  `users.json`, or `social-config.json`.

## MVP Design

### Command UX

Accepted commands:

```text
follow up: <topic, question, URL, or pasted story excerpt>
follow-up: <topic, question, URL, or pasted story excerpt>
research this: <topic, question, URL, or pasted story excerpt>
```

Rejected commands:

```text
follow up
research this
more
what about this?
```

The bot should reply with guidance instead of silently ignoring short owner
tests.

### Execution Model

The implementation should add a small follow-up service, not a new daily
pipeline path.

Proposed module:

```text
orchestrator/followup.py
```

Responsibilities:

- Normalize the request.
- Build a scoped prompt with:
  - the user's follow-up question,
  - optional source URL/story excerpt,
  - recent context if available,
  - clear requirement for fresh sources and "why now".
- Run one or more research agents through existing `run_single_agent`.
- Return a structured result with findings, links, degraded status, and next
  action.
- Write an optional local markdown artifact under
  `reports/ramsay/followups/YYYY-MM-DD-<slug>.md`.
- Log a safe trace event such as `followup_research_complete`.

MVP should run one scoped research agent first. A later version can fan out to
multiple agents if quality demands it.

### Slack Integration

Primary integration:

- Add command handling to `BriefingHandler` for `#mp-briefing`.

Draft-thread integration:

- Add a shared helper so `posts`, `skills`, and `tips` approval loops can detect
  a `follow up:` reply, run follow-up research, post the result, and then keep
  waiting for a real approval/edit/skip decision.

Do not broadly route all thread replies in `slack_bot/bot.py` unless tests prove
the approval loops cannot handle this cleanly. The current bot deliberately
ignores thread replies so approval text does not start a second pipeline.

### Trace and Artifact Rules

Trace event payloads should include only safe metadata:

```json
{
  "source": "slack",
  "channel_type": "briefing",
  "query_hash": "sha256:...",
  "query_preview": "first 120 chars, redacted",
  "status": "completed",
  "finding_count": 5,
  "artifact": "reports/ramsay/followups/2026-06-26-agent-reach.md"
}
```

Artifacts may include generated follow-up findings and public source URLs. They
must not include raw Slack user IDs, tokens, subscriber data, or private message
history.

## Success Criteria

- `#mp-briefing` accepts `follow up: <topic>` and returns a scoped research
  result in-thread.
- At least one draft workflow can accept `follow up:` in its approval thread
  without approving, posting, skipping, or losing the draft.
- Dry-run mode produces deterministic follow-up output without Claude, network,
  Slack, email, social posting, or Fly sync.
- Follow-up output includes 3-7 findings, source links where available, "why
  this matters", and a recommended next action.
- Failures are visible in Slack and trace logs as degraded or failed; they are
  not silent.
- The feature does not weaken newsletter quality gates, source-health checks,
  dedupe checks, or social approval safety.
- CI-equivalent tests pass locally.
- Handoff/runbook evidence is updated.

## Open Questions

1. Should the first version include true Slack Block Kit buttons, or is
   command-first acceptable until interactivity is explicitly configured?
2. Should follow-up findings be stored permanently in `memory.db`, or only as
   trace events plus markdown artifacts for MVP?
3. Which channel should be the main home for follow-ups: `#mp-briefing`,
   `#mp-posts`, or a new `#mp-followups` channel?
4. Should follow-up research be allowed to use live external sources immediately,
   or should the first implementation ship with dry-run/local-only smoke first?

## Implementation Tasks

Keep the `Done` column. Future agents should update it in place instead of
deleting the column.

| # | Done | Task | Acceptance | Verify | Files |
|---|---|---|---|---|---|
| 1 | No | Add follow-up parser tests | Accepted and rejected command forms are explicit. | `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` | `tests/test_followup_research.py` |
| 2 | No | Add follow-up service dry-run path | Dry-run returns deterministic findings and calls no Claude/network. | `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` | `orchestrator/followup.py`, tests |
| 3 | No | Add safe trace/artifact writing | Completion/failure emits safe metadata and optional markdown artifact. | `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` | `orchestrator/followup.py`, `orchestrator/traces_db.py` only if needed |
| 4 | No | Wire `#mp-briefing` command | `follow up: ...` posts acknowledgement and final result in-thread. | `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_followup_research.py -q` | `slack_bot/handlers/briefing.py`, tests |
| 5 | No | Wire one draft-thread workflow | `follow up:` in a draft approval loop researches without approving/posting. | `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_approval.py -q` | `slack_bot/handlers/posts.py` or `skills.py`, shared helper |
| 6 | No | Add regression checks for no auto-post/no full pipeline | Follow-up command does not call `run.py`, social posting, email, or sync. | `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_social.py -q` | tests |
| 7 | No | Update docs and handoff evidence | Runbook records commands, results, blockers, and live-smoke status. | `git diff --check` | this file, `.claude/handoffs/...` |
| 8 | No | Run Graphify after code changes | Graphify artifacts are current if indexed code/docs changed. | `graphify update . && graphify check-update .` | `graphify-out/` |
| 9 | No | Optional owner-approved Fly smoke | Live Slack command returns result and triggers no forbidden outbound actions. | owner-approved smoke checklist | no code unless smoke finds bug |

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Thread reply routing collides with approval parsing | Could accidentally approve/post or start duplicate work | Prefer handler-loop interception; keep approval parser fail-closed; add regression tests |
| True Slack buttons require app interactivity not currently wired | Could expand scope into Slack app config | MVP command-first; ask owner before Block Kit/interactivity |
| Follow-up run becomes a second hidden pipeline | Could create unexpected sends/syncs/social output | Use a separate follow-up service with no delivery phases |
| Raw Slack content leaks into traces/docs | Privacy risk | Store hashes/previews only in traces; do not commit artifacts |
| External source failures produce bland output | Quality regression | Mark degraded visibly and include source health/failure reason |
| Claude/network calls make tests flaky | CI instability | Dry-run deterministic path and mocks for all external boundaries |

## Slash Goal Prompt

Use this after the owner reviews and accepts the runbook:

```text
/goal Implement MindPattern v3 Feature 24: Ask Follow-Up Research.

Primary source of truth:
- docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md
- .claude/handoffs/2026-06-26-system-audit-slack-social.md

This is a new-feature pass for the "Ask Follow-Up" Research Button/Command.
Start with the command-first MVP unless the owner explicitly approves Slack
Block Kit interactivity.

Hard requirements:
- Keep Slack-bot-first behavior.
- Owner-only commands; fail closed if owner identity is missing.
- No background auto-research.
- No full daily pipeline run from this feature.
- No newsletter send, social post, Fly sync, or deployment without explicit
  owner approval.
- No live outbound social post ever without explicit owner approval in Slack.
- Dry-run/focused tests must not call Claude, network, Slack, email, social APIs,
  or Fly.
- Do not expose or commit secrets, personal data, raw Slack message bodies,
  subscriber data, databases, users.json, or social-config.json.
- Do not add dependencies or change schema without explicit owner approval.

Execution rules:
- Start by recording current dirty files and baseline tests.
- Follow the runbook task table in dependency order.
- For each task: write/update tests first, implement the smallest change, run
  the task verification command, then update the Done column and evidence.
- Preserve unrelated user changes.
- Keep draft-thread follow-up behavior from approving, posting, skipping, or
  losing the draft.
- After code/docs changes, run Graphify where required.
- Work in small commits by verified task group.

Definition of done:
- `#mp-briefing` accepts `follow up: <topic>` and returns scoped findings
  in-thread.
- At least one Slack draft/review workflow accepts a `follow up:` reply without
  approving or posting anything.
- Follow-up service has deterministic dry-run behavior and safe trace/artifact
  output.
- Follow-up failures are visibly marked degraded or failed.
- CI-equivalent tests pass locally.
- Runbook and handoff are current for the next agent.
- Repo is clean or dirty files are clearly explained.
```


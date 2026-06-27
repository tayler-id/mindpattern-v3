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
7. The Slack Editorial Desk pairs with this feature as the daily story chooser:
   it should let Tayler approve, save, revise, reject, or ask follow-up on story
   candidates from one Slack thread.

If any of these are wrong, update this runbook before implementation starts.

## Objective

Build a controlled way for Tayler to ask, from Slack, "go deeper on this story"
without running the whole newsletter pipeline.

Paired objective: add a Slack Editorial Desk command that shows today's best
story candidates in one thread, then lets Tayler make editorial decisions from
Slack instead of reconstructing the day from logs, reports, and scattered
drafts.

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

The Editorial Desk should show candidates with actions:

- `approve <n>`: mark candidate as approved for newsletter or social angle.
- `save <n>`: keep the candidate for later without using it today.
- `revise <n>: <guidance>`: ask the bot to reframe the angle.
- `reject <n>: <reason>`: mark the candidate as not useful and preserve why.
- `follow up <n>: <question>`: launch the scoped follow-up research flow for
  that candidate.

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
- Do not let Editorial Desk approval publish anything. Editorial approval means
  "this story/angle is worth using", not "post this live".

## Tech Stack

- Python 3.14 locally through `.venv/bin/python3`.
- Python on Fly for the Slack Socket Mode bot.
- Slack bot entry point: `slack_bot/bot.py`.
- Slack handler registry: `slack_bot/registry.py`.
- Slack handlers: `slack_bot/handlers/`.
- Shared Slack helpers: `slack_bot/handlers/base.py`.
- Agent execution: `orchestrator/agents.py`.
- Pipeline tracing: `orchestrator/traces_db.py`.
- Candidate source data: `memory.db`, reports, and pipeline artifacts.
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

# Editorial Desk tests after adding them
.venv/bin/python3 -m pytest tests/test_editorial_desk.py tests/test_slack_bot.py -q

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
slack_bot/handlers/editorial.py  proposed Slack Editorial Desk command handler
slack_bot/handlers/posts.py      #mp-posts social draft workflow
slack_bot/handlers/skills.py     #mp-skills draft workflow
slack_bot/handlers/tips.py       #mp-tips draft workflow
orchestrator/agents.py           run_single_agent and run_claude_prompt
orchestrator/traces_db.py        pipeline_runs, agent_runs, events
orchestrator/editorial.py        proposed story candidate loading/decision logic
reports/ramsay/followups/        proposed local follow-up markdown artifacts
data/editorial-desk/             proposed uncommitted candidate/decision artifacts
tests/test_slack_bot.py          Slack handler and bot behavior tests
tests/test_followup_research.py  proposed focused follow-up tests
tests/test_editorial_desk.py     proposed Editorial Desk tests
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
- Editorial Desk loads ranked candidates without requiring the owner's local DB
  in CI.
- Editorial Desk actions update candidate state without posting social content.
- `follow up <n>` from Editorial Desk launches the follow-up path for the right
  candidate.
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
7. Send `desk` or `editorial desk` in the approved channel.
8. Confirm the bot returns today's candidate list in one thread.
9. Send `save 1`, `reject 2: stale`, and `follow up 3: why now?` in the thread.
10. Confirm no candidate action posts to a live platform.

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
- Ask first: making Editorial Desk decisions alter newsletter synthesis
  automatically before that behavior has an explicit test and owner approval.
- Never: run the full daily pipeline from the follow-up command.
- Never: auto-send a newsletter from this feature.
- Never: auto-post social content from this feature.
- Never: treat Editorial Desk approval as social posting approval.
- Never: commit local databases, secrets, Slack message bodies, subscriber data,
  `users.json`, or `social-config.json`.

## How Slack Editorial Desk Works

Think of the Editorial Desk as a daily inbox of story options.

Today, the system researches, synthesizes, writes, and posts status. The human
has to inspect reports, Slack threads, and source counts to decide what is
actually worth using. Editorial Desk changes that into one control thread:

1. The bot gathers today's strongest candidates from the research findings,
   current report, source health, and any social draft candidates.
2. The bot ranks them and posts a numbered list in Slack.
3. Tayler replies with simple commands against the numbers.
4. The bot records the decision and, if needed, triggers follow-up research.
5. Later newsletter/social steps can read those decisions, but only after that
   integration is explicitly implemented and tested.

Example Slack thread:

```text
Tayler: editorial desk

Bot:
Today's story candidates

1. Agent Reach social search reliability
   Why it matters: source health decides newsletter quality.
   Sources: X fallback, Exa, YouTube
   Suggested use: follow-up research

2. North Mini Code local coding model
   Why it matters: cheap agent loops without frontier pricing.
   Sources: Hugging Face, GitHub
   Suggested use: newsletter story or social angle

Reply:
approve 2
save 1
reject 3: stale
revise 2: make this more tactical for builders
follow up 1: compare agent-reach vs opencli vs native CLIs
```

Junior-dev mental model:

- `Editorial Desk` is the UI/controller.
- `Candidate loader` is the data access layer.
- `Decision store` is state.
- `Follow-up research` is a command the desk can call.
- `Newsletter/social` are consumers of decisions later, not automatic effects
  in the MVP.

This pairs well with Ask Follow-Up because every candidate has two possible
states: either it is strong enough to use now, or it needs deeper research. The
desk gives you the decision buttons; follow-up gives you the deeper investigation
when a candidate is interesting but not ready.

## Editorial Desk MVP Design

### Command UX

Accepted root commands:

```text
desk
editorial desk
today's candidates
story candidates
```

Accepted thread commands:

```text
approve <number>
approve <number> newsletter
approve <number> social
save <number>
reject <number>: <reason>
revise <number>: <guidance>
follow up <number>: <question>
status
```

Rejected commands should return guidance and change no state.

### Approval Semantics

Editorial Desk approval is an editorial signal, not a send command.

For the MVP, `approve <n>` should mean:

- This candidate is worth using.
- Prefer it for today's newsletter/social planning.
- Preserve the approved angle and any guidance for later pipeline steps.

It should not mean:

- Send the newsletter.
- Publish to social.
- Skip quality checks.
- Block the daily newsletter forever if Tayler does not respond.

Recommended MVP behavior:

- If Tayler approves candidates before synthesis, the newsletter can prefer
  those candidates once that integration is implemented.
- If Tayler does not approve anything, the daily newsletter still runs using the
  normal quality-gated pipeline.
- If a candidate is approved for social, it should only create or prioritize a
  Slack draft. It still needs the normal explicit posting approval before any
  live social action.

Possible later mode:

- `editorial lock` could intentionally require approved candidates before
  synthesis, but that should be a separate owner-approved feature because the
  newsletter must not fail just because nobody replied in Slack.

### Candidate Shape

Use a stable data object so Slack formatting, tests, and later dashboard work
can share one contract:

```python
candidate = {
    "id": "2026-06-26-001",
    "title": "Agent Reach social search reliability",
    "summary": "X search failed but feed fallback worked; Reddit needs OpenCLI.",
    "source_urls": ["https://..."],
    "source_names": ["X", "Exa", "YouTube"],
    "score": 0.86,
    "recommended_use": "follow_up",
    "status": "pending",
}
```

MVP candidate sources, in order:

1. Current-day findings in `memory.db`, if available.
2. Current-day newsletter/report sections, if available.
3. Current-day social draft/topic artifact, if available.
4. Deterministic fixture candidates in tests.

### Decision State

MVP should avoid schema changes. Store decisions in an uncommitted JSON artifact:

```text
data/editorial-desk/YYYY-MM-DD-decisions.json
```

Later, after approval, this can move into `memory.db` for durable analytics.

Decision states:

- `approved`
- `saved`
- `rejected`
- `revision_requested`
- `followup_requested`

Each decision should record safe metadata only: candidate ID, action, timestamp,
short reason/guidance, and optional artifact path. Do not store raw Slack user
IDs or full Slack message bodies.

## Ask Follow-Up MVP Design

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
- `editorial desk` returns today's ranked story candidates in one Slack thread.
- Editorial Desk actions `approve`, `save`, `revise`, `reject`, and
  `follow up` update decision state without posting anything live.
- Editorial Desk `follow up <n>` launches scoped follow-up for the chosen
  candidate.
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
5. Should Slack Editorial Desk live in `#mp-briefing`, `#mp-posts`, or its own
   `#mp-editorial` channel?
6. Should `approve <n>` mean "approved for newsletter", "approved for social
   angle", or should the command require a target such as
   `approve 2 newsletter`?
7. Should saved candidates feed tomorrow's newsletter planning automatically,
   or only appear when explicitly requested?

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
| 7 | No | Add Editorial Desk parser tests | Root and thread commands are accepted/rejected explicitly. | `.venv/bin/python3 -m pytest tests/test_editorial_desk.py -q` | `tests/test_editorial_desk.py` |
| 8 | No | Add candidate loader dry-run/fixture path | CI can rank candidates without local private DB data. | `.venv/bin/python3 -m pytest tests/test_editorial_desk.py -q` | `orchestrator/editorial.py`, tests |
| 9 | No | Add decision store | Actions persist safe candidate decisions without schema changes. | `.venv/bin/python3 -m pytest tests/test_editorial_desk.py -q` | `orchestrator/editorial.py`, tests |
| 10 | No | Wire Editorial Desk Slack command | `editorial desk` posts a numbered candidate thread. | `.venv/bin/python3 -m pytest tests/test_editorial_desk.py tests/test_slack_bot.py -q` | `slack_bot/handlers/briefing.py` or `slack_bot/handlers/editorial.py`, tests |
| 11 | No | Wire Editorial Desk actions | `approve`, `save`, `revise`, `reject`, and `follow up` update state safely. | `.venv/bin/python3 -m pytest tests/test_editorial_desk.py tests/test_followup_research.py -q` | Slack handler, `orchestrator/editorial.py`, follow-up integration |
| 12 | No | Add no-live-post regression for Editorial Desk | Editorial actions cannot call social posting/email/sync. | `.venv/bin/python3 -m pytest tests/test_editorial_desk.py tests/test_social.py -q` | tests |
| 13 | No | Update docs and handoff evidence | Runbook records commands, results, blockers, and live-smoke status. | `git diff --check` | this file, `.claude/handoffs/...` |
| 14 | No | Run Graphify after code changes | Graphify artifacts are current if indexed code/docs changed. | `graphify update . && graphify check-update .` | `graphify-out/` |
| 15 | No | Optional owner-approved Fly smoke | Live Slack commands return results and trigger no forbidden outbound actions. | owner-approved smoke checklist | no code unless smoke finds bug |

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Thread reply routing collides with approval parsing | Could accidentally approve/post or start duplicate work | Prefer handler-loop interception; keep approval parser fail-closed; add regression tests |
| True Slack buttons require app interactivity not currently wired | Could expand scope into Slack app config | MVP command-first; ask owner before Block Kit/interactivity |
| Follow-up run becomes a second hidden pipeline | Could create unexpected sends/syncs/social output | Use a separate follow-up service with no delivery phases |
| Raw Slack content leaks into traces/docs | Privacy risk | Store hashes/previews only in traces; do not commit artifacts |
| External source failures produce bland output | Quality regression | Mark degraded visibly and include source health/failure reason |
| Claude/network calls make tests flaky | CI instability | Dry-run deterministic path and mocks for all external boundaries |
| Editorial Desk approval is mistaken for publish approval | Could post unintentionally if wired into social path incorrectly | Treat editorial approval as story selection only; add no-live-post regression tests |
| Candidate state creates another hidden source of truth | Later agents may not know what Slack decisions mean | Store decisions in a documented JSON contract first; update handoff/runbook evidence |
| Ranking candidates from `memory.db` makes CI depend on private data | CI failure or false confidence | Use fixture/dry-run candidate loader in tests |

## Slash Goal Prompt

Use this after the owner reviews and accepts the runbook:

```text
/goal Implement MindPattern v3 Feature 24: Ask Follow-Up Research plus Slack Editorial Desk.

Primary source of truth:
- docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md
- .claude/handoffs/2026-06-26-system-audit-slack-social.md

This is a new-feature pass for the "Ask Follow-Up" Research Button/Command and
the paired Slack Editorial Desk. Start with the command-first MVP unless the
owner explicitly approves Slack Block Kit interactivity.

Hard requirements:
- Keep Slack-bot-first behavior.
- Owner-only commands; fail closed if owner identity is missing.
- No background auto-research.
- No full daily pipeline run from this feature.
- No newsletter send, social post, Fly sync, or deployment without explicit
  owner approval.
- No live outbound social post ever without explicit owner approval in Slack.
- Editorial Desk approval means story/angle selection only; it must not publish
  anything live.
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
- Keep Editorial Desk actions from posting social content or sending email.
- After code/docs changes, run Graphify where required.
- Work in small commits by verified task group.

Definition of done:
- `#mp-briefing` accepts `follow up: <topic>` and returns scoped findings
  in-thread.
- At least one Slack draft/review workflow accepts a `follow up:` reply without
  approving or posting anything.
- Follow-up service has deterministic dry-run behavior and safe trace/artifact
  output.
- `editorial desk` shows ranked story candidates in one Slack thread.
- Editorial Desk supports `approve`, `save`, `revise`, `reject`, and
  `follow up` actions with safe decision state.
- Follow-up failures are visibly marked degraded or failed.
- CI-equivalent tests pass locally.
- Runbook and handoff are current for the next agent.
- Repo is clean or dirty files are clearly explained.
```

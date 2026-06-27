# Spec and Runbook: Feature 24 - Ask Follow-Up Research

> Status: In progress
> Owner: Tayler
> Author: Codex
> Created: 2026-06-26
> Source evidence: `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
> Feature row: New Feature Ideas table, row 24
> Implementation plan: `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-implementation-plan.md`

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
7. The optional Slack Social Ideas Desk pairs with this feature only for social
   post ideas. It must not review, select, approve, block, or send newsletter
   stories.

If any of these are wrong, update this runbook before implementation starts.

## Objective

Build a controlled way for Tayler to ask, from Slack, "go deeper on this story"
without running the whole newsletter pipeline.

Paired social objective: optionally add a Slack Social Ideas Desk command that
shows social post ideas in one thread, then lets Tayler save, revise, reject,
draft, or request follow-up research for a social angle. This is not a
newsletter review desk and must never become one.

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

The Social Ideas Desk should show social post ideas with optional actions:

- `draft <n>`: create a Slack social draft/manual-copy candidate only.
- `save <n>`: keep the social idea for later without posting it.
- `revise <n>: <guidance>`: ask the bot to reframe the social angle.
- `reject <n>: <reason>`: mark the social idea as not useful and preserve why.
- `follow up <n>: <question>`: launch the scoped follow-up research flow for
  that social idea.

## Non-Goals

- Do not implement background auto-research based on every newsletter story.
- Do not auto-post to LinkedIn, Bluesky, X, or any other social platform.
- Do not send an extra email or create a second daily newsletter from Slack
  follow-up or Social Ideas Desk actions.
- Do not run `run.py` as part of a Slack follow-up request.
- Do not add dependencies unless the owner explicitly approves.
- Do not change database schema for the MVP unless the implementation proves it
  cannot meet acceptance criteria with trace events and local artifacts.
- Do not expose Slack message bodies, secrets, subscriber data, `users.json`,
  `social-config.json`, `memory.db`, or `traces.db` in committed files.
- Do not make Tayler manually choose newsletter stories. The pipeline remains
  responsible for selection.
- Do not create a newsletter review desk. The desk concept is allowed only for
  social post ideas.
- Do not make the normal daily newsletter wait for Slack feedback or approval.
  Scheduled research, writing, and sending must keep running through the normal
  quality-gated pipeline.
- Do not let Social Ideas Desk feedback publish anything. `draft <n>` means
  "make a Slack draft/manual-copy candidate", not "post this live".

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

# Social Ideas Desk tests after adding them
.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_slack_bot.py -q

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
slack_bot/handlers/followup.py   shared Slack follow-up formatting/interceptor
slack_bot/handlers/briefing.py   #mp-briefing status commands
slack_bot/handlers/social_ideas.py  proposed Slack Social Ideas Desk command handler
slack_bot/handlers/posts.py      #mp-posts social draft workflow
slack_bot/handlers/skills.py     #mp-skills draft workflow
slack_bot/handlers/tips.py       #mp-tips draft workflow
orchestrator/agents.py           run_single_agent and run_claude_prompt
orchestrator/traces_db.py        pipeline_runs, agent_runs, events
orchestrator/social_ideas.py     proposed social idea loading/feedback logic
reports/ramsay/followups/        proposed local follow-up markdown artifacts
data/social-ideas/               proposed uncommitted social idea feedback artifacts
tests/test_slack_bot.py          Slack handler and bot behavior tests
tests/test_followup_research.py  proposed focused follow-up tests
tests/test_social_ideas_desk.py  proposed Social Ideas Desk tests
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
- Social Ideas Desk loads ranked social post ideas without requiring the
  owner's local DB in CI.
- Social Ideas Desk actions update idea state without posting social content.
- `follow up <n>` from Social Ideas Desk launches the follow-up path for the
  right social idea.
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
7. Send `social ideas` in the approved social channel, likely `#mp-posts`.
8. Confirm the bot returns today's social idea list in one thread.
9. Send `save 1`, `reject 2: stale`, `draft 3`, and
   `follow up 3: why now?` in the thread.
10. Confirm no idea action posts to a live platform.

## Boundaries

- Always: keep Slack-bot-first behavior.
- Always: use owner-only command handling.
- Always: test parser, dry-run, handler, and approval-regression behavior before
  committing.
- Always: update this runbook and handoff with evidence after implementation.
- Always: keep follow-up runs scoped and visibly degraded when source/agent
  inputs fail.
- Always: keep normal daily newsletter research, synthesis, writing, and send
  behavior independent from Social Ideas Desk feedback.
- Ask first: adding Slack Block Kit interactivity or changing Slack app settings.
- Ask first: database schema changes.
- Ask first: adding dependencies.
- Ask first: deploying to Fly or running a live Slack smoke.
- Ask first: storing follow-up outputs in `memory.db` as permanent findings.
- Ask first: using Social Ideas Desk feedback anywhere outside social planning.
- Never: run the full daily pipeline from the follow-up command.
- Never: auto-send an extra newsletter from this feature.
- Never: auto-post social content from this feature.
- Never: make Slack Social Ideas Desk a required manual story-picking, research,
  writing, or send gate for the newsletter.
- Never: block scheduled daily newsletter research, synthesis, writing, or
  sending on Slack feedback.
- Never: treat Social Ideas Desk feedback as live social posting approval.
- Never: commit local databases, secrets, Slack message bodies, subscriber data,
  `users.json`, or `social-config.json`.

## How Slack Social Ideas Desk Works

Think of the Social Ideas Desk as a daily review panel for social post ideas,
not newsletter stories.

The normal system researches, synthesizes, writes, and sends the newsletter on
schedule. Social Ideas Desk sits after or beside that flow and helps reuse strong
research as social post ideas without blocking the newsletter:

1. The bot gathers candidate social angles from current reports, findings, and
   existing social draft/topic artifacts.
2. The bot shows a numbered list in Slack with why each idea could become a
   post.
3. Tayler can ignore it completely and the scheduled newsletter still
   researches, writes, and sends through normal quality gates.
4. If Tayler replies, the bot records social-planning feedback, creates a draft,
   or triggers follow-up research.
5. No Social Ideas Desk action can publish live. Live posts still require the
   existing explicit social approval path.

Example Slack thread:

```text
Tayler: social ideas

Bot:
Today's social post ideas

1. Agent Reach social search reliability
   Why it matters: source health is a useful builder lesson.
   Sources: X fallback, Exa, YouTube
   Suggested use: tactical LinkedIn/Bluesky post

2. North Mini Code local coding model
   Why it matters: cheap agent loops without frontier pricing.
   Sources: Hugging Face, GitHub
   Suggested use: builder take or short thread

Optional replies:
draft 2
save 1
reject 3: stale
revise 2: make this more tactical for builders
follow up 1: compare agent-reach vs opencli vs native CLIs
```

Junior-dev mental model:

- `Social Ideas Desk` is the review UI for social post ideas.
- `Idea loader` is the data access layer.
- `Feedback store` is state.
- `Follow-up research` is a command the desk can call.
- `Social draft creation` is a safe output, but live social posting still needs
  explicit owner approval.
- `Newsletter` is not a consumer of Social Ideas Desk feedback in the MVP.

This pairs well with Ask Follow-Up because a social angle may be promising but
under-explained. The desk shows the social idea; follow-up gives you a way to ask
for deeper investigation without touching newsletter selection or delivery.

## Social Ideas Desk MVP Design

### Command UX

Accepted root commands:

```text
desk
social ideas
post ideas
today's social ideas
```

Accepted thread commands:

```text
draft <number>
save <number>
reject <number>: <reason>
revise <number>: <guidance>
follow up <number>: <question>
status
```

Rejected commands should return guidance and change no state.

### Feedback Semantics

Social Ideas Desk feedback is a social planning signal, not a newsletter gate or
publish approval.

For the MVP, `draft <n>` should mean:

- Create or prioritize a Slack social draft/manual-copy candidate.
- Preserve the source idea and any guidance for later social planning.
- Do not publish anything live.

It should not mean:

- Choose the newsletter stories manually.
- Send the newsletter.
- Publish to social.
- Skip quality checks.
- Block the daily newsletter's research, writing, or sending if Tayler does not
  respond.

Recommended MVP behavior:

- If Tayler gives no feedback, the daily newsletter still researches, writes,
  and sends using the normal quality-gated pipeline.
- If Tayler asks for `draft <n>`, the bot creates or prioritizes a Slack draft.
  It still needs the normal explicit posting approval before any live social
  action.
- If Tayler asks for `follow up <n>`, the bot runs scoped follow-up research and
  returns the findings in-thread.

### Candidate Shape

Use a stable data object so Slack formatting, tests, and later dashboard work
can share one contract:

```python
idea = {
    "id": "2026-06-26-001",
    "title": "Agent Reach social search reliability",
    "summary": "X search failed but feed fallback worked; Reddit needs OpenCLI.",
    "source_urls": ["https://..."],
    "source_names": ["X", "Exa", "YouTube"],
    "score": 0.86,
    "recommended_use": "social_draft",
    "status": "pending",
}
```

MVP social idea sources, in order:

1. Current-day social draft/topic artifact, if available.
2. Current-day report sections or newsletter output after they already exist.
3. Current-day findings in `memory.db`, if available.
4. Deterministic fixture ideas in tests.

### Feedback State

MVP should avoid schema changes. Store feedback in an uncommitted JSON artifact:

```text
data/social-ideas/YYYY-MM-DD-feedback.json
```

Later, after owner approval for a storage/schema change, this can move into
`memory.db` for durable analytics.

Feedback states:

- `draft_requested`
- `saved`
- `rejected`
- `revision_requested`
- `followup_requested`

Each feedback item should record safe metadata only: idea ID, action, timestamp,
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
- `social ideas` returns ranked social post ideas in one Slack thread.
- Social Ideas Desk actions `draft`, `save`, `revise`, `reject`, and
  `follow up` update feedback state without posting anything live or affecting
  newsletter research, writing, or sending.
- Social Ideas Desk `follow up <n>` launches scoped follow-up for the chosen
  social idea.
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
5. Should Slack Social Ideas Desk live in `#mp-posts`, `#mp-briefing`, or a new
   `#mp-social-ideas` channel?
6. Should `draft <n>` route into the existing `#mp-posts` draft generator, or
   create a manual-copy draft artifact first?
7. Should saved social ideas feed a later social calendar automatically, or only
   appear when explicitly requested?

## Implementation Tasks

Keep the `Done` column. Future agents should update it in place instead of
deleting the column.

| # | Done | Task | Acceptance | Verify | Files |
|---|---|---|---|---|---|
| 1 | Yes | Add follow-up parser tests | Accepted and rejected command forms are explicit. | `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` | `tests/test_followup_research.py` |
| 2 | Yes | Add follow-up service dry-run path | Dry-run returns deterministic findings and calls no Claude/network. | `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` | `orchestrator/followup.py`, tests |
| 3 | Yes | Add safe trace/artifact writing | Completion/failure emits safe metadata and optional markdown artifact. | `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` | `orchestrator/followup.py`, `orchestrator/traces_db.py` only if needed |
| 4 | Yes | Wire `#mp-briefing` command | `follow up: ...` posts acknowledgement and final result in-thread. | `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_followup_research.py -q` | `slack_bot/handlers/briefing.py`, tests |
| 5 | Yes | Wire one draft-thread workflow | `follow up:` in posts, skills, and tips draft approval loops researches without approving/posting and keeps waiting. | `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsEditFlow tests/test_slack_bot.py::TestSkillsTipsEditFlow tests/test_slack_bot.py::TestBriefingFollowupCommand -q` -> 14 passed | `slack_bot/handlers/posts.py`, `skills.py`, `tips.py`, `followup.py`, tests |
| 6 | Yes | Add regression checks for no auto-post/no full pipeline | Follow-up command does not call `run.py`, runner/newsletter delivery, social posting, or Fly sync; `MP_DISABLE_OUTBOUND=1` forces dry-run without agent calls. | `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q` -> 60 passed | `tests/test_followup_research.py` |
| 7 | No | Add Social Ideas Desk parser tests | Root and thread commands are accepted/rejected explicitly. | `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py -q` | `tests/test_social_ideas_desk.py` |
| 8 | No | Add social idea loader dry-run/fixture path | CI can rank social ideas without local private DB data. | `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py -q` | `orchestrator/social_ideas.py`, tests |
| 9 | No | Add social idea feedback store | Actions persist safe idea feedback without schema changes. | `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py -q` | `orchestrator/social_ideas.py`, tests |
| 10 | No | Wire Social Ideas Desk Slack command | `social ideas` posts a numbered social idea thread. | `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_slack_bot.py -q` | `slack_bot/handlers/social_ideas.py`, tests |
| 11 | No | Wire Social Ideas Desk actions | `draft`, `save`, `revise`, `reject`, and `follow up` update feedback safely without posting live or touching newsletter flow. | `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_followup_research.py -q` | Slack handler, `orchestrator/social_ideas.py`, follow-up integration |
| 12 | No | Add no-live-post/no-newsletter-gate regression for Social Ideas Desk | Social idea actions cannot call live posting/email/sync or block newsletter phases. | `.venv/bin/python3 -m pytest tests/test_social_ideas_desk.py tests/test_social.py tests/test_runner.py -q` | tests |
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
| Social Ideas Desk feedback is mistaken for newsletter control or publish approval | Could block the newsletter or post unintentionally | Treat feedback as social-planning only; add no-live-post and no-newsletter-gate regression tests |
| Social idea feedback creates another hidden source of truth | Later agents may not know what Slack feedback means | Store feedback in a documented JSON contract first; update handoff/runbook evidence |
| Ranking ideas from `memory.db` makes CI depend on private data | CI failure or false confidence | Use fixture/dry-run idea loader in tests |

## Slash Goal Prompt

Use this after the owner reviews and accepts the runbook:

```text
/goal Implement MindPattern v3 Feature 24: Ask Follow-Up Research plus optional Slack Social Ideas Desk.

Primary source of truth:
- docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md
- docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-implementation-plan.md
- .claude/handoffs/2026-06-26-system-audit-slack-social.md

This is a new-feature pass for the "Ask Follow-Up" Research Button/Command and
the optional paired Slack Social Ideas Desk. Social Ideas Desk is only for social
post ideas and follow-up research. It is not a newsletter story review desk, not
a newsletter approval gate, and not a live social posting approval. Start with
the command-first MVP unless the owner explicitly approves Slack Block Kit
interactivity.

Hard requirements:
- Keep Slack-bot-first behavior.
- Owner-only commands; fail closed if owner identity is missing.
- No new background auto-research loop from this feature.
- No full daily pipeline run from this feature.
- No extra/manual newsletter send from this feature, social post, Fly sync, or
  deployment without explicit owner approval.
- No live outbound social post ever without explicit owner approval in Slack.
- The pipeline remains responsible for choosing newsletter stories.
- The normal scheduled daily newsletter must not wait for Social Ideas Desk
  feedback or approval to research, write, or send.
- Social Ideas Desk must be social-post-ideas only; it must not select,
  approve, block, write, or send newsletter stories.
- Social Ideas Desk feedback must not publish anything live.
- Dry-run/focused tests must not call Claude, network, Slack, email, social APIs,
  or Fly.
- Do not expose or commit secrets, personal data, raw Slack message bodies,
  subscriber data, databases, users.json, or social-config.json.
- Do not add dependencies or change schema without explicit owner approval.

Execution rules:
- Start by recording current dirty files and baseline tests.
- Follow the implementation plan task by task, in dependency order.
- For each task: write/update tests first, implement the smallest change, run
  the task verification command, then update the Done column and evidence.
- Preserve unrelated user changes.
- Keep draft-thread follow-up behavior from approving, posting, skipping, or
  losing the draft.
- Keep Social Ideas Desk actions from posting social content, sending email, or
  touching newsletter story selection.
- Keep Social Ideas Desk feedback from blocking newsletter research, writing, or
  sending.
- After code/docs changes, run Graphify where required.
- Work in small commits by verified task group.

Definition of done:
- `#mp-briefing` accepts `follow up: <topic>` and returns scoped findings
  in-thread.
- At least one Slack draft/review workflow accepts a `follow up:` reply without
  approving or posting anything.
- Follow-up service has deterministic dry-run behavior and safe trace/artifact
  output.
- `social ideas` shows ranked social post ideas in one Slack thread.
- Social Ideas Desk supports `draft`, `save`, `revise`, `reject`, and
  `follow up` actions with safe feedback state.
- The newsletter still researches, writes, and sends from the normal
  quality-gated pipeline without waiting for Social Ideas Desk feedback.
- Follow-up failures are visibly marked degraded or failed.
- CI-equivalent tests pass locally.
- Runbook and handoff are current for the next agent.
- Repo is clean or dirty files are clearly explained.
```

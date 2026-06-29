# 2026-06-26 System Audit, Slack/Social Diagnosis, and Improvement Backlog

## Scope

This handoff started as an audit-only pass requested by Tayler: understand
MindPattern v3 as it works today, diagnose why Slack/social posting has not
worked for weeks, and prepare prioritized recommendations.

It now also tracks the 2026-06-26 fix-first recovery implementation. Production
deploy/smoke was not run in this recovery pass without owner approval.

## Current Repo State

- Branch: `main`
- Remote tracking: `main...origin/main`
- HEAD when inspected: `44329ba03d07ce3495d61277711b1fa8a283613e`
- Worktree was clean before this handoff file was added.
- `graphify-out/GRAPH_REPORT.md` was refreshed on 2026-06-26 after Task 23:
  6674 nodes, 10330 edges, 409 communities, built from `77ba2277`.

## Recovery Implementation Status

Fix-first tasks completed locally through Task 24:

- Slack posts, skills, and tips now use fail-closed approval parsing.
- Slack draft edit flow now re-previews edited copy and requires a second
  explicit approval before any live post.
- Disabled social platforms now return manual-copy draft output instead of
  making the daily social phase disappear.
- `#mp-briefing` now has redacted bot doctor/status visibility plus source,
  social, and quality-floor status.
- Preflight now emits structured per-source health for RSS, HN, Twitter/X,
  Reddit, Exa, and YouTube, including unavailable/failed/timeout states.
- Newsletter synthesis now has a tested quality floor, duplicate story/angle
  risk checks, agent coverage floor, and source-balance candidate selection.
- GitHub Actions now runs a deterministic critical subset of
  `tests/test_runner.py` instead of excluding runner behavior entirely.
- Obsolete defang tests were updated to preserve the restored research-agent
  contract: no default Claude tool allow/deny fences for daily research agents.
- Graphify artifacts were refreshed and `graphify check-update .` exited
  cleanly.

Local recovery commit range before the Graphify/evidence commit:

- First recovery commit: `6690b5d docs: add fix-first recovery runbook`
- Last code/CI commit: `3059d10 ci: run critical runner tests`
- Full list: `git log --oneline --reverse origin/main..HEAD`

Latest Task 23 verification:

- `.venv/bin/python3 -m pytest tests/test_agent_defang.py tests/test_identity.py::test_research_agent_command_does_not_add_default_tool_fences -q` -> 8 passed in 0.11s.
- `.venv/bin/python3 -m pytest -q --tb=short tests/test_runner.py::TestPhaseTrendScan tests/test_runner.py::TestPhaseResearch tests/test_runner.py::TestPhaseSynthesis tests/test_runner.py::TestPhaseSocial` -> 23 passed in 0.40s.
- `.venv/bin/python3 -m pytest tests/test_runner.py -q` -> 69 passed in 0.58s.
- `.venv/bin/python3 -m pytest tests/ -q --tb=short --ignore=tests/test_cors.py --ignore=tests/test_engagement_linkedin.py --ignore=tests/test_memory_cli.py --ignore=tests/test_runner.py -k "not test_blocked_when_at_limit and not test_get_model_research_agent"` -> 1154 passed, 3 deselected, 1 warning in 93.93s.

Graphify verification:

- `graphify update .` -> rebuilt `graphify-out/graph.json` and
  `graphify-out/GRAPH_REPORT.md`.
- `graphify check-update .` -> exit 0.

Remaining approval-bound work:

- Production Fly deploy, live Slack channel smoke, and full daily pipeline run
  remain deferred until Tayler explicitly approves them.

External or approval-bound blockers:

- Reddit remains dependent on an authenticated backend; the pipeline now marks
  it unavailable instead of treating it as silent empty research.
- Twitter/X query search remains dependent on a working search backend/cookie
  path; failures now surface in source health with safe diagnostics.
- Exa and YouTube production health still require a network-enabled production
  smoke because local sandbox network failures are not proof of production
  failure.
- No live Slack post, outbound social post, Fly deploy, or full daily pipeline
  was run during this recovery goal.

## Feature 24 Ask Follow-Up Update - 2026-06-27

Ask Follow-Up now treats `cover`, `draft`, `archive`/`save`, and `ignore` as
real owner actions, not vague recommendations.

Implemented behavior:

- `follow up: <question>` fans out to four focused research agents:
  `followup-web-researcher`, `followup-social-researcher`,
  `followup-technical-researcher`, and `followup-skeptic-researcher`.
- Slack labels the agent-returned `next_action` as `Suggested next step`.
  Real owner commands are shown separately as `Actions`.
- `cover` stores follow-up findings as high-importance
  `followup_cover_candidate` findings for the next day. The normal scheduled
  newsletter pipeline will consider those findings; no newsletter is sent from
  the follow-up action.
- `draft` routes the follow-up findings into the existing
  `PostsHandler._run_and_approve()` social pipeline, so it uses the established
  Creative Director, writers, critics, humanizer, and expeditor path. Live
  posting still requires explicit Slack approval.
- `archive` / `save` writes follow-up findings into `memory.db.findings` and
  links them into the working `entity_graph`, so the artifact is part of
  durable memory/graph state instead of only markdown.
- `ignore` stores an agent note marking the follow-up handled.
- `#mp-briefing` now waits for one owner action reply after a follow-up result.
  The post/skills/tips approval loops also recognize follow-up actions before
  normal approval parsing.

Verification for this update:

- `.venv/bin/python3 -m pytest tests/test_followup_research.py -q` -> 15
  passed.
- `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsEditFlow tests/test_slack_bot.py::TestSkillsTipsEditFlow tests/test_slack_bot.py::TestBriefingFollowupCommand tests/test_runner.py::TestDryRunPhases -q`
  -> 34 passed.
- `.venv/bin/python3 -m pytest tests/test_social.py -q` -> 48 passed.
- `python3 -m py_compile orchestrator/followup.py slack_bot/handlers/followup.py slack_bot/handlers/briefing.py slack_bot/handlers/posts.py slack_bot/handlers/skills.py slack_bot/handlers/tips.py`
  -> passed.
- `git diff --check` -> passed.

Still not done until explicitly run:

- Deploy this update to Fly.
- Live Slack smoke in `#mp-briefing`:
  1. send `follow up: <specific topic>`;
  2. confirm agent coverage and findings return;
  3. reply `archive`, `cover`, and `draft` on separate follow-up runs;
  4. confirm `draft` waits for approval and does not post by itself.
- Optional Social Ideas Desk remains deferred and social-only.

## Features 17, 18, 20, and 21 Spec Draft - 2026-06-28

Created the spec and dependency-ordered implementation plan for the next
feature bundle:

- Feature 17: Narrative Arc Builder
- Feature 18: Social Angle Lab
- Feature 20: Audio Morning Briefing
- Feature 21: Short-Form Video Script Mode

Primary files:

- `docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-runbook.md`
- `docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-implementation-plan.md`

Scope decisions captured in the runbook:

- Feature 20 is not a dashboard feature. It should generate audio from the
  newsletter/research pipeline in MindPattern v3 and render it on the public
  Rabbit Hole site at `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`.
- Feature 21 starts as Slack-ready video script packages with source evidence,
  captions, shot lists, and manual-publish labels. Actual MP4 generation is
  optional and requires explicit approval for provider/dependency choices.
- Feature 18 must use the existing Slack-bot-first social workflow. It can hand
  selected angles to the existing approval-gated social draft path, but it must
  not auto-post.
- Feature 17 creates source-backed narrative arc artifacts for synthesis,
  social angles, audio, and video scripts. It should not force newsletter story
  selection or require Slack approval before the daily newsletter runs.

Research sources checked for the spec include official/current docs for OpenAI
TTS/video APIs, Slack external file uploads, Vercel Blob and Next.js route
handlers/static assets, C2PA/c2patool provenance, OWASP LLM Top 10, Microsoft
GraphRAG, Graphiti, Remotion, and FFmpeg. Agent Reach was checked with
`agent-reach doctor --json` during this planning pass.

The new-feature ideas table now has a persistent `Done` column. Rows 17, 18,
20, and 21 are marked `No - spec ready`; row 24 Ask Follow-Up is marked `Yes`
with local/CI evidence; row 25 Social Ideas Desk remains `Deferred`.

Planning follow-up: the implementation plan now includes phase checkpoints and
fixes the dependency order so Social Angle Lab wires `draft <n>` first, while
`video angle <n>` is handled later in the Feature 21 video-script phase after
the video package service exists.

Owner follow-up on 2026-06-28: add an Opus 4.8 execution gate. The runbook and
implementation plan now require a run/review with Opus 4.8 before substantial
implementation continues, unless Tayler explicitly approves continuing in a
non-Opus execution environment.

No implementation, tests, deploy, full pipeline run, Vercel change, Fly change,
schema change, or provider dependency install was performed for Features 17,
18, 20, or 21 in this spec pass.

## Features 17/18/20/21 Opus 4.8 Approval Gate - 2026-06-28

Task 0 (Opus 4.8 runbook/plan review gate) is complete. Reviewed by Opus 4.8
(`claude-opus-4-8[1m]`) acting purely as an approval gate; no feature code was
implemented, nothing was committed, and no deploy/pipeline/schema/dependency
action was taken.

Verdict: **APPROVED TO CONTINUE**, conditional on the required edits below being
made before the specific tasks they gate.

Evidence reviewed:

- Runbook and implementation plan read in full.
- Hard requirements verified at the spec level: F17 enrichment-only; F18 Angle
  Critic reads as a skeptical assigning editor (focus, why-now, audience value,
  evidence strength, tension, specificity, Tayler fit, risk calibration, hard
  kill switches), not a generic ranker; F20 publishes to the Rabbit Hole site
  through the v3 public read-only API, not the old dashboard UI; F21 is
  Slack-script-only with MP4/provider work owner-gated.
- Task 2 foundation slice (`orchestrator/media_contracts.py` +
  `tests/test_media_artifact_contracts.py`) judged acceptable; redaction,
  date/slug/path validation, and traversal guards are solid.
  `.venv/bin/python3 -m pytest tests/test_media_artifact_contracts.py -q`
  -> 6 passed.

Conditional required edits (binding before the gated task):

1. F17 enrichment-only must be made enforceable. Arcs may be injected ONLY into
   synthesis pass 2 / narrative context (runner.py:1356), NEVER into
   `_balance_story_candidates()` (runner.py:1196) or pass-1 story selection
   ("Select exactly 5 stories", runner.py:1234). Add a regression test asserting
   the pass-1 selected story set is identical with and without arcs for the same
   fixtures. Gates Tasks 4-6.
2. F18 writer/expeditor conflict is a hard deadlock, not a soft disagreement:
   `social/writers.py:310-316` makes "I run 12 agents" / "my pipeline" an
   absolute pipeline-failing kill switch, while `agents/expeditor.md:70-72`
   flags-for-revision any draft that lacks one of those exact strings. The two
   prompts contradict on identical tokens, so live `#mp-posts` likely already
   loops or fails. Capture an explicit owner-approved boundary (hide-infra vs.
   show-builder-credibility) and reconcile both prompts + tests BEFORE Task 8.
3. F18 angle artifacts must be pinned under gitignored
   `reports/ramsay/social-angles/`. `data/social-angles/` is NOT gitignored
   (proven: tracked `data/social-drafts/eic-topic.json`), so the `data/` option
   would commit angle content. Resolve the runbook's "data/ vs reports/"
   ambiguity in favor of the ignored path or add an explicit `.gitignore` entry.

Non-blocking notes for implementers:

- Generated audio/arc/video artifacts under `reports/` are already safe
  (`.gitignore` line 25 ignores `reports/`). Keep all generated media there.
- F20's "first adapter = OpenAI TTS" introduces a paid third-party provider and
  new credentials — a departure from the subscription-only posture. The dry-run
  MVP must be fully functional with deterministic output and no OpenAI
  dependency; live TTS stays owner-gated. Consider local macOS `say` as a
  zero-cost local TTS option for dev/dry-run.
- `dashboard/routes/api.py` is the public API layer, not the dashboard viewer
  UI; adding read-only audio/arc endpoints there satisfies the "not the
  dashboard" requirement. Do not build a viewer UI in the dashboard for F20.

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

Corrected desired fix path:

1. Keep the product direction Slack-bot-first, not background auto-post-first.
2. Treat the separate Slack channels as the publishing surface:
   - `#mp-posts`: URL/idea -> full social pipeline -> drafts -> owner approval.
   - `#mp-skills`: raw skill tip -> "Skill of the Day!" platform drafts.
   - `#mp-tips`: raw tip -> "Tayler'd Tip!" platform drafts.
   - `#mp-engagement`: search/reply sniper -> approved replies.
   - `#mp-approvals`: daily pipeline approval gates.
   - `#mp-briefing`: run status and morning digest.
   - `#mp-harness`: harness/developer operations.
3. Separate "platform can publish after Slack approval" from "pipeline should
   auto-create and auto-post." The former is needed; the latter is not wanted.
4. Enable platform credentials only so approved Slack-channel drafts can post.
5. Keep every outward post behind an explicit owner reply in the Slack thread.
6. Fix handler approval semantics before turning posting back on: `posts` is
   strict, but `skills` and `tips` currently default unclear replies to all
   platforms.
7. Add manual-copy fallback when a platform is disabled, so the bot still
   formats excellent posts without sending them.
8. Verify by dropping one controlled test message in each Slack content channel
   and confirming it produces drafts, waits for owner approval, and only posts
   after an explicit approval reply.

## Slack Regression Context: Local Bot -> Fly Bot

User clarification: the Slack bot/channel workflow was working at one point,
then the system was updated to run the bot on Fly so posts could be created
from the phone, and the workflow stopped working after that move.

Evidence from history:

- Original Slack bot handoff (`2026-03-21`) says the bot was designed as a
  local Socket Mode daemon running on the Mac with macOS Keychain credentials.
- Follow-up handoff (`2026-03-22`) says `com.taylerramsay.slack-bot` was
  running locally via launchd, connected via Socket Mode, with channels:
  `#mp-posts`, `#mp-engagement`, `#mindpattern-approvals`, `#mp-briefing`.
- M0 plan explicitly changed the architecture so the Fly app could support
  phone-post workflow:
  - `a7767e5` container hardening: `start.sh` runs dashboard + Slack bot.
  - `ca3fbfc` bot hardening: executor dispatch + heartbeat -> `/healthz`.
  - `00ef198` Fly -> Mac journal: phone posts should reach local `memory.db`.
- Current local launchd Slack bot services are not registered, so the local
  daemon path is no longer active.
- Current Fly state during this audit:
  - `/healthz` says bot is alive.
  - Fly `SLACK_CHANNEL_CONFIG` resolves all 7 handlers: posts, skills, tips,
    engagement, approvals, briefing, harness.
  - Running Fly bot process has `/root/.local/bin` in PATH and
    `CLAUDE_CODE_OAUTH_TOKEN` present.
  - `/app/data` is symlinked to `/data`, so repo-relative data paths resolve to
    the Fly volume.

Live Slack check on 2026-06-26:

- User sent a live test in `#mp-posts`.
  - Fly logs show the event reached the bot:
    `Event received: type=message, channel=C0ANEDEDJD7, user=U0AM88ZGK8A`.
  - The bot replied and started `PostsHandler`:
    `[mp-posts] Creative Director: generating brief`.
  - The handler progressed to:
    `[mp-posts] Brief generated` and `[mp-posts] Running writers`.
  - Writer stage then failed for both platforms:
    `Writer failed for bluesky: No module named 'core'` and
    `Writer failed for linkedin: No module named 'core'`.
  - This proves Socket Mode, owner filtering, `#mp-posts` routing, and the
    first Claude call worked on Fly. The concrete failure boundary was the Fly
    image packaging: deployed code imports `core`, but the Dockerfile did not
    copy `core/` into `/app`.
  - Fix committed as `a847ddf`: add `COPY core/ core/` to `Dockerfile` and
    add `tests/test_fly_dockerfile.py` to guard the packaging dependency.
  - Fix deployed to Fly on 2026-06-26. Verification:
    `https://mindpattern.fly.dev/healthz` returned ok, all 7 Slack handlers
    registered, Socket Mode connected, and SSH import check showed
    `/app/core/__init__.py`.
- Slack API check from the deployed bot token shows:
  - `#mp-posts` = `C0ANEDEDJD7`, bot member, user member, public, not archived.
  - `#mp-skills` = `C0AP3CCL4G5`, bot member, user member, public, not archived.
  - `#mp-tips` = `C0APYE9HBK3`, bot member, user member, public, not archived.
  - `#mp-briefing` and `#mp-engagement` also show bot/user membership.
- Earlier Slack history metadata, without message bodies, before the follow-up
  `#mp-skills` / `#mp-tips` tests:
  - Latest `#mp-skills` owner message: 2026-05-12 09:36:58 EDT.
  - Latest `#mp-tips` owner message: 2026-05-12 09:15:07 EDT.
  - Latest `#mp-posts` owner message: 2026-06-26 14:08:36 EDT.
- Follow-up live test on 2026-06-26:
  - Slack delivered current-day events to both handlers:
    - `#mp-skills` at 18:53:54 UTC, channel `C0AP3CCL4G5`.
    - `#mp-tips` at 18:54:08 UTC, channel `C0APYE9HBK3`.
  - No bot reply followed because both handlers silently returned for messages
    shorter than 20 characters unless the exact message was `help` or `?`.
  - Fix in progress: short inputs now reply with channel-specific guidance
    instead of disappearing. Regression tests added in `tests/test_slack_bot.py`.
- Interpretation for `#mp-skills` / `#mp-tips`:
  - They are not deleted, private, archived, or missing from the deployed bot
    config.
  - The bot and owner are still members of both channels.
  - No current-day user message has landed in those channels according to Slack
    history. The next useful test is a live `help` message in each channel while
    tailing Fly logs.
  - Current code makes `#mp-skills` and `#mp-tips` reactive channels: a user
    pastes a skill/tip, then the bot creates drafts and waits for approval. The
    audit has not found a daily scheduled path that automatically creates Skill
    of the Day or Tayler'd Tip drafts.
  - The Slack app manifest only includes public-channel scopes/events
    (`channels:*`, `message.channels`). If these channels are ever converted to
    private channels, the current bot will not receive their messages.

Interpretation:

- The regression is probably not "bot process dead" or "channels missing".
- More likely failure boundary: a Slack event from the phone reaches, or fails
  to reach, the handler after the local -> Fly move. `/healthz` does not prove
  event delivery, handler dispatch, draft generation, approval polling, or
  platform posting.
- The next proof needs to be a live handler smoke, not another heartbeat check.

Required smoke sequence:

1. In Slack from the phone, send `help` to `#mp-posts`.
   - If no reply: investigate Slack event subscription, bot invite, channel ID,
     owner ID filtering, or Socket Mode event delivery.
2. Send `status` to `#mp-briefing`.
   - If no reply: handler dispatch or owner filtering is broken.
3. Send `help` to `#mp-skills` and `#mp-tips`.
   - If help works but drafting fails: generation path is broken.
4. Tail Fly logs while sending the messages.
   - Look for `Event received`, handler errors, Claude CLI errors, missing file
     errors, or posting-client errors.
5. Only after help/status work, test a non-live draft generation path.
   - Do not approve a live platform post until the draft, edit, and approval
     loop are proven.

## Fix-First Table: Existing Things That Are Broken or Not Proven Working

These are not feature ideas. They are existing paths that are disabled, broken,
unsafe, or not proven healthy enough to rely on.

Implementation runbook/spec: `docs/runbooks/2026-06-26-fix-first-recovery-runbook.md`.
Task breakdown plan: `docs/runbooks/2026-06-26-fix-first-recovery-implementation-plan.md`.

Goal execution baseline on 2026-06-26:

- Dirty files were docs-only: this handoff plus the two runbook files.
- Slack/social safety baseline:
  `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q`
  -> 172 passed in 3.27s.
- Preflight/newsletter baseline:
  `.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_evaluator.py tests/test_dedup_resurfacing.py tests/test_newsletter.py -q`
  -> 66 passed in 88.43s.
- Runner baseline:
  `.venv/bin/python3 -m pytest tests/test_runner.py -q`
  -> 61 passed in 0.61s.
- No live Slack post, email send, Fly deploy, full pipeline run, schema change,
  or dependency change was performed.
- Task 2 complete: added shared `slack_bot.approval.parse_platform_approval()`
  and switched `#mp-posts` to use it.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 39 passed in 0.02s.
  - `.venv/bin/python3 -m pytest tests/test_approval_parsing.py -q`
    -> 53 passed in 3.10s.
- Task 3 complete: switched `#mp-skills` and `#mp-tips` to the shared
  fail-closed approval parser. Unclear replies now post nothing.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 57 passed in 0.03s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q`
    -> 219 passed in 3.25s.
- Task 4 complete: added `slack_bot.drafts` helpers for `edit platform:
  replacement` replies. Edit commands are parsed as revisions, not approvals.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 64 passed in 0.03s.
- Task 5 complete: wired `#mp-posts` edit flow. `edit platform: replacement`
  now re-previews and requires a second explicit approval before posting.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 67 passed in 0.03s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q`
    -> 229 passed in 3.24s.
- Task 6 complete: wired the same edit flow into `#mp-skills` and `#mp-tips`.
  Edits now update one platform draft, re-preview, and still require a separate
  explicit approval. Invalid edits return an error and keep waiting.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 73 passed in 0.04s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q`
    -> 235 passed in 3.27s.
- Task 7 complete: disabled platforms now return structured manual-copy
  results in `#mp-posts`, `#mp-skills`, and `#mp-tips` without initializing
  live API clients. Skills/tips no longer mark client failures as successful.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 79 passed in 0.19s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_posting.py -q`
    -> 132 passed in 0.18s.
- Task 8 complete: added a redacted Slack bot `doctor` report in
  `#mp-briefing`. It reports registered handlers, configured channel count,
  missing channel config names, owner configured/missing, token source labels,
  and heartbeat freshness without printing tokens, owner IDs, channel IDs, or
  message bodies.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 81 passed in 0.11s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q`
    -> 243 passed in 3.23s.
- Task 9 complete: centralized platform publish modes in `social.posting`.
  `enabled: true` is live, configured `enabled: false` is `manual_only` by
  default, explicit `draft_enabled: false` is `skipped`, and unknown/missing
  platforms are `error`. Slack post/skills/tips handlers now use the same mode
  helper and canonical result statuses.
  - `.venv/bin/python3 -m pytest tests/test_social.py tests/test_posting.py -q`
    -> 58 passed in 0.12s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 81 passed in 0.10s.
- Task 10 complete: `SocialPipeline` now targets draft-capable platforms, so
  all-disabled platform config can still select a topic, create a brief, write
  drafts, request approval, and return `manual_copy` results without
  initializing live API clients. Draft-only writer failures are structured
  `Writing: ...` errors, not early platform skips.
  - `.venv/bin/python3 -m pytest tests/test_social.py -q`
    -> 46 passed in 0.11s.
  - `.venv/bin/python3 -m pytest tests/test_social.py tests/test_runner.py -q`
    -> 107 passed in 0.63s.
- Task 11 complete: `_phase_social()` now skips only when no platform is
  draft-capable. Disabled-but-draft-capable config runs `SocialPipeline` and
  can return `manual_copy`; manual-only/skipped/error results are not stored as
  live `posted` engagement signals.
  - `.venv/bin/python3 -m pytest tests/test_runner.py -q`
    -> 62 passed in 0.48s.
  - `.venv/bin/python3 -m pytest tests/test_social.py tests/test_runner.py -q`
    -> 108 passed in 0.53s.
- Task 12 complete: `#mp-briefing` pipeline summaries now distinguish posted,
  manual-copy draft, skipped, error, kill-day, and no-post social states. Manual
  summaries include platform/status only, not draft bodies.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q`
    -> 84 passed in 0.10s.
  - `.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_runner.py -q`
    -> 146 passed in 0.52s.
- Task 13 complete: `preflight.run_all()` now returns `source_health` while
  preserving `items`, `assignments`, and `source_counts`. Each source records
  `status`, `count`, `duration_ms`, and `reason`; success, empty, exception,
  timeout, and missing-tool states are classified.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py::test_source_health_success tests/test_preflight.py::test_source_health_empty tests/test_preflight.py::test_source_health_exception tests/test_preflight.py::test_source_health_timeout tests/test_preflight.py::test_source_health_missing_cli -q`
    -> 5 passed in 0.01s.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py -q`
    -> 32 passed in 88.34s.
- Task 14 complete: RSS now exposes `fetch_with_diagnostics()` and `run_all()`
  merges RSS diagnostics into `source_health`. Normal, empty, partial, timeout,
  and failed states are represented; partial failures include `feed_errors`
  with bad feed context while preserving healthy feed items.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py::test_rss_fetch_with_diagnostics_normal_feed tests/test_preflight.py::test_rss_fetch_with_diagnostics_empty_feed tests/test_preflight.py::test_rss_fetch_with_diagnostics_names_bad_feed tests/test_preflight.py::test_source_health_merges_rss_diagnostics -q`
    -> 4 passed in 0.01s.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py -q`
    -> 36 passed in 88.45s.
- Task 15 complete: Twitter/X and HN now expose diagnostic fetchers and
  `run_all()` merges them into `source_health`. Twitter/X failures include
  backend, query, exit code, and safe stderr snippet. HN empty/failure states
  include query thresholds and structured stderr context.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py::test_hn_fetch_with_diagnostics_empty tests/test_preflight.py::test_hn_fetch_with_diagnostics_failure tests/test_preflight.py::test_twitter_fetch_with_diagnostics_cli_failure tests/test_preflight.py::test_twitter_fetch_with_diagnostics_success_shape -q`
    -> 4 passed in 0.01s.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py -q`
    -> 40 passed in 88.42s.
- Task 16 complete: Reddit, Exa, and YouTube now expose diagnostic fetchers and
  `run_all()` uses them. Reddit backend-off/all-failed states report
  `unavailable`; missing `mcporter` or `yt-dlp` reports `unavailable`; runtime
  tool errors and timeouts report `failed` or `timeout` with safe
  backend/query/channel context. `run_all()` now returns
  `source_health_summary`, excluding unavailable optional sources from the
  expected-source denominator while keeping configured failures visible.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py -q`
    -> 46 passed in 88.37s.
- Task 17 complete: `_phase_trend_scan()` now writes source-health summary into
  the `preflight_complete` trace with run date, source counts, compact
  per-source `status`/`count`/`reason`, and no nested tool stderr payloads.
  `#mp-briefing status` reads the latest matching preflight trace and reports
  responsive source count, unavailable source names, and degraded source
  names/statuses without printing raw backend errors or message content.
  - `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseTrendScan::test_logs_source_health_summary_to_trace tests/test_slack_bot.py::TestBriefingSocialState::test_status_reports_source_health_from_latest_trace -q`
    -> 2 passed in 0.07s.
  - `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_slack_bot.py tests/test_preflight.py -q`
    -> 194 passed in 88.94s.
- Task 18 complete: `orchestrator.evaluator.assess_quality_floor()` now
  returns `pass`, `degraded`, or `fail_retryable` with metrics, thresholds, and
  reasons. It is a pure helper only; newsletter send behavior is unchanged
  until the integration task. Defaults are documented in the runbook:
  overall/coverage/dedup/sources scores, 11-of-13 agents, 70 findings, 4 source
  classes, 0.75 responsive source ratio, 0.80 unique URL ratio, and 0.35
  single-source dominance ceiling with separate retryable floors.
  - `.venv/bin/python3 -m pytest tests/test_evaluator.py::test_assess_quality_floor_passes_good_synthetic_run tests/test_evaluator.py::test_assess_quality_floor_marks_degraded_synthetic_run tests/test_evaluator.py::test_assess_quality_floor_marks_retryable_bad_synthetic_run -q`
    -> 3 passed in 0.01s.
  - `.venv/bin/python3 -m pytest tests/test_evaluator.py tests/test_runner.py -q`
    -> 72 passed in 0.48s.
- Task 19 complete: `detect_duplicate_story_risk()` now flags repeated
  canonical URLs, near-title repeats, and repeated story angles against recent
  findings. The quality-floor helper includes `duplicate_story_risk` with
  default ceiling `0.0` and retryable ceiling `0.20`. Exact URL repeats ignore
  tracking query strings and can be bypassed only by explicit new-angle/follow-
  up metadata or a detectably different source date.
  - `.venv/bin/python3 -m pytest tests/test_dedup_resurfacing.py::TestNewsletterDuplicateAngleGate::test_repeated_adjacent_day_story_fails_duplicate_angle_check tests/test_evaluator.py::test_duplicate_story_risk_flags_repeated_url tests/test_evaluator.py::test_quality_floor_flags_repeated_adjacent_day_angle tests/test_evaluator.py::test_duplicate_story_risk_does_not_overblock_related_story -q`
    -> 4 passed in 0.06s.
  - `.venv/bin/python3 -m pytest tests/test_dedup_resurfacing.py tests/test_evaluator.py -q`
    -> 25 passed in 0.07s.
- Task 20 complete: `_phase_research()` now assesses agent coverage before
  cross-agent dedup mutates finding lists. It returns `research_degraded` and
  an `agent_coverage` block with status, retryable flag, contributing count,
  zero-finding agents, failed agents, and reasons. Degraded coverage is logged
  as `research_agent_coverage`. 8-of-13 contributing agents is degraded;
  6-of-13 is `fail_retryable`; zero/failed agents are named.
  - `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseResearch::test_research_marks_8_of_13_agents_degraded tests/test_runner.py::TestPhaseResearch::test_research_marks_6_of_13_agents_retryable -q`
    -> 2 passed in 0.23s.
  - `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_agents.py -q`
    -> 102 passed in 0.59s.
- Task 21 complete: synthesis pass 1 now uses `_balance_story_candidates()`.
  The story-selection candidate pool caps dominant source classes using the
  `0.35` source ceiling and orders smaller source classes first; pass 2 still
  receives the full findings list for context. If only one source class is
  healthy, source balance is marked degraded and `source_balance_degraded` is
  written to traces instead of fabricating diversity.
  - `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis::test_source_balance_caps_single_source_candidate_dominance tests/test_runner.py::TestPhaseSynthesis::test_source_balance_marks_single_healthy_source_degraded -q`
    -> 2 passed in 0.08s.
  - `.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_runner.py -q`
    -> 113 passed in 88.88s.
- Task 22 complete: `_phase_synthesis()` now applies `assess_quality_floor()`
  after newsletter evaluation and before delivery can read the report.
  Retryable failures rewrite the report with the deterministic source-grounded
  fallback and log `newsletter_quality_floor_retryable`; degraded-but-usable
  drafts get a visible `Degraded issue notice` and log
  `newsletter_quality_floor_degraded`. The synthesis result includes
  `quality_floor`, `quality_fallback`, and `degraded`; `#mp-briefing status`
  surfaces the latest quality-floor incident from traces. Delivery receipt
  logic was not changed.
  - `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis::test_retryable_quality_floor_uses_deterministic_fallback tests/test_runner.py::TestPhaseSynthesis::test_degraded_quality_floor_adds_visible_notice tests/test_slack_bot.py::TestBriefingSocialState::test_status_reports_source_health_from_latest_trace -q`
    -> 3 passed in 0.17s.
  - `.venv/bin/python3 -m pytest tests/test_runner.py tests/test_newsletter.py tests/test_newsletter_receipts.py tests/test_slack_bot.py -q`
    -> 184 passed in 0.81s.

Keep the `Done` column in this table. Future agents should update the value in
place instead of deleting the column.

| Area | Done | What should happen | What is happening | Why it is not working | Fix needed |
|---|---|---|---|---|---|
| Daily social phase | Yes | Pipeline should create social candidates or an approval flow. | It skips social entirely. | `linkedin.enabled=false` and `bluesky.enabled=false`; runner exits with `Social: no platforms enabled`. | Separate "format draft" from "post live"; do not skip Slack draft creation just because posting APIs are off. |
| Slack approval for daily social | Yes | Daily pipeline should post approval requests to Slack. | It never reaches approval. | Social phase exits before `ApprovalGateway` runs. | Let pipeline send candidates to Slack bot/channel without auto-posting. |
| `#mp-posts` live posting | Yes | URL/idea should become platform drafts, then wait for approval. | Bot exists, but live posting depends on platform config/secrets. | Platform clients still need enabled config to publish. | Add manual-copy fallback when a platform is disabled; only post after explicit approval. |
| `#mp-skills` approval | Yes | It should only post after clear owner approval. | Unclear replies can default to all platforms. | Handler falls back to `approved = platforms` if reply is not understood. | Use strict parser: unclear reply means no post. |
| `#mp-tips` approval | Yes | It should only post after clear owner approval. | Unclear replies can default to all platforms. | Handler also defaults unclear replies to all platforms. | Use strict parser: unclear reply means no post. |
| Slack edit flow | Yes | User should paste edits and have the draft updated. | UI text says edits are allowed, but approval parsing does not really apply edits. | "Paste edited text" is advertised but not implemented as a real draft-revision state. | Add `edit bluesky: ...`, re-preview, then require approval again. |
| Slack bot local visibility | Partial | Logs should show current bot activity. | Local `reports/slack-bot.log` stopped around 2026-06-08. | Local launchd Slack bot services are not registered; production bot runs on Fly now. | Decide Fly-only bot vs reinstall local bot; add clear docs/status. |
| Slack channel health | Partial | Each channel should be testable. | Fly bot heartbeat is alive, but handler-by-handler behavior was not proven. | `/healthz` proves bot heartbeat, not that every channel command works. | Add bot `doctor`/`status` command that checks registered channels. |
| RSS preflight | Yes | RSS should produce source items. | Logs show RSS returned 0 for recent runs. | Earlier logs said `feedparser` was missing; later smoke still returned 0. | Add per-feed diagnostics; confirm feeds and dependency in real run environment. |
| Reddit preflight | Blocked | Reddit should produce community signal. | Reddit returns 0 / Agent Reach says Reddit backend is off. | No authenticated Reddit backend configured. | Install/configure Reddit backend or remove it from expected source count. |
| Twitter/X preflight | Partial | Twitter search should produce trend items. | Auth works, search fails. | `twitter search` failed with HTTP 404 / cookie extraction issue. | Fix query-search backend or switch Agent Reach backend. |
| HN preflight | Yes | HN should produce builder/startup items. | HN returned 0. | Query, threshold, or API path is likely too strict or failing silently. | Add per-query diagnostics and adjust thresholds. |
| Exa preflight | Yes | Exa should contribute semantic web search. | It recovered in logs, but local sandbox smoke failed DNS. | Local sandbox cannot prove production health; prior logs had timeouts. | Add production source-health report, not only local checks. |
| YouTube preflight | Yes | YouTube should fetch videos. | It recovered in logs, but local sandbox smoke failed DNS. | Sandbox network failure; not enough production proof. | Add daily YouTube source-count alert. |
| Newsletter quality floor | Yes | Bad input days should retry or escalate. | Newsletter still sends on weak-source days. | Delivery is gated more strongly than content quality. | Add pre-send floor: minimum agents, sources, unique URLs, and duplicate-angle score. |
| Duplicate story control | Yes | Same story should not repeat across days. | Exact duplicate titles were not found, but repeated URLs/angles remain possible. | Current dedupe catches some title/embedding duplicates, not "same angle again" well enough. | Add semantic cross-issue duplicate detector. |
| Agent coverage | Yes | Usually 13 agents should contribute. | Recent days had 6-8 contributing agents. | Some agents failed, timed out, or stored zero findings. | Retry zero agents or mark issue degraded before synthesis. |
| Source balance | Yes | Newsletter should not be dominated by one source. | arXiv dominated recent findings. | Source weighting lets one source overfill the issue. | Cap source dominance and boost underrepresented source classes. |
| CI coverage | Yes | Critical runner behavior should be tested in CI. | `tests/test_runner.py` is ignored in GitHub Actions. | Main pipeline tests are excluded. | Split/stabilize runner tests and put critical subset back in CI. |
| Graphify freshness | Yes | Architecture graph should match HEAD. | Graph report is stale. | Built from old commit `eb913fee`. | Run/update Graphify after code changes. |

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

## 2026-06-26 No-Outbound Smoke And Follow-Up Fixes

Smoke scope:
- A real local pipeline smoke was run with `MP_DISABLE_OUTBOUND=1`; it was not a
  live newsletter send and did not post to LinkedIn/Bluesky.
- It was intentionally interrupted at the daily social Slack approval wait after
  the newsletter path had been proven.
- The local report is `reports/ramsay/2026-06-26.md`; it was 5111 words when
  first written and 5242 words after the degraded notice/footer.

Smoke evidence:
- Source-only smoke after fixes: RSS 152, HN 171, X/Twitter partial with feed
  fallback 3, Reddit unavailable, Exa 2, YouTube 1.
- Full no-outbound run `research-2026-06-26-e3fff7`: 371 preflight items, 177
  new, 194 already covered.
- Full source counts: GitHub 118, RSS 152, arXiv 30, Exa 25, YouTube 15, HN 11,
  X/Twitter 20 partial via feed fallback, Reddit 0 unavailable.
- Research: 13/13 agents completed, 181 raw findings, 52 cross-agent duplicates
  removed, 91 findings stored.
- Synthesis: evaluator overall 0.882; quality floor marked degraded for source
  dominance 0.41 over ceiling 0.35 and duplicate story risk 0.069 over ceiling 0.
- Delivery: `MP_DISABLE_OUTBOUND=1` blocked email send and subscriber broadcast.

Important caveats:
- The smoke exposed that the daily social pipeline can still auto-generate a
  social topic candidate and post a Slack approval request to
  `#mindpattern-approvals`. That is not the same as the intended
  channel-first `#mp-posts`, `#mp-skills`, and `#mp-tips` workflow.
- After the smoke, `run.py --skip-social` was wired to `MP_SKIP_SOCIAL=1`;
  `MP_SKIP_SOCIAL=1` skips social and engagement phases.
- After the smoke, `MP_DISABLE_OUTBOUND=1` blocks Slack approval/notification
  messages and skips Fly sync. Slack approval failures now fail closed instead
  of auto-approving Gate 1.
- `traces.db` had phase/events/checkpoints, but research agent execution was not
  mirrored into `agent_runs`. Future runs now create/complete `agent_runs` rows
  from the main runner after each agent result. Interrupted runs are now marked
  `interrupted`; the two smoke runs were manually corrected from stale
  `running` to `interrupted`.
- Reddit remains blocked by OpenCLI Chrome extension/login. X query search still
  returns HTTP 404, but feed fallback can return items when auth works.

## Top Next Actions

1. Make the Slack bot channel workflow the primary social product path, not the
   daily pipeline auto-post path.
2. Fix approval parsing consistency in `#mp-skills` and `#mp-tips` so unclear
   replies never default to posting.
3. Add manual-copy fallback for disabled platforms, so formatting still works
   even when API posting is off.
4. Fix source-channel observability and alerts so RSS/HN/Reddit/Twitter zeros
   are visible before the newsletter is written.
5. Add a newsletter quality floor that retries or escalates when source count,
   agent count, unique URLs, or duplicate angles fall below thresholds.

## 30 Pure New Feature Ideas

These are new product/platform ideas, not repairs. They assume the broken
source, newsletter quality, and Slack approval paths are stabilized first.

Keep the `Done` column in this table. Future agents should update the value in
place instead of deleting the column.

| # | Done | New feature | What it adds | Why it matters | Likely systems | Effort / Risk | Success signal |
|---|---|---|---|---|---|---|---|
| 1 | No | Slack Social Ideas Desk | A dedicated Slack command that shows social post ideas with draft/save/revise/reject/follow-up actions. | Turns Slack into a social planning room without touching newsletter story selection or sending. | `slack_bot`, `memory.db`, `reports`, social drafts | M / Med | User can review social post ideas, create drafts, and request follow-up from one Slack thread. |
| 2 | No | Topic Watchlists | User-defined topics like "agent security", "AI IDEs", "MCP", or "SaaS disruption" with custom depth and priority. | Lets the system intentionally track what matters instead of only reacting to feeds. | `memory`, `preflight`, dashboard | M / Low | Watchlist topics appear with coverage and freshness scores. |
| 3 | No | Trend Radar Dashboard | Visual map of rising topics, sources, companies, people, and tools over 7/30/90 days. | Makes research direction visible and helps spot momentum before it becomes obvious. | dashboard, embeddings, `run_quality` | L / Med | Dashboard shows trend clusters and velocity. |
| 4 | No | Opportunity Brief Generator | Converts research into "what to build / sell / write / test next" briefs. | Moves beyond newsletter summarization into actionable strategy. | `orchestrator`, memory, dashboard | M / Med | Each issue can produce 3-5 opportunity briefs. |
| 5 | No | Personal AI Research Assistant Chat | Ask questions over findings, newsletters, source archive, and vault memory. | Turns the archive into an interactive product instead of static history. | dashboard, embeddings, reports | L / Med | User can ask "what did we learn about MCP security this month?" |
| 6 | No | Story Lifecycle Tracker | Tracks a story from first signal to follow-up coverage, newsletter inclusion, social draft, and user feedback. | Prevents repeated stale coverage while preserving valuable follow-ups. | memory, reports, social | M / Med | Each major story has first-seen, used-in, and follow-up history. |
| 7 | No | Audience Feedback Portal | Lightweight page where readers can rate stories, request more/less, and submit topic requests. | Creates structured reader feedback instead of relying only on email replies. | dashboard, feedback tables | M / Low | Feedback records flow into preferences. |
| 8 | No | Reader Segment Editions | Generate optional editions for builder, founder, investor, or security-reader emphasis. | Lets one research run serve multiple audiences without diluting the main issue. | newsletter synthesis, preferences | L / Med | Same findings produce multiple distinct issue variants. |
| 9 | No | Weekly Strategy Memo | A Friday memo that synthesizes the week's patterns, not just daily stories. | Adds higher-level value and avoids daily-only short-termism. | reports, synthesis, memory | M / Low | Weekly memo cites the week's strongest evidence. |
| 10 | No | "Why This Matters" Cards | For each major story, generate a concise card: what happened, why now, who cares, what to do. | Makes content easier to reuse in Slack, social, and dashboard. | newsletter, dashboard, social | M / Low | Cards generated for top stories every day. |
| 11 | No | Source Trust Ledger | Tracks source reliability, freshness, uniqueness, and historical usefulness. | Helps the system prefer strong sources and explain why weak ones were downgraded. | preflight, memory, dashboard | M / Low | Top sources have trust/novelty scores. |
| 12 | No | Company/Product Tracker | Follow specific companies, repos, products, and standards over time. | Useful for recurring intelligence on important players. | preflight, memory graph | M / Low | Dashboard shows timeline per company/product. |
| 13 | No | GitHub Project Radar | Dedicated view for fast-rising repos, maintainers, funding, releases, and adoption signals. | Converts GitHub data into a real discovery product. | preflight GitHub, dashboard | M / Low | Radar highlights new projects before mainstream coverage. |
| 14 | No | MCP/Agent Tool Registry | Searchable registry of tools, MCP servers, CLIs, install commands, health, and use cases. | Builds on the platform's existing agent-tool focus and makes it reusable. | dashboard, memory, agent-reach | M / Med | User can search "best YouTube transcript tools" and get vetted options. |
| 15 | No | Build Recipe Generator | Converts "Skill of the Day" style findings into step-by-step implementation recipes. | Makes the newsletter directly useful to builders. | skill-finder, newsletter, dashboard | M / Low | Recipes include steps, prerequisites, and source links. |
| 16 | No | Experiment Backlog | Auto-generates product/code experiments from research and stores them as candidate tickets. | Bridges research into actual building work. | harness, memory, dashboard | M / Med | Findings can create ranked experiment cards. |
| 17 | No - spec ready | Narrative Arc Builder | Tracks multi-day arcs like "AI IDEs consolidate" or "agent governance becomes a category." | Produces deeper analysis than isolated daily items. | memory graph, synthesis | L / Med | Issues can include recurring arcs with evidence trails. |
| 18 | No - spec ready | Social Angle Lab | For any story, generate multiple social angles: contrarian, builder lesson, market take, tactical tip. | Gives the Slack bot richer choices without auto-posting. | Slack bot, social writers | M / Low | `#mp-posts` can ask for angle variants. |
| 19 | No | Content Swipe File | Saves strongest hooks, openers, titles, analogies, and post formats from past successful content. | Improves voice and speed over time. | memory, social, dashboard | M / Low | Bot can reuse proven structures without copying old content. |
| 20 | No - spec ready | Audio Morning Briefing | Generate a short spoken briefing from the daily issue or top research and publish it to the Rabbit Hole website, not the old dashboard. | Adds a useful consumption mode for mornings. | newsletter, TTS provider, v3 API, Rabbit Hole site | M / Med | User can play a 3-5 minute briefing on the public site. |
| 21 | No - spec ready | Short-Form Video Script Mode | Converts a selected story into a 30-60 second video script and shot list, then posts the package to Slack for manual social publishing. | Expands content output beyond newsletter and text social without auto-posting. | Slack bot, social writers, optional media provider | M / Low | Slack returns script, caption, B-roll notes, source links, and manual-publish labels. |
| 22 | No | Newsletter Section A/B Lab | Test alternate section ordering, titles, or framing against user/reader feedback. | Lets quality improve from evidence, not taste alone. | newsletter, feedback, evaluator | L / Med | Version metrics show which framing performs better. |
| 23 | No | Personal Knowledge Graph Explorer | Browse entities, topics, sources, and story relationships from the vault/database. | Makes the accumulated research legible. | memory graph, dashboard | L / Med | User can navigate from topic to stories to sources. |
| 24 | Yes | "Ask Follow-Up" Research Button | From a newsletter story or Slack draft, trigger a deeper follow-up research run. | Lets human curiosity steer the next layer of research. | Slack bot, orchestrator agents | M / Med | Implemented locally/CI: `#mp-briefing` and draft threads accept follow-up, four focused agents fan out, and `cover`/`draft`/`archive`/`ignore` actions are tested. Live smoke remains owner-approved. |
| 25 | Deferred | Slack Social Ideas Desk | A dedicated Slack command that shows social post ideas with draft/save/revise/reject/follow-up actions. | Turns Slack into a social planning room without touching newsletter story selection or sending. | Slack bot, memory, reports, social drafts | M / Med | User can review social post ideas, create drafts, and request follow-up from one Slack thread. |
| 26 | No | Competitive Landscape Maps | For a topic, produce a market map of companies, tools, categories, and open-source projects. | Useful for strategy and product opportunity discovery. | preflight, synthesis, dashboard | L / Med | Topic page shows category map with sources. |
| 27 | No | Decision Journal | Track editorial/product decisions made from the research and whether they paid off. | Closes the loop between insight and action. | vault, dashboard, memory | M / Low | Decisions link to source evidence and later outcomes. |
| 28 | No | Public Collections | Curated public pages like "Best AI agent tools this month" or "MCP security brief." | Turns private research into shareable assets. | dashboard, reports | M / Med | Collection page can be published from selected findings. |
| 29 | No | Sponsor/Partner Match Finder | Finds companies/tools that match newsletter themes and audience. | Creates monetization/business-development options without changing editorial flow. | research agents, dashboard | M / Med | Weekly list of relevant sponsor/partner leads. |
| 30 | No | Personal Engagement CRM | Track people engaged with on Bluesky/LinkedIn, conversation history, follow-ups, and outcomes. | Makes engagement strategic instead of one-off replies. | social engagement, memory, dashboard | M / Med | Contact timeline shows replies, topics, and next actions. |
| 31 | No | Research API / Webhooks | Expose selected findings, cards, and briefs to other tools through API/webhooks. | Lets MindPattern become infrastructure for other workflows. | FastAPI dashboard, auth, memory | L / High | Authenticated endpoint returns current findings/cards. |

## Mixed Repair and Improvement Backlog

Keep the `Done` column in this table. Future agents should update the value in
place instead of deleting the column.

| # | Done | Title | Type | Problem | Proposed change / why it matters | Files/systems | Benefit | Effort / Risk | Verification |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Yes | Slack-bot-first social workflow | Existing behavior | The audit over-framed social as daily auto-posting. | Make Slack channels the primary creation and approval UX; daily pipeline may suggest candidates, but user controls posts. | `slack_bot/handlers/*`, `social/pipeline.py` | Matches intended workflow and prevents surprise posts. | M / Med | One test draft per channel waits for owner approval before posting. |
| 2 | Yes | Separate draft generation from publishing | Reliability | Platform `enabled=false` currently blocks social work entirely in the daily path. | Add a "format-only" mode that always creates Slack drafts and only posts when an explicit approval plus enabled credential exists. | `social-config.json`, `slack_bot/handlers/posts.py`, `social/posting.py` | Bot remains useful even when APIs are off. | M / Med | Disabled platform returns formatted manual-copy draft, not a hard skip. |
| 3 | Yes | Fix `#mp-skills` unclear approval default | Safety | `skills.py` defaults unclear replies to all platforms. | Reuse the strict parser from `posts.py`; unclear text should not post. | `slack_bot/handlers/skills.py`, tests | Prevents accidental posting. | S / Low | Reply "wait" or pasted edit posts nothing. |
| 4 | Yes | Fix `#mp-tips` unclear approval default | Safety | `tips.py` also defaults unclear replies to all platforms. | Same strict approval parser and tests. | `slack_bot/handlers/tips.py`, tests | Prevents accidental posting. | S / Low | Reply "hold on" or "skip linkedin" posts nothing. |
| 5 | Yes | Implement real Slack edit flow | Existing behavior | Handlers say "paste edited text" but do not reliably replace drafts. | Let owner reply `edit bluesky: ...` or paste a replacement, then show a new preview and require approval. | `slack_bot/handlers/base.py`, `posts.py`, `skills.py`, `tips.py` | Turns Slack into an actual editor, not just approve/skip. | M / Med | Pasted edit updates draft and requires second approval. |
| 6 | No | Channel-specific post templates | New feature | `#mp-posts`, `#mp-skills`, and `#mp-tips` have similar code but different brand formats. | Extract templates for general post, Skill of the Day, Tayler'd Tip, launch note, contrarian take. | `slack_bot/handlers`, `agents/*.md` | Faster, more consistent content. | M / Low | Snapshot tests for each channel format. |
| 7 | No | Slack preview cards | New feature | Drafts are plain code blocks with limited metadata. | Show platform, char count, sources, policy warnings, expected action buttons/text. | `slack_bot/handlers/*` | Easier review from phone. | M / Low | Preview includes source URLs and limits. |
| 8 | No | Pending draft queue | New feature | If owner misses approval, work disappears after timeout. | Store drafts as pending with channel/thread/status and allow `status`, `approve`, `skip`, `revise` later. | `memory.db`, `slack_bot`, dashboard | No lost social work. | M / Med | Timeout draft can be resumed next day. |
| 9 | No | Social content calendar | New feature | There is no planning view of pending/posted ideas. | Add dashboard/Slack view for draft queue, posted history, channel source, and next recommended post. | dashboard, `social_posts` | Better cadence and planning. | L / Med | Calendar shows pending and published posts. |
| 10 | No | Daily newsletter-to-Slack idea picker | New feature | Newsletter stories are not automatically turned into Slack draft candidates. | After newsletter send, post top 3 social angles to `#mp-posts` or `#mp-briefing` for user selection. | `orchestrator/runner.py`, `slack_bot/handlers/briefing.py` | Converts research into posts without auto-posting. | M / Med | Briefing thread has 3 candidate post buttons/replies. |
| 11 | Yes | `#mp-briefing` richer run report | Existing behavior | Briefing only shows basic counts. | Include source counts, agent count, quality score, newsletter sent, social skipped reason, bot health. | `slack_bot/handlers/briefing.py` | One place to see daily health. | S / Low | `status` returns source/quality/social details. |
| 12 | Yes | Bot self-test command | Reliability | It is hard to know which Slack channels are wired. | Add `status`/`doctor` command showing registered handlers, owner ID, token source, heartbeat. | `slack_bot/registry.py`, `bot.py` | Faster incident diagnosis. | S / Low | Bot reports all configured channels. |
| 13 | Yes | Platform manual-copy fallback | Reliability | Disabled API posting can make social feel broken. | If platform disabled, output final copy with "manual post" instructions instead of trying API. | `social/posting.py`, handlers | Keeps workflow moving safely. | S / Low | Disabled LinkedIn returns copy block. |
| 14 | No | Approval buttons or structured commands | New feature | Free-text approval is fragile. | Add Slack Block Kit buttons or strict commands (`approve bluesky`, `revise linkedin`, `skip`). | Slack bot handlers | Fewer accidental actions. | L / Med | Button click updates draft status. |
| 15 | Yes | Source-health preflight gate | Newsletter quality | RSS/HN/Reddit/Twitter were repeatedly zero. | Fail open to newsletter only with visible warning/retry; do not silently degrade. | `preflight/run_all.py`, `runner.py` | Prevents weak-input newsletters. | M / Med | Zero major sources creates alert before synthesis. |
| 16 | Yes | RSS feed health repair | Existing behavior | Logs showed RSS failed from missing `feedparser`; smoke later still returned 0. | Lock dependency and add per-feed health report. | `requirements.txt`, `tools/rss-fetch.py` | Restores high-quality recurring sources. | S / Low | RSS returns items or names bad feeds. |
| 17 | Blocked | Reddit authenticated backend | Source quality | `agent-reach doctor` says Reddit backend is off. | Install/configure a real Reddit backend or mark Reddit unavailable with alert. | Agent Reach/OpenCLI config, `preflight/reddit.py` | Restores community signal. | M / Med | Reddit preflight >0 or explicit unavailable alert. |
| 18 | Partial | Twitter search repair | Source quality | `twitter status` works but `twitter search` failed. | Fix cookie/search path or use another Agent Reach backend for query search. | `preflight/twitter.py`, agent-reach config | Restores X trend signal. | M / Med | Query `AI agents` returns entries. |
| 19 | Yes | HN zero-source diagnosis | Source quality | HN returned 0 in recent logs and smoke. | Lower/adjust thresholds, inspect API query terms, add per-query diagnostics. | `preflight/hn.py` | Restores builder/startup discovery. | S / Low | HN preflight returns nonzero or explains zero. |
| 20 | Yes | Newsletter quality floor | Newsletter quality | Low source/agent counts still send. | Require minimum source diversity, agent coverage, unique URLs, and no duplicate angles; otherwise retry/escalate. | `orchestrator/evaluator.py`, `runner.py` | Protects daily quality. | M / Med | Bad synthetic run does not silently send. |
| 21 | Yes | Duplicate angle detector | Newsletter quality | Exact title duplicates were absent, but repeated angles/URLs remain possible. | Score semantic story overlap across current and previous 3 issues. | `orchestrator/evaluator.py`, embeddings | Less repeated content. | M / Low | Known repeated stories are flagged. |
| 22 | Partial | Story freshness audit | Newsletter quality | Old or repeated stories can resurface. | Add per-story source date, first-seen date, and "why now" checks. | `runner.py`, `newsletter.py` | More timely newsletter. | M / Low | Old story without new angle is rejected. |
| 23 | Yes | Agent coverage floor | Research quality | Recent days had 6-8 agents storing findings versus desired 13. | Retry failed/zero agents or label issue as degraded before synthesis. | `orchestrator/agents.py`, `runner.py` | Broader coverage and fewer bland issues. | M / Med | Zero-agent run retries or warns loudly. |
| 24 | Yes | Source balance weighting | Research quality | arXiv dominated recent stored findings. | Cap single-source dominance and boost underrepresented source classes. | `preflight/run_all.py`, synthesis prompt | More varied newsletter. | M / Med | Top source cannot dominate issue. |
| 25 | No | Newsletter-to-social memory link | New feature | Social posts are not tightly connected back to newsletter stories. | Store which newsletter story generated each Slack draft/post. | `social_posts`, `reports`, handlers | Better learning and dedup. | M / Low | Social row links to newsletter section/story. |
| 26 | No | Feedback from Slack reactions | New feature | User preference learning mostly depends on email replies/manual feedback. | Let Slack reactions on stories/drafts feed preferences. | Slack bot, `memory/feedback.py` | Faster personalization. | M / Low | Reaction updates preference record. |
| 27 | No | Best-story archive | New feature | High-grade findings are buried in daily issues. | Maintain searchable "best stories/angles" vault with source, date, why it mattered. | memory/vault/dashboard | Better reuse without repeats. | M / Low | Dashboard/search returns top prior angles. |
| 28 | No | Ops incident timeline | Reliability | Incidents require manual log/DB reconstruction. | Auto-build daily timeline: launch, sources, agents, send, sync, Slack/social state. | `traces.db`, dashboard, briefing | Faster debugging. | M / Low | One command shows run timeline. |
| 29 | Yes | Put runner tests back in CI | Developer workflow | CI ignores `tests/test_runner.py`. | Split or stabilize runner tests and include critical subsets in GitHub Actions. | `.github/workflows/test.yml`, tests | Catches pipeline regressions before merge. | M / Med | CI runs runner phase tests. |
| 30 | Yes | Keep Graphify current | Developer workflow | Graph report is stale vs HEAD. | Run/update graph after code changes and surface staleness in handoffs. | `graphify-out/`, hooks | Better architecture navigation for agents. | S / Low | Graph report commit matches HEAD. |

## 2026-06-26 Feature 24 Runbook Draft

- Created `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-runbook.md`
  as the spec/runbook for new-feature table row 24, `"Ask Follow-Up" Research
  Button`, and expanded it to include the optional paired Slack Social Ideas
  Desk feature.
- Created
  `docs/runbooks/2026-06-26-feature-24-ask-follow-up-research-implementation-plan.md`
  with a dependency-ordered task breakdown. Required Ask Follow-Up work is
  separated from optional Social Ideas Desk work so further research can ship
  without waiting for the social-ideas layer.
- Added Slack Social Ideas Desk to the new-feature ideas table as row 25; later
  rows are renumbered.
- Scope is command-first Slack follow-up research from `#mp-briefing` and
  draft/review threads plus an optional Slack command that shows social post
  ideas with draft, save, revise, reject, and follow-up actions. It explicitly
  does not run the full daily pipeline, send newsletters, post social content,
  sync Fly, change schema, or add dependencies without owner approval.
- There is no newsletter desk in scope. The normal scheduled
  newsletter remains responsible for research, story selection, writing, and
  sending through the quality-gated pipeline. Social Ideas Desk is social-only;
  it can create drafts/manual-copy candidates and trigger follow-up research,
  but it cannot approve, block, write, or send the newsletter and cannot publish
  live social posts.
- Implementation progress: baseline was clean and focused baseline tests passed
  before edits (`tests/test_slack_bot.py tests/test_approval.py
  tests/test_social.py -q`, `tests/test_runner.py::TestDryRunPhases -q`).
  Added `orchestrator/followup.py` plus `tests/test_followup_research.py` for
  parser, redaction, deterministic dry-run, safe trace/artifact writing, and
  degraded live-agent failure behavior. Verification:
  `.venv/bin/python3 -m pytest tests/test_followup_research.py -q`.
- Added `#mp-briefing` follow-up command handling. `follow up: <topic>` now
  acknowledges in-thread, runs the scoped follow-up service, and posts a
  phone-readable result. Vague follow-up commands reply with guidance and do not
  run the service. Verification:
  `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestBriefingFollowupCommand -q`.
- Added shared draft-thread follow-up handling in
  `slack_bot/handlers/followup.py`, then wired `#mp-posts`, `#mp-skills`, and
  `#mp-tips` approval loops to consume `follow up:` before edit/approval
  parsing. The reply returns scoped findings in-thread, keeps waiting for a
  real edit/skip/approval reply, and does not call `_post_to_platforms()` or
  `_post()` because of the follow-up. Verification:
  `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsEditFlow::test_followup_reply_runs_research_and_keeps_waiting tests/test_slack_bot.py::TestSkillsTipsEditFlow::test_followup_reply_runs_research_and_keeps_waiting tests/test_followup_research.py -q`
  -> 9 passed; `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsEditFlow tests/test_slack_bot.py::TestSkillsTipsEditFlow tests/test_slack_bot.py::TestBriefingFollowupCommand -q`
  -> 14 passed.
- Added Ask Follow-Up safety regressions in `tests/test_followup_research.py`
  proving the service has no daily runner/newsletter/social posting/Fly delivery
  imports or call tokens, and that `MP_DISABLE_OUTBOUND=1` forces deterministic
  dry-run without calling the default agent boundary. Verification:
  `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q`
  -> 60 passed.
- Broader local verification passed after the Ask Follow-Up MVP changes:
  `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_slack_bot.py tests/test_approval.py tests/test_social.py -q`
  -> 212 passed; `.venv/bin/python3 -m pytest -q --tb=short tests/test_runner.py::TestPhaseTrendScan tests/test_runner.py::TestPhaseResearch tests/test_runner.py::TestPhaseSynthesis tests/test_runner.py::TestPhaseSocial`
  -> 23 passed.
- Graphify was refreshed after code/docs changes:
  `graphify update .` -> 6826 nodes, 10611 edges, 420 communities;
  `graphify check-update .` -> exit 0.
- Pushed to `origin/main` and watched GitHub Actions `Tests` successfully after
  the final evidence push.
- Optional Social Ideas Desk is intentionally deferred in this goal. No
  Social Ideas Desk parser, loader, feedback store, or Slack command was
  implemented.
- The runbook includes assumptions, non-goals, exact commands, project
  structure, code style, testing strategy, boundaries, success criteria, a
  task table with a `Done` column, risks, and a ready-to-paste `/goal` prompt.
- Remaining required Ask Follow-Up work: none for the local/CI implementation.
  No Fly deploy, live Slack smoke, full daily pipeline run, newsletter send, or
  live social post has been run for this feature.

## 2026-06-28 Features 17/18/20/21 Implementation Progress

- Active goal: implement Feature 17 Narrative Arc Builder, Feature 18 Social
  Angle Lab, Feature 20 Audio Morning Briefing to Rabbit Hole, and Feature 21
  Short-Form Video Script Mode from
  `docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-runbook.md` and
  `docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-implementation-plan.md`.
- Opus 4.8 approval gate is satisfied and recorded in the implementation plan.
  Binding F17 condition was applied: narrative arcs are enrichment-only and may
  be injected only into synthesis pass 2 / narrative context, never
  `_balance_story_candidates()` or pass-1 story selection.
- Feature 17 status: Tasks 3-6 are implemented locally. `orchestrator/arcs.py`
  builds deterministic multi-day/source-backed arc artifacts under
  `reports/<user>/arcs/YYYY-MM-DD.json`. `dashboard/routes/api.py` exposes
  public read-only `/api/narrative-arcs` and `/api/narrative-arcs/{arc_id}`
  with date/user/arc-id validation and whitelisted/redacted output.
- Runner integration: `orchestrator/runner.py` loads active/emerging arcs only
  after synthesis pass 1 has completed, formats them with
  `format_arcs_for_synthesis()`, and injects them into pass 2 only. Missing or
  invalid arc artifacts degrade visibly through trace events and do not block
  newsletter generation.
- Verification run after the Feature 17 API/pass-2 slice:
  `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q` -> 6 passed;
  `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis -q`
  -> 10 passed; `.venv/bin/python3 -m pytest tests/test_evaluator.py -q`
  -> 12 passed; combined focused suite
  `.venv/bin/python3 -m pytest tests/test_media_artifact_contracts.py tests/test_narrative_arcs.py tests/test_runner.py::TestPhaseSynthesis tests/test_evaluator.py -q`
  -> 34 passed.
- Current next task: Feature 21 Task 18, wire #mp-posts video command and
  angle handoff. Feature 18 Tasks 7-10, Feature 20 Tasks 11-15, and Feature 21
  Tasks 16-17 are complete locally/cross-repo.
  Angle artifacts stay in gitignored
  `reports/ramsay/social-angles/`, not `data/social-angles/`.
- Feature 18 Task 7 status: implemented locally. `orchestrator/social_angles.py`
  now provides a pure strict parser/contract for `angles:`, `angle lab:`,
  `angles finding <id>`, and `angles arc <arc_id>`, rejects unclear or
  newsletter-control commands, redacts sensitive request previews, pins angle
  artifacts to `reports/<user>/social-angles/YYYY-MM-DD.json`, and defines the
  public `SocialAngleCandidate` contract. Verification:
  `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q` -> 6 passed.
- Feature 18 Task 8 status: implemented locally after owner approved the
  boundary. The approved boundary is: practitioner transparency is allowed only
  when it teaches a source-backed builder/operator lesson; agent counts,
  cron/pipeline flexing, automated-infrastructure flexing, and product-demo
  framing are disallowed. Reconciled `social/writers.py`,
  `agents/expeditor.md`, platform writer/critic prompts, EIC, and engagement
  writer. Added deterministic `generate_social_angles()`, injectable provider
  boundary, `critique_social_angle()` assignment-editor scoring/cuts, ranked
  `shown_angles`, and artifact writes under
  `reports/<user>/social-angles/YYYY-MM-DD.json`. Verification:
  `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q` -> 10
  passed. Grep confirmed old conflicting phrases absent from `agents/` and
  `social/writers.py`.
- Feature 18 Task 9 status: implemented locally. `#mp-posts` now intercepts
  Social Angle Lab commands before URL/idea handling, runs deterministic angle
  generation, and posts ranked candidates in-thread with source/artifact
  evidence and an explicit "No live post" label. Vague or invalid angle
  commands reply with guidance and do not fall through to the social pipeline.
  Verification: `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsAngleCommand -q`
  -> 3 passed; `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 94
  passed.
- Feature 18 Task 10 status: implemented locally. After ranked angle output,
  `#mp-posts` waits for `draft <n>` or `draft <angle_id>`, converts the selected
  angle into the existing social topic shape, and calls `_run_and_approve()` so
  normal preview/edit/approval gates still control posting. Unclear replies do
  nothing and post no content. Verification:
  `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q` -> 12
  passed; `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 96
  passed.
- Feature 20 Task 11 status: implemented locally. Added pure
  `orchestrator/audio_briefing.py` script builder that converts report markdown
  into spoken prose, transcript markdown, source notes, hashes, and
  AI-generated/manual-publish labels. It strips tables, fenced code, raw URLs,
  and markdown noise from spoken script; preserves markdown source links in show
  notes; and marks visible quality-floor degraded reports as degraded.
  Verification: `.venv/bin/python3 -m pytest tests/test_audio_briefing.py -q`
  -> 4 passed; `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_media_artifact_contracts.py -q`
  -> 10 passed.
- Feature 20 Task 12 status: implemented locally. Added `TTSProviderConfig`,
  `tts_provider_config_from_env()`, and `build_tts_audio()` to produce
  deterministic dry-run metadata by default and require explicit env config
  plus an injected adapter for live TTS. Missing live config or adapter fails
  closed without provider/network imports or calls. Verification:
  `.venv/bin/python3 -m pytest tests/test_audio_briefing.py -q` -> 9 passed;
  `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_media_artifact_contracts.py -q`
  -> 15 passed.
- Feature 20 Task 13 status: implemented locally. Added safe
  `reports/<user>/audio/YYYY-MM-DD.*` paths and `write_audio_artifacts()` for
  MP3 bytes when present, transcript markdown, metadata JSON, and provenance
  JSON. Metadata includes source report hash, script hash, provider/model/voice,
  source count, generated timestamp, AI-generated/manual-publish labels, and
  audio-file presence. Trace events record ready/degraded/failed statuses via
  `audio_briefing_artifact`. Verification:
  `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_traces_db.py -q`
  -> 20 passed; `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_media_artifact_contracts.py tests/test_traces_db.py -q`
  -> 26 passed.
- Feature 20 Task 14 status: implemented locally. Added public read-only
  `/api/audio-briefings`, `/api/audio-briefings/{date}`,
  `/api/audio-briefings/{date}/file`, and
  `/api/audio-briefings/{date}/transcript` endpoints that serve only validated
  `reports/<user>/audio/YYYY-MM-DD.*` artifacts. Public metadata is whitelisted;
  invalid dates/users and missing artifacts return empty list or 404. Added the
  audio prefix to the public-read auth allowlist and verified private routes
  stay protected. Verification:
  `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_audio_briefing.py -q`
  -> 27 passed; `.venv/bin/python3 -m pytest tests/test_auth_middleware.py tests/test_api_contract.py tests/test_audio_briefing.py -q`
  -> 43 passed.
- Feature 20 Task 15 status: implemented in `mindpattern-rabbit-hole` and
  committed there as `69b9d6e feat: render audio briefings`. Added typed audio
  helpers, `AudioBriefing` types, and `AudioBriefingPlayer` with native audio
  controls, transcript links, source links, and visible AI-generated/manual-
  publish labels. `/briefings` shows compact players for dates with audio
  without nesting controls inside links; `/briefings/[date]` renders the full
  player above the report body and degrades cleanly when no audio exists.
  Verification in Rabbit Hole: `pnpm lint` -> 0 errors, 2 pre-existing
  warnings; `pnpm exec tsc --noEmit --incremental false` -> passed.
- Feature 21 Task 16 status: implemented locally. Added pure
  `orchestrator/video_scripts.py` with strict parsing for `video script:`,
  `video finding <id>`, `video arc <id>`, and `video angle <n>`. Unrelated text
  returns `None`; malformed supported commands return failed request objects
  without falling through. Parser rejects live-post/manual-publish violations
  and newsletter-control wording, redacts sensitive text, and defines stable
  `VideoScriptPackage` public output with safe URLs and visible labels.
  Verification: `.venv/bin/python3 -m pytest tests/test_video_scripts.py -q`
  -> 5 passed; `.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_media_artifact_contracts.py -q`
  -> 11 passed.
- Feature 21 Task 17 status: implemented locally. Added deterministic
  `generate_video_script_package()` and safe `video_script_artifact_paths()`
  under gitignored `reports/<user>/video-scripts/YYYY-MM-DD-<slug>.{json,md}`.
  The service produces one selected 30/45/60 second Slack-ready package with
  hook, spoken script, shot list, captions, source URLs, claim-to-source
  evidence, AI-assisted/manual-publish labels, and risk labels. Weak or missing
  evidence returns a degraded package with follow-up research recommendation
  and no fabricated claim evidence. Verification:
  `.venv/bin/python3 -m pytest tests/test_video_scripts.py -q` -> 9 passed;
  `.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_media_artifact_contracts.py -q`
  -> 15 passed.
- Feature 21 Task 18 status: implemented locally. `#mp-posts` now intercepts
  `video script: <topic/url>`, `video finding <id>`, `video arc <id>`, and
  `video angle <n>` before URL/idea fallback. Direct video commands produce
  phone-readable Slack script packages with "manual publish only" labels and
  safe ignored artifacts. `video angle <n>` only works as a reply after a Social
  Angle Lab result, uses the selected angle's source evidence, and does not
  call `_run_and_approve()` or post to social platforms. Finding and arc
  evidence lookup is read-only and degrades visibly when local evidence is
  missing. Verification:
  `.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_slack_bot.py -q`
  -> 109 passed.
- Feature 21 Task 19 status: implemented locally. Added `slack_bot/files.py`
  with Slack's external upload sequence for script artifacts:
  `files.getUploadURLExternal`, raw-byte upload to the returned URL, then
  `files.completeUploadExternal` with `channel_id` and the parent `thread_ts`.
  The helper never calls legacy `files.upload`, surfaces missing `files:write`,
  keeps auth inside the Slack client, and has an injectable raw-upload boundary
  so tests make no Slack/network calls. Verification:
  `.venv/bin/python3 -m pytest tests/test_slack_files.py tests/test_video_scripts.py -q`
  -> 15 passed.
- Task 20 safety regression status: implemented locally. Added
  `tests/test_media_feature_safety.py` to scan new media modules for forbidden
  outbound/deploy/posting markers, verify Slack video dry paths do not post,
  upload, or run the social pipeline, verify unclear Social Angle Lab replies
  change no state, verify Slack file upload tests use the mocked raw-upload
  boundary, and verify public media output redacts Slack mentions, email, and
  token-shaped data. Verification:
  `.venv/bin/python3 -m pytest tests/test_media_feature_safety.py tests/test_narrative_arcs.py tests/test_social_angle_lab.py tests/test_audio_briefing.py tests/test_video_scripts.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q`
  -> 96 passed, 1 Starlette/httpx deprecation warning.
- Task 21 release hygiene status: implemented locally. Updated the runbook
  status, implementation-plan Done table/checkpoints, and this handoff. Ran
  `git diff --check` -> passed; `graphify update .` -> rebuilt 7259 nodes,
  11666 edges, 439 communities, with HTML viz skipped because the graph exceeds
  the 5000-node default; `graphify check-update .` -> passed. Final full-suite
  verification after all commits: `.venv/bin/python3 -m pytest -q` -> 1338
  passed, 1 Starlette/httpx deprecation warning. Current v3 branch is ahead of
  origin/main with feature commits; unrelated dirty files remain in
  `data/ramsay/**`, `data/social-drafts/eic-topic.json`, `run-launchd.sh`, and
  `tests/test_launchd_wrapper.py`. Current Rabbit Hole branch is
  `rabbit-hole`; only the Task 15 audio rendering commit was made there, with
  pre-existing unrelated dirty files still present in `src/components/story/`,
  `src/components/wire/`, `src/lib/sections.ts`, and `docs/specs/`.
- No full daily pipeline, Fly deploy, Vercel deploy, Slack live smoke,
  newsletter send, social post, schema change, dependency install, or TTS/video
  provider call has been run for this feature slice. Rabbit Hole edits were
  limited to Task 15 and committed in that repo.

## Do Not Do Yet

- Do not refactor `orchestrator/runner.py` before the Slack/social config issue
  and source-health issues are fixed.
- Do not turn daily social into background auto-posting. Use Slack bot channels
  as the primary human-controlled publishing surface.
- Do not enable both LinkedIn and Bluesky at once for live API posting.
- Do not rely on local sandbox source-smoke failures as proof of production
  network failure.
- Do not remove approval gates to force posting.
- Do not change dedup thresholds broadly until duplicate examples are measured
  with URLs, titles, and semantic similarity.

## Rabbit Hole Public Intelligence Site MVP - 2026-06-28

- Goal started: implement and release the Rabbit Hole Public Intelligence Site
  MVP, replacing the broken/not-useful chat-first experience with a
  source-backed public intelligence site.
- Primary docs:
  `docs/runbooks/2026-06-28-rabbit-hole-public-intelligence-site-spec.md` and
  `docs/runbooks/2026-06-28-rabbit-hole-public-intelligence-site-implementation-plan.md`.
- Product direction locked in docs: content-first, archive-first, not
  dashboard-first and not chat-first. The full newsletter remains a canonical
  blog-style briefing page, while a structured issue graph powers entity,
  source, finding, story, and arc routes.
- Research-backed decisions added to docs: JSON/JSON-LD-ready artifact-first
  storage, W3C-style provenance, typed graph relationships, historical
  newsletter backfill, and dynamic templates instead of hand-built entity pages.
- Task 0 baseline:
  - v3 dirty before implementation: `data/ramsay/**`,
    `data/social-drafts/eic-topic.json`, `run-launchd.sh`,
    `tests/test_launchd_wrapper.py`, plus the new Rabbit Hole spec/plan docs.
  - Rabbit Hole dirty before implementation: `src/components/story/rabbit-hole.tsx`,
    `src/components/wire/wire-row.tsx`, `src/lib/sections.ts`, and untracked
    `docs/specs/2026-06-26-backend-{plan-tasks,spec}.md`.
  - Baseline verification: `.venv/bin/python3 -m pytest tests/test_api_contract.py -q`
    -> 15 passed; `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`
    -> 4 passed; Rabbit Hole `pnpm lint` -> 0 errors, 2 pre-existing warnings
    (`src/app/api/chat/route.ts`, `src/components/explore/explore-tabs.tsx`);
    Rabbit Hole `pnpm exec tsc --noEmit --incremental false` -> passed.
- Release gates remain: no full daily pipeline, newsletter send, live social
  post, Fly deploy, Vercel deploy, schema change, dependency install, provider
  enablement, or production indexing change without explicit owner approval.

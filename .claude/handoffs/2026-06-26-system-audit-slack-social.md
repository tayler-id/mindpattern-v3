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

## Fix-First Table: Existing Things That Are Broken or Not Proven Working

These are not feature ideas. They are existing paths that are disabled, broken,
unsafe, or not proven healthy enough to rely on.

| Area | What should happen | What is happening | Why it is not working | Fix needed |
|---|---|---|---|---|
| Daily social phase | Pipeline should create social candidates or an approval flow. | It skips social entirely. | `linkedin.enabled=false` and `bluesky.enabled=false`; runner exits with `Social: no platforms enabled`. | Separate "format draft" from "post live"; do not skip Slack draft creation just because posting APIs are off. |
| Slack approval for daily social | Daily pipeline should post approval requests to Slack. | It never reaches approval. | Social phase exits before `ApprovalGateway` runs. | Let pipeline send candidates to Slack bot/channel without auto-posting. |
| `#mp-posts` live posting | URL/idea should become platform drafts, then wait for approval. | Bot exists, but live posting depends on platform config/secrets. | Platform clients still need enabled config to publish. | Add manual-copy fallback when a platform is disabled; only post after explicit approval. |
| `#mp-skills` approval | It should only post after clear owner approval. | Unclear replies can default to all platforms. | Handler falls back to `approved = platforms` if reply is not understood. | Use strict parser: unclear reply means no post. |
| `#mp-tips` approval | It should only post after clear owner approval. | Unclear replies can default to all platforms. | Handler also defaults unclear replies to all platforms. | Use strict parser: unclear reply means no post. |
| Slack edit flow | User should paste edits and have the draft updated. | UI text says edits are allowed, but approval parsing does not really apply edits. | "Paste edited text" is advertised but not implemented as a real draft-revision state. | Add `edit bluesky: ...`, re-preview, then require approval again. |
| Slack bot local visibility | Logs should show current bot activity. | Local `reports/slack-bot.log` stopped around 2026-06-08. | Local launchd Slack bot services are not registered; production bot runs on Fly now. | Decide Fly-only bot vs reinstall local bot; add clear docs/status. |
| Slack channel health | Each channel should be testable. | Fly bot heartbeat is alive, but handler-by-handler behavior was not proven. | `/healthz` proves bot heartbeat, not that every channel command works. | Add bot `doctor`/`status` command that checks registered channels. |
| RSS preflight | RSS should produce source items. | Logs show RSS returned 0 for recent runs. | Earlier logs said `feedparser` was missing; later smoke still returned 0. | Add per-feed diagnostics; confirm feeds and dependency in real run environment. |
| Reddit preflight | Reddit should produce community signal. | Reddit returns 0 / Agent Reach says Reddit backend is off. | No authenticated Reddit backend configured. | Install/configure Reddit backend or remove it from expected source count. |
| Twitter/X preflight | Twitter search should produce trend items. | Auth works, search fails. | `twitter search` failed with HTTP 404 / cookie extraction issue. | Fix query-search backend or switch Agent Reach backend. |
| HN preflight | HN should produce builder/startup items. | HN returned 0. | Query, threshold, or API path is likely too strict or failing silently. | Add per-query diagnostics and adjust thresholds. |
| Exa preflight | Exa should contribute semantic web search. | It recovered in logs, but local sandbox smoke failed DNS. | Local sandbox cannot prove production health; prior logs had timeouts. | Add production source-health report, not only local checks. |
| YouTube preflight | YouTube should fetch videos. | It recovered in logs, but local sandbox smoke failed DNS. | Sandbox network failure; not enough production proof. | Add daily YouTube source-count alert. |
| Newsletter quality floor | Bad input days should retry or escalate. | Newsletter still sends on weak-source days. | Delivery is gated more strongly than content quality. | Add pre-send floor: minimum agents, sources, unique URLs, and duplicate-angle score. |
| Duplicate story control | Same story should not repeat across days. | Exact duplicate titles were not found, but repeated URLs/angles remain possible. | Current dedupe catches some title/embedding duplicates, not "same angle again" well enough. | Add semantic cross-issue duplicate detector. |
| Agent coverage | Usually 13 agents should contribute. | Recent days had 6-8 contributing agents. | Some agents failed, timed out, or stored zero findings. | Retry zero agents or mark issue degraded before synthesis. |
| Source balance | Newsletter should not be dominated by one source. | arXiv dominated recent findings. | Source weighting lets one source overfill the issue. | Cap source dominance and boost underrepresented source classes. |
| CI coverage | Critical runner behavior should be tested in CI. | `tests/test_runner.py` is ignored in GitHub Actions. | Main pipeline tests are excluded. | Split/stabilize runner tests and put critical subset back in CI. |
| Graphify freshness | Architecture graph should match HEAD. | Graph report is stale. | Built from old commit `eb913fee`. | Run/update Graphify after code changes. |

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

## 30 Prioritized Recommendations

| # | Title | Type | Problem | Proposed change / why it matters | Files/systems | Benefit | Effort / Risk | Verification |
|---|---|---|---|---|---|---|---|---|
| 1 | Slack-bot-first social workflow | Existing behavior | The audit over-framed social as daily auto-posting. | Make Slack channels the primary creation and approval UX; daily pipeline may suggest candidates, but user controls posts. | `slack_bot/handlers/*`, `social/pipeline.py` | Matches intended workflow and prevents surprise posts. | M / Med | One test draft per channel waits for owner approval before posting. |
| 2 | Separate draft generation from publishing | Reliability | Platform `enabled=false` currently blocks social work entirely in the daily path. | Add a "format-only" mode that always creates Slack drafts and only posts when an explicit approval plus enabled credential exists. | `social-config.json`, `slack_bot/handlers/posts.py`, `social/posting.py` | Bot remains useful even when APIs are off. | M / Med | Disabled platform returns formatted manual-copy draft, not a hard skip. |
| 3 | Fix `#mp-skills` unclear approval default | Safety | `skills.py` defaults unclear replies to all platforms. | Reuse the strict parser from `posts.py`; unclear text should not post. | `slack_bot/handlers/skills.py`, tests | Prevents accidental posting. | S / Low | Reply "wait" or pasted edit posts nothing. |
| 4 | Fix `#mp-tips` unclear approval default | Safety | `tips.py` also defaults unclear replies to all platforms. | Same strict approval parser and tests. | `slack_bot/handlers/tips.py`, tests | Prevents accidental posting. | S / Low | Reply "hold on" or "skip linkedin" posts nothing. |
| 5 | Implement real Slack edit flow | Existing behavior | Handlers say "paste edited text" but do not reliably replace drafts. | Let owner reply `edit bluesky: ...` or paste a replacement, then show a new preview and require approval. | `slack_bot/handlers/base.py`, `posts.py`, `skills.py`, `tips.py` | Turns Slack into an actual editor, not just approve/skip. | M / Med | Pasted edit updates draft and requires second approval. |
| 6 | Channel-specific post templates | New feature | `#mp-posts`, `#mp-skills`, and `#mp-tips` have similar code but different brand formats. | Extract templates for general post, Skill of the Day, Tayler'd Tip, launch note, contrarian take. | `slack_bot/handlers`, `agents/*.md` | Faster, more consistent content. | M / Low | Snapshot tests for each channel format. |
| 7 | Slack preview cards | New feature | Drafts are plain code blocks with limited metadata. | Show platform, char count, sources, policy warnings, expected action buttons/text. | `slack_bot/handlers/*` | Easier review from phone. | M / Low | Preview includes source URLs and limits. |
| 8 | Pending draft queue | New feature | If owner misses approval, work disappears after timeout. | Store drafts as pending with channel/thread/status and allow `status`, `approve`, `skip`, `revise` later. | `memory.db`, `slack_bot`, dashboard | No lost social work. | M / Med | Timeout draft can be resumed next day. |
| 9 | Social content calendar | New feature | There is no planning view of pending/posted ideas. | Add dashboard/Slack view for draft queue, posted history, channel source, and next recommended post. | dashboard, `social_posts` | Better cadence and planning. | L / Med | Calendar shows pending and published posts. |
| 10 | Daily newsletter-to-Slack idea picker | New feature | Newsletter stories are not automatically turned into Slack draft candidates. | After newsletter send, post top 3 social angles to `#mp-posts` or `#mp-briefing` for user selection. | `orchestrator/runner.py`, `slack_bot/handlers/briefing.py` | Converts research into posts without auto-posting. | M / Med | Briefing thread has 3 candidate post buttons/replies. |
| 11 | `#mp-briefing` richer run report | Existing behavior | Briefing only shows basic counts. | Include source counts, agent count, quality score, newsletter sent, social skipped reason, bot health. | `slack_bot/handlers/briefing.py` | One place to see daily health. | S / Low | `status` returns source/quality/social details. |
| 12 | Bot self-test command | Reliability | It is hard to know which Slack channels are wired. | Add `status`/`doctor` command showing registered handlers, owner ID, token source, heartbeat. | `slack_bot/registry.py`, `bot.py` | Faster incident diagnosis. | S / Low | Bot reports all configured channels. |
| 13 | Platform manual-copy fallback | Reliability | Disabled API posting can make social feel broken. | If platform disabled, output final copy with "manual post" instructions instead of trying API. | `social/posting.py`, handlers | Keeps workflow moving safely. | S / Low | Disabled LinkedIn returns copy block. |
| 14 | Approval buttons or structured commands | New feature | Free-text approval is fragile. | Add Slack Block Kit buttons or strict commands (`approve bluesky`, `revise linkedin`, `skip`). | Slack bot handlers | Fewer accidental actions. | L / Med | Button click updates draft status. |
| 15 | Source-health preflight gate | Newsletter quality | RSS/HN/Reddit/Twitter were repeatedly zero. | Fail open to newsletter only with visible warning/retry; do not silently degrade. | `preflight/run_all.py`, `runner.py` | Prevents weak-input newsletters. | M / Med | Zero major sources creates alert before synthesis. |
| 16 | RSS feed health repair | Existing behavior | Logs showed RSS failed from missing `feedparser`; smoke later still returned 0. | Lock dependency and add per-feed health report. | `requirements.txt`, `tools/rss-fetch.py` | Restores high-quality recurring sources. | S / Low | RSS returns items or names bad feeds. |
| 17 | Reddit authenticated backend | Source quality | `agent-reach doctor` says Reddit backend is off. | Install/configure a real Reddit backend or mark Reddit unavailable with alert. | Agent Reach/OpenCLI config, `preflight/reddit.py` | Restores community signal. | M / Med | Reddit preflight >0 or explicit unavailable alert. |
| 18 | Twitter search repair | Source quality | `twitter status` works but `twitter search` failed. | Fix cookie/search path or use another Agent Reach backend for query search. | `preflight/twitter.py`, agent-reach config | Restores X trend signal. | M / Med | Query `AI agents` returns entries. |
| 19 | HN zero-source diagnosis | Source quality | HN returned 0 in recent logs and smoke. | Lower/adjust thresholds, inspect API query terms, add per-query diagnostics. | `preflight/hn.py` | Restores builder/startup discovery. | S / Low | HN preflight returns nonzero or explains zero. |
| 20 | Newsletter quality floor | Newsletter quality | Low source/agent counts still send. | Require minimum source diversity, agent coverage, unique URLs, and no duplicate angles; otherwise retry/escalate. | `orchestrator/evaluator.py`, `runner.py` | Protects daily quality. | M / Med | Bad synthetic run does not silently send. |
| 21 | Duplicate angle detector | Newsletter quality | Exact title duplicates were absent, but repeated angles/URLs remain possible. | Score semantic story overlap across current and previous 3 issues. | `orchestrator/evaluator.py`, embeddings | Less repeated content. | M / Low | Known repeated stories are flagged. |
| 22 | Story freshness audit | Newsletter quality | Old or repeated stories can resurface. | Add per-story source date, first-seen date, and "why now" checks. | `runner.py`, `newsletter.py` | More timely newsletter. | M / Low | Old story without new angle is rejected. |
| 23 | Agent coverage floor | Research quality | Recent days had 6-8 agents storing findings versus desired 13. | Retry failed/zero agents or label issue as degraded before synthesis. | `orchestrator/agents.py`, `runner.py` | Broader coverage and fewer bland issues. | M / Med | Zero-agent run retries or warns loudly. |
| 24 | Source balance weighting | Research quality | arXiv dominated recent stored findings. | Cap single-source dominance and boost underrepresented source classes. | `preflight/run_all.py`, synthesis prompt | More varied newsletter. | M / Med | Top source cannot dominate issue. |
| 25 | Newsletter-to-social memory link | New feature | Social posts are not tightly connected back to newsletter stories. | Store which newsletter story generated each Slack draft/post. | `social_posts`, `reports`, handlers | Better learning and dedup. | M / Low | Social row links to newsletter section/story. |
| 26 | Feedback from Slack reactions | New feature | User preference learning mostly depends on email replies/manual feedback. | Let Slack reactions on stories/drafts feed preferences. | Slack bot, `memory/feedback.py` | Faster personalization. | M / Low | Reaction updates preference record. |
| 27 | Best-story archive | New feature | High-grade findings are buried in daily issues. | Maintain searchable "best stories/angles" vault with source, date, why it mattered. | memory/vault/dashboard | Better reuse without repeats. | M / Low | Dashboard/search returns top prior angles. |
| 28 | Ops incident timeline | Reliability | Incidents require manual log/DB reconstruction. | Auto-build daily timeline: launch, sources, agents, send, sync, Slack/social state. | `traces.db`, dashboard, briefing | Faster debugging. | M / Low | One command shows run timeline. |
| 29 | Put runner tests back in CI | Developer workflow | CI ignores `tests/test_runner.py`. | Split or stabilize runner tests and include critical subsets in GitHub Actions. | `.github/workflows/test.yml`, tests | Catches pipeline regressions before merge. | M / Med | CI runs runner phase tests. |
| 30 | Keep Graphify current | Developer workflow | Graph report is stale vs HEAD. | Run/update graph after code changes and surface staleness in handoffs. | `graphify-out/`, hooks | Better architecture navigation for agents. | S / Low | Graph report commit matches HEAD. |

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

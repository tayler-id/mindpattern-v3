# Handoff: Slack Interactive Bot — Implementation + System Hardening

## Session Metadata
- Created: 2026-03-21 12:58:20
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: feat/slack-bot
- Session duration: ~4 hours

### Recent Commits (for context)
  - ec43ce6 docs: handoff for Slack bot setup and next steps
  - d43452f feat: add Slack interactive bot with Socket Mode + plugin architecture
  - adb1712 docs: Slack interactive bot plan + pipeline data updates
  - 60630c2 harden: eng review — 151 new tests, timeout safety, error logging, file cleanup
  - 9f89a75 Merge branch 'feat/obsidian-memory'

## Handoff Chain

- **Continues from**: [2026-03-19-132008-v32-ceo-review.md](./2026-03-19-132008-v32-ceo-review.md)
- **Supersedes**: All prior handoffs — this captures complete system state

## Current State Summary

This session merged the `feat/obsidian-memory` branch into main (75 commits), ran a comprehensive code review fixing 34 issues, hardened the system with 151 new tests + error handling fixes, planned and implemented a Slack interactive bot. The bot code is complete but not yet running — it needs Slack app configuration (Socket Mode enablement, app-level token, channel creation). The `feat/slack-bot` branch is ready for the setup steps below.

## Codebase Understanding

### Architecture Overview

MindPattern is an autonomous AI research pipeline that runs daily at 7 AM via launchd. It has 12 phases: INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → LEARN → SOCIAL → ENGAGEMENT → EVOLVE → ANALYZE → MIRROR → SYNC. The new Slack bot adds an interactive layer on top — users can message the system anytime via 4 dedicated Slack channels, each handled by a separate handler class.

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| slack_bot/bot.py | Socket Mode listener + event routing | New — the bot daemon entry point |
| slack_bot/registry.py | Channel → handler mapping from Keychain | New — config-driven handler loading |
| slack_bot/handlers/posts.py | URL → full agent pipeline → approve → post | New — core feature |
| slack_bot/handlers/engagement.py | Search + reply sniper | New — fixes broken engagement |
| slack_bot/handlers/base.py | BaseHandler with reply/thread/URL helpers | New — shared handler infrastructure |
| social/approval.py | Existing Slack approval gates | Modified earlier (review fixes) — NOT coupled to bot |
| orchestrator/runner.py | Main pipeline loop | Modified (hardening) — 54 new tests cover it |
| social/engagement.py | Engagement pipeline | Needs LinkedIn RSS fix (not yet done) |
| docs/superpowers/plans/2026-03-19-slack-interactive-bot.md | Full implementation plan | Reference for remaining work |

### Key Patterns Discovered

- All Claude CLI calls go through `orchestrator/agents.py` — 3 dispatch functions: `run_single_agent()`, `run_agent_with_files()`, `run_claude_prompt()`
- Slack bot reuses these same functions — agents are the same, just triggered from Slack instead of the pipeline
- The bot and pipeline are intentionally decoupled — they share credentials and Claude CLI but don't depend on each other
- File-based mutex (`/tmp/mindpattern-bot.mutex` and `/tmp/mindpattern-pipeline.lock`) prevents concurrent Claude CLI calls
- Owner user ID filtering ensures bot only responds to configured user (security)

## Work Completed

### Tasks Finished

- [x] Merged feat/obsidian-memory to main (75 commits)
- [x] Pre-landing code review — 34 fixes (SQL injection, path traversal, LLM trust boundary, dead X platform config)
- [x] System hardening — 151 new tests (test_runner.py: 54, test_sync.py: 36, test_approval.py: 61)
- [x] Keychain subprocess timeouts added (3 files)
- [x] 9 bare except:pass blocks replaced with logging
- [x] RSS feed socket timeout added
- [x] File cleanup (.lock files, temp images)
- [x] API retry with backoff for Resend (feedback.py)
- [x] CEO review — SCOPE EXPANSION mode, 6 proposals all accepted
- [x] Eng review — plan approved, approval.py decoupling decided
- [x] Design review — dashboard scored B, AI slop A
- [x] QA — health score 95/100, 624 tests passing
- [x] Slack bot implementation — 11 files, 1,147 lines
- [x] Installed session-handoff skill from softaworks/agent-toolkit

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Socket Mode (not webhook) | Socket Mode vs Fly.io webhook vs polling loop | Runs on Mac, no public URL, real-time, uses existing Keychain/Claude CLI |
| Plugin architecture | Plugin vs hardcoded if/elif routing | Future extensibility — CRM, email, more channels coming |
| 4 channels (not 1) | 1 combined vs 4 separate channels | User explicitly wanted one channel per agent function |
| Keep approval.py unchanged | Delegate to bot vs independent | Decoupling prevents bot crash from blocking pipeline |
| Geist font for dashboard | Geist vs system fonts vs Inter | Vercel-like precision, designed for dev tools (decided but not implemented) |

## Pending Work

### Immediate Next Steps

1. **Enable Socket Mode on existing Slack app** — api.slack.com/apps → MindPattern → Settings → Socket Mode → Enable. Then generate an App-Level Token with scope `connections:write` and store: `security add-generic-password -s slack-app-token -a mindpattern -w "xapp-..."`
2. **Add missing bot scopes** — OAuth & Permissions → add `channels:manage`. Add event subscription: `message.channels`. Reinstall app to workspace.
3. **Create 3 Slack channels** — `#mp-posts`, `#mp-engagement`, `#mp-briefing`. Invite the bot to each. Get channel IDs and store: `security add-generic-password -s slack-channel-config -a mindpattern -w '{"posts":"C_XXX","engagement":"C_XXX","approvals":"C0ALSRHAATH","briefing":"C_XXX"}'`
4. **Store owner user ID** — `security add-generic-password -s slack-owner-user-id -a mindpattern -w "U0AM88ZGK8A"`
5. **Test the bot** — `source .venv/bin/activate && python3 -m slack_bot` then paste a URL in #mp-posts
6. **Fix LinkedIn engagement** — replace broken `search_via_jina()` in `social/engagement.py` with LinkedIn RSS + Jina Reader approach (see plan doc)
7. **Write tests for slack_bot/** — bot, registry, handler tests with mocked Slack API
8. **Deploy launchd daemon** — `cp slack_bot/launchd/com.taylerramsay.slack-bot.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.taylerramsay.slack-bot.plist`

### Blockers/Open Questions

- [ ] Slack app needs Socket Mode enabled + app-level token generated (manual step in Slack admin)
- [ ] Bot token may need additional scopes reinstalled — current scopes may not include `channels:manage` or event subscriptions
- [ ] LinkedIn token may be expired (dashboard showed "token refresh file not found")

### Deferred Items

- CRM channel integration (architecture supports it, not built yet)
- Email channel integration
- Dashboard design system changes (Geist font adoption decided, not implemented)
- Metrics page default date range fix
- LinkedIn engagement reply automation (currently draft-only with manual copy-paste)

## Context for Resuming Agent

### Important Context

- The `slack_sdk` package is installed in `.venv/`, NOT system-wide. Always `source .venv/bin/activate` before running the bot.
- The existing Slack bot token (`xoxb-...`) is in Keychain under `slack-bot-token`. The app-level token (`xapp-...`) for Socket Mode does NOT exist yet — must be generated in Slack admin.
- Channel `#mindpattern-approvals` (C0ALSRHAATH) already exists and is used by the pipeline's `_slack_approval()`. The 3 new channels (#mp-posts, #mp-engagement, #mp-briefing) need to be created.
- Your Slack user ID is `U0AM88ZGK8A`. The bot's user ID is `U0ALSRW2YA3`.
- The bot and pipeline are fully independent — the pipeline's approval flow in `social/approval.py` was intentionally NOT modified. Both systems post to Slack separately.
- Test suite: 624 tests, all passing. No tests yet for the `slack_bot/` module.

### Assumptions Made

- The existing MindPattern Slack app can be extended with Socket Mode (it's not restricted to HTTP-only)
- The bot will run on the same Mac as the pipeline (same Keychain, same Claude CLI subscription)
- Single-user only — bot filters by owner user ID

### Potential Gotchas

- `slack_sdk` is only in `.venv/` — the launchd plist uses `/opt/homebrew/bin/python3` which may not have it. May need to adjust the plist to activate venv or install slack_sdk system-wide.
- The `PYTHONPATH` in the plist must point to the project root for imports to work
- If the pipeline is running when the bot receives a message, the mutex will queue it — but the bot doesn't have a real queue, it just tells the user to wait. A proper queue is a future enhancement.

## Environment State

### Tools/Services Used

- Claude CLI (Pro subscription) — used by both pipeline and bot for agent dispatch
- Slack API (Socket Mode) — WebSocket connection for real-time messaging
- Jina Reader (r.jina.ai) — URL reading for article content
- macOS Keychain — all credentials stored here
- launchd — daemon management for both pipeline and bot

### Active Processes

- Daily pipeline: `com.taylerramsay.daily-research` (7 AM via launchd)
- Slack bot: NOT running yet (needs setup)

### Environment Variables

- PYTHONPATH (set in launchd plist)
- PATH (set in launchd plist)
- Keychain services: slack-bot-token, slack-app-token (MISSING), slack-owner-user-id (MISSING), slack-channel-config (MISSING), bluesky-app-password, linkedin-access-token, resend-api-key

## Related Resources

- Implementation plan: `docs/superpowers/plans/2026-03-19-slack-interactive-bot.md`
- CEO plan: `~/.gstack/projects/tayler-id-mindpattern-v3/ceo-plans/2026-03-19-slack-interactive-bot.md`
- Architecture doc: `docs/ARCHITECTURE.md`
- QA report: `.gstack/qa-reports/qa-report-mindpattern-fly-dev-2026-03-19.md`
- Design audit: `.gstack/design-reports/design-audit-mindpattern-fly-dev-2026-03-20.md`
- Test plan: `~/.gstack/projects/tayler-id-mindpattern-v3/taylerramsay-main-test-plan-20260320-104445.md`

---

**Security Reminder**: Before finalizing, run `validate_handoff.py` to check for accidental secret exposure.

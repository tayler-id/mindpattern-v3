# Handoff: Slack Interactive Bot

## Session Metadata
- Created: 2026-03-21
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: `feat/slack-bot` (based on `main`)
- Session duration: ~4 hours (review + hardening + planning + implementation)

## What Was Done This Session

### 1. Code Review (`/review`)
- 34 issues found across 12 critical + 22 informational
- All 34 fixed: SQL injection, path traversal, LLM trust boundary, dead code
- Tests: 473 → 473 (all passing after fixes)
- Committed: `a3ca4d3` + `9f89a75` (merge to main)

### 2. System Hardening (`/plan-eng-review`)
- 151 new tests written (test_runner.py, test_sync.py, test_approval.py)
- Added keychain subprocess timeouts (10s) across 3 files
- Fixed 9 bare `except: pass` blocks with proper logging
- Added RSS feed socket timeout (30s)
- Added file cleanup (.lock files, temp images)
- Added API retry with backoff for Resend email fetching
- Tests: 473 → 624 (all passing)
- Committed: `60630c2`

### 3. CEO Review (`/plan-ceo-review`)
- Mode: SCOPE EXPANSION — 6 expansions all accepted
- Vision: Transform mindpattern from batch pipeline to conversational AI media team
- Approach: Socket Mode Slack bot with plugin architecture
- Plan saved: `docs/superpowers/plans/2026-03-19-slack-interactive-bot.md`
- CEO plan: `~/.gstack/projects/tayler-id-mindpattern-v3/ceo-plans/2026-03-19-slack-interactive-bot.md`

### 4. Eng Review (`/plan-eng-review`)
- Approved plan with 1 architecture change: keep approval.py unchanged (no coupling between bot and pipeline)
- All reviews cleared

### 5. Slack Bot Implementation (Phase 1-4)
- Built complete `slack_bot/` module (11 files, 1,147 lines)
- Committed: `d43452f` on `feat/slack-bot`

## Current State

### Branch: `feat/slack-bot`
```
d43452f feat: add Slack interactive bot with Socket Mode + plugin architecture
adb1712 docs: Slack interactive bot plan + pipeline data updates
60630c2 harden: eng review — 151 new tests, timeout safety, error logging, file cleanup
9f89a75 Merge branch 'feat/obsidian-memory'
a3ca4d3 fix: pre-landing review — 30 fixes across security, trust boundary, and dead code
```

### Files Created
```
slack_bot/
├── __init__.py
├── __main__.py          # python3 -m slack_bot
├── bot.py               # Socket Mode listener + event routing
├── registry.py          # Channel → handler mapping (Keychain/env config)
├── app-manifest.json    # Slack app manifest for quick setup
├── handlers/
│   ├── __init__.py
│   ├── base.py          # BaseHandler (reply, thread, react, URL reading)
│   ├── posts.py         # #mp-posts: URL → full agent pipeline → approve → post
│   ├── engagement.py    # #mp-engagement: search + reply sniper
│   ├── approvals.py     # #mp-approvals: pipeline gate passthrough
│   └── briefing.py      # #mp-briefing: pipeline status summaries
└── launchd/
    └── com.taylerramsay.slack-bot.plist
```

### Tests
- 624 tests passing (existing suite)
- No tests yet for slack_bot/ module (TODO for next session)

## What's NOT Done — Next Session TODO

### 1. Slack App Configuration (5 min manual)
The existing MindPattern Slack app needs additional setup:

**Add Socket Mode:**
- Go to https://api.slack.com/apps → select MindPattern app
- Settings → Socket Mode → Enable Socket Mode
- Generate an App-Level Token with scope `connections:write`
- Store it: `security add-generic-password -s slack-app-token -a mindpattern -w "xapp-..."`

**Add missing bot scopes:**
- OAuth & Permissions → Bot Token Scopes → add: `channels:manage` (to create channels)
- Reinstall app to workspace after adding scopes

**Add event subscription:**
- Event Subscriptions → Subscribe to bot events → add `message.channels`

### 2. Create Slack Channels (2 min manual)
Create these channels in Slack and invite the bot:
- `#mp-posts`
- `#mp-engagement`
- `#mp-briefing`
- `#mp-approvals` already exists as `#mindpattern-approvals` (C0ALSRHAATH)

### 3. Store Channel Config in Keychain
After creating channels, get their IDs and store:
```bash
security add-generic-password -s slack-owner-user-id -a mindpattern -w "U0AM88ZGK8A"
security add-generic-password -s slack-channel-config -a mindpattern -w '{"posts":"C_XXX","engagement":"C_XXX","approvals":"C0ALSRHAATH","briefing":"C_XXX"}'
```

### 4. Test the Bot
```bash
cd /Users/taylerramsay/Projects/mindpattern-v3
source .venv/bin/activate
python3 -m slack_bot
```
Then post a URL in #mp-posts and verify the pipeline fires.

### 5. Fix LinkedIn Engagement
- Replace broken `search_via_jina()` with LinkedIn RSS + Jina Reader approach
- File: `social/engagement.py`
- See plan: `docs/superpowers/plans/2026-03-19-slack-interactive-bot.md` → "Engagement Fix"

### 6. Write Tests for slack_bot/
- test_bot.py: Socket Mode connect/reconnect (mock slack_sdk)
- test_registry.py: channel routing
- test_handlers.py: posts pipeline, engagement search, reply sniper (mock agents)

### 7. Deploy Daemon
```bash
cp slack_bot/launchd/com.taylerramsay.slack-bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.taylerramsay.slack-bot.plist
```

## Key Architectural Decisions
1. **Socket Mode** (not webhook) — runs on Mac, no public URL, uses WebSocket
2. **Plugin architecture** — BaseHandler + registry, adding new channel = 1 file
3. **No approval.py coupling** — bot and pipeline are independent, both post to their own channels
4. **Mutex** — file-based lock prevents Claude CLI collisions between bot and pipeline
5. **Owner filtering** — bot only responds to configured user ID (U0AM88ZGK8A)

## Existing Credentials in Keychain
| Service | Status |
|---------|--------|
| slack-bot-token | EXISTS (xoxb-...) |
| slack-app-token | MISSING — needs Socket Mode setup |
| slack-owner-user-id | MISSING — value is U0AM88ZGK8A |
| slack-channel-config | MISSING — needs channel IDs |
| bluesky-app-password | EXISTS |
| linkedin-access-token | EXISTS (may be expired) |
| resend-api-key | EXISTS |

## Review Readiness
| Review | Status |
|--------|--------|
| Eng Review | CLEARED (2026-03-20) |
| CEO Review | CLEARED (2026-03-19) |
| Design Review | CLEARED (2026-03-20) |
| QA | Health 95/100 (2026-03-19) |

# Deployment — launchd agents (macOS)

Two launchd agents keep MindPattern running on the host Mac. Copies live here
so a machine move is reproducible (the `~/Library/LaunchAgents` originals are
not in the repo).

| Agent | File | What it does |
|-------|------|--------------|
| `com.mindpattern.pipeline` | `com.mindpattern.pipeline.plist` | Runs `run-launchd.sh` hourly 07–11. The wrapper enforces a once-per-day marker + run window, so extra triggers are cheap no-ops and provide catch-up if the Mac was asleep at 07:00. |
| `com.mindpattern.slackbot` | `com.mindpattern.slackbot.plist` | Long-running Socket Mode daemon (`python -m slack_bot`). `KeepAlive` restarts it on crash/wake. Handles #posts, #tips, #skills, #approvals, etc. |

## Install (new machine)

```sh
cp deploy/com.mindpattern.pipeline.plist  ~/Library/LaunchAgents/
cp deploy/com.mindpattern.slackbot.plist  ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mindpattern.pipeline.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mindpattern.slackbot.plist
launchctl list | grep mindpattern   # verify both registered
```

## Prerequisites (the things that broke on the last machine move)

launchd gives a **minimal PATH**, and the pipeline/bot shell out to external
tools. The `PATH` in both plists must point at where these actually live:

- **claude CLI** — `~/.local/bin/claude`
- **flyctl** — `~/.fly/bin/flyctl` (must be authenticated: `flyctl auth login`)
- **node/npm/npx** — `~/.local/node/bin`
- **venv** — `.venv/` in the repo (plists call `.venv/bin/python3`)

Secrets are in the macOS Keychain (account `mindpattern`): `slack-bot-token`,
`slack-app-token`, `resend-api-key`, `bluesky-app-password`, etc.

## Manage

```sh
launchctl kickstart -k gui/$(id -u)/com.mindpattern.slackbot   # restart bot
launchctl bootout gui/$(id -u)/com.mindpattern.pipeline        # unload
tail -f reports/slack-bot.log reports/launchd-decisions.log    # logs
```

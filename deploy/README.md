# Deployment

## Shipping the backend: `deploy/deploy.sh`

This is the deploy. A bare `flyctl deploy` is not.

Replacing the Fly machine empties every in-memory cache in
`dashboard/routes/api.py`, and a Vercel deploy drops the whole Next.js ISR
cache. Either way the next reader pays the cold render. On 2026-08-26 four
deploys in one evening left mindpattern.ai cold, with nothing to recover it
until the operator noticed and warmed it by hand.

```sh
deploy/deploy.sh                # tests, 3.11 compile gate, fly deploy, purge + warm
deploy/deploy.sh --warm-only    # after a Vercel deploy: crawl the whole sitemap
deploy/deploy.sh --skip-tests   # compile gate only (rare)
```

Steps, in order: `python3.11 -m py_compile` over `dashboard/ orchestrator/
slack_bot/` (Fly runs 3.11, the venv is 3.14), `pytest tests/ -q`, `flyctl
deploy --strategy immediate`, poll `/healthz` until the machine answers, poll
`/api/warmup/status` until the phase leaves `running`, print any `incomplete`
warm-up steps, then `python3 -m orchestrator.sync warm`. A warm-only run skips
the compile gate and the tests: it ships nothing.

### Two scopes, because the two failures are different

`--scope changed` (the default after a backend deploy) purges the paths the
day's publish wrote and crawls them back. `--scope site` (the default for
`--warm-only`) crawls the site's own `sitemap.xml` and purges nothing, because
a Vercel deploy has already dropped every entry a purge would drop. The
sitemap set is ordered entry points, all `/e/`, all `/source/`, then the
newest 30 briefings, 30 blog dates and 200 stories, roughly 370 pages. The
whole sitemap is over 7,000 URLs and no serial crawl finishes it; the archive
tail renders in 0.2-3.4s cold and crawlers re-warm it themselves.

Getting this wrong is what the script was written for. `changed_site_paths`
on a day with no publish yet returns exactly four paths, all of which answer
200, so the earlier version printed "purged and warm" over a site where ~780
story pages and 86 entity pages were still cold.

The script exits nonzero if the crawl covered less than it was asked to cover:
no paths, nothing crawled, any page erroring, or the crawl budget running out
mid-set. Other exit codes: 2 unknown argument, 3 `MP_SANDBOX=1`, 4 no
python3.11, 5 `/healthz` never returned.

### Purge-on-publish secret

`orchestrator/sync.py` POSTs the changed paths to the site's
`/api/revalidate` with a shared secret in the `x-revalidate-secret` header.
Set the same value in two places:

- Vercel project env var `REVALIDATE_SECRET`.
- This machine: `MP_REVALIDATE_SECRET`, or `~/.mindpattern-revalidate-secret`.

Unset, the pipeline logs a warning, skips the purge, and the site falls back
to its hour-long TTL. The publish still succeeds; readers just wait.

## launchd agents (macOS)

The checked-in plists describe host launchd configurations, not proof that either
job is currently loaded. Installed files and loaded state can differ. See
[Scheduling](../docs/ARCHITECTURE.md#scheduling) for the pipeline's calendar,
wrapper guards, and evidence limits.

| Agent | File | What it does |
|-------|------|--------------|
| `com.mindpattern.pipeline` | `com.mindpattern.pipeline.plist` | Invokes `run-launchd.sh` on the checked-in calendar. See [Scheduling](../docs/ARCHITECTURE.md#scheduling) for trigger times and delivery/sync retry behavior. |
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

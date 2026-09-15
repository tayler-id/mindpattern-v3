---
name: verify-mindpattern
description: Drive and verify MindPattern backend behavior through its isolated control CLI. Use for reproducing API behavior, checking a changed reader flow, inspecting synthetic responses, or collecting verification evidence. Browser rendering and live pipeline operations need their own checks.
---

# Verify MindPattern

Run commands from the `mindpattern-v3` repository root with its Python 3.14 virtual environment. Read the relevant entry in the [feature map](references/features/README.md) before selecting checks. The CLI uses the actual FastAPI routes and authentication middleware with synthetic artifacts.

## Launch

The default CLI starts a disposable worker for each command. It copies current source into a temporary workspace, seeds synthetic state, and removes the workspace when the command ends.

```sh
.venv/bin/python3 -m verification --help
.venv/bin/python3 -m verification features
.venv/bin/python3 -m verification doctor
```

For real HTTP inspection, keep this command in its own terminal:

```sh
.venv/bin/python3 -m verification serve --port 8011
```

Wait for Uvicorn to report that it is running. Use a different loopback port if 8011 is occupied. Stop the command with Ctrl-C when finished. Do not stop unrelated processes to free a port.

## Doctor

Run `doctor` before driving a feature or when a result looks wrong. Read its response and limitations. A reachable health route does not prove that a production database, Slack bot, or pipeline is healthy. This command describes the synthetic instance.

## Drive

```sh
.venv/bin/python3 -m verification features stories
.venv/bin/python3 -m verification verify stories
.venv/bin/python3 -m verification request '/api/stories?user=ramsay&limit=10'
.venv/bin/python3 -m verification request '/api/stories/verification-story?user=ramsay'
.venv/bin/python3 -m verification request '/api/stories?user=ramsay' --base-url http://127.0.0.1:8011
```

Use `verify all` for the five implemented CLI scenarios. This is a bounded backend smoke, not the full repository suite. `request` inspects a supported GET route. Unsupported routes require extending the driver with an isolated fixture and behavior assertions.

The default transport exercises the real ASGI app. `serve` exercises Uvicorn and real HTTP. Both skip application lifespan, including the background cache warmup. Neither proves that a browser renders the response correctly.

For frontend work, follow the [public frontend entry](references/features/other-workflows.md) and the sibling repository's instructions. For pipeline or publishing work, use the existing operational skill linked there.

## Evidence

```sh
.venv/bin/python3 -m verification verify all --evidence /private/tmp/mp-verification-proof
```

Choose a new evidence directory for each run. Read the saved assertions and response bodies before reporting success. Keep the source identity, command, scenario, response status, observed result, and coverage limits together. Do not save bearer tokens or authorization headers.

A proof shows the action and its observable result. For a story change, check its list entry, detail, source references, and affected exclusion paths. For a cache change, inspect the resulting scratch artifacts as well as the response. Use the same production request path; calling an internal function alone does not prove routing or authentication.

Report failures and unsupported paths explicitly. A synthetic fixture demonstrates behavior for that input. It does not establish the quality or completeness of personal research data.

## Cleanup

Short-lived commands remove only their own temporary runtime state. Stop a foreground `serve` command through its owning terminal. Confirm that the evidence directory still exists after cleanup. Preserve evidence for review, including failed runs.

Do not use `run.py`, `run-launchd.sh`, `start.sh`, or a live Slack connection as verification setup. A pipeline dry run can still write reports, checkpoints, and local databases.

## Helpers

The CLI implementation lives in [verification/](../../../verification/). Its `--help` output is the command reference. The [maintenance procedure](references/maintenance.md) describes how to update the driver and feature map together.

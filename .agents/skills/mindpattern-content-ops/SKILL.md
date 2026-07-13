---
name: mindpattern-content-ops
description: Diagnose and operate MindPattern's post-research content stages, including synthesis, newsletter delivery, SITE_CONTENT, Slack approval, social publishing, audio briefings, video scripts, and Fly sync. Use for pipeline status, artifact checks, safe dry runs, approval failures, media workflows, or publishing readiness in mindpattern-v3. Do not use for preflight research, general copywriting, repository release, or archive backfill.
---

# MindPattern Content Ops

Prefer current code, tests, `social-config.json`, reports, markers, and runtime state over dated handoffs.

## Classify the request

- For status or diagnosis, inspect state and artifacts without starting the pipeline.
- For a safe simulation, explain that dry runs still write local logs, artifacts, checkpoints, and acquire the pipeline lock.
- For a live run, publishing action, Slack connection, sync, or deployment, require explicit authorization immediately before the action.

## Inspect the system

Use these sources as relevant: `run.py`, `orchestrator/pipeline.py`, `orchestrator/runner.py`, `orchestrator/newsletter.py`, `social/pipeline.py`, `social/approval.py`, `slack_bot/`, `orchestrator/audio_briefing.py`, `orchestrator/video_scripts.py`, `social-config.json`, and `reports/`.

Start with narrow diagnostics such as `.venv/bin/python3 -m harness.health_report`, the pipeline lock, current daily markers, checkpoint state, receipt records, and recent report artifacts.

## Verify narrowly

Select only the relevant group:

```sh
.venv/bin/python3 -m pytest tests/test_newsletter.py tests/test_newsletter_receipts.py tests/test_evaluator.py -q
.venv/bin/python3 -m pytest tests/test_slack_bot.py tests/test_social.py tests/test_approval.py tests/test_approval_parsing.py -q
.venv/bin/python3 -m pytest tests/test_narrative_arcs.py tests/test_social_angle_lab.py tests/test_audio_briefing.py tests/test_video_scripts.py tests/test_media_artifact_contracts.py tests/test_media_feature_safety.py -q
.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q
```

Run `.venv/bin/python3 run.py --user ramsay --dry-run --skip-social` only when a local simulation is requested. Never run the live pipeline, `run-launchd.sh`, or `python3 -m slack_bot` merely to answer a status question.

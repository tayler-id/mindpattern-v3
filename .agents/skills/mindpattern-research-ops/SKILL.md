---
name: mindpattern-research-ops
description: Diagnose and operate MindPattern's eight-source preflight and 13-agent research layer, including source health, routing, deduplication, transient failures, follow-up research, and finding validation. Use for mindpattern-v3 research-pipeline or source-backend work. Do not use for ordinary one-off web research, newsletter or social operations, site backfill, or generic software research.
---

# MindPattern Research Ops

Use current code, tests, policies, and source health as truth. Treat dated research documents as rationale, not current status.

## Inspect before running

Read the relevant parts of `preflight/`, `orchestrator/agents.py`, `orchestrator/router.py`, `orchestrator/traces_db.py`, `orchestrator/followup.py`, `verticals/ai-tech/agents/`, and `policies/research.json`.

Check configured backends with `agent-reach doctor --json`, `twitter status`, `yt-dlp --version`, or `mcporter list exa --status` only when that source is in scope. Use `agent-reach` alone for ordinary public-web fetching.

## Verify narrowly

```sh
.venv/bin/python3 -m pytest tests/test_preflight.py tests/test_agents.py tests/test_agent_defang.py tests/test_dedup_resurfacing.py tests/test_followup_research.py -q
.venv/bin/python3 -m pytest -q --tb=short tests/test_runner.py::TestPhaseTrendScan tests/test_runner.py::TestPhaseResearch
```

Inspect stored findings with:

```sh
.venv/bin/python3 memory_cli.py search-findings --days 7 --min-importance high --limit 20
```

Do not invent a standalone `preflight/run_all.py` operation or instantiate private pipeline internals. A live research run currently enters the delivery pipeline and requires explicit authorization.

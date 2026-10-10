# devtools/cli.py

> `bin/mpdev`, one command in front of every developer tool, plus the check runner and the doctor.

## What It Does

`bin/mpdev <command>` maps each command to a module's `main(argv)` in `COMMANDS`. `bin/mpdev help` lists them, with the ones that make model calls or write live state named as such.

The launcher picks Python in order: `MP_PYTHON`, this checkout's `.venv`, the main checkout's `.venv` from a worktree, then `python3`.

## Check

`devtools/check.py` runs `devtools/checks.json` in order and exits 1 if any check fails. It writes each check's log to `.scratch/checks/<commit>/` and a receipt to `.scratch/checks/<commit>.json`.

The checks are data, so the CLI, CI, and the skills read one list. Today: doctor, config, layers, knowledge, tests.

## Doctor

`devtools/doctor.py` is read-only. It probes Python, packages, the model and GitHub CLIs, the databases, and the code graph's freshness, and prints a fix for each blocked probe.

`--ci`, or `CI=true`, keeps only the probes CI can pass: Python and packages.

## Depends On

[[tools/replay]], [[core/trace_store]], `harness/layers.py`, `harness/knowledge_graph.py`, `core/config.py`. Plan: `docs/specs/2026-10-10-agent-ready-codebase.md`.

## Last Updated

2026-10-10. Created with step 1 of the agent-ready plan.

# tools/replay_day.py, tools/bakeoff.py, tools/usage_report.py

> Rerun a past day on real data without touching the live checkout, compare two issues blind, and measure usage.

## Replay

`tools/replay_day.py --date D --stage synthesis|research --state-root ~/Projects/mindpattern-v3 --out DIR` copies the code into a scratch workspace and snapshots `memory.db` and `traces.db` with the SQLite backup API.

It restores the day's trends, sets `MP_DISABLE_OUTBOUND=1`, and sends traces to `DIR/traces`. `--models FILE` swaps routes, `--agents a,b` picks research agents, `--dry-run` makes no model calls.

## Bakeoff

`tools/bakeoff.py --a A.md --b B.md --out DIR` writes `compare.html` with both issues in random order and their violation counts. `--reveal DIR` prints which was which.

## Usage Report

`tools/usage_report.py --date D` totals Claude transcript usage by task and model, deduped by message and request id. Transcripts repeat usage across lines of one response, and an earlier hand count was 2.5 times too high for that reason.

## Health, Mutation, Backfill

`tools/health.py` reads traces.db, memory.db and the story folders and prints a row per day with the problems it finds, against the evaluator's floors and the editorial story target.

`tools/mutate.py` breaks one line, runs the named tests, and restores the file byte for byte. `tools/site_backfill.py` writes missing site stories for past dates, optionally with the critic on Claude.

## Results Kept

Replays live in `data/ramsay/replays/` (gitignored). The Sep 30 synthesis replays and the Oct 2 research replays are recorded in `docs/specs/2026-10-02-models-harness-policies-spec.md`.

## Depends On

[[orchestrator/runner]], [[core/trace_store]].

## Last Updated

2026-10-02. Created with the models harness.

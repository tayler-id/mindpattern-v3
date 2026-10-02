# mp/cli.py

> `mp`, the deterministic tools research and deep-dive agents call through `Bash(mp *)` instead of following prose rules. Launcher at `bin/mp`.

## Commands

Seven commands, each printing JSON.

- `mp finding add` validates a finding against `contracts/research_finding.schema.json` and the research policy, rejects same-run and 10-day duplicates, and stores it the moment it is confirmed.
- `mp findings list`, `mp seen "<lead>" ...` (180 days of coverage, several leads per call), `mp fetch <url> --max-chars N --offset N`.
- `mp evidence add --story S` stores deep-dive evidence for [[orchestrator/deep_dive]].
- `mp lint <file>` and `mp tells --since N` measure a draft or the published issues against the writing policy.

## Input Format

Records go in a quoted heredoc, one `field: value` per line, with `---` between records. Claude Code's Bash check refuses any command containing `{"`, so inline JSON failed on every call in the first real replay.

The quoted heredoc passes apostrophes, `$`, and backticks through untouched. `--json` still takes an object or a list, for scripts.

## Why It Exists

On Sep 27 and Sep 29 2026, 6 and 4 of 13 agents hit the 35-turn cap and printed nothing, so their whole day of research was lost. A stored finding survives the cap, and [[orchestrator/agents]] merges stored and printed findings.

## Known Fragile Points

Agents give up on a tool after a refusal, so every refusal shape matters.

- Agents may call it as `bin/mp`. Both grants exist, and the grant contract counts both as `mp`.
- A refused command makes an agent give up on `mp` for the rest of its run. Every refusal shape seen so far has a test.
- Every exit code means something: 0 accepted, 2 rejected with reasons, 1 could not run.

## Last Updated

2026-10-02. Created with the models harness.

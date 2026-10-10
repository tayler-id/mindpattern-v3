# Spec: an agent-ready codebase

Status: approved by the owner 2026-10-10. Step 1 built on `feat/agent-ready` 2026-10-10.

## Objective

An agent that has never seen this repository can change it and prove the change works without asking anyone. It finds every developer tool in one place behind one command, runs the same checks CI runs, runs any phase of the pipeline against real data without touching live state, and reads skills that tell it exactly which checks a change needs. Constraints live in code, not in prose: a lint baseline, a type checker, import layers, red-before-green in CI. A bug bot turns failures into GitHub issues and a triage agent reproduces them.

No rewrite. Each step is a small PR that ends in a check that proves it, and nothing in the live daily run changes until a step says so.

The model for this is `tayler-id/agent-team-workspace`, which already has checks stored as data and run by one command, a read-only doctor, a CI red-green replay of every commit's tests against its parent, and a create and maintain pair of verification skills.

## What exists today

| Area | State on 2026-10-10 |
|------|---------------------|
| CI | `.github/workflows/test.yml` runs pytest on pull requests and on main. Since 2026-04-01 (`65fb9e7`) it skips `tests/test_runner.py` except four phase classes, `tests/test_cors.py`, and `tests/test_memory_cli.py` because they depend on the local machine. No lint, type, layer, config, or knowledge check runs in CI. |
| Static analysis | None. `layers.toml` holds import rules and `python -m harness.layers check` passes on 165 cross-package imports, but only when someone runs it. |
| Knowledge check | `python -m harness.knowledge_graph check` reports 5 failures, all section lead paragraphs over 250 characters. |
| Developer tools | Mixed into `tools/` with six scripts the pipeline itself runs (`arxiv-fetch`, `github-fetch`, `hn-fetch`, `reddit-fetch`, `rss-fetch`, `image-gen`). Documented in `docs/tools.md`. |
| Running the pipeline in parts | `tools/replay_day.py` covers SYNTHESIS and RESEARCH. No other phase can run outside the live run. |
| Skills | `.agents/skills/verify-mindpattern` drives the website. Nothing drives or verifies the pipeline. `.claude/agents` has a code reviewer, a security auditor and a test engineer. |
| Bug finding | The harness scout, fix and review loop last ran 2026-04-02. It files JSON tickets in `harness/tickets/`, not GitHub issues. |
| Triage | The five triage labels exist on GitHub. Issue #24 has waited in `needs-triage` since 2026-05-04. |
| Code graph | Git hooks rebuild `graphify-out/` after every commit and checkout, and the main checkout keeps it out of git with skip-worktree. The committed copy was last refreshed 2026-07-24, so a fresh clone, CI, or a cloud agent gets a stale graph. |

## Principles

- **Checks are data.** The list of checks lives in one JSON file. The CLI, CI, and the skills all read it, so they can't drift apart.
- **Ratchets only tighten.** Lint and type baselines record today's violations. A new violation fails. A fixed one shrinks the baseline. Raising a baseline is a reviewed edit, the same rule `layers.toml` already follows.
- **Red before green.** A test that hasn't been seen failing proves nothing. CI replays each commit's changed tests against its parent and requires them to fail there.
- **Outbound stays off outside the live run.** Every tool that runs pipeline code sets `MP_DISABLE_OUTBOUND=1` and writes only to a scratch workspace or its `--out` folder.
- **One command to learn.** `bin/mpdev <subcommand>` fronts every developer tool.

## Target layout

```
bin/
  mp            research agents' tools (unchanged)
  mpdev         developer CLI: python -m devtools.cli
devtools/       every tool for working on the codebase
  cli.py        mpdev subcommands
  checks.json   the checks, as data
  check.py      runs checks.json, writes a receipt per commit
  doctor.py     read-only: is this machine ready to work and test?
  replay_day.py rerun_call.py bakeoff.py mutate.py health.py
  usage_report.py site_backfill.py
  baselines/    lint and type ratchets (step 2)
tools/          scripts the pipeline runs (unchanged)
.claude/skills/ and .agents/skills/   project skills for Claude and Codex
```

## Steps

### Step 1. One folder and one command for developer tools

- [x] Move the seven developer tools from `tools/` to `devtools/` with `git mv`. Every caller, test, and doc path is updated by a script that checks each file before writing it (the file still parses, and only the expected paths changed).
- [x] `bin/mpdev` with subcommands `replay`, `rerun`, `bakeoff`, `mutate`, `health`, `usage`, `site-backfill`, `check`, `doctor`.
- [x] `devtools/checks.json` and `mpdev check`. It runs every check in order, prints pass or fail with timings, and writes a receipt for the commit (`.scratch/checks/<sha>.json`, with the dirty flag). It exits 1 when any check fails. `--only ID` and `--list` work.
- [x] `mpdev doctor`, read-only. Python version, required packages, the `claude`, `codex` and `gh` CLIs, readable databases, a fresh code graph, and skip-worktree on `graphify-out/`. Each failure prints its fix. `--ci` skips what CI can't have (CLIs, live data).
- [x] Fix the knowledge-check failures so the knowledge check can join `checks.json`. There were 34, not 5: the check prints only its first five.
- Acceptance: `bin/mpdev check` passes on the branch. Breaking any one check makes `mpdev check` exit 1 and name it. `git grep` finds the old tool paths only in dated specs.

### Step 2. Static analysis with a ratchet

- [ ] `requirements-dev.txt` with pytest, ruff, and mypy.
- [ ] `mpdev lint`. Ruff with a baseline of today's violations per file and rule in `devtools/baselines/ruff.json`. A new violation or a higher count fails. `--update` rewrites the baseline after a cleanup.
- [ ] `mpdev types`. Mypy over an allowlist in `devtools/baselines/typed.txt`, starting with `devtools/`, `orchestrator/threads.py`, `orchestrator/issue_format.py`, `orchestrator/editorial.py`, and `orchestrator/deep_dive.py`. A module joins the list when it passes.
- [ ] Both join `checks.json`, with the layer check.
- Acceptance: a new unused import in any file fails `mpdev lint`. An existing violation doesn't. A type error in an allowlisted module fails `mpdev types`.

### Step 3. CI runs the same checks

- [ ] Jobs: `doctor` (`mpdev doctor --ci`), `static` (lint, types, layers), `config` (`core.config check` and every contract loads), `docs` (knowledge check, Mermaid parse), `tests` (the full suite), `red-green`.
- [ ] Make the four skipped test files machine-independent and run them in CI.
- [ ] `devtools/red_green.py BASE HEAD`. For each commit that changes both source and tests, run its changed test files against the parent (they must fail) and at the commit (they must pass). A commit that changes only tests or docs skips. A pull request that changes source with no changed test fails.
- Acceptance: a pull request that adds a guard whose test passes without the guard turns CI red.

### Step 4. Run any phase of the pipeline

- [ ] `mpdev run --phase NAME --date D` on the replay workspace, for every phase. DELIVER renders the email and writes what it would send to `<out>/outbox/`. SYNC builds the bundle and doesn't upload. SOCIAL and ENGAGEMENT stay manual and are not runnable here.
- [ ] Before each phase is added, a short audit lists what it reads, writes, and sends, kept in `docs/tools.md`.
- Acceptance: each phase runs in a scratch workspace with outbound off, and a test that hashes the live tree before and after proves nothing live changed.

### Step 5. Skills that tell agents how to check their work

- [ ] `verify-pipeline` skill (Claude and Codex copies). Doctor, run a phase, drive, evidence, cleanup, all through `mpdev`, with a feature map per phase.
- [ ] `check-your-work` skill. Which checks a change needs. A prompt change needs a replay and a rerun. A new guard needs `mpdev mutate`. Every change needs `mpdev check`.
- [ ] Adopt `maintain-verification-skill` from agent-team-workspace as the upkeep loop.
- [ ] `mpdev skills check`. Every command a repo skill names must exist and answer `--help`. Joins `checks.json`.
- Acceptance: removing a subcommand a skill uses fails `mpdev skills check`.

### Step 6. Bug bot and triage agent

- [ ] `mpdev bugbot`, deterministic. It collects problems from `health --json`, failed model calls, `layout_violations` and prose-gate events, and CI failures on main. Each problem gets a fingerprint. It skips any problem already open and files the rest as GitHub issues labeled `bug` and `needs-triage`, with the evidence and the commands that reproduce it. It prints by default and files only with `--file`.
- [ ] `mpdev triage`. A Claude agent on its own route with a triage skill and the `mpdev` tools. For each `needs-triage` issue it reproduces what it can, comments with the evidence, and proposes a label. `--apply` sets the label.
- [ ] Retire the harness JSON tickets in favor of GitHub issues. The fix loop can later pick up `ready-for-agent`.
- Acceptance: a known failure in a fixture traces database makes the bug bot propose exactly one issue, and a second run proposes none.

## Testing

Every new function gets a test that calls it the way its users do and checks a literal result. Every new guard is broken once with `mpdev mutate` and must go RED. Every step's PR runs `mpdev check` at each commit before it is pushed.

## Boundaries

- Always: run `mpdev check` before a commit. Watch a new test fail before trusting it. Keep checks in `checks.json`.
- Ask the owner first: any dependency beyond pytest, ruff and mypy. Letting the bug bot file issues on a schedule. Letting the triage agent change labels unattended. Any change to launchd or the live run.
- Never: push or merge without the owner's permission rule for it. Skip or loosen a check to land a change. Raise a baseline to hide a new violation. Run the live pipeline outside its schedule.

## Success criteria

- On a fresh clone, `bin/mpdev doctor` and `bin/mpdev check` give the same verdict CI gives.
- Every phase except SOCIAL and ENGAGEMENT runs in a scratch workspace on real data.
- CI rejects a source change whose test was never seen failing.
- The bug bot files issues from real failures without duplicates, and the triage agent's comment lets a person or agent reproduce the problem.

## Open questions

- Type checker. Mypy is the default because it installs with pip. Pyright is stricter and needs Node.
- Branch protection. Whether CI failures block merges is a GitHub setting for the owner.
- Runtime fetchers. Whether the six pipeline scripts move out of `tools/` later, for example to `preflight/fetchers/`.

# Autonomous Routines Plan

**Scope (Tayler's decision): the Claude Code team's 11 routines, all running daily, on
`mindpattern-v3`.** Crash-fuzzer fans out internally across the repo's 4 runtime surfaces;
everything else is one routine each. The `vercel-mindpattern` variants (§4b) are a later
extension, not part of the daily 11.

Status: **draft for approval — nothing built yet.**

---

## Findings that shaped this plan

Four assumptions were checked against the code, and three were wrong:

| Assumption | Reality |
|---|---|
| No `/verify` exists; build it from scratch | `harness/gates.py` already has `gate_tests_pass`, `gate_syntax_valid`, `validate_ticket`, `determine_review_depth`. **Extend it, don't build a parallel system.** |
| A `slack_bot → harness` import would crash on Fly | `slack_bot/handlers/harness.py` imports `harness.tickets` in 4 places — deliberately, as *function-local* deferred imports with a documented "run on the Mac" fallback. A naive layering rule flags these as violations. **The layer manifest needs an allowlist.** |
| No CI, so flaky-test data may not exist | `.github/workflows/test.yml` runs on PRs and pushes to `main`. Flake history is minable via `gh run list`. **Viable.** |
| `mindpattern-rabbit-hole` is a separate project | It is a **git worktree** of `vercel-mindpattern` (shared `.git`, same remote). Three checkouts, one repo. |

---

## 1. Constraints that differ from the source setup

The Claude Code team runs these across iOS/Android/desktop/web/CLI/SDK with an org-sized
review pool and real crash telemetry. Three differences drive every decision below.

**One reviewer.** 25 routines opening daily PRs produces a queue nobody clears. PR volume
is a design constraint, not an afterthought — routines must either auto-merge behind hard
gates or batch their findings.

**Quota is the binding constraint.** The newsletter is the product and has been starved
twice already (see `research-tool-starvation-incident`, `job-hunt-quota-collision`). On
2026-08-13 a single Agora session burned 228M tokens through ~60 workflow subagents in
under an hour, on an account already near its weekly cap. A routine fleet is that failure
mode, scheduled.

**"Real app, no mocks" has a cost ceiling.** A full pipeline run is 3–4.8 hours
(`traces.db`, last 5 runs) and enormous token spend. The crash fuzzer **cannot** work by
re-running `run.py` end to end.
It targets phase-level entry points with recorded and mutated inputs instead — real code
paths, real DB, no full-pipeline replay.

---

## 2. Prerequisites

None of the routines are safe or useful until these four land.

**P1 — `harness/sandbox.py`, fail-closed side-effect isolation.**
Temp copies of `memory.db` and `traces.db`; Resend, Bluesky, LinkedIn, and Fly sync hard
disabled; `claude` calls budgeted. Every routine asserts sandbox before doing anything.
`MP_DRY_RUN` already exists and is the hook. Without this, a fuzzer eventually publishes
garbage to mindpattern.ai or fires a real approval.

**P2 — `/verify` as an extension of `harness/gates.py`.**
Adds to the existing gates: boot the target surface in sandbox, replay the repro, assert
it **fails pre-fix and passes post-fix**, emit the truth table, run `graphify update .`.
The pre-fix failure assertion is what makes a routine's PR trustworthy.

**P3 — `layers.toml`, a declared layer manifest with an allowlist.**
Encodes the real rules: `harness/` is not in the container image, `dashboard/` must not
reach into orchestrator internals, the four graphs stay separate. Allowlists intentional
deferred imports like `slack_bot/handlers/harness.py`.

**P4 — Reconcile the frontend worktrees.** *(Blocks only the web routines — Phase 3,
not Phase 1.)* `vercel-mindpattern` is on `modern-web-guidance-compliance`,
`mindpattern-rabbit-hole` on `main`, with diverged `package.json`. Web routines need one
agreed base branch or PRs target the wrong thing.

---

## 3. Fan-out rule

**Per-app only for `crash-fuzzer`. Everything else is repo-wide.**

Crash fuzzing splits because the runtime entry points genuinely differ — an HTTP request,
a Slack event, a feed record, a DB write. Nothing else does. Dup-unifier, dead-code, and
the abstraction routines operate on the whole import graph; scoping them to one package
hides cross-package findings, which is exactly where duplication and layering rot live.

This is a correction to an earlier draft that fanned the logic routines out per app.

---

## 4. Routine catalog

### 4a. The daily 11 (mindpattern-v3)

Crash-fuzzer is one routine with four surface targets — the first four rows. The
remaining ten rows are the other ten routines, one each.

| Routine | Scope | Signal source |
|---|---|---|
| `crash-fuzzer-siteapi` | `dashboard/` | local FastAPI + schemathesis over OpenAPI; approval-token endpoints prioritized |
| `crash-fuzzer-pipeline` | `orchestrator/` phase entry points | mutated `preflight/` feed records — malformed RSS, unicode, empty results, oversized payloads |
| `crash-fuzzer-slackbot` | `slack_bot/` | mutated Socket Mode event payloads |
| `crash-fuzzer-memorykg` | `memory/`, `kg/` | concurrent writes, WAL contention, malformed rows |
| `logic-bugfixer` | rotating module | formal model (§5) — reachable rows with no branch |
| `logic-simplifier` | rotating module | formal model — branches with identical outcomes |
| `dup-unifier` | repo-wide | graphify + model equivalence across packages |
| `dead-code` | repo-wide | graphify reachability; log-probe suspected-dead, delete next day |
| `useless-test-pruner` | repo-wide | mutation testing — tests that survive every mutant |
| `flaky-test-fixer` | repo-wide | `gh run list` history for same-SHA pass/fail splits |
| `shipped-feature-inliner` | repo-wide | `MP_*_ENABLED` flags on 100% for N days |
| `ant-only-shipper` | repo-wide | owner-gated surfaces (`slack-owner-user-id`, harness commands, endpoints the site never calls) — ship or delete on usage |
| `abstraction-improver` | repo-wide | single-implementation interfaces, wrapper-only classes, one-caller indirection |
| `abstraction-police` | repo-wide | import edges vs `layers.toml` |

### 4b. Later extension: vercel-mindpattern (not in the daily 11)

Closest match to the original setup, since this one actually has a UI.

| Routine | Notes |
|---|---|
| `crash-fuzzer-web` | Playwright against a real browser — the `e2e` script already exists. Console errors, unhandled rejections, hydration failures. |
| `dead-code-web` | `knip` / `ts-prune` — provable here, unlike Python |
| `dup-unifier-web`, `abstraction-police-web` | TS import graph |
| `useless-test-pruner-web`, `flaky-test-fixer-web` | mutation + CI history |

**Highest value first:** `abstraction-police` catches a class of bug the tests structurally
cannot — local runs have `harness/` present, the container does not. `crash-fuzzer-pipeline`
gets real malformed input from the 8 feeds on day one.

---

## 5. The shared formal model

One decision table per module per night, diffed against implemented branches. Each kind of
mismatch belongs to a different routine, so the model is built once and shared:

| Mismatch | Owner |
|---|---|
| Reachable row, no branch | `logic-bugfixer` |
| Two branches, identical outcomes | `logic-simplifier` |
| Same table in two modules | `dup-unifier` |
| Row unreachable under all inputs | `dead-code` |
| Row with no test, or test mapping to no row | `useless-test-pruner` |

The model **is** the truth table the PR posts — not a second artifact.

Best targets, by logic density: `orchestrator/router.py`, `orchestrator/prose_gate.py`, the
`Phase` state machine in `orchestrator/pipeline.py`, `policies/`, `social/posting.py` gates,
and the approval-token states in `dashboard/` (also security-relevant — tokens arrive in URLs).

Honest caveat: sharing works cleanly for gap and duplication detection. Reachability proofs
for dead code need more rigor than a decision table gives, and will likely stay separate.

---

## 6. Shared contract

**Every PR carries:** a repro that fails pre-fix and passes post-fix, the truth table,
`/verify` output, and `graphify update .`.

**Truth table format:**

```
| # | Input / state       | Expected | Pre-fix | Post-fix |
| 1 | empty feed, 0 items | skip     | CRASH   | skip     |
```

**Slack:** a `#mp-fuzzer` channel, one top-level thread per routine per day named
`{routine} · {date}`, updates threaded beneath, PR link as the closing message.
`slack_bot/` already dispatches by channel, so this is a new handler, not new infra.

---

## 7. Budget and schedule

One nightly scheduler, not 25 cron entries. It runs a rotating subset under a hard token
budget and stops when the budget is spent.

- Never overlaps the newsletter window (wake ~08:00 ET through delivery).
- Runs on the account that is **not** serving the pipeline that day.
- Crash fuzzers and `abstraction-police` get frequent slots; simplifier, dup-unifier, and
  the abstraction/flag routines go weekly.
- Hard cap on PRs opened per night, so the queue stays reviewable.

---

## 8. Rollout

**Step 1 — foundation.** P1–P3 and the formal-model builder. (P4 waits for the web
extension.)

**Step 2 — all 11, nightly, from day one.** One scheduler runs the full set in sequence
each night under the §7 budget. The budget and the nightly PR cap are the safety valve —
scope is not reduced; when the budget runs out, remaining routines resume next night where
they left off, on a rotation so no routine starves permanently.

**Watch week 1 closely:** merge rate, false positives, sandbox escapes. Tune prompts and
budgets from that evidence rather than cutting routines.

---

## 9. Decisions (resolved 2026-08-14, Tayler)

1. **Merge policy: review-first week, then auto-merge mechanical.** Week 1 every routine
   opens PRs for review to measure the false-positive rate; then dead-code,
   useless-test-pruner, and flag-inlining flip to fully-gated auto-merge. Behavior-changing
   fixes stay reviewed.
2. **Account: the fleet runs on the non-pipeline account, starting when its weekly window
   rolls over Aug 16.** Foundation built ahead of that on the current session.
3. **PR budget: 3 per night.** Routines that find more carry findings into the next
   night's rotation.
4. **Frontend base branch (P4): still open** — blocks only the Phase 3 web extension.

## 10. Build log

- **2026-08-14 — Step 1 foundation landed.** P1 `harness/sandbox.py` (guard env
  MP_SANDBOX/MP_DRY_RUN/MP_SKIP_SOCIAL/MP_DISABLE_OUTBOUND, sqlite-backup DB copies,
  claude-call budget, `assert_sandbox()`), hard inline guards at the outbound boundaries
  (`send_newsletter`, `social/posting._api_call_with_retry`, five `orchestrator/sync.py`
  entry points — dependency-free by design, harness/ is not in the container). P2
  `/verify` in `harness/gates.py`: `gate_repro_flips` (repro must fail at base_ref and
  pass post-fix, both runs sandboxed via worktree), truth-table formatter,
  `gate_graphify_updated`, `run_verify`, CLI `python3 -m harness.gates verify`. P3
  `layers.toml` (ratchet manifest of today's 116 blessed cross-package imports +
  container/excluded hard rule + deferred allowlist) enforced by
  `python3 -m harness.layers check`. 43 tests: `test_sandbox.py`, `test_verify_gate.py`,
  `test_layers.py`. Next: formal-model builder (§5) + nightly scheduler + first two
  routines (`abstraction-police`, `crash-fuzzer-pipeline`).

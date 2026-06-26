# MindPattern v4 — Specification

> Status: **Draft v1 — awaiting approval**
> Owner: Tayler
> Created: 2026-05-12
> Working location: `mindpattern-v3/V4-SPEC.md` (to be moved to fresh v4 repo on approval)

## Decision log

Every fork resolved before drafting. Re-open a row only by explicit decision; never silently.

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Provider strategy | Dual-provider, swappable per-agent (Claude + DeepSeek, both first-class) | User directive |
| D2 | Memory gatekeeper enforcement | Process-level daemon; SQLite lives behind it; all teams talk over Unix socket | User pick — maximum isolation, can't be bypassed by `sqlite3.connect()` |
| D3 | Gatekeeper logic | Deterministic policy engine (rules-based, no LLM in loop) | User directive — fast, predictable |
| D4 | Team-to-team communication | Shared memory only (`team_outputs` for payloads; `team_executions` / `step_executions` for run state) | Research: cron-driven single-machine; Prefect = escape hatch |
| D5 | Scheduling | Anthropic Routines (primary) + launchd config preserved as fallback | Research preview but only cloud option that uses Max subscription auth |
| D6 | Identity evolution | Versioned + auto-rollback (every evolution = new version row; quality regression auto-reverts) | User pick — auditable, recoverable |
| D7 | Tenancy | Single-user, `user_id` plumbing kept for future-proofing | User pick — honest about today |
| D8 | v3 cohabitation | Fresh repo (`mindpattern-v4`); v3 daily cron runs untouched until cutover | User pick |
| D9 | Subscription leverage | Claude Code headless + Agent SDK (both use Max subscription auth, no separate API credits) | Research: Max $200 plan inventory |
| D10 | Rejected | Claude SDK subagents as the team-comms layer | Research: parent-spawns-child only; subagents can't spawn subagents; locks comms to one provider |
| D11 | Dashboard in v4 | **Dropped entirely.** Daemon read-only fast path (R7) leaves the door open to add a dashboard/MCP/Desktop consumer later without touching team code. | User directive — never uses v3 dashboard |
| D12 | Approval gates | Slack-only (replaces v3 iMessage dependency on macOS Full Disk Access) | Reduces brittle deployment surface |

---

## 1. Objective

Rebuild MindPattern as a modular, extensible multi-agent system whose source of truth is a single SQLite database guarded by a process-level policy daemon. v4 must:

1. **Replace the 1388-line god runner** (`orchestrator/runner.py`) with independently-deployable agent teams that communicate only through gated shared memory.
2. **Make memory access bypass-proof** — no team can `sqlite3.connect()` directly; 5 such bypasses exist in v3 and they break the gatekeeper concept.
3. **Run on dual providers** — every agent declares a provider (`claude` or `deepseek`); the same agent code runs against either. DeepSeek for cheap/tool-heavy work, Claude for synthesis/judgment.
4. **Be extensible** — adding a new team is a directory, a `team.toml`, and a Python module. No runner edits.
5. **Cut operational fragility** — kill the iMessage approval dependency, the dashboard-shells-out-to-CLI hack, hardcoded `"ramsay"` constants, and the three subtly-different Claude dispatch functions.

### Success looks like

- A new agent team can be added in under an hour without modifying the orchestrator.
- Every memory write is logged with `(team, run_id, table, op, policy_decision)`; querying `SELECT * FROM memory_ops WHERE run_id=?` reconstructs what every team did.
- Pipeline runs daily via Anthropic Routines without requiring the Mac to be awake.
- v3 and v4 run in parallel for at least one week with measurable parity on newsletter quality + social engagement before v3 is decommissioned.
- All teams pass `mypy --strict`.

### Non-goals

- Real-time / sub-second processing — this is a daily-cron system, deliberately.
- Microservices, Kubernetes, message brokers — single machine + SQLite is the substrate.
- Multi-tenant SaaS — single-user with `user_id` plumbing only.
- Beating AI-content detectors — orthogonal voice work tracked separately.

---

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.14 (match v3) | No need to also switch runtimes |
| Type checking | `mypy --strict` as a gate | v3 has none; v4 enforces |
| Storage | SQLite (WAL mode), single `memory.db` per user | Already the source of truth; daemon front-ends it |
| Memory daemon | `memory-daemon` (Python, asyncio, Unix socket) | Process isolation; only path into SQLite |
| LLM providers | Claude (via Claude Code CLI + Agent SDK) and DeepSeek (via `deepseek` Python SDK) | D1, D9 |
| Scheduling | Anthropic Routines primary, launchd fallback config in repo | D5 |
| Web/API | FastAPI (match v3 dashboard pattern) | Familiar; only used for dashboard + approval UI |
| Testing | pytest, no network in unit tests, subprocess mocked | v3 convention; tightened |
| Lint/format | `ruff` (lint + format), `mypy --strict` | One tool for both |
| Dependency mgmt | `uv` | Faster than pip; lockfile reproducibility |

---

## 3. Architecture — Teams + Memory + Comms

### Top-level layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ Scheduler (Routines → triggers orchestrator)                        │
└────────┬────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Orchestrator (~150 lines, NOT a god class)                          │
│   Discovers teams from teams/*/team.toml                            │
│   Runs phases via dependency-ordered execution plan                 │
│   Writes team_executions rows; never opens SQLite directly         │
└────────┬────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Agent teams (each is a Python package with a team.toml manifest)    │
│   research/    newsletter/    social-decider/    social-writers/    │
│   learning/    engagement/    identity/          memory-sync/       │
│   [new teams: drop directory, declare manifest, done]               │
└────────┬────────────────────────────────────────────────────────────┘
         │ all I/O via local Unix socket
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Memory Daemon (memory-daemon)                                       │
│   - Owns ALL SQLite connections                                     │
│   - Enforces policy engine on every read + write                    │
│   - Emits memory_ops rows                                         │
│   - Versions identity files; auto-rolls back on quality regression  │
└────────┬────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ data/{user_id}/memory.db  (WAL, single canonical SQLite database)   │
└─────────────────────────────────────────────────────────────────────┘
```

### How teams talk to each other

Per **D4** (research recommendation): teams **do not call each other**. Each team:

1. Receives a `RunContext(run_id, user_id, memory_client, logger)` from the orchestrator.
2. Reads any inputs it needs via `memory_client.get_team_output(run_id, "<team_name>")` or named queries.
3. Writes its `TeamResult` via `memory_client.put_team_output(run_id, my_name, result)`.
4. Returns. The orchestrator schedules the next team.

The orchestrator's dependency graph is declared in `teams/<name>/team.toml`:

```toml
# teams/newsletter/team.toml
name = "newsletter"
phase = 4
depends_on = ["research", "synthesis-trends"]
critical = true
provider = "claude"
model = "opus"
timeout_seconds = 900
```

That's the entire extensibility surface. New team = new directory + manifest + Python module exposing `run(ctx: RunContext) -> TeamResult`. The orchestrator builds the DAG at startup; cycles or missing dependencies fail fast at boot, not at runtime.

### Tables — two tiers

v4's tables split cleanly into **Tier 2 (instance / observability)** — what happened during a run — and **Tier 3 (data / domain)** — what the system produced. This mirrors a workflow engine's `WorkflowInstance` / `WorkflowInstanceStep` (instance) vs the domain entities the steps operate on.

#### Tier 2 — Instance tables (7)

Every row here is observability data. Parent → child by FK.

| Table | One row per | Key columns |
|---|---|---|
| `runs` | A full pipeline execution | `run_id, user_id, trigger, started_at, finished_at, status, error` |
| `team_executions` | A team running within a run | `team_exec_id, run_id→runs, team_name, phase, started_at, finished_at, status, error, duration_ms` |
| `step_executions` | A step running within a team | `step_exec_id, team_exec_id→team_executions, step_name, started_at, finished_at, status, retries, error` |
| `llm_calls` | A round-trip to Claude or DeepSeek | `llm_call_id, step_exec_id→step_executions, provider, model, input_tokens, output_tokens, cached_tokens, latency_ms, cost_usd, prompt_hash, response_hash, status` |
| `tool_calls` | A tool invocation by an LLM | `tool_call_id, llm_call_id→llm_calls, tool_name, input_json, output_json, status, latency_ms` |
| `memory_ops` | A read/write through the gatekeeper | `memory_op_id, step_exec_id→step_executions, team_name, op, target_table, policy_decision, payload_hash, ts` |
| `policy_violations` | A rejected write | `violation_id, memory_op_id→memory_ops, rule_id, payload_hash, ts` |

This split is non-negotiable. Without `step_executions`, you can't tell which step inside a failing team broke. Without `llm_calls` / `tool_calls`, you can't tell which Claude call burned 50k tokens. v3 has these scattered across `traces.db` (14 tables); v4 consolidates them with explicit FKs.

#### Tier 3 — Domain tables (12)

The "datatypes" the system collects.

| Table | Produced by | Consumed by |
|---|---|---|
| `team_outputs` | every team | downstream teams (sole inter-team channel) |
| `sources` | research (fetch) | research (extract), engagement |
| `findings` | research | newsletter, social-decider, learning |
| `trends` | trend_scan | research, newsletter |
| `newsletters` | newsletter | social-decider, deliver |
| `social_posts` | social-writers | social-poster, signal collector |
| `engagement_replies` | engagement | user (via Slack approval) |
| `signals` | signal collectors | learning |
| `entity_memories` | learning | research, newsletter (context) |
| `patterns` | learning | every team (context) |
| `identity_versions` | identity (EVOLVE phase, D6) | every team (context) |
| `failures` | every team (on error) | learning (next run) |

Each Tier 3 table gets a Pydantic model in `memory_daemon/schemas/` and a DAO module in `memory_client/`. Full DDL + Pydantic for every table is written in Phase A step 1 of the build plan; this section names them, the build phase defines their columns.

---

## 4. Memory Gatekeeper Contract

The daemon is the single point of access to `memory.db`. **No exceptions.** If a team needs a query the daemon doesn't expose, the answer is to add a method to the daemon — not to bypass it.

### Why daemon over in-process library

Honestly considered. An in-process library + lint rule banning `import sqlite3` is simpler operationally and almost as good. Daemon wins on four grounds:

1. **Unified audit log** — pipeline, Slack bot, future MCP/dashboard all write to one `memory_ops` table. Library-per-process fragments this.
2. **Policy hot-swap** — new rules don't require redeploying every consumer.
3. **Free enforcement for new teams** — the stated extensibility priority: drop in a new team, get policy gates without opt-in.
4. **Concurrent writers** — Slack bot writes feedback while pipeline writes findings. Single enforcement point.

Cost: one more process to babysit. The operational rules below (R1–R8) make daemon-down survivable; if we can't meet them, flip to the library approach.

### Daemon operational rules (R1–R8)

| # | Rule | Implementation |
|---|---|---|
| R1 | Auto-restart on crash | launchd `KeepAlive` (macOS) / `Restart=always` (Linux), 5s backoff |
| R2 | Startup contract | Orchestrator runs `mindpattern daemon health-check` before every run; refuses to start if unhealthy |
| R3 | Crash-safe | SQLite WAL, checkpoint every 60s, daemon holds no uncommitted state >100ms |
| R4 | Graceful local journal | Critical writes (`team_outputs`, `findings`) fail loud if daemon is down. Non-critical (`memory_ops`, `team_executions`, `step_executions`) buffer to a local journal file and drain on reconnect |
| R5 | Foreground debug mode | `mindpattern daemon start --foreground` runs in terminal for live crash inspection |
| R6 | Single-binary surface | Daemon is same Python package as orchestrator; started as a subprocess; not a separate codebase |
| R7 | Read-only fast path | Separate connection pool for read-only queries; bypasses heavy policy engine (deny-list for sensitive tables only) so Slack tail latency stays low |
| R8 | Idempotent restart | Daemon clears in-flight transactions on boot; clients send `client_request_id`; gatekeeper rejects duplicates within 60s |

### Protocol

- Unix socket at `/tmp/mindpattern-{user_id}.sock`
- Length-prefixed JSON frames (no HTTP overhead)
- Methods: `get`, `put`, `query` (named queries only — no raw SQL across the wire), `version`, `audit`, `health`
- Auth: Unix socket permission bits + a `MEMORY_TOKEN` env var checked on connect
- All clients carry `client_request_id` (UUID) for R8 dedup

### Policy engine (deterministic only — D3)

Rules live in `src/mindpattern/policies/memory/*.yaml`. Each rule is a pure function. Every read and write runs the rule chain. Adding a new rule is one YAML file + a registration line. No runtime LLM calls.

```yaml
# Example: policies/memory/banned_content.yaml
rule: banned-content-hard
applies_to: [findings, social_posts, newsletter_drafts]
op: write
checks:
  - field_does_not_contain: { fields: [body, content, title], values: ["Synchrony Bank"] }
action_on_fail: reject_and_log
```

```yaml
# Example: policies/memory/voice_tics.yaml
rule: voice-tic-blacklist
applies_to: [social_posts, newsletter_drafts]
op: write
checks:
  - phrase_blacklist: ["I keep coming back to", "I use Claude every day"]  # last loaded from voice.md
action_on_fail: reject_and_retry      # signals writer to regenerate
```

### Initial rule set, organized by class

Eight classes; replaces v1's flat list of 7. Lock these in before M1 starts.

| Class | Rule | Action | Notes |
|---|---|---|---|
| **Identity & ownership** | Table-level ACL per `team.toml` (`writes = [...]`) | `reject_and_log` | Out-of-scope writes blocked at the gate |
| | Identity files (soul/user/voice) writable only via `identity_versions` path, only by `identity` team | `reject_and_log` | See §6 |
| | `decisions`, `memory_ops`, `team_executions`, `step_executions` are append-only — no UPDATE/DELETE through gatekeeper | `reject_and_log` | Audit invariant (the `finished_at` / `status` updates use append-on-finalize pattern) |
| **Content safety** | Banned terms: "Synchrony Bank" (employer) on every text field | `reject_and_log` | Hard ban, no retry |
| | Voice-tic blacklist (sourced from `voice.md`): "I keep coming back to" etc. | `reject_and_retry` | Signals writer to regenerate |
| | "Claude every day" qualifier: rejected unless "personal projects" appears in same field | `reject_and_retry` | Writer regenerates |
| | PII regex redaction: SSN, email, phone on `findings`, `social_posts` | `redact_and_continue` | Silent fix, logged |
| **Schema integrity** | Pydantic model validation per table | `reject_and_log` | Schemas live in `memory_daemon/schemas/` |
| | FK integrity: `run_id`, `user_id`, `source_id` must exist | `reject_and_log` | Foreign keys not enforced by SQLite alone |
| | Field size caps (body ≤ 200KB, title ≤ 500 chars, etc.) | `reject_and_log` | Catch runaway LLM output |
| **Quality gates** | Newsletter `body` ≥ 800 chars | `reject_and_log` | Triggers retry at team layer |
| | Findings require `source_url` OR `synthesis_origin` (not both null) | `reject_and_log` | Softened from v1 — synthesis findings are legit |
| | Social posts ≤ platform char limit (Bluesky 300, LinkedIn 3000) | `reject_and_log` | Per-table override |
| **Resource limits** | Max writes per (team, table, run) — default 1000 | `reject_and_log` | Catch infinite loops |
| | Per-team token budget per run (declared in `team.toml`) | `reject_and_log` at provider boundary | Provider layer enforces |
| | Max external API calls per team per run | `reject_and_log` at provider boundary | Cost cap |
| **Voice & brand** | Banned phrase set hot-loaded from `voice.md` at daemon start | `reject_and_retry` | Adding a phrase = edit voice.md, restart daemon |
| | Required-disclaimer rules (extensible — "personal projects" is rule #1) | `reject_and_retry` | Declared in `policies/memory/disclaimers.yaml` |
| **Audit invariants** | Timestamp sanity: no future `created_at`, no pre-2020 | `reject_and_log` | Clock-skew bugs caught at the gate |
| | Every write emits a `memory_ops` row before returning | enforced by daemon | Non-negotiable |
| **Dedup & idempotency** | Findings deduped by URL hash within 24h window | `reject_silently` | Prevent re-storing same source |
| | Write requests deduped by `client_request_id` within 60s | `reject_silently` | R8 retry-safe |

### Action codes

- `reject_and_log` — write rejected, row in `policy_violations`, error returned to client
- `reject_and_retry` — write rejected, error tagged `RETRYABLE` so the team layer can regenerate (e.g., LLM rewrites)
- `redact_and_continue` — modify the payload, write the redacted version, log the modification
- `reject_silently` — write dropped, no error (dedup case), counted in metrics

---

## 5. Provider Abstraction (D1)

Single interface, two implementations:

```python
# providers/base.py
class LLMProvider(Protocol):
    async def complete(self, *,
        system: str,
        messages: list[Message],
        tools: list[Tool] | None = None,
        max_tokens: int = 4096,
        thinking: bool = False,
    ) -> Completion: ...

# providers/claude_code.py — uses `claude` CLI in headless mode (Max subscription auth)
# providers/claude_sdk.py — uses Claude Agent SDK (also Max subscription auth)
# providers/deepseek.py — uses DeepSeek HTTP API + API key
```

Teams never import a provider directly. They request one via:

```python
ctx.provider("synthesis-writer").complete(system=..., messages=...)
```

The orchestrator resolves the provider from `team.toml`'s `provider` + `model` fields. Per-team override at runtime is allowed for A/B testing.

### Headless Claude rules

- One subprocess pattern only (replaces v3's three subtly-different functions).
- `Popen` with explicit process-group + manual kill on timeout (fixes v3's grandchild-survives-timeout bug).
- All Claude Code prompts go through `prompts/` directory; never inlined.
- Hook into Claude Code session-transcript files to capture full traces for the gatekeeper's `memory_ops` log.

---

## 6. Identity Versioning (D6)

Soul/user/voice files are **read-only at runtime**. They live conceptually in SQLite, are materialized to disk at session start, and never edited in place.

| Step | What happens |
|---|---|
| 1 | EVOLVE phase generates a proposed diff |
| 2 | Daemon writes new row to `identity_versions` with `active=false` |
| 3 | Daemon marks new version `active=true`, old row `active=false` |
| 4 | Next run starts with new version |
| 5 | If that run's `run_quality.score < (prev_run.score - threshold)`, daemon auto-rolls back: reactivates previous version, logs `auto_rollback` event |
| 6 | Manual rollback: `mindpattern identity rollback --to-version N` |

No git in this path. Identity history lives in SQLite where the daemon owns it. `decisions.md`-equivalent becomes a `decisions` table.

---

## 7. Extensibility Model

A new agent team requires exactly this:

```
teams/my-new-team/
├── team.toml           # name, phase, depends_on, provider, model, reads, writes
├── __init__.py         # exports run(ctx: RunContext) -> TeamResult
├── prompts/            # prompt templates (if Claude-based)
└── tests/test_*.py     # at least one test
```

On boot, the orchestrator:

1. Discovers `teams/*/team.toml`
2. Validates each manifest against `team.schema.json`
3. Builds the DAG; fails fast on cycles, missing dependencies, or unknown providers
4. Validates declared `reads`/`writes` against gatekeeper-known tables
5. Registers the team

Manifest schema enforced by `pydantic`. The orchestrator stays small (~150 lines) because the manifests carry the configuration. **Adding research vertical #14 should be the same effort as adding the first one.**

---

## 8. Commands

```
# Run a pipeline
mindpattern run [--user ramsay] [--resume <phase>] [--dry-run]

# Run a single team
mindpattern team run <team_name> [--run-id <id>]

# Memory daemon
mindpattern daemon start | stop | status
mindpattern daemon audit --since 1h
mindpattern daemon policies test <rule-id> <payload.json>

# Identity
mindpattern identity show
mindpattern identity rollback --to-version N
mindpattern identity diff --from N --to M

# Provider testing
mindpattern provider test claude
mindpattern provider test deepseek

# Dev
uv sync                              # install
mypy --strict src/                   # type-check gate
ruff check src/ && ruff format src/  # lint + format
pytest -x -q                         # tests
mindpattern dev seed                 # seed dev DB
```

---

## 9. Project Structure (proposed)

```
mindpattern-v4/
├── SPEC.md
├── README.md
├── pyproject.toml          # uv + ruff + mypy config
├── src/mindpattern/
│   ├── orchestrator/       # ~150 lines, NOT a god class
│   │   ├── runner.py       # discovers teams, builds DAG, executes
│   │   └── manifest.py     # team.toml parsing + validation
│   ├── memory_daemon/      # the gatekeeper process
│   │   ├── server.py       # asyncio Unix socket server
│   │   ├── policies.py     # rule engine
│   │   ├── schemas/        # pydantic models per table
│   │   ├── audit.py        # memory_ops logging
│   │   └── identity.py     # identity versioning + auto-rollback
│   ├── memory_client/      # what teams import; NEVER imports sqlite3
│   ├── providers/          # claude_code.py, claude_sdk.py, deepseek.py
│   ├── policies/           # YAML rule definitions
│   └── teams/              # one directory per team
│       ├── research/
│       ├── newsletter/
│       ├── social-decider/
│       ├── social-writers/
│       ├── learning/
│       ├── engagement/
│       ├── identity/
│       └── memory-sync/
├── tests/
│   ├── unit/               # per module, mocked
│   ├── integration/        # daemon + memory_client roundtrip
│   └── e2e/                # full pipeline against seeded DB
├── scripts/
│   ├── migrate-from-v3.py  # one-shot SQLite migration
│   └── launchd-fallback.plist
└── docs/
    ├── adr/                # ADRs for D1-D10 + future
    └── architecture.md
```

---

## 10. Code Style

```python
# Every team module looks like this. No exceptions.
from mindpattern.memory_client import MemoryClient
from mindpattern.types import RunContext, TeamResult

async def run(ctx: RunContext) -> TeamResult:
    research = await ctx.memory.get_team_output(ctx.run_id, "research")
    if not research.findings:
        return TeamResult.skipped("no findings")

    response = await ctx.provider().complete(
        system=ctx.load_prompt("system.md"),
        messages=[{"role": "user", "content": research.synthesize()}],
    )

    await ctx.memory.put_team_output(
        ctx.run_id,
        team="newsletter",
        result={"draft": response.text, "model": response.model},
    )
    return TeamResult.ok()
```

Conventions:

- `str | None`, never `Optional[str]`
- `logging.getLogger(__name__)` only; no print
- Type hints required everywhere (`mypy --strict`)
- Async-first; sync only at process boundaries
- No `sqlite3` import outside `memory_daemon/`
- No `subprocess` import outside `providers/claude_code.py`
- One-line docstrings only when the name isn't self-explanatory
- Imports: stdlib → third-party → local

---

## 11. Testing Strategy

| Level | Location | What it covers | Network? |
|---|---|---|---|
| Unit | `tests/unit/<module>/` | Pure functions, policy rules, manifest validation | No |
| Integration | `tests/integration/` | Daemon + memory_client roundtrip; team `run()` with fake daemon | No |
| E2E | `tests/e2e/` | Full pipeline against seeded DB, providers stubbed | No |
| Smoke | `tests/smoke/` (manual) | Real Claude + DeepSeek calls; gated behind `RUN_SMOKE=1` | Yes |

Rules:

- Every new team ships with at least one integration test.
- Every new policy rule ships with both a passing case and a failing case.
- CI: `mypy --strict` + `ruff check` + `pytest -x -q` on every PR. No green = no merge.
- No mocks of the database in integration tests; use a real ephemeral SQLite + real daemon subprocess.

---

## 12. Boundaries

**Always do**
- Run `mypy --strict`, `ruff`, and `pytest -x -q` before commits
- Add a test with every new team or policy rule
- Write through `memory_client`; the daemon owns SQLite
- Use `RunContext` for all I/O; never reach for globals
- Surface assumptions in the spec before writing code

**Ask first**
- Schema changes to any Tier 2 instance table (`runs`, `team_executions`, `step_executions`, `llm_calls`, `tool_calls`, `memory_ops`, `policy_violations`) or to `team_outputs` / `identity_versions`
- New external API integration (cost / lock-in implications)
- Adding a new provider (changes the dual-provider invariant)
- Changing the orchestrator core
- Migrating v3 → v4 cutover timing

**Never do**
- `import sqlite3` outside `src/mindpattern/memory_daemon/`
- `subprocess` outside `src/mindpattern/providers/claude_code.py`
- Hardcode user IDs (always read from config)
- Mention "Synchrony Bank" in any agent prompt, training data, or fixture
- Disable a policy rule to make a test pass
- Commit `.env`, `keys/`, `.claude/`, or any `*.db`

---

## 13. Success Criteria

v4 ships when **all** are true:

- [ ] All 8 v3 teams ported and passing parity tests against v3 outputs (newsletter quality score within ±5% of v3 baseline)
- [ ] Adding a new dummy team takes < 60 minutes (timed exercise)
- [ ] Zero `sqlite3.connect()` calls anywhere outside `memory_daemon/` (CI grep gate)
- [ ] `mypy --strict src/` passes with no `# type: ignore` outside vendored code
- [ ] `pytest -x -q` passes with zero flakes across 10 consecutive runs
- [ ] Pipeline runs via Anthropic Routines for 7 consecutive days without manual intervention
- [ ] Memory daemon survives a kill -9 mid-write without DB corruption (chaos test)
- [ ] Identity auto-rollback triggers correctly in a planted regression scenario
- [ ] All 7 initial policy rules from §4 reject the bad case in tests
- [ ] v3 and v4 run in parallel for at least one week with outputs reviewed by Tayler

---

## 14. Migration plan from v3

| Phase | Action | Deliverable | Gate |
|---|---|---|---|
| M0 | Init `mindpattern-v4/` repo, `uv`, `mypy`, `ruff`, CI skeleton | Empty green CI | CI green |
| M1 | Build memory daemon + memory_client + 3 policy rules | Daemon serves a real `get`/`put`; banned-content rule rejects in test | Integration tests pass |
| M2 | Migrate v3 schema → v4; one-shot `scripts/migrate-from-v3.py` | New `memory.db` populated from a v3 snapshot | Spot-check rows |
| M3 | Build provider abstraction; port both Claude (Code + SDK) and DeepSeek | `mindpattern provider test claude\|deepseek` both pass | Manual verify |
| M4 | Port `research` team (the biggest, 13 sub-agents) | Output matches v3 on 3 seed topics | Parity test |
| M5 | Port `newsletter`, `synthesis`, `learning` teams | Daily newsletter generates end-to-end | Manual review |
| M6 | Port `social-decider`, `social-writers`, `engagement` | Bluesky + LinkedIn posts generate (no auto-send yet) | Manual review |
| M7 | Port `identity` with versioning + auto-rollback | Planted regression triggers rollback | Chaos test |
| M8 | Port `memory-sync`; replace iMessage gates with Slack-only approval | Daily sync to Fly.io completes | Manual verify |
| M9 | Wire Anthropic Routines trigger; verify launchd fallback config | 7 consecutive Routines-driven runs | Production parity |
| M10 | Parallel run v3 + v4 for 1 week | Side-by-side diff report | Manual sign-off |
| M11 | Cutover: disable v3 launchd; v4 becomes primary | v3 archived | — |

**Dashboard (v3's `mindpattern.fly.dev`) is explicitly out of scope.** The daemon's read-only fast path (R7) and named-query API leave the door open for a future dashboard, MCP server, or Claude Desktop integration to be added as a separate consumer process without changing any team code.

Each phase ends with a single `mindpattern` command that proves it works. No phase is "done" until that command returns 0.

---

## 15. Open questions

These don't block drafting but need answers before the corresponding migration phase.

| Q | Question | Blocks |
|---|---|---|
| Q1 | Repo location: `~/Projects/mindpattern-v4/` or somewhere else? | M0 |
| Q2 | DeepSeek model selection per agent — V3, V2.5, or per-task? | M3 |
| Q3 | ~~iMessage approval gate replacement~~ → **Resolved: Slack-only.** | — |
| Q4 | Routines minimum 1-hour interval — does that affect sub-hourly Slack reactions, or do those stay on launchd? | M9 |
| Q5 | ~~v3 dashboard~~ → **Resolved: dropped from v4 entirely.** Daemon R7 + named-query API leave the door open for any future consumer (dashboard, MCP, Desktop). | — |
| Q6 | ~~Knowledge graph (`harness/`)~~ → **Resolved: dropped from v4.** Re-evaluate after M11 if there's a concrete reason to bring it back. | — |
| Q7 | MCP server (`mcp/memory_server.py`) — does v4 need this for Claude Desktop integration? | Optional, after M11 |

---

## 16. What this spec deliberately does NOT do

- **Pick a UI/dashboard direction.** Q5 is a follow-on spec, not part of v4 core.
- **Define a Cowork integration.** Awaiting clarity on what Cowork actually is in 2026.
- **Solve voice quality.** That's the Voice A/B spec (already in this repo). v4 inherits whatever voice work has shipped by cutover.
- **Build a SaaS surface.** D7 keeps the door open but doesn't open it.
- **Replace SQLite with a vector DB or graph DB.** Embedding columns stay where they are.

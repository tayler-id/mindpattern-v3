# SPEC: MindPattern v4

> Status: Draft v1 — awaiting approval
> Owner: Tayler
> Created: 2026-05-09
> Supersedes: nothing (v3 keeps running until v4 reaches parity)

## 1. Objective

Rebuild MindPattern's daily pipeline on proper agentic patterns, **producing the same outputs as v3** (Resend newsletter, Bluesky/LinkedIn posts, engagement, identity evolution, Obsidian mirror, Fly sync), and **add a self-improvement loop that actually works** (replacing the disabled `EVOLVE` phase). The architecture, not the product, is the rewrite.

## 2. Non-goals (v4.0)

These are explicitly **not changing** in v4.0:

- The 12-phase deterministic order (it works, it's the spine)
- Resend as the newsletter delivery pipe
- Bluesky and LinkedIn as the social channels
- The 33 agent skill files' content (upgraded format, same intent)
- The "invisible system" kill switch (writers must never say "I run agents," "my pipeline," "I built this system")
- mindpattern.ai on Fly.io as the public dashboard
- The `MIRROR` phase generating Obsidian files
- The `IDENTITY` phase evolving `soul.md` / `voice.md` / `decisions.md` (untouched by DREAM — see §10)
- Any new product (no Buttondown, no Ghost, no separate blog platform — those are deferred to v4.1+ if at all)

## 3. What v4.0 changes vs v3

| v3 today | v4 — proper pattern |
|---|---|
| `orchestrator/runner.py`: 1,388 lines, hand-coded `_phase_*` methods with checkpoint/traces/monitor/regression-check inlined into each phase | `v4/loop.py`: `AgentLoop` (~120 lines) with typed `pre_loop_hooks` + `post_tool_hooks`. Cross-cutting concerns become hooks, registered once. Phases become handlers, not god-methods. |
| `orchestrator/agents.py`: subprocess `claude -p` per call — opaque, no streaming, no tool-loop visibility, fresh context every time | Claude Agent SDK with one Lead Agent + on-demand subagents (deer-flow shape). Real tool-use loop. SDK Sessions persist within a phase. |
| 33 markdown agent files with ad-hoc structure | Open-spec `SKILL.md` format (Anthropic + OpenAI standard): `allowed-tools`, `paths:`, `disable-model-invocation`, `references/` subdirs, pushy descriptions. Same content, portable structure. |
| Agents barely read from KG, memory.db, identity files at runtime | `Vault` MCP server (4 tools: `recall / remember / relate / forget`) over `sqlite-vec` extending existing `memory.db`. Every agent grounds in accumulated knowledge. |
| State is a mutable god-object on `ResearchPipeline` (`self.trends`, `self.agent_results`, `self.newsletter_text`, …) | Pydantic typed `RunState` passed phase-to-phase. Reducers, not assignment. Inspectable, validated, restorable. |
| `traces.db` schema is project-shaped; observability is hand-rolled per phase | Reshape `traces.db` to OpenTelemetry GenAI span model. Add `pydantic-logfire`'s one-line `instrument_claude_agent_sdk()` for visibility. Personal tier free (10M spans/mo). |
| No context management — every `claude -p` call gets a fresh context | Three-tier compaction (microcompact + auto-compact + manual) for any long-running agent loop. |
| `EVOLVE` disabled because audit found zero improvement | Replaced by `DREAM` (§9): risk-tiered, anchor-set-gated, pairwise-judged, regret-monitored. Forbidden from touching identity files or its own gating. |
| Sandbox/policy is open-coded per phase | `policies/engine.py` drives a unified gating contract; SDK `permissionDecision` hook reads it. |
| Zero tests on the orchestrator core | Every pattern below has a corresponding `tests/v4/test_*.py`. Binary success criteria in §11. |

## 4. Architecture

### 4.1 The `AgentLoop`

One class. Drives every Claude Agent SDK call in v4.

```python
class AgentLoop:
    def __init__(
        self,
        client: ClaudeAgentClient,
        skill_registry: SkillRegistry,
        vault: VaultClient,
        pre_loop_hooks: list[PreLoopHook] = (),
        post_tool_hooks: list[PostToolHook] = (),
        max_iterations: int = 100,
    ): ...

    def run(self, prompt: str, *, agent_type: str = "lead") -> RunResult: ...
```

- **`PreLoopHook = Callable[[AgentLoop, Messages], Optional[Messages]]`** — runs before each LLM call. Returning a list replaces messages. Used for: context compaction, event-source drain (Slack, file watchers, scheduled triggers).
- **`PostToolHook = Callable[[AgentLoop, Messages], Optional[list[ContentBlock]]]`** — runs after tool execution, before `tool_result` is appended. Returning blocks extends the result. Used for: trace logging, regression detection, policy validation.
- Two exit paths: model returns `stop_reason != "tool_use"`, OR iteration count hits `max_iterations`. Caller inspects `loop.iteration` to distinguish.
- Loop file is **never** edited by phase code. Stages compose by registering hooks and tools.

### 4.2 Lead Agent + on-demand subagents (deer-flow shape)

- One Lead Agent per phase (constructed by the phase handler). Lead has the full Vault toolset + skill library.
- Subagents spawned via the SDK `task` primitive. Two presets: `Explore` (read-only Vault + WebSearch + WebFetch) and `general-purpose` (full toolset minus `task`).
- Subagents inherit microcompact and trace hooks. They get their own iteration budget (default 30).
- No `TeammateAgent`-style hand-rolled second loop. Subagents reuse `AgentLoop`.

### 4.3 Skills (open-spec `SKILL.md`)

Every agent skill in `agents/` and `verticals/ai-tech/agents/` migrates to:

```yaml
---
name: synthesis-writer
description: Write the daily newsletter from selected stories. Use when synthesizing today's findings into the morning email.
allowed-tools: vault_recall vault_remember Read
disable-model-invocation: false
paths: []
---

[skill body — instructions, voice anchors, output schema]
```

- Body kept under ~500 lines; long context goes in `agents/<skill>/references/*.md`.
- Skills loaded on demand via SkillRegistry. Descriptions go in the Lead Agent's system prompt for routing; bodies load when invoked.
- `disable-model-invocation: true` for any skill with side effects (e.g. `deliver-newsletter`, `post-to-bluesky`).
- Eval pinning per Anthropic's `skill-creator`: each skill carries optional `evals/*.json`. CI re-runs them on edit.

### 4.4 The `Vault` MCP server

One MCP server. Four tools. Stateless. Server Card published.

```
vault_recall(query: str, kind: str | None = None, since: str | None = None,
             format: "concise" | "detailed" = "concise") -> RecallResult
vault_remember(content: str, kind: str, source: str, refs: list[str] = []) -> str
vault_relate(a: str, b: str, kind: str) -> None
vault_forget(id: str) -> None
```

- `RecallResult` is a tagged union: `{type: "graph_node" | "sql_row" | "markdown_chunk" | "playbook_entry", ...}`.
- Backed by `memory.db` extended with `sqlite-vec` (no new infra). Indexes: chunks of `harness/knowledge/`, identity files, `interactions`, `decisions`, `playbooks/`, per-agent traces.
- Every record typed at write: `fact | decision | preference | event | observation | playbook`. Provenance + `created_at` + `valid_until` (bi-temporal).
- Hybrid retrieve: 0.7 vector + 0.3 BM25, MMR diversity, source citation in every result.
- Truncate at the MCP boundary, never at the model boundary. Large results spill to `vault://artifacts/{id}` with a preview + `read_artifact(ref, range)` follow-up.

### 4.5 Pydantic typed state

```python
class RunState(BaseModel):
    run_id: str
    user_id: str
    date_str: str
    current_phase: Phase
    user_config: UserConfig
    preflight: PreflightData | None = None
    trends: list[Trend] = []
    findings: list[Finding] = []
    newsletter: NewsletterDraft | None = None
    newsletter_eval: dict | None = None
    social_result: SocialResult | None = None
    identity_result: IdentityResult | None = None
    dream_proposals: list[Proposal] = []
```

- Phase handlers receive `RunState`, return `RunState` (immutable update via `state.model_copy(update={...})`).
- Persisted to `traces.db` after each phase (run-id ledger). Resume reconstructs from JSON.

### 4.6 Observability

- Reshape `traces.db` to the OpenTelemetry GenAI span model: `run`, `span(parent_span_id, kind, name, model, tokens, cost, attrs)`, `tool_call`, `message`, `score`, `artifact`, `feedback`. SQL aggregates + future OTLP export.
- `logfire.instrument_claude_agent_sdk()` — one line, every SDK call traced. Personal tier (10M spans/mo, 1 seat) is sufficient.
- Hooks emit to both `traces.db` (system of record) and Logfire (UI).

### 4.7 Triggers (always-on optional, v4.0 stays cron)

v4.0 keeps launchd 7am cron. `v4/triggers/` defines the contract for an `events` SQLite table that future versions will drain via a pre-loop hook (Slack, file changes, schedule, TUI input). Wired but unused in v4.0 — proves the surface, doesn't ship the daemon.

## 5. Module layout

```
v4/
  SPEC.md                      this document
  loop.py                      AgentLoop + hook types
  state.py                     Pydantic RunState + Phase enum
  skills/
    registry.py                load SKILL.md, expose descriptions + bodies
    types.py                   SkillFrontmatter (pydantic)
  vault/
    server.py                  MCP server entry point
    schema.py                  RecallResult tagged union
    indexer.py                 (re)build sqlite-vec from KG/identity/SQL
    consolidator.py            nightly dedup + invalidate-contradicted
  agents/
    lead.py                    Lead Agent factory
    subagents.py               Explore / general-purpose presets
  phases/
    init.py
    trend_scan.py
    research.py
    synthesis.py
    deliver.py
    learn.py
    social.py
    engagement.py
    identity.py
    mirror.py
    sync.py
    dream.py                   NEW
  hooks/
    compact.py                 microcompact + auto-compact
    trace.py                   span emission + Logfire
    regression.py              prompt regression check
    policy.py                  PolicyEngine gating via SDK permissionDecision
    event_drain.py             stub for v4.1 always-on triggers
  observability/
    schema.sql                 traces.db OTel GenAI shape
    logfire.py                 instrumentation entrypoint
  improve/
    proposal.py                Proposal pydantic model
    anchor.py                  golden anchor set load + run
    judge.py                   pairwise LLM judge with order-flip
    regret.py                  7-day rolling regret rate from user_feedback + edits
    router.py                  three-tier risk router
    revert.py                  auto-revert on regret spike
  triggers/                    (v4.1 surface, contract only in v4.0)
    contract.md
    events_schema.sql
  cli.py                       v4 entrypoint (parity with bin/run-pipeline)

tests/v4/
  test_loop.py
  test_skills.py
  test_vault.py
  test_state.py
  test_hooks.py
  test_phases_<each>.py
  test_dream.py
  test_anchor.py
  test_judge.py
  test_regret.py

agents/                        (existing, migrated in place)
  *.md  — frontmatter upgraded, body unchanged
```

## 6. Public API contract

The following are stable. Renames or signature changes go through the "Ask first" gate (§10).

```python
# Phase entry point — every phase implements this
def run_phase(state: RunState, deps: PhaseDeps) -> RunState: ...

# Hook contracts
PreLoopHook  = Callable[["AgentLoop", Messages], Optional[Messages]]
PostToolHook = Callable[["AgentLoop", Messages], Optional[list[ContentBlock]]]

# Skill loading
class SkillRegistry:
    def descriptions(self) -> dict[str, str]: ...
    def load(self, name: str) -> SkillBody: ...
    def evals(self, name: str) -> list[EvalCase]: ...

# Vault client (MCP wrapper)
class VaultClient:
    def recall(self, query: str, *, kind: str | None = None,
               since: str | None = None,
               format: Literal["concise","detailed"] = "concise") -> RecallResult: ...
    def remember(self, content: str, kind: str, source: str,
                 refs: list[str] = ()) -> str: ...
    def relate(self, a: str, b: str, kind: str) -> None: ...
    def forget(self, id: str) -> None: ...

# DREAM
class Proposal(BaseModel):
    target_file: str
    diff: str  # unified diff
    risk_tier: Literal["auto", "approve", "forbidden"]
    evidence_run_ids: list[str]
    anchor_results: AnchorResults
    pairwise_winrate: float | None
    rationale: str
```

## 7. Phases on the new architecture

All 11 active phases (EVOLVE stays disabled; DREAM is new):

| Phase | Handler | LLM use | Hooks attached |
|---|---|---|---|
| `INIT` | `phases/init.py` | none | trace |
| `TREND_SCAN` | `phases/trend_scan.py` | none (deterministic) | trace |
| `RESEARCH` | `phases/research.py` | Lead Agent + 13 subagents (parallel via SDK Managed Agents primitive when stable; ThreadPoolExecutor today) | trace, compact, policy, regression |
| `SYNTHESIS` | `phases/synthesis.py` | Lead Agent (2-pass: select → write) | trace, compact, policy |
| `DELIVER` | `phases/deliver.py` | none (Resend HTTP) | trace |
| `LEARN` | `phases/learn.py` | one Sonnet call (learnings.md regenerate) | trace, compact |
| `SOCIAL` | `phases/social.py` | full SocialPipeline as Lead Agent + subagents (eic, expeditor, art-director, illustrator, writers, critics, humanizer) | trace, compact, policy |
| `ENGAGEMENT` | `phases/engagement.py` | Lead Agent (find conversations → draft → approve → post) | trace, compact, policy |
| `IDENTITY` | `phases/identity.py` | one Sonnet call (proposes diff to identity files; YOU still merge — DREAM cannot touch these) | trace, compact |
| `MIRROR` | `phases/mirror.py` | none (SQLite → Obsidian markdown) | trace |
| `SYNC` | `phases/sync.py` | none (Fly upload) | trace |
| `DREAM` | `phases/dream.py` | Lead Agent + Explore subagents | trace, compact, policy |

`policies/engine.py` validates outputs after each phase via the `policy` post-tool hook. Same contract as v3, refactored to read from a single JSON schema.

## 8. The kill switch (preserved)

`hooks/policy.py` enforces v3's social writer kill list as an SDK `permissionDecision` denial:

> Writers MUST NEVER produce text containing: "I run agents", "I run 12 agents", "my agents", "agents every morning", "my pipeline", "cron job", "launchd", "automation", "I build AI", "I built this system", "the system I built", or any reference to automated infrastructure, agent pipelines, or AI systems Tayler operates. The reader must never know an automated system exists.

Detection: regex pre-check + a humanizer post-check. Violation → `permissionDecision: deny` with a corrective instruction. Three consecutive violations → fail the social phase, send Slack alert. (Same behavior as v3, formalized.)

## 9. Self-improvement: `DREAM`

Replaces the disabled `EVOLVE`. Anthropic-Dreaming-shaped: nightly review → plain-text playbooks → structured proposals → risk-tiered apply.

### 9.1 Inputs

- `traces.db` for the day (run + spans + tool_calls + scores)
- `user_feedback` table (Resend webhook signal — accept/reject/edit text)
- `run_quality` (NewsletterEvaluator output) + 7-day rolling delta
- `prompt_tracker` regressions
- Per-agent traces (`data/ramsay/mindpattern/agents/{agent}/{date}.md`)
- Cross-pipeline signals (`memory.signals`)
- Distribution-shift report (today's source/topic mix vs 30-day baseline)

### 9.2 Outputs

A list of `Proposal` records, each with:
- `target_file`, unified `diff`
- `risk_tier`: `"auto"`, `"approve"`, or `"forbidden"` (forbidden are dropped immediately, with telemetry)
- `evidence_run_ids`: pointers to spans that motivated the change
- `anchor_results`: pass/fail per anchor input
- `pairwise_winrate`: candidate vs baseline on 10 today inputs (order-flipped)
- `rationale`: short prose, stored alongside the proposal

### 9.3 Risk tiers (config in `policies/dream.json`)

**AUTO-APPLY** (no human in loop):
- New `playbook` entries (additive, never destructive) under `data/ramsay/mindpattern/playbooks/`
- New entries to `voice.md`'s `banned_phrases` list (never removals)
- New voice exemplars for the writers' RAG corpus
- Bounded numeric tweaks (±20% of current value) to non-identity numeric fields in `policies/research.json` (e.g. trend score thresholds)
- New entries to `agents/references/*.md` (additive)

**APPROVE** (queued to morning email; later TUI in v4.1):
- Edits to skill prompt bodies (`agents/*.md`, `verticals/ai-tech/agents/*.md`)
- Edits to skill frontmatter (`description`, `allowed-tools`)
- Voice.md changes other than additive banned-phrases
- Source weight rebalances in trend detector
- Routing/dispatch policy changes
- Removals of any kind (banned phrases, exemplars, sources)

**FORBIDDEN** (DREAM may not propose; if it does, dropped + alerted):
- `data/ramsay/mindpattern/soul.md`
- `data/ramsay/mindpattern/user.md`
- `data/ramsay/mindpattern/decisions.md`
- `v4/loop.py`, `v4/state.py`, `v4/phases/dream.py` (no self-modifying improver)
- `policies/dream.json` (the gating policy itself)
- `policies/engine.py`, `v4/agents/lead.py`, `v4/agents/subagents.py` (routing)
- The kill-switch list

### 9.4 Gating (every proposal, every tier)

1. **Run against the golden anchor set** (10–20 frozen `(date, findings, voice_state)` triples in `v4/improve/anchors/`). **Any regression on any anchor → reject.** Pinned at v4.0 launch by Tayler; expandable, never auto-modified.
2. **Pairwise judge** (`improve/judge.py`): candidate vs baseline on 10 of today's inputs. LLM judge sees both orderings (PairS pattern). Winrate < 0.55 → reject. Pointwise scoring is forbidden.
3. **For AUTO-APPLY only**: also requires the change to be a member of the AUTO whitelist in `policies/dream.json`.

### 9.5 Regret monitoring + auto-revert

- Every applied change gets a `proposal_id` recorded in the file's git note.
- Regret signal = (count of negative `user_feedback` rows) + (count of social drafts edited by Tayler in the SocialPipeline) per day.
- 7-day rolling regret rate computed each morning. If applied change's 7-day-after rate exceeds (7-day-before rate × 1.3), **auto-revert** + Slack alert + add to `data/ramsay/mindpattern/playbooks/regressions.md`.

### 9.6 What DREAM is allowed to learn (concrete v4.0 list)

- Voice violations observed in user-edited drafts → propose addition to `voice.md` banned phrases (APPROVE)
- Agents producing `<15` findings 5+ days in a row → propose skill-description tweak (APPROVE)
- Sources producing zero findings 7 days → propose source drop (APPROVE)
- Topics with high feedback weight that agents undercover → boost in dispatch context (AUTO, bounded)
- "What worked yesterday" → playbook entry that future SYNTHESIS reads via `vault_recall(query, kind="playbook")` (AUTO)
- Successful synthesis structural patterns → playbook entry (AUTO)
- New voice exemplars from approved drafts → RAG corpus (AUTO)

## 10. Boundaries — Always / Ask first / Never

**Always:**
- Preserve v3 outputs (Resend newsletter, Bluesky/LinkedIn social, engagement, identity, mirror, Fly sync) at parity
- Honor the kill switch on all writer outputs
- Validate every phase output through `policies/engine.py`
- Persist `RunState` to `traces.db` after each phase (resumable)
- Run pre-merge eval on any skill body change (CI)

**Ask first** (open a ticket or surface in morning approval email):
- Adding a new phase to the order
- Renaming any item in §6 public API
- Adding a new top-level dependency
- Adding a new external service
- Changing the SDK provider abstraction (we are Claude-committed in v4.0)

**Never:**
- DREAM modifying `soul.md`, `user.md`, `decisions.md`, the loop, the gating policy, or itself
- Auto-applying any change without anchor + winrate gates
- Pointwise LLM-as-judge scoring as the sole signal
- Skipping the kill-switch check on social/newsletter outputs
- Storing API keys, OAuth tokens, or `social-config.json` in git
- Hardcoded `client.messages.create` outside `v4/agents/`
- Swallowing exceptions inside hooks (every hook logs with traceback)

## 11. Success criteria (binary, gates v4.0 ship)

1. `pytest tests/v4/ -q` green; ≥80% line coverage on `v4/loop.py`, `v4/state.py`, `v4/skills/registry.py`, `v4/vault/`, `v4/improve/`.
2. `python -m v4.cli run --user ramsay --date 2026-MM-DD --dry-run` exits 0 with a deterministic phase trace.
3. End-to-end run on a single user produces: a Resend newsletter (sent), 1+ social posts (Bluesky+LinkedIn), engagement output, identity proposals, Obsidian mirror updated, Fly sync 200.
4. `v4/loop.py` is ≤150 lines and is the **only** file that calls Claude SDK `messages.create` (or its successor).
5. Every phase handler is a function `run_phase(state, deps) -> RunState` — no class state mutated outside the returned `RunState`.
6. Every agent skill in `agents/` and `verticals/ai-tech/agents/` has valid `SKILL.md` frontmatter that round-trips through pydantic; `--lint-skills` exits 0.
7. `Vault` MCP server passes its conformance test: `recall/remember/relate/forget` round-trip a typed record with provenance and bi-temporal stamps.
8. Logfire shows nested spans for one full run: `phase → invoke_agent → execute_tool → chat`, with token + cost attrs.
9. `traces.db` schema matches the OpenTelemetry GenAI shape; an `--export-otlp` flag emits valid OTLP for one run.
10. The kill-switch hook denies a synthetic violation in a unit test; three consecutive denials fail the social phase.
11. DREAM produces ≥1 AUTO-APPLY proposal that passes anchor + winrate gates on a frozen 7-day backtest, and the change appears in git with a `proposal_id` git note.
12. DREAM auto-reverts a synthetically-bad change when regret rate spikes in test (`tests/v4/test_revert.py`).
13. DREAM is provably forbidden from touching the §9.3 forbidden list (a unit test asserts this).
14. The 7-day shadow run (v4 alongside v3, both writing newsletters; only v3's gets sent) shows v4 newsletter quality scores ≥ v3's on the NewsletterEvaluator overall metric, with anchor-set parity.
15. `golden anchor set` exists at `v4/improve/anchors/` with ≥10 frozen inputs, each with reference outputs from v3.

When all 15 are green, v4 takes over: the launchd job switches from `bin/run-pipeline` to `python -m v4.cli run`. v3 stays in repo as `legacy/` for a 30-day rollback window, then archived.

## 12. Migration plan (6 weeks)

Greenfield `v4/` directory. v3 keeps running daily 7am throughout. No flag flip until §11 all green.

| Week | Ship |
|---|---|
| **1 — Foundation** | `v4/loop.py` + `v4/state.py` + hook types + `tests/v4/test_loop.py`. `v4/skills/registry.py` + `--lint-skills`. `v4/vault/` skeleton: schema, MCP server bones, `sqlite-vec` wired into `memory.db`. v4 policy schema in `policies/v4.json`. |
| **2 — Three phases** | Refactor `TREND_SCAN`, `RESEARCH`, `SYNTHESIS` onto Lead Agent + SKILL.md format; SDK replaces `claude -p` subprocess for these three; reshape `traces.db` to OTel GenAI; `logfire.instrument_claude_agent_sdk()`. End-to-end run produces the same newsletter as v3 (compared by hash + diff in test). |
| **3 — Remaining phases** | Refactor `DELIVER/LEARN/SOCIAL/ENGAGEMENT/IDENTITY/MIRROR/SYNC` onto same loop. Pydantic typed state passed phase-to-phase. v4 `cli.py` entrypoint at parity with v3's runner. |
| **4 — Measurement floor** | Pin **golden anchor set** (10–20 frozen inputs from the last 30 days, with v3 outputs as baseline). Build **pairwise judge** (`improve/judge.py`) with order-flipping. Wire **regret signal** from `user_feedback` + social-draft-edit telemetry. Build **auto-revert** with git-note proposal IDs. |
| **5 — DREAM (auto lane)** | `phases/dream.py`: structured proposal generation, three-tier router, AUTO-APPLY path. Forbidden-target unit test. Synthetic-bad-change revert test. First end-to-end DREAM dry run on 7-day backtest. |
| **6 — DREAM (approve lane) + shadow run** | DREAM APPROVE path: morning email digest with proposal + diff + evidence + click-to-approve link. Begin **7-day shadow run** (v4 produces a newsletter alongside v3; only v3's sends; compare quality + anchor-set + voice-fidelity). When all §11 criteria green, flip launchd to v4. |

## 13. Tests required (per `tests/v4/`)

- `test_loop.py` — exit paths, hook ordering, `tool_use_id` echo
- `test_state.py` — model_copy semantics, JSON round-trip
- `test_skills.py` — SKILL.md round-trip, eval pinning
- `test_vault.py` — recall + remember + relate + forget round-trip; bi-temporal correctness; tagged-union output schema
- `test_hooks.py` — compact, trace, regression, policy, kill-switch
- `test_phases_<each>.py` — handler contract, RunState in/out, deterministic on fixture
- `test_dream.py` — proposal generation, risk routing, anchor + winrate gating, forbidden-target refusal
- `test_anchor.py` — anchor regression detection
- `test_judge.py` — order-flip robustness, position-bias check
- `test_regret.py` — 7-day rolling computation, edge cases
- `test_revert.py` — synthetic regression triggers auto-revert with git note

CI (week 2 onward): pytest + skill-lint + traces-shape-validator on every PR.

## 14. Decisions deferred to v4.1+ (in priority order)

1. **TUI** — Textual viewer (opencode-style daemon split). DREAM approval moves from email to in-place diff click.
2. **Always-on triggers** — drain Slack/file-watch/schedule events from the `events` table via `event_drain` hook; APScheduler in same Python process.
3. **Long-form blog assist** — separate from newsletter; agent helps Tayler write blog posts on mindpattern.ai (LONGFORM phase, weekly).
4. **Local Mistral Small 3 + Nomic Embed v1.5** for nervous-system calls (classify, dedup, embed).
5. **Mistral La Plateforme (EU/GDPR/ZDR)** for cheap synthesis calls (replaces dropped DeepSeek hosted API).
6. **KG sidecar property graph** — typed predicates extracted from `[[ ]]` links + nightly drift validator.
7. **Routines** integration for offload-able jobs once Anthropic lifts the 1h cadence + 15/day cap.
8. **Anthropic ZDR contract** — sales-gated. Apply when v4 traffic justifies.

---

End of SPEC v4.0.

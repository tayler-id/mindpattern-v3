# Spec: Research-pipeline reliability hardening

> Status: **In progress** (retry/prompt hardening implemented; source-tool restoration pending live install)
> Owner: Tayler · Author: Claude · Created: 2026-06-23
> Trigger: 2026-06-23 newsletter built from ~6/13 agents because the Anthropic API returned `529 Overloaded` and the pipeline does not retry.

## Assumptions (correct these or I proceed with them)

1. Scope is the **research pipeline** (13 research agents + 8 preflight sources). Not v4/KG, not newsletter/social phases (those already retry).
2. "Fix everything else" = retry on transient API errors + restore the dead sources + record the real failure cause. Concurrency/model tier are **off-limits** (see Non-goals).
3. The spec ships to the repo and is reviewed before any code; implementation is TDD.
4. The 3 missing CLI tools are installed by **you** on this Mac (I provide exact commands); everything else is code.

## 1. Objective

The daily pipeline must **survive transient Anthropic API errors** (chiefly `529 overloaded_error`) instead of dropping agents to 0 findings, and the **dead data sources must feed data again** — all **without reducing agent concurrency or model tier**.

Done when: a 529 (or other transient API error) on an agent call is retried and recovers; X/Exa/YouTube sources return data; and a failed agent records *why* it failed (`overloaded` / `rate_limit` / `timeout` / `parse_error` / `other`) instead of the catch-all `"Non-zero exit code"`.

## 2. Eval — what's actually failing  *(the "eval the errors" deliverable)*

Evidence: `reports/launchd-stderr.log` (11,449 lines) + `orchestrator/agents.py`.

| Failure | Count | Nature | Cause |
|---|---|---|---|
| `API Error: 529 Overloaded` | **7** (all today) | **Acute** | API overloaded; **zero retry** in `run_single_agent`. These are exactly the 7 zero-finding agents. |
| `exited with code 1` (research agents) | **104** (all-time) | Recurring | Mixed: 529, possible `--max-turns 35` exhaustion, hook failures. **Mislabeled** — see below. |
| `…timed out…` mentions | ~100+ | Recurring | Mix of agent 30-min (`1800s`) kills + preflight tool timeouts (github 60s, rss 120s, exa 60s). Needs clean split (Task 1). |
| `xreach/mcporter/yt-dlp not found` | **27** | **Chronic** | X/Twitter, Exa, YouTube sources dead since the machine move — feeding **zero** data daily. |

**Two root causes:**
- **Today (acute):** transient overload + **no retry**. `529` is `overloaded_error`, explicitly retryable.
- **Chronic:** 3 of 8 sources dead (missing CLI tools); failure labels are lossy.

**The lossy-label bug** (`orchestrator/agents.py:420-421`): on a non-zero exit the code records `result.error = proc.stderr[:500] if proc.stderr else "Non-zero exit code"`. A 529 arrives on **stdout** (`"API Error: 529 Overloaded…"`), stderr is empty → the real cause is discarded and findings show as an unexplained 0. This is why diagnosing today took a stdout grep, not a glance at the error field.

## 3. Strategy — researched options  *(the "research better strategies" deliverable)*

Authoritative source: the `claude-api` skill (Anthropic API reference) + `shared/error-codes.md`.

> **Hard constraint: the pipeline runs on Tayler's Anthropic *subscription* via the `claude` CLI (`CLAUDE_CODE_OAUTH_TOKEN`), NOT the paid pay-per-token API.** Any strategy that needs an Anthropic API key bills per token and moves the pipeline off the subscription — those are rejected regardless of technical merit.

| # | Strategy | Verdict |
|---|---|---|
| 1 | **Retry transient errors (429/5xx/529) with exponential backoff + FULL JITTER** by re-invoking the existing `claude` CLI call. | **✅ CHOSEN — immediate.** Stays 100% on your **subscription** (`claude` CLI, no API key, no per-token billing). Jitter is essential *because* we keep full concurrency: 13 agents that all 529 must not retry in lockstep (that just re-triggers 529). Recovery, not load-shaping. |
| 2 | Move agent calls onto the **Anthropic SDK / Agent SDK** → built-in `max_retries` backoff. | **❌ Rejected — requires the paid API.** The SDK authenticates with an API key and bills per token; it would move the pipeline OFF your subscription. (The CLI has no `max_retries` flag, so we implement our own wrapper instead — Option 1.) |
| 3 | **Message Batches API** — async, 50% cheaper. | **❌ Rejected — paid API only** (same billing switch as #2), plus a full async/poll redesign. |
| 4 | **Priority / service tier** — more capacity for higher cost. | **❌ Rejected — paid API only.** |

**The `claude` CLI does retry internally but gives up and surfaces the 529 as a one-shot `exit 1`** — so our own outer retry wrapper (Option 1) is what's needed, and it's the *only* option that keeps you on the subscription.

**Also rejected per your directive ("do not tame the load"):** concurrency caps, Opus→Sonnet downgrade-on-overload, staggered/serialized starts. Backoff+jitter on *retry only* is kept (it does not reduce steady-state parallelism).

## 4. Non-goals

- ❌ **Switching agent calls to the paid Anthropic API / SDK.** The pipeline runs on Tayler's **subscription** via the `claude` CLI; no API key, no per-token billing.
- ❌ Reducing agent concurrency (all 13 stay parallel).
- ❌ Downgrading model tier (`research_agent` stays `opus_1m`) — even as overload mitigation.
- ❌ v4 SDK migration, Batch API, priority tier (researched above; all require the paid API → rejected).
- ❌ Touching newsletter/social phases (already have retry) or the KG work.

## 5. Tech stack & conventions

- Python 3.14, **stdlib only** (no new deps — `time`, `random`, `subprocess`).
- Tests: `.venv/bin/python3 -m pytest tests/ -x -q` (system `python3` has no pytest). Offline; **mock the `claude` CLI subprocess**.
- Touch points: `orchestrator/agents.py` (`run_single_agent`), `orchestrator/router.py` (timeouts/turns — read-only unless approved), `preflight/{twitter,exa,youtube}.py` (env only), `tests/test_*agents*.py`.

## 6. Design (proposed)

**Retry wrapper inside `run_single_agent`:**
- After the subprocess returns, **classify** the result: `success | overloaded | rate_limit | server_error | timeout | parse_error | other` by inspecting exit code + stdout signature (`"API Error: 529"` / `overloaded` / `429` / `rate limit`) — *not* just stderr.
- Retry **only** transient classes (`overloaded`, `rate_limit`, `server_error`) and our own `timeout` (optional — open question). Do **not** retry `parse_error` or clean-exit-no-findings (those are prompt/format bugs).
- Backoff: **full jitter** — `sleep = random.uniform(0, min(cap, base * 2**attempt))`. Proposed `base=2s`, `cap=60s`, **3 attempts**. Honor a `retry-after` value if present in output.
- Record the final `classification` on `AgentResult` and log it, replacing the bare `"Non-zero exit code"`.
- Determinism for tests: inject the sleep function and RNG (or a `retry_config`) so tests assert behavior without real waits.

**Restore sources:** install `xreach`, `yt-dlp`, `mcporter` (your machine); verify each preflight module finds its tool.

**Source-tool install commands (2026-06-23):**

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

# Baseline installer/doctor for Agent Reach channels (Jina, YouTube, GitHub, RSS, Exa).
uv tool install "https://github.com/Panniantong/agent-reach/archive/main.zip"
agent-reach install --env=auto
agent-reach doctor

# Direct tools used by current preflight modules.
brew install yt-dlp
brew install steipete/tap/mcporter

# Legacy Twitter/X CLI expected by preflight/twitter.py today.
uv tool install xreach
```

Current Agent Reach docs now describe the active Twitter/X upstream as
`twitter`, not `xreach`; if the legacy `xreach` package no longer resolves,
patch `preflight/twitter.py` to fall back to `twitter search` before declaring
the X source dead.

## 7. Boundaries

- **Always:** TDD (failing test first); mock the CLI; no new deps; keep 13 agents parallel on `opus_1m`; log every failure with its classification + traceback.
- **Ask first:** changing `router.py` timeouts/max_turns; adding a dependency; anything touching the live launchd job or running pipeline.
- **Never:** move agent calls off the `claude` CLI / subscription onto the paid API (no API keys, no per-token billing); reduce concurrency or downgrade model for load reduction; retry non-transient failures; swallow exceptions silently; commit secrets.

## 8. Success criteria (binary, testable)

1. A simulated **529** (mock CLI: overloaded text on stdout, exit 1) is retried with backoff+jitter and **recovers** when a later mocked attempt returns findings. *(unit test)*
2. A **non-transient** failure (parse error / clean exit, no findings) is **not** retried. *(unit test)*
3. Failure **cause is classified and recorded** (`overloaded`/`rate_limit`/`timeout`/`parse_error`/`other`) — never the bare `"Non-zero exit code"`. *(unit test + log)*
4. Backoff uses **full jitter** so simultaneous 529s don't retry in lockstep. *(unit test asserts jitter range)*
5. `xreach`, `yt-dlp`, `mcporter` installed; X/Exa/YouTube preflight return data. *(manual verification — your machine)*
6. **Failure taxonomy** produced from `traces.db` + logs (counts per category, last N days) — quantifies the 104 exit-1s and the timeout population. *(Task 1 artifact)*
7. `.venv/bin/python3 -m pytest tests/ -x -q` green; every new function has a test.

## 9. Open questions (need your call before PLAN)

1. **Retry budget:** OK with **3 attempts, base 2s, cap 60s, full jitter**? (Worst case ≈ +90s on a retried agent; agents run in parallel, so pipeline cost is bounded by the slowest and stays far under the 1800s timeout.)
2. **Timeouts in scope?** There are ~100+ timeout mentions historically. Options: (a) leave timeouts out of this spec, fix only API-error retry now; (b) also retry once on our own 1800s timeout; (c) just quantify them in Task 1 and decide after. (Proposed: **c**.)
3. **Source restore:** want me to hand you exact install commands now, or wait until the code fix lands?

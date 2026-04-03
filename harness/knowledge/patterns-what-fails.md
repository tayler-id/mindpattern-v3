# What Fails

> Anti-patterns, common failure modes. Updated by harness from failed tickets and run issues.

## Pipeline

- **Zero-findings systemic failure** — Runs 12-13 produced zero findings. Root cause unknown but recovered in Run 14 (234 findings).
- **Distribution gap** — Posts generated but not delivered. Run 14: posted to none. Runs 16-18: intermittent. Partially resolved Run 19.
- **Sources regression on security topics** — Sources score collapsed to 0.333 when security topics dominate (Run 19). Structural issue in [[orchestrator/evaluator]].

## Harness

- **Parallel worktree creation races** — Git config lock contention. 2/3 agents fail, find wrong worktree. Fixed with stagger.
- **High max_turns burns tokens** — 40 turns on Opus for a single complex ticket consumed hundreds of thousands of tokens with no result. Reduced to 15.
- **Research tickets too ambitious** — "Prompt compression via LLMLingua-2" is an M-effort feature with external dependency. Fix agents can't install new packages in worktrees. Keep tickets to S-effort or split.
- **Scout re-reads everything** — No memory between runs. Burns 20+ turns reading files it already knows. Knowledge graph should fix this.

## External API Patterns

- **Jina Reader errors pass through as content** — curl exits 0 even when Jina returns error JSON (`{"code":451,...}`). Must validate response content, not just exit code. Fixed 2026-04-02 with `_is_jina_error()` + direct fallback.
- **Silent user-facing failures** — Handlers that return early without replying leave users confused. Always acknowledge input, even on rejection. Fixed 2026-04-02 in skills handler.

## Agent Patterns

- **Skill file missing = silent empty prompt** — Agent runs without skill content, produces garbage or generic findings.
- **NOVELTY REQUIREMENT is prompt-only** — No hard dedup. Agents sometimes return duplicates, caught at 0.90 similarity threshold downstream.

## Migration

- **Migration ordering in _ensure_table()** — CREATE INDEX on a new column BEFORE ALTER TABLE ADD COLUMN crashes on existing databases. Tests pass because they use fresh in-memory SQLite. Production databases have the old schema. Always put ALTER TABLE migrations before CREATE INDEX on new columns. (2026-04-02, checkpoint.py)

## Last Updated

2026-04-02.

2026-04-01 — initial patterns from run history analysis.

- **2026-04-01-R014 rejected** — **REVIEW: REJECTED**

**Reason:** The `traces_db.py` self-test (`if __name__ == "__main__"`) fails because it still expects exactly 14 tables, but the new `model_routing_log` table brings the count to 15. The self-test's `expected` list and the module docstring ("Tables (14 total)") were not updated. This is a regression in the self-test script. (2026-04-01 19:11)

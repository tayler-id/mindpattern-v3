# policies and contracts

> Behavior that changes without a code edit. Each file is checked when it loads, so a bad edit stops the run before any model call.

## Files

Six kinds of file, each validated on load.

- `config/models.json`: the route per task. See [[core/model_cli]].
- `policies/writing.json`: 70 banned or capped phrases with examples, counterexamples, surfaces, target models, and review-by dates, plus budgets such as `em_dash_per_issue`.
- `policies/editorial.json`: top stories, deep-dive stories, the newsletter length (lead stories included), site candidate and issue story caps, the republish tracker threshold, the layout (`newsletter.layout`, lists and tables per story and section), and the lead-story rules in `threads`.
- `policies/research.json`: finding fields, age, banned entities, injection patterns. Read by `policies/engine.py` and [[mp/cli]].
- `policies/observability.json`: trace retention and the per-run soft budget. See [[core/trace_store]].
- `contracts/*.schema.json`: `critic_verdict`, `editor_edits`, `research_finding`, `evidence_item`, `threads`.

## Writing Policy Loader

`orchestrator/word_bank.py` loads `writing.json` through `load_bank()`. A row fails the load when its pattern misses its own example, matches its counterexample, does not compile, or carries an unknown key.

The 54 rows that used to be a Python literal were exported and checked equal field by field. The prose gate, the site lint, the editor, and every writer prompt read the same file.

## Contracts

`core/contracts.py` checks a small JSON Schema subset with no new dependency. Codex also enforces the schema on its side through `--output-schema`.

## Last Updated

2026-10-02. Created with the models harness.

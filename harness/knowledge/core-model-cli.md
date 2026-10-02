# core/model_cli.py

> One call path for every model call, Claude or Codex. Builds the argv, runs the CLI, parses its event stream, falls back, and records the call.

## Routes

Each task names a route in `config/models.json`: provider, model, effort, turns, timeout, an optional fallback. `core/config.py` loads it with an mtime cache.

`python -m core.config check` validates the file and prints every route. It rejects unknown keys, an unknown provider or effort, a Claude route without effort (Haiku excepted), and a fallback that has its own fallback.

## Key Functions

Two entry points, one argv builder, and one parser per CLI.

- `call_model(request, route=None, runner, recorder)` returns a `ModelResult`. It tries the fallback once on timeout, rate limit, error, or a CLI that will not start.
- `run_task_process(task, prompt, system_prompt_file, tools, unit, cwd, env, output_schema)` returns a `ClaudeProcessResult` for callers that still read stdout.
- `build_argv(route, request)` builds `claude -p --output-format stream-json --verbose` or `codex exec --json`.
- `parse_claude_stream` and `parse_codex_stream` turn either stream into text, usage, steps, and subagents.

## Clean Context

Claude runs with `--setting-sources project,local --strict-mcp-config`, so the user's plugins, hooks, and MCP servers stay out. A one-word call cost $0.075 with them and $0.017 without.

Codex runs with `--ignore-rules` and its plugin, skill, hook, app, browser, and computer-use features off. `--ignore-user-config` drops the login, so it is not used.

## Contracts

A route can pass a JSON schema from `contracts/`. Codex enforces it with `--output-schema`, and `core/contracts.py` checks the answer for every provider. See [[policies/files]].

## Depends On

`core/config.py`, `core/claude_cli.py`, [[core/trace_store]] as the default recorder. Used by [[orchestrator/agents]], [[orchestrator/deep_dive]], [[orchestrator/newsletter_editor]], the site writer and critic, KG extraction, and the knowledge flush.

## Known Fragile Points

What can still go wrong around a call.

- A failed trace write is logged and never fails the call. A test holds that, since the Slack bot on Fly calls models too.
- `~/.codex/AGENTS.md` still loads for Codex. No flag skips it without dropping the login.
- `--bare` would cut Claude's context further but needs an API key, which this machine does not use.

## Last Updated

2026-10-02. Created with the models harness (spec `docs/specs/2026-10-02-models-harness-policies-spec.md`).

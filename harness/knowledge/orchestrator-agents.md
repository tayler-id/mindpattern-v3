# orchestrator/agents.py

> Parallel dispatch for research agents. Every call goes through [[core/model_cli]], and agents store findings with [[mp/cli]] as they go.

## What It Does

Builds per-agent prompts (soul + skill + trends + claims + preflight), runs each through `run_task_process`, and merges the findings the agent stored with `mp` and the ones it printed. 13 agents in parallel.

## Key Functions

Prompt building, dispatch, and the merge of stored and printed findings.

- `AgentResult` dataclass — agent_name, findings, raw_output, exit_code, duration_ms, killed_by_timeout, error
- `build_agent_prompt(agent_name, user_id, date_str, soul_path, agent_skill_path, context, trends, claims, preflight_items, already_covered, identity_dir)` — assembles full prompt with identity, skill, dynamic context
- `run_single_agent(agent_name, prompt, task_type)` runs the agent's route, parses JSON findings, and merges stored ones
- `merge_findings(printed, stored)` dedupes by URL, so an agent that hits the turn cap keeps what it stored
- `STORE_FINDINGS_SECTION` is the prompt section that teaches `mp finding add`, `mp seen`, and `mp fetch`
- `dispatch_research_agents(user_id, date_str, context_fn, trends, claims, max_workers, preflight_data)` — ThreadPoolExecutor parallel dispatch
- `run_claude_prompt(prompt, task_type, system_prompt_file, allowed_tools)` — general-purpose claude call wrapper
- `get_agent_list(user_id, vertical)` — returns agent names from verticals/ or overrides
- `get_agent_skill_path(agent_name, user_id, vertical)` — resolves skill .md file path

## Depends On

[[core/model_cli]] and [[orchestrator/router]] (routes from `config/models.json`), [[mp/cli]], skill files in [[agents/research-agents]]

## Known Fragile Points

Parsing, timeouts, and prompt rules that code does not enforce yet.

- JSON parsing is lenient — if output has markdown fences or text around JSON, parsing can fail
- Agent timeout is 30 min (research_agent). Findings stored with `mp` survive it, printed ones do not
- Skill file loading has no fallback — missing file = empty skill, no error
- Soul/voice files optional — missing = runs without, no warning
- Allowed tools list is static, so AGENT_ALLOWED_TOOLS can't be configured per agent. It grants `mp` by name and as `bin/mp`
- NOVELTY REQUIREMENT is prompt-only — no hard dedup, relies on 0.90 similarity catch downstream

## Architecture Note

The prompt has a fixed order, and its static parts repeat across all 13 agents.

Prompt structure: JSON schema (top) + SOUL identity + agent skill + dynamic context (trends, claims, preflight) + novelty requirements + Phase 1 items + Phase 2 instructions + JSON schema (bottom). Schema is repeated twice. Identity files identical across all 13 agents. These static sections are compression candidates.

## Last Modified By Harness

2026-10-02. Calls moved to [[core/model_cli]], findings stored through [[mp/cli]], the Subagent Delegation block removed.

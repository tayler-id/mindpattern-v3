# orchestrator/agents.py

> Parallel Claude CLI dispatch for research agents. ThreadPoolExecutor, subprocess calls, JSON parsing.

## What It Does

Builds per-agent prompts (soul + skill + trends + claims + preflight), runs `claude -p` via subprocess, parses JSON findings from output. 13 agents in parallel with max_workers configurable.

## Key Functions

- `AgentResult` dataclass — agent_name, findings, raw_output, exit_code, duration_ms, killed_by_timeout, error
- `build_agent_prompt(agent_name, user_id, date_str, soul_path, agent_skill_path, context, trends, claims, preflight_items, already_covered, identity_dir)` — assembles full prompt with identity, skill, dynamic context
- `run_single_agent(agent_name, prompt, task_type)` — runs `claude -p` subprocess, parses JSON findings
- `dispatch_research_agents(user_id, date_str, context_fn, trends, claims, max_workers, preflight_data)` — ThreadPoolExecutor parallel dispatch
- `run_claude_prompt(prompt, task_type, system_prompt_file, allowed_tools)` — general-purpose claude call wrapper
- `get_agent_list(user_id, vertical)` — returns agent names from verticals/ or overrides
- `get_agent_skill_path(agent_name, user_id, vertical)` — resolves skill .md file path

## Depends On

[[orchestrator/router]] (model selection, timeouts, max_turns), skill files in [[agents/research-agents]]

## Known Fragile Points

- JSON parsing is lenient — if output has markdown fences or text around JSON, parsing can fail
- Agent timeout is 30 min (research_agent) — kills abruptly, no partial output recovery
- Skill file loading has no fallback — missing file = empty skill, no error
- Soul/voice files optional — missing = runs without, no warning
- Model routing hardcoded per task_type — no per-agent customization
- Allowed tools list is static — AGENT_ALLOWED_TOOLS can't be configured per agent
- NOVELTY REQUIREMENT is prompt-only — no hard dedup, relies on 0.90 similarity catch downstream

## Architecture Note

Prompt structure: JSON schema (top) + SOUL identity + agent skill + dynamic context (trends, claims, preflight) + novelty requirements + Phase 1 items + Phase 2 instructions + JSON schema (bottom). Schema is repeated twice. Identity files identical across all 13 agents. These static sections are compression candidates.

## Last Modified By Harness

Never — created 2026-04-01.

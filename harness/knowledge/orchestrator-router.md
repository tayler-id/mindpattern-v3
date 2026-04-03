# orchestrator/router.py

> Model routing, max turns, timeouts, pricing. Central config for all claude calls.

## Routing Table

| Task Type | Model | Max Turns | Timeout |
|-----------|-------|-----------|---------|
| trend_scan | haiku | 5 | 120s |
| research_agent | opus_1m | 35 | 1800s |
| synthesis_pass1 | opus | 10 | 300s |
| synthesis_pass2 | opus_1m | 20 | 900s |
| social_writer | sonnet | 10 | 300s |

## Key Functions

- `get_model(task_type)` — returns Claude model ID
- `get_max_turns(task_type)` — returns max turns
- `get_timeout(task_type)` — returns timeout seconds
- `estimate_cost(model, input_tokens, output_tokens)` — USD estimate

## Depends On

Nothing. Used by [[orchestrator/agents]].

## Known Fragile Points

- Task types hardcoded — no config file
- MODEL_PRICING duplicated in [[orchestrator/observability]] — source of truth confusion
- research_agent timeout is 30 min — burns tokens if agent loops
- No per-user or per-agent override
- Pricing is static — must update code when Anthropic changes prices

## Last Modified By Harness

Never — created 2026-04-01.

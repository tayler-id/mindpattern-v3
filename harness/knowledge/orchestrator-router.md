# orchestrator/router.py

> Thin reader over `config/models.json`. The routes live in the config file now, and [[core/model_cli]] is the only caller that runs them.

## Routing Table

As of 2026-10-02 (`python -m core.config check` prints the live file):

| Task | Provider and model | Effort | Turns | Timeout |
|------|--------------------|--------|-------|---------|
| trend_scan | claude-haiku-4-5 | none | 5 | 60s |
| research_agent | claude-sonnet-5-5 | high | 35 | 1800s |
| synthesis_pass1 | claude-opus-5-5 | high | 10 | 600s |
| synthesis_pass2 | claude-opus-5-5 | high | 30 | 900s |
| story_deep_dive | claude-sonnet-5-5 | medium | 15 | 600s |
| newsletter_editor | codex gpt-6.1-sol, Sonnet 5.5 fallback | medium | none | 600s |
| site_story_writer | claude-sonnet-5-5 | medium | 8 | 300s |
| site_story_critic | codex gpt-6.1-sol, Sonnet 5.5 fallback | medium | none | 300s |
| kg_extract | claude-haiku-4-5 | none | 1 | 300s |
| eic, evolve | claude-opus-5-5 | high | 15, 10 | 600s |

Social tasks stay on the `sonnet` alias at high effort.

## Key Functions

- `get_route(task_type)` returns the `Route` from config, or `_default` under the task's name.
- `get_model`, `get_max_turns` (default 10), `get_timeout` read fields off it.

## Depends On

`core/config.py`. Used by [[orchestrator/agents]] and `knowledge/flush.py`.

## Known Fragile Points

Two route choices to watch on live runs.

- Research on Sonnet 5.5 costs about 70% less per agent than Opus 5.5 and found about a third fewer new stories in four Oct 2 replays. Moving `research_agent` back is one line.
- Haiku takes no effort setting. Every other Claude route must pin one, so the user's interactive setting cannot leak in.

## Last Updated

2026-10-02. Routes moved from code to `config/models.json`.

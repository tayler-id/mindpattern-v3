# Workflows outside the initial CLI scenarios

## Sub-features

| Area | User behavior | Current verification source |
| --- | --- | --- |
| Research | Gather source material, dispatch researchers, validate findings, run follow-up research. | [Research operations skill](../../../mindpattern-research-ops/SKILL.md) |
| Briefings | Read dated newsletters and structured issues, synthesize and deliver a briefing. | [Content operations skill](../../../mindpattern-content-ops/SKILL.md), `tests/test_site_issue_contracts.py` |
| Findings and graph | Browse findings, inspect entities, follow relationships, query stored memory. | `tests/test_api_contract.py`, `tests/test_site_graph_api.py`, `tests/test_memory_cli.py` |
| Editorial | Review proposed social content, approve or reject it, inspect engagement history. | [Content operations skill](../../../mindpattern-content-ops/SKILL.md), `tests/test_approval.py` |
| Media | Produce audio briefings and video scripts from approved content. | [Content operations skill](../../../mindpattern-content-ops/SKILL.md), `tests/test_media_artifact_contracts.py` |
| Operations | Inspect pipeline status, run history, traces, performance, and reader analytics. | `tests/test_pipeline.py`, `tests/test_traces_db.py`, `tests/test_site_analytics.py` |
| Public frontend | Read, search, and follow story and entity pages in a browser. | [Site quality skill](../../../rabbit-hole-site-quality/SKILL.md), sibling repository instructions |

## How to get to it (user POV)

The owner uses private dashboard pages such as `/pipeline-status`, `/run-history`, `/findings`, `/newsletters`, `/editors-desk`, `/social-history`, `/engagement-history`, and `/site-analytics`. Readers use public API-backed story, issue, source, and entity pages on Rabbit Hole.

The research pipeline starts through `run.py`. It is an operational command that can progress into delivery and publishing. Its existence in this map is not permission to run it.

## Driving it with verification

These workflows are not implemented by the new CLI. Select the relevant existing offline tests or operational skill. For example:

```sh
.venv/bin/python3 -m pytest tests/test_site_issue_contracts.py -x -q
.venv/bin/python3 -m pytest tests/test_site_graph_api.py -x -q
.venv/bin/python3 -m pytest tests/test_approval.py -x -q
.venv/bin/python3 -m pytest tests/test_site_analytics.py -x -q
```

For a public frontend change, switch to `../mindpattern-rabbit-hole`, read its instructions, then run lint, TypeScript checking, build, and a browser smoke against an isolated backend. Backend JSON alone does not prove browser behavior.

Add a dedicated map entry and driver scenario when work needs one of these paths. Use a synthetic fixture that supports the real route before claiming that the CLI verifies it.

## Gotchas

Private dashboard handlers retain several import-time paths, and newsletter code has a legacy absolute report-directory fallback. Extending the CLI requires checking those paths. Pipeline dry runs still write local artifacts. Production health checks and saved personal state cannot be inferred from the synthetic doctor response.

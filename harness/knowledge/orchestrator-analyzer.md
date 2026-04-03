# orchestrator/analyzer.py

> Self-optimization. Reads agent traces, compares against skill files, produces JSON diffs.

## What It Does

Builds prompt from agent traces + skill files + metrics + regression data. LLM produces JSON diffs (section replacements/appends). Applies diffs to skill .md files. Records hashes via [[orchestrator/prompt_tracker]].

## Key Functions

- `build_analyzer_prompt(trace_dir, skill_files, date_str, metrics, regression_data, agent_history, agent_scorecards)` — assembles full context
- `parse_analyzer_output(raw_output)` — extracts JSON from LLM output (tries direct parse, fences, braces)
- `apply_analyzer_changes(changes, project_root, traced_files, prompt_tracker)` — applies diffs to files
- `_find_and_replace_section(content, section_name, new_body)` — replaces ## section body
- `_append_to_section(content, section_name, new_content)` — appends with dedup check
- `_normalize_path(file_path, project_root)` — fixes LLM-generated short paths

## Depends On

[[orchestrator/prompt_tracker]], memory.vault.atomic_write. Modifies skill files in [[agents/research-agents]].

## Known Fragile Points

- Path normalization is guesswork — tries known prefixes
- traced_files validation optional — None = apply all changes blindly
- Regex fence pattern is too loose — matches any ``` block, not just json
- Section dedup too aggressive — removes ALL duplicate headings

## Last Modified By Harness

Never — created 2026-04-01.

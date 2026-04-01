# MindPattern Autonomous Harness

Self-improving outer loop. Agents find issues, create TDD tickets, fix in worktrees, test, review, and create PRs.

## Ticket JSON Schema

```json
{
  "id": "YYYY-MM-DD-NNN",
  "title": "Short description of the issue or improvement",
  "type": "bug|improvement|feature|research",
  "source": "scout|research",
  "priority": "P1|P2|P3",
  "status": "open|in_progress|done|failed|held",
  "description": "Detailed description with context",
  "requirements": ["Requirement 1", "Requirement 2"],
  "done_criteria": ["What success looks like 1", "What success looks like 2"],
  "tdd_spec": {
    "test_file": "tests/test_something.py",
    "tests_to_write": ["test_function_name_1", "test_function_name_2"]
  },
  "files_to_modify": ["path/to/file.py"],
  "context": "Additional context, links to traces, error messages",
  "created_at": "ISO-8601",
  "expires_at": "ISO-8601 (created_at + 7 days)",
  "feedback_history": []
}
```

## Priority Levels

- **P1**: Failures, regressions, broken functionality. Fix immediately.
- **P2**: Performance issues, quality degradation, missing error handling. Fix soon.
- **P3**: Improvements, refactors, new features, research proposals. Fix when capacity.

## For Scout Agent

- Query `data/ramsay/traces.db` via `sqlite3` CLI
- Check `agent_runs` for failures in last 7 days
- Check `quality_scores` and `quality_history` for regressions
- Check `pipeline_phases` for slow or failed phases
- Check `alerts` for unacknowledged issues
- Scan `TODO|FIXME|HACK|XXX` in Python files (exclude .venv, node_modules)
- Read `harness/feedback.json` for past PR outcomes
- Read existing tickets in `harness/tickets/` to avoid duplicates
- Generate 3-5 tickets per run, prioritized by impact

## For Fix Agent

- ALWAYS write tests first (TDD — red, green, refactor)
- Read the ticket JSON for exact requirements
- Run the specific test file with `python3 -m pytest <test_file> -x -q` before and after
- Keep changes minimal and focused on the ticket scope
- Do not modify unrelated files
- Follow existing code patterns (look at neighboring code)
- Commit with: `fix: <ticket title> [harness/<ticket-id>]`

## For Review Agent

- Read the diff: `git diff main...HEAD`
- Check: does the diff match the ticket requirements?
- Check: are tests meaningful (not just passing trivially)?
- Check: no regressions in existing tests
- Check: follows CLAUDE.md conventions
- Push the fix branch to origin before creating the PR
- If approved: `gh pr create --title "<title>" --body "<evidence>"`
- If rejected: do NOT create PR, document rejection reason

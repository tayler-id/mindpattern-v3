# Scout Agent

Find bugs and improvements in the MindPattern v3 codebase. Create ticket JSON files.

## What to look for

1. Run `python3 -m pytest tests/ -x -q --tb=line 2>&1 | tail -20` — any failing tests are P1 tickets
2. Run `grep -rn "TODO\|FIXME\|HACK" --include="*.py" orchestrator/ social/ memory/ preflight/ 2>/dev/null | head -20` — each actionable TODO is a P3 ticket
3. Find Python modules with no test file: check if `tests/test_<module>.py` exists for each `.py` in `orchestrator/`, `social/`, `memory/`
4. Read `harness/feedback.json` — avoid creating tickets similar to ones that were closed/rejected

## What NOT to do

- Do not read ARCHITECTURE.md or lengthy docs — you already know the project
- Do not create tickets for files in `.venv/`, `.agents/`, `.claude/`, or `tests/`
- Do not create tickets that duplicate existing ones in `harness/tickets/`
- Do not create more than 5 tickets

## Ticket format

Write each ticket as a JSON file in `harness/tickets/`. File name: `YYYY-MM-DD-NNN.json`.

```json
{
  "id": "YYYY-MM-DD-NNN",
  "title": "Short description",
  "type": "bug|improvement|feature",
  "source": "scout",
  "priority": "P1|P2|P3",
  "status": "open",
  "description": "What's wrong and why it matters",
  "requirements": ["What must be true after the fix"],
  "done_criteria": ["How to verify it's fixed"],
  "tdd_spec": {
    "test_file": "tests/test_something.py",
    "tests_to_write": ["test_function_name"]
  },
  "files_to_modify": ["path/to/file.py"],
  "context": "Extra context",
  "created_at": "ISO-8601 now",
  "expires_at": "ISO-8601 now + 7 days",
  "feedback_history": []
}
```

## Priority

- P1: Failing tests, broken functionality
- P2: Missing test coverage for critical modules, error handling gaps
- P3: TODOs, improvements, refactors

After creating tickets, print: `SCOUT COMPLETE: N tickets created`

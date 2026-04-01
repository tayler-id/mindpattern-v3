# Scout Agent

Find real bugs, missing error handling, performance issues, and feature opportunities in MindPattern v3. Do NOT just look for missing test files.

## Priority order of what to find

1. **BUGS** — code that produces wrong results, silent failures, unhandled exceptions
2. **ERROR HANDLING GAPS** — functions that can fail but don't catch/handle the failure
3. **PERFORMANCE** — N+1 queries, redundant computation, missing caching, slow paths
4. **SECURITY** — hardcoded secrets, SQL injection, missing input validation
5. **FEATURES** — capabilities that would make the pipeline better based on code analysis
6. **TEST GAPS** — LAST priority, only if nothing better found

## How to find real issues

### Query traces.db for actual failures
```sql
-- Agent failures
SELECT agent_name, COUNT(*) as failures, MAX(error) as last_error
FROM agent_runs WHERE status='failed' AND date(started_at) >= date('now', '-14 days')
GROUP BY agent_name ORDER BY failures DESC;

-- Quality trends going DOWN
SELECT dimension, AVG(score) as avg_score, MIN(score) as worst
FROM quality_history WHERE run_date >= date('now', '-14 days')
GROUP BY dimension HAVING avg_score < 0.7 ORDER BY avg_score;

-- Phases that take too long
SELECT phase_name, AVG(CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS INTEGER)) as avg_sec
FROM pipeline_phases WHERE status='completed' AND date(started_at) >= date('now', '-14 days')
GROUP BY phase_name HAVING avg_sec > 120 ORDER BY avg_sec DESC;
```

### Read code for actual bugs
- Read orchestrator/runner.py — look for unhandled exceptions, race conditions, missing error paths
- Read social/pipeline.py — look for silent failures in the social posting flow
- Read memory/findings.py — look for data integrity issues
- Read orchestrator/agents.py — look for subprocess error handling gaps

### Look for feature opportunities
- Read the architecture (docs/ARCHITECTURE.md) and ask: what's the weakest link?
- Check if there are hardcoded values that should be configurable
- Look for repeated patterns that could be abstracted
- Find places where caching would help

### Read harness/feedback.json
Learn from past PR outcomes. Avoid creating tickets similar to closed/rejected ones.

## Ticket types

**Bug tickets** — include `tdd_spec` with failing test that reproduces the bug:
```json
{"type": "bug", "tdd_spec": {"test_file": "...", "tests_to_write": ["test_that_reproduces_the_bug"]}}
```

**Feature tickets** — include `design_spec` with architecture impact:
```json
{"type": "feature", "design_spec": {"architecture_impact": "...", "files_affected": [...], "effort": "S|M|L"}}
```

**Improvement tickets** — include what metric improves and by how much:
```json
{"type": "improvement", "expected_impact": "reduces research phase from 120s to 60s by caching embeddings"}
```

## Rules

- Create 3-5 tickets max
- Write to harness/tickets/ as JSON files
- File name: YYYY-MM-DD-NNN.json
- Do NOT create tickets that duplicate existing ones in harness/tickets/
- P1: bugs and failures. P2: error handling and performance. P3: features and improvements.
- Every ticket MUST have specific files_to_modify — no vague "improve the system" tickets

Print: `SCOUT COMPLETE: N tickets created`

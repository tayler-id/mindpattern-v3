# Shared Issue Log

> Every component writes here when something breaks. The harness reads this before every fix attempt.
> Format: timestamped entries, newest first. Include root cause if known.

## Issues

### 2026-04-02 17:22 — Ticket 2026-03-31-011 rejected

- **Source**: harness/review
- **Details**: Ticket: Add test coverage for memory/graph.py (knowledge graph operations). Reason: REVIEW: REJECTED

The branch adds only `harness/knowledge/memory-graph.md` — a knowledge doc. It does **not** create `tests/test_graph.py` at all.

### 2026-04-02 17:22 — Ticket 2026-04-01-003 rejected

- **Source**: harness/review
- **Details**: Ticket: Add test coverage for memory/embeddings.py pure math functions. Reason: REVIEW: REJECTED

The branch is missing the primary deliverable: **`tests/test_embeddings.py` was never created**. The diff shows only:

### 2026-04-02 17:20 — Ticket 2026-03-31-009 rejected

- **Source**: harness/review
- **Details**: Ticket: Add test coverage for social/eic.py (editor-in-chief decision layer). Reason: **REVIEW: REJECTED**

The branch `harness/2026-03-31-009` is identical to `main` — it has zero commits beyond main. No `tests/test_eic.py` file was created, no test coverage was added. The ticket requires at least 5 tests covering topic ranking, verdict parsing, malformed JSON handling, threshold sk

### 2026-04-02 17:19 — Ticket 2026-03-31-008 rejected

- **Source**: harness/review
- **Details**: Ticket: Add test coverage for social/posting.py (LinkedIn/Bluesky posting client). Reason: **REVIEW: REJECTED**

The branch `harness/2026-03-31-008` points to the exact same commit as `main` (`0b33961`). There are zero changes — no `tests/test_posting.py` was created, no tests were written. The branch appears to have been created but no work was done on it.

### 2026-04-02 17:14 — Ticket 2026-04-01-010 rejected

- **Source**: harness/review
- **Details**: Ticket: Checkpoint resume does not restore in-memory state — EVOLVE and IDENTITY degrade after crash recovery. Reason: REVIEW: REJECTED

**Reason:** The branch `harness/2026-04-01-010` is identical to `main` (both at commit `0b33961`). No code changes were made:

### 2026-04-02 17:00 — Ticket 2026-04-01-009 rejected

- **Source**: harness/codex
- **Details**: No tdd_spec field; primary done criterion ("actionability >= 0.65 over 7-day window") is untestable by fix agent

### 2026-04-02 17:00 — Ticket 2026-03-31-R003 rejected

- **Source**: harness/codex
- **Details**: 4 files, M effort, failed twice already (linkedin test + missing classify_trace import); requires LLM calls for tip extraction

### 2026-04-02 17:00 — Ticket 2026-04-01-R017 rejected

- **Source**: harness/codex
- **Details**: 3 files, M effort, 7 tests, requires semantic similarity search for full LLM responses; too complex for 25 turns

### 2026-04-02 17:00 — Ticket 2026-04-01-R016 rejected

- **Source**: harness/codex
- **Details**: 3 files, M effort, 7 tests, requires embedding-based clustering of issues; too complex for 25 turns

### 2026-04-02 17:00 — Ticket 2026-04-01-R011 rejected

- **Source**: harness/codex
- **Details**: 4 files, M effort, requires creating LLM judge prompts + new Haiku calls + storing scores; too ambitious for fix agent

### 2026-04-02 17:00 — Ticket 2026-04-01-R012 rejected

- **Source**: harness/codex
- **Details**: 5 files + new launchd daemon + modifies social-config.json (do not commit); too many moving parts for 25 turns

### 2026-04-02 17:00 — Ticket 2026-03-31-R005 rejected

- **Source**: harness/codex
- **Details**: Requires pip install llmlingua (new dependency); known anti-pattern — fix agents can't install packages in worktrees

### 2026-04-02 17:00 — Ticket 2026-03-31-006 rejected

- **Source**: harness/codex
- **Details**: Requires pushing to GitHub and verifying CI runs externally; fix agent cannot do this

### 2026-04-02 17:00 — Ticket 2026-03-31-011 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_graph.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-03-31-010 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_patterns.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-03-31-009 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_eic.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-03-31-008 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_posting.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-03-31-002 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_agents.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-04-01-003 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_embeddings.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-04-01-002 rejected

- **Source**: harness/codex
- **Details**: Duplicate: tests/test_checkpoint.py already exists; archived version completed

### 2026-04-02 17:00 — Ticket 2026-04-01-001 rejected

- **Source**: harness/codex
- **Details**: Already fixed: find_resumable_run now uses AND user_id = ? (line 124); also archived

### 2026-04-02 16:50 — Jina Reader errors passed through as article content

- **Source**: slack_bot/handlers/base.py
- **Error**: Jina Reader returns JSON error (e.g. `{"code":451,"name":"SecurityCompromiseError"}`) but curl exits 0. `read_url()` treats error JSON as valid content.
- **Impact**: #mp-posts pipeline feeds error JSON to Creative Director, writers produce empty drafts. User sees "Got it: {"data":null,...}" then "pipeline didn't produce any drafts."
- **Fix applied**: Added `_is_jina_error()` to detect JSON error responses, `_read_url_direct()` as fallback scraper with browser User-Agent.
- **Lesson**: Always validate content from external APIs — a successful HTTP response doesn't mean valid content.

### 2026-04-02 16:50 — Skills handler silently ignores short messages

- **Source**: slack_bot/handlers/skills.py
- **Error**: Messages < 20 chars silently dropped (no reaction, no reply).
- **Impact**: User gets zero feedback, thinks bot is broken.
- **Fix applied**: Short messages now get a reply explaining the tip is too short.
- **Lesson**: Never silently ignore user input. Always acknowledge, even if rejecting.

### 2026-04-02 16:50 — Stale tests for LinkedIn engagement + router model

- **Source**: tests/test_engagement_linkedin.py, tests/test_orchestrator.py
- **Error**: Test expects `search_via_jina` called for LinkedIn, but code disabled LinkedIn search. Test expects `"opus"` but router returns `"claude-opus-4-6[1m]"`.
- **Fix applied**: Updated tests to match current code behavior.
- **Lesson**: When code behavior changes, update tests in the same commit.

### 2026-04-02 06:26 — checkpoint.py migration ordering crash

- **Source**: pipeline (run-launchd.sh)
- **Error**: `sqlite3.OperationalError: no such column: user_id`
- **Root cause**: Harness ticket `2026-04-01-001` added `user_id` column to checkpoints table but put `CREATE INDEX ON user_id` before `ALTER TABLE ADD COLUMN user_id`. Works on fresh DBs (tests pass) but crashes on existing production DBs missing the column.
- **Fix applied**: Moved ALTER TABLE before CREATE INDEX in `orchestrator/checkpoint.py`
- **Lesson**: Migration code must be tested against existing databases, not just fresh ones. Harness tests use in-memory SQLite which always creates fresh tables — they will never catch migration ordering bugs.

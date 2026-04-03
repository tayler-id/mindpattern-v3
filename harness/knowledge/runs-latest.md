# Latest Harness Run

> Updated after each harness run with outcomes.

## Run: 2026-04-01 (first run with knowledge graph)

**Status:** In progress

### Tickets Processed

- **2026-04-01-R013**: passed — https://github.com/tayler-id/mindpattern-v3/pull/12

- **2026-04-01-R014**: rejected (**REVIEW: REJECTED**

**Reason:** The `traces_db.py` self-test (`if __name__ == "__main__"`) fails because it still expects exactly 14 tables, but the new `model_routing_log` table brings the count to 15. The self-test's `expected` list and the module docstring ("Tables (14 total)") were not updated. This is a regression in the self-test script.)

- **2026-04-01-R015**: passed — https://github.com/tayler-id/mindpattern-v3/pull/11

_None yet — run started, scout in progress._

### PRs Created

- https://github.com/tayler-id/mindpattern-v3/pull/12

- https://github.com/tayler-id/mindpattern-v3/pull/11

_None yet._

### Issues Discovered

- Git config lock race on parallel worktree creation (fixed: 5s stagger)
- Fix agent max_turns too high at 40 (fixed: reduced to 15)
- 3 tickets failed due to stale worktree reuse

### Config Changes

- harness/config.json: fix max_turns 40->15, timeout 1200->600
- harness/run.sh: added 5s stagger between parallel agent launches

## Previous Runs

_No prior harness run data recorded in knowledge graph._

## Last Updated

2026-04-01 19:19.

2026-04-01 19:19.

2026-04-01 19:11.

2026-04-01 19:10.

2026-04-01.

## Final Summary (2026-04-01 19:19)

- Processed: 3
- PRs created: 4
- Failed: 0
- Remaining: 33

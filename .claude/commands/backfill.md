---
description: Durable goal - backfill the Rabbit Hole archive from a fresh worktree until no work remains
---

<!-- backfill-core-start -->
/goal Convert the Rabbit Hole archive until no backfill work remains.

Definition of done (machine-checkable): `status` reports
`remaining_unclaimed == 0 AND in_progress == 0`. remaining_unclaimed alone
is not done: work may be claimed by active agents; wait and re-check.

You are an OPERATOR, not a developer: never edit/write/delete repo files,
never commit, never kill processes you did not start, never run run.py,
never deploy. Your only writes are the artifacts and notebook lines the
backfill itself produces.

Setup (once per session; every session gets its own worktree):
1. AGENT=<unique name, e.g. claude-op-1421 / codex-op-1421>
2. git -C /Users/taylerramsay/Projects/mindpattern-v3 worktree add "/tmp/backfill-$AGENT" HEAD
3. cd "/tmp/backfill-$AGENT"
4. PY=/Users/taylerramsay/Projects/mindpattern-v3/.venv/bin/python
   ROOT=/Users/taylerramsay/Projects/mindpattern-v3/reports
   export MP_REPORTS_DIR="$ROOT"
   (every command below also takes --reports-root "$ROOT": artifacts, claims,
   and the notebook must land in the canonical tree the site serves)

The loop (repeat until done or a stop condition):
1. "$PY" -m orchestrator.site_backfill status --reports-root "$ROOT"
   -> remaining_unclaimed == 0 AND in_progress == 0: report final status,
      go to Cleanup, the goal is COMPLETE.
   -> remaining_unclaimed == 0 but in_progress > 0: other agents own the
      tail; wait 30 minutes and re-check status.
2. Preconditions for a batch (if any fail: report why, wait, retry later):
   - /tmp/mindpattern-ran-$(date +%F) and /tmp/mindpattern-synced-$(date +%F)
     exist (today's newsletter delivered and synced) and it is after 13:00.
   - No batch of yours already running.
3. "$PY" -m orchestrator.site_backfill claim --size 50 --agent "$AGENT" --reports-root "$ROOT"
4. In a Claude session: MP_SITE_STORY_WRITER=claude
   In a Codex session:  MP_SITE_STORY_WRITER=codex   (spends Codex quota)
   <writer env> "$PY" -m orchestrator.site_backfill run --claim <claim_id> --workers 2 --reports-root "$ROOT"
   Watch live: tail -f "$ROOT/ramsay/site-backfill-notebook.md"
5. Report after every batch: outcomes JSON, any ABORTED reason, fresh
   status JSON, and the notebook lines for your claim id.
6. Stop conditions:
   - ABORTED (usage_limit or failure streak): stop for the day. Do not retry.
   - At most 2 batches per day per agent, at least 2 hours apart.
   - failed:* outcomes are normal (the critic refusing unpublishable copy);
     they auto-release and later batches retry them. Do not "fix" them.

Cleanup:
7. cd / && git -C /Users/taylerramsay/Projects/mindpattern-v3 worktree remove "/tmp/backfill-$AGENT" --force
   (nothing to merge: operators change no code; artifacts already live in
   the canonical data root)
<!-- backfill-core-end -->

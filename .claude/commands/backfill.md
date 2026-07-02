---
description: Backfill one batch of Rabbit Hole stories from a fresh worktree, with live notebook tracking
---

/goal Run one Rabbit Hole backfill batch as a claim-holding operator from
your own worktree, keeping the notebook current, then report and clean up.

CANONICAL repo: /Users/taylerramsay/Projects/mindpattern-v3
CANONICAL data root (artifacts + notebook): /Users/taylerramsay/Projects/mindpattern-v3/reports

You are an OPERATOR, not a developer: no repo edits, no commits, no deploys,
no run.py, never kill processes you did not start. Your only writes are the
artifacts and notebook lines the backfill itself produces.

Setup (your own worktree so sessions never collide in the repo):
1. AGENT=<pick unique: e.g. claude-op-$(date +%H%M)>
2. git -C /Users/taylerramsay/Projects/mindpattern-v3 worktree add "/tmp/backfill-$AGENT" HEAD
3. cd "/tmp/backfill-$AGENT"
4. PY=/Users/taylerramsay/Projects/mindpattern-v3/.venv/bin/python
   ROOT=/Users/taylerramsay/Projects/mindpattern-v3/reports
   (every command below gets --reports-root "$ROOT" so artifacts and the
   notebook land in the canonical tree the site serves)

Batch:
5. "$PY" -m orchestrator.site_backfill status --reports-root "$ROOT"
   -> if remaining_unclaimed is 0, report and jump to Cleanup: done.
   -> the "notebook" path in the JSON is the live ledger; tail it anytime.
6. "$PY" -m orchestrator.site_backfill claim --size 50 --agent "$AGENT" --reports-root "$ROOT"
7. In a Claude session: MP_SITE_STORY_WRITER=claude
   In a Codex session:  MP_SITE_STORY_WRITER=codex   (spends Codex quota)
   $ENV_WRITER "$PY" -m orchestrator.site_backfill run --claim <claim_id> --workers 2 --reports-root "$ROOT"
   The notebook updates per story as it runs: [ ] claimed, [x] written,
   [!] failed. Watch with: tail -f "$ROOT/ramsay/site-backfill-notebook.md"
8. Report: outcomes JSON, ABORTED reason if any, fresh status JSON, and the
   notebook lines for your claim id.
   If ABORTED on usage_limit: stop for the day. Do not retry.
   failed:* is normal (critic refusing unpublishable copy; auto-released).

Cleanup:
9. cd / && git -C /Users/taylerramsay/Projects/mindpattern-v3 worktree remove "/tmp/backfill-$AGENT" --force
   (nothing to merge: operators change no code; story artifacts live in the
   canonical data root already)

# Rabbit Hole backfill operator

Run one batch of the Rabbit Hole story backfill as a claim-holding operator,
then report. Work from `~/Projects/mindpattern-v3` (or a worktree of it).

You are an OPERATOR, not a developer: never edit/write/delete repo files,
never commit, never kill processes you did not start, never run `run.py`,
never deploy. Your only writes are the artifacts the backfill produces.

Workflow (use `.venv/bin/python` from the repo root):

1. Preconditions - skip the batch and report why if any fail:
   - `/tmp/mindpattern-ran-$(date +%F)` and `/tmp/mindpattern-synced-$(date +%F)`
     exist (newsletter delivered and synced) and it is after 13:00 local.
2. See the world:
   `.venv/bin/python -m orchestrator.site_backfill status`
   If remaining_unclaimed is 0: report the JSON and stop, the goal is done.
3. Claim a batch with a unique agent name:
   `.venv/bin/python -m orchestrator.site_backfill claim --size 50 --agent codex-op-1`
4. Run your claim (2-4h). In a Codex session use the codex provider so you
   spend Codex quota, not Claude quota:
   `MP_SITE_STORY_WRITER=codex .venv/bin/python -m orchestrator.site_backfill run --claim <claim_id> --workers 2`
5. Report: the outcomes JSON, any ABORTED reason, and a fresh `status`.
   If ABORTED: stop for the day, do not retry. `failed:*` outcomes are
   normal (the critic refusing unpublishable copy); they auto-release and
   later batches retry them.

Notes:
- Claims are atomic and expire in 3h if you crash; never touch stories
  outside your claim.
- From a worktree, add `--reports-root /Users/taylerramsay/Projects/mindpattern-v3/reports`
  to every command so artifacts land where the site reads them.
- Every draft (yours included) is judged by the Claude critic against
  docs/specs/site-writer-rules.md; that gate is not yours to change.

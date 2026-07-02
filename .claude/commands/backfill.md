---
description: Run one claimed batch of the Rabbit Hole story backfill (any agent, safe in parallel)
---

/goal Run one batch of the Rabbit Hole story backfill as a claim-holding
operator, then report.

You are an OPERATOR, not a developer: never edit/write/delete repo files,
never commit, never kill processes you did not start, never run `run.py`,
never deploy. Your only writes are the artifacts the backfill produces.

Workflow (all from the repo root, using .venv/bin/python):

1. Preconditions — skip the batch and report why if any fail:
   - `/tmp/mindpattern-ran-$(date +%F)` and `/tmp/mindpattern-synced-$(date +%F)`
     exist (today's newsletter is delivered and synced), and it is after 13:00.
   - `claude -p "reply ok" --max-turns 8 --output-format text` prints "ok"
     (skip this check if you were told to use the codex provider).
2. See the world:
   `.venv/bin/python -m orchestrator.site_backfill status`
   If remaining_unclaimed is 0, report the status JSON and stop: done.
3. Claim your batch (pick a unique agent name, e.g. claude-op-1 / codex-op-1):
   `.venv/bin/python -m orchestrator.site_backfill claim --size 50 --agent <name>`
4. Run it (2-4h). Default provider is Claude; use codex only if told to:
   `MP_SITE_STORY_WRITER=claude .venv/bin/python -m orchestrator.site_backfill run --claim <claim_id> --workers 2`
   (codex provider: `MP_SITE_STORY_WRITER=codex`, spends Codex quota instead)
5. Report: the outcomes JSON, any ABORTED reason, and a fresh `status`.
   If ABORTED on usage_limit: stop for the day, do not retry.
   `failed:*` outcomes are normal (the critic refusing unpublishable copy);
   those stories were auto-released and later batches retry them.

Notes:
- Claims make parallel agents safe: your claim is yours alone and expires in
  3h if you crash. Never touch stories outside your claim.
- If you are running inside a git worktree, pass the canonical data root:
  `--reports-root /Users/taylerramsay/Projects/mindpattern-v3/reports`
  on every command, so artifacts land where the site reads them.

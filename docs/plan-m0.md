# Implementation Plan: M0 — Foundation

Spec: `docs/spec-v4.md` (v1.0). Audit refs: `docs/audit-2026-06-11.md`.
Principle: contract tests land FIRST, then every change is verified against them.
Every task leaves the system deployable; the newsletter never misses a morning.

## Architecture Decisions

- **Lock down `dashboard/` in place, rename to `api/` at the end of M0** — moving files before
  tests exist invites silent breakage; the contract tests make the rename mechanical.
- **Default-deny via middleware** using the existing-but-unwired `is_public_route` allowlist
  (the auth model v3 intended but never installed). Public = the 12 Vercel GET endpoints,
  `/mcp`, `/healthz`, `/data/art/*`. Everything else: bearer token or 401.
- **`core/` is new code; v3 modules adopt it incrementally** — M0 wires receipts/llm-gate into
  the highest-risk paths only (DELIVER, SOCIAL, posts handler); full adoption happens as
  M1-M3 touch each module.
- **History purge is the only destructive task** — isolated as the final task, requires explicit
  owner go-ahead at execution time (force-push rewrites remote history).

## Task List

### Phase A — Safety net (build before touching anything)

**Task 1: Vercel API contract tests** (M, ~2 files)
- Snapshot live responses from the 12 GET endpoints + /mcp into fixtures; derive shape
  assertions from `vercel-mindpattern/src/lib/types.ts`.
- Accept: one test per endpoint asserting status + response shape; runnable against local app
  (TestClient) and `--live` against mindpattern.fly.dev.
- Verify: `.venv/bin/python3 -m pytest tests/test_api_contract.py -q` green against the deployed app.
- Deps: none. Files: `tests/test_api_contract.py`, `tests/fixtures/api/*.json`.

**Task 2: Fix the 7 failing v3 tests** (S-M)
- test_compile ×2, test_cors ×2, test_mirror, test_sync, test_trend_history — fix or delete
  with their dead modules (per audit). A green baseline is required before any refactor.
- Accept: `pytest tests/ -q` → 0 failures.
- Deps: none.

### Checkpoint A: full suite green incl. contract tests · baseline tagged `pre-m0` in git

### Phase B — The substrate (`core/`)

**Task 3: `core/db.py` + `core/time.py`** (S, 2 files + tests)
- Connection manager (WAL, `with db:` transactions, one open/close discipline), `now_utc()` —
  the single timestamp format.
- Accept: context-manager rollback test passes (orphan-row bug class, audit findings.py:501);
  all timestamps from one helper.
- Deps: none.

**Task 4: `core/migrations.py`** (S)
- `PRAGMA user_version` ladder; migration 001 = baseline-stamp existing schema; 002 = receipts
  + journal tables.
- Accept: fresh DB and existing memory.db both migrate to same user_version; idempotent re-run.
- Deps: Task 3.

**Task 5: `core/receipts.py` + kill switch** (S)
- `claim(action_key) -> bool` (INSERT OR IGNORE on e.g. `newsletter:2026-06-12`,
  `post:bluesky:2026-06-12:<hash>`); `MP_DISABLE_OUTBOUND=1` check helper every outbound
  path must call.
- Accept: double-claim returns False; kill switch test; documented action-key scheme.
- Deps: Task 4.

**Task 6: `core/llm.py` — the single claude gate** (M)
- Popen + start_new_session + killpg (the pattern from agents.py:392 that run_claude_prompt
  lacks — audit HIGH), JSON-schema validation, one retry-with-error-feedback, never raises.
- Accept: timeout kills the whole process group (mocked); `{"findings": null}`-class garbage
  returns None instead of propagating (audit agents.py:514).
- Deps: none. (Adoption by callers is incremental; M0 wires it into the posts handler + expeditor.)

### Checkpoint B: suite green · `core/` at 100% test coverage (it's small; it's the foundation)

### Phase C — The perimeter

**Task 7: Default-deny auth middleware** (M)
- Install middleware enforcing `is_public_route` (dashboard/auth.py:34 — exists, unwired);
  allowlist = 12 Vercel GETs, /mcp, /healthz, /data/art. Shared-secret header auth for the
  pipeline's `/api/approvals` POST/poll (audit HIGH api.py:832).
- Accept: contract tests still green; `POST /api/editors-desk/{id}/approve`,
  `/prompts/{agent}/revert`, `/api/engagement/post` → 401 without token; approvals work with
  the pipeline secret.
- Deps: Task 1. Files: dashboard/app.py, dashboard/auth.py, orchestrator side of approvals.

**Task 8: Kill the `/data` mount + input validation** (S)
- Replace `app.mount("/data", ...)` (audit CRITICAL app.py:54) with an art-only static dir;
  `_valid_date()` on report routes (path traversal, api.py:572); `^[a-z0-9_-]+$` on `user`
  params (api.py:74).
- Accept: `GET /data/ramsay/memory.db` → 404; art still serves; traversal test fails closed.
- Deps: Task 7.

**Task 9: Container hardening** (S)
- `tini` as PID 1 (signal forwarding/zombie reaping — audit start.sh), non-root `USER`,
  stop COPYing `social-config.json`/`users.json` into the image (read from /data volume).
- Accept: SIGTERM reaches both processes (graceful bot shutdown fires); container runs unprivileged.
- Deps: none. Files: Dockerfile, start.sh, fly.toml.

### Checkpoint C: deploy to Fly · contract tests `--live` green · mindpattern.ai site fully working · DB no longer downloadable

### Phase D — The action boundary

**Task 10: Posting truthfulness** (M)
- Check `success` flag in `_post_with_jitter`/`_post_pending` (audit CRITICAL pipeline.py:781);
  record failures as failures; receipts (Task 5) claimed before every platform post;
  PostsHandler honors `enabled` flags (verified live 2026-06-11); per-run expeditor verdict
  file (tempfile, not the shared `expedite-verdict.json`).
- Accept: mocked 4xx → stored `posted=False` + Slack shows the error; disabled platform never
  posts; two concurrent pipelines don't collide.
- Deps: Task 5.

**Task 11: Strict approval parsing** (M)
- `approval.py`: explicit affirmative tokens only ("go/all/yes/post"/platform names), anything
  else = no-decision; thread-scoped polling (audit CRITICAL approval.py:577); approver
  allowlist = owner user ID; full draft text shown (no 500-char truncation); Expeditor verdict
  displayed loudly in the approval message. Same parser fixes in `slack_bot/handlers/posts.py`
  ("skip linkedin" must skip — audit posts.py:287).
- Accept: parser table-test: "wait"/"hold on"/"skip linkedin"/"why?" all → no post;
  non-owner replies ignored.
- Deps: none (parallel-safe with 10).

**Task 12: Bot hardening** (M)
- Fail-closed owner check (bot.py:64), event dedup by `event_ts` TTL set (bot.py:127),
  handler dispatch on a dedicated executor (stop blocking the socket pool, base.py:78),
  heartbeat file the bot touches every 30s + `/healthz` fails if stale >2 min (root cause of
  the 2026-06-11 outage).
- Accept: no-owner-configured → bot refuses commands; duplicate event processed once;
  stale heartbeat → healthz 503 (Fly auto-restarts).
- Deps: none.

**Task 13: Newsletter receipts + delivery truthfulness** (S)
- DELIVER claims `newsletter:{date}` receipt before send; broadcast records per-recipient;
  failed delivery alerts Slack instead of logging-and-completing (audit runner.py:888);
  fix `e.response is not None` retry bug (newsletter.py:560); markdown2 `safe_mode="escape"`.
- Accept: simulated crash-after-send + resume → zero duplicate emails (the audit's
  double-send scenario, now a test).
- Deps: Task 5.

**Task 14: De-fang research agents** (S)
- Remove `Bash` and `Agent` from `AGENT_ALLOWED_TOOLS` (audit CRITICAL agents.py:52);
  remove `WebFetch` from the harness research agent; make `--dry-run` real (forces
  MP_DISABLE_OUTBOUND).
- Accept: dispatched agent tool list contains no shell; dry-run sends/posts nothing (test).
- Deps: Task 5 (kill switch).

### Checkpoint D: suite green · manual phone test: message → drafts → "wait" does NOT post → "skip" works → approve posts exactly once

### Phase E — Data flow & cleanup

**Task 15: Fly→Mac journal** (M)
- Bot appends outbound events (phone posts, approvals, reactions) to `/data/journal.jsonl`;
  pipeline INIT pulls + ingests into memory.db (posts → social_posts so dedup/caps see them —
  audit HIGH posts.py:304); ingested offset tracked.
- Accept: phone-posted item appears in local memory.db next pipeline run; idempotent re-ingest.
- Deps: Tasks 4, 10.

**Task 16: Safe sync** (S)
- `Connection.backup()` snapshot instead of live-file tar (audit sync.py:230); remove stale
  `-wal/-shm` on Fly in the same remote command as extraction; call `restart_app()` after
  sync (sync.py:291 — exists, never called).
- Accept: sync test verifies snapshot consistency; remote replace leaves no stale WAL.
- Deps: none.

**Task 17: Dead-code deletion, round 1** (S)
- Claims mechanism, cost plumbing (`cost_log`, `log_cost`, `estimate_cost`), `Phase.EVOLVE`
  no-handler warning, `_web_approval`, `_defer_posts` half-feature, `findings_fts`,
  `migrate_existing_db` (superseded by Task 4), `traces_create_phase`/`complete_phase`.
- Accept: suite green; `grep` finds zero references to deleted names.
- Deps: Tasks 4, 13.

**Task 18: Git history purge** (S — ⚠ destructive, owner go-ahead at execution)
- `git rm --cached` + `git filter-repo` for `data/ramsay/memory.db.backup-small`,
  `data/memory.db`, `social-config.json`, `users.json`; broaden `.gitignore` (`*.db*`);
  coordinate force-push; local backup of the repo first.
- Accept: `git log --all -- <paths>` empty; clone-from-remote contains no DB/PII;
  fresh `git ls-files` clean.
- Deps: everything else merged (do last; history rewrite invalidates open branches).

### Checkpoint M0 complete (= spec success criteria)
- [ ] Contract tests green against deployed Fly app; mindpattern.ai works
- [ ] Raw DB not downloadable; non-allowlisted routes 401
- [ ] Kill-and-resume run: zero duplicate emails/posts (receipt tests)
- [ ] "wait" in approval thread does not post; failed post recorded as failed
- [ ] Bot heartbeat: kill socket → Fly restarts machine inside 2 min
- [ ] Phone post appears in local memory.db after next pipeline run
- [ ] History contains no DB/PII files

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Auth middleware breaks the Vercel site | High | Task 1 ships first; contract tests run `--live` after every deploy |
| Deploy during the 7 AM pipeline SYNC window corrupts upload | Med | Deploy window: never 6 AM–12 PM (existing launchd guard convention; sync truncation lesson 2026-06-10) |
| History force-push breaks something that pulls main (run-launchd.sh auto-pulls!) | Med | Task 18 last + owner-coordinated; re-clone/reset the Mac checkout immediately after |
| Receipt keys too coarse (block legitimate re-sends) | Low | Keys include date + content hash; receipts table has a manual-override delete |
| Two-process container quirks resurface under tini | Low | Task 9 deployed alone, verified via heartbeat + contract tests before Phase D |

## Estimated Effort

18 tasks, all S/M. Roughly: Phase A+B in one day's session, C+D each a day, E a day —
~4–5 working sessions for M0, matching the spec's "~1 week".

## Open Questions

None blocking — Task 18's force-push timing is the only owner-coordination point, and it's
deliberately last.

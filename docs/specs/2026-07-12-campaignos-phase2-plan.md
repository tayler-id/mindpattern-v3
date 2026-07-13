# Phase 2: CampaignOS implementation plan and task list

- **Status:** **Approved by Tayler on 2026-07-12** (G1). Gates G2–G6 remain closed until individually approved
- **Date:** 2026-07-12
- **Governing spec:** `2026-07-11-campaignos-four-campaign-pilot-spec.md` (approved 2026-07-12, Decisions 1–5 and 7–9; Decision 6 open, due before campaign 1 launch)
- **Target repository:** `~/Projects/campaignos` (created by task T1)
- **Ceilings (from Decision 9):** 80 engineering execution hours + 12 active owner-review hours through private rehearsal. Reaching either ceiling pauses work; sunk cost is not permission to continue.

## 1. Estimate

Base estimate **72 hours** engineering; the 80-hour ceiling leaves an 8-hour (11%) buffer. If actuals threaten the ceiling, apply the scope-cut ladder in section 5 rather than eroding quality gates.

| Stage | Work | Est. hours |
|---|---|---:|
| S0 | Repo scaffold: git init, venv, pyproject, pytest config, README, repo CLAUDE.md, .gitignore (data/, artifacts/) | 3 |
| S1 | `contracts.py` typed records + `store.py` SQLite migrations, optimistic `transition_campaign`, campaign state machine | 8 |
| S2 | `locks.py` (own atomic lock, stale recovery, conservative mindpattern busy check, 06:45–13:00 window guard), `outbound.py` kill-switch boundary, sanitized Claude CLI invocation module with version/flag/auth preflight | 8 |
| S3 | `candidates.py` (raw-byte snapshot, SHA-256 identity, ambiguity rejection incl. same-date variants), `evidence.py` claim lock, `prompts.py`, manual source import | 9 |
| S4 | `drafting.py` + `validation.py` (claim coverage, exact quotes, originality rubric records, policy/accessibility checks, visual-only-reference scan) | 9 |
| S5 | Media: `providers/` (base, fake, macos_tts), `render/cards.py` Pillow templates, `render/ffmpeg.py` composition/probe, caption timing via per-segment TTS durations, loudness/blank-frame/caption gates | 12 |
| S6 | `bundle.py` core/leaf/audit hash manifest, `review.py` single-review checklist + scores, `slack_approval.py` durable nonce lifecycle | 8 |
| S7 | `attempts.py` slot lifecycle + five-minute window + UNCERTAIN reconciliation, `metrics.py` null-preserving imports + outcome cards, `learning.py` proposals | 6 |
| S8 | mindpattern-v3 touch points: story revision-hash endpoint + deterministic slug resolution; analytics extension (`events_db.py`, `site_analytics.py`, rabbit-hole `analytics.ts`) — each behind its own ask-first gate | 8 |
| S9 | Security/injection fixtures, static no-publisher/no-fetcher assertions, crash-injection suite | 5 |
| S10 | Rehearsal: synthetic offline campaign, real-story private rehearsal, crash/restart drills, minute measurement | 4 |
| | **Total** | **72** |

**Owner-hour budget (12h):** plan review 1h · pilot.db schema review 1h · FFmpeg install decision 0.5h · mindpattern endpoint + analytics reviews 1.5h · ElevenLabs/voice setup 2h · synthetic + private rehearsal reviews 3h · buffer 3h.

## 2. Dependency order and parallelism

```
S0 → S1 → S2 ─┬→ S3 → S4 ─┬→ S6 → S7 → S10
              │            │
              └→ S5 ───────┘        S8 (independent; any time after S0, gated)
                                    S9 (grows alongside every stage; final sweep after S7)
```

- S5 (media) depends only on S2's outbound boundary and can proceed in parallel with S3/S4.
- S8 (mindpattern touch points) is independent of the campaignos codebase and can be scheduled around the daily pipeline; the revision-hash endpoint must land before the first *real-story* rehearsal (S10 step 2), and the analytics extension before campaign 1 launch.
- S9 is not a phase-end afterthought: each stage lands with its tests; S9 is the adversarial fixture sweep on top.

## 3. Verification checkpoints

1. **After S1:** full state-machine round-trip offline; crash/resume at every commit point; stale expected-version rejected.
2. **After S2:** preflight proves subscription auth + all required CLI flags on the installed version; injected fake `ANTHROPIC_API_KEY`/provider creds are stripped or block; busy check loses to all three fixture mindpattern lock states.
3. **After S4:** a seeded unsupported claim, altered quote, and visual-only reference each block validation.
4. **After S5:** fake-provider render produces a probe-passing MP4/MP3/captions from fixtures with `MP_DISABLE_OUTBOUND=1`; a live-provider call under that flag is a test failure.
5. **After S6:** wrong-hash approval rejected; core edit invalidates all leaves; leaf edit invalidates one; Slack `SENDING` crash → `UNCERTAIN_APPROVAL_REQUEST` reconciled by nonce.
6. **After S7:** duplicate create on an `UNCERTAIN` slot blocked; five-minute expiry cancels untouched attempts.
7. **S10 gates the launch decision:** rehearsal completes the spec's seven-step safe end-to-end list; owner review measured ≤45 min.

## 4. Ask-first checkpoints (each needs a separate yes)

| # | Gate | Proposal |
|---|---|---|
| G1 | This plan | Approve estimate, order, and task list below |
| G2 | FFmpeg install (Decision 7 execution) | `brew install ffmpeg` (default GPL build; local composition only, nothing redistributed). Install outside 06:45–13:00 |
| G3 | `pilot.db` schema | Presented as migration 0001 before S1 merges |
| G4 | mindpattern revision-hash endpoint + deterministic slug fix | Small PR to `dashboard/routes/api.py`; includes rejecting/resolving same-date duplicate story files |
| G5 | Analytics extension | Cross-repo PRs per spec section 11 (aggregates only, session-scoped, opt-out preserved) |
| G6 | ElevenLabs live provider | Enabled only after rehearsal passes and Decision 6 is answered; first paid call is its own yes |

## 5. Scope-cut ladder (applied in order if the 80h ceiling is threatened)

1. Drop the Short template from the initial build (spec requires it only from campaign 2; build it between campaigns 1 and 2).
2. Reduce Pillow evidence-card templates from three visual treatments to two, keeping the three-scene evidence minimum.
3. Defer `learning.py` retrospective proposals to a manual owner-written retrospective for campaigns 1–2.
4. If still over: pause and return for a new owner decision (per Decision 9). Quality gates, security tests, and the approval/attempt lifecycles are never cut.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Caption timing per-segment TTS assembly proves inaccurate | Fallback is a separately approved aligner dependency (new G-gate); detected in S5, early enough to re-plan |
| Mindpattern lock paths change under CampaignOS | Busy-check paths are config, not constants; window guard is the backstop |
| Claude CLI update changes flag surface | Preflight pins supported version range and fails closed |
| Render time/heat on the Mac | Measured in S10 rehearsal before any public commitment |
| Estimate optimism | 11% buffer + scope-cut ladder + hard pause at 80h |

## 7. Task list (dependency-ordered)

- [ ] **T1 (S0):** Create `~/Projects/campaignos`: git init, `.venv`, `pyproject.toml`, `pytest.ini`, `.gitignore` (`data/`, `artifacts/`, `.venv/`), README, repo CLAUDE.md stating the spec's Always/Ask-first/Never boundaries.
  - Acceptance: `pytest` runs (0 tests) offline; repo has no network dependency.
  - Verify: fresh clone + `pytest -x -q`.
- [ ] **T2 (S1):** `contracts.py` — frozen dataclasses with `schema_version` for Campaign, Claim, ScriptSegment, Asset, Approval, Attempt, MetricImport; enum states and reason codes.
  - Acceptance: round-trip + unknown-field/version tests pass; malformed input raises typed errors.
  - Verify: `pytest tests/test_contracts.py`.
- [ ] **T3 (S1):** `store.py` — migration 0001 (**G3 gate before merge**), WAL, parameterized queries, `transition_campaign` with expected-version optimistic locking.
  - Acceptance: crash/resume at every commit boundary; stale version rejected; single-writer enforced.
  - Verify: `pytest tests/test_store.py` incl. crash-injection fixtures.
- [ ] **T4 (S2):** `locks.py` — atomic `mkdir` lock with token/PID/start metadata + race-tested stale recovery; read-only busy check against configured mindpattern lock paths; 06:45–13:00 window guard.
  - Acceptance: loses conservatively to dir-lock/flock/harness-lock fixtures; own-lock races deterministic.
  - Verify: `pytest tests/test_locks.py` (spawned-process race test).
- [ ] **T5 (S2):** `outbound.py` + `claude.py` — kill-switch checked before credential resolution on every external boundary; sanitized CLI invocation (allowlist env, scratch cwd, stdin prompt, `--safe-mode --tools "" --disable-slash-commands --strict-mcp-config --mcp-config '{"mcpServers":{}}' --no-chrome --no-session-persistence --json-schema`), version/flag/auth preflight, call/attempt/wall-time caps, `BLOCKED_MODEL_CAPACITY` classification.
  - Acceptance: injected paid-API/provider creds stripped or preflight blocks; `MP_DISABLE_OUTBOUND=1` blocks before any lookup; schema-validated outputs only.
  - Verify: `pytest tests/test_claude_boundary.py tests/test_security.py -k env`.
- [ ] **T6 (S3):** `candidates.py` — eligibility listing from `MINDPATTERN_REPORTS_DIR`, raw-byte snapshot, `story_revision_sha256`, rejection of any multi-file slug resolution (cross- or same-date), full-hash seed dedupe.
  - Acceptance: fixture with same-date bare/prefixed variants is rejected; re-seed converges on one campaign.
  - Verify: `pytest tests/test_candidates.py`.
- [ ] **T7 (S3):** `evidence.py` + `prompts.py` — 3–7 claim lock, two-model-attempt cap, manual source import (URL/time/hash/excerpt, ≤6 docs), static assertion of no network fetcher.
  - Acceptance: `REJECTED_EVIDENCE` exit paths work; injection fixtures in source text cannot alter policy or paths.
  - Verify: `pytest tests/test_evidence.py tests/test_security.py -k injection`.
- [ ] **T8 (S4):** `drafting.py` — script segments with claim IDs, scene plan, channel packages from locked claims only.
  - Acceptance: segment introducing an unlocked entity/number/date fails validation downstream.
  - Verify: `pytest tests/test_drafting.py`.
- [ ] **T9 (S4):** `validation.py` — 100% consequential-segment coverage, exact-quote match, originality rubric records, duplicate hard-fail, visual-only-reference scan, rights/disclosure presence.
  - Acceptance: each spec section-9 deterministic gate has a passing and a failing fixture.
  - Verify: `pytest tests/test_validation.py`.
- [ ] **T10 (S5):** `providers/` — base interface, deterministic fake, macOS `say` rehearsal provider; billable-slot fingerprint/estimate/cap records; `UNCERTAIN_PROVIDER` on ambiguity.
  - Acceptance: fake timeout/crash → `UNCERTAIN_PROVIDER`, duplicate spend blocked until reconciled.
  - Verify: `pytest tests/test_providers.py`.
- [ ] **T11 (S5, after G2):** `render/cards.py` + `render/ffmpeg.py` — Pillow evidence cards/thumbnail, FFmpeg composition, probe checks (duration, loudness ≈ −16 LKFS / TP ≤ −1 dBFS, blank frames, caption coverage), per-segment caption timing.
  - Acceptance: fixture render passes all probe gates; corrupted/blank/missing-caption fixtures fail.
  - Verify: `pytest tests/test_render.py` (skips gracefully if FFmpeg absent, but rehearsal requires it).
- [ ] **T12 (S6):** `bundle.py` — core/leaf/audit SHA-256 manifest with dependency-scoped invalidation.
  - Acceptance: core change invalidates all leaves; leaf change invalidates exactly one; hashes deterministic.
  - Verify: `pytest tests/test_bundle.py`.
- [ ] **T13 (S6):** `slack_approval.py` + `review.py` — durable READY→SENDING→AWAITING_OWNER lifecycle with nonce, idempotent owner-reply ingestion, fail-closed on missing owner identity; CLI review checklist with the five scores; `REHEARSAL_REVIEWED` cannot become `APPROVED`.
  - Acceptance: crash after SENDING → `UNCERTAIN_APPROVAL_REQUEST`; stale/duplicate reply cannot approve a new hash.
  - Verify: `pytest tests/test_approval.py` (mocked Slack transport).
- [ ] **T14 (S7):** `attempts.py` — one unresolved attempt per slot, destination-revision recheck, five-minute window (publish-action semantics for YouTube), `UNCERTAIN` blocking + explicit reconciliation.
  - Verify: `pytest tests/test_attempts.py`.
- [ ] **T15 (S7):** `metrics.py` + `learning.py` + `cli.py` wiring — null-with-reason imports, outcome cards, proposals-only retrospective; full CLI surface from spec section 13.
  - Acceptance: CLI dry run under `MP_DISABLE_OUTBOUND=1` makes zero network calls; no publish/reply/follow/like/vote/dm/upload command exists (static assertion).
  - Verify: `pytest tests/test_metrics.py tests/test_cli.py tests/test_security.py -k static`.
- [ ] **T16 (S8, G4 gate):** mindpattern-v3 PR — revision-hash endpoint for the story served at `/s/<slug>`, deterministic date-scoped slug resolution, rejection/logging of duplicate story files.
  - Verify: `mindpattern-v3: pytest tests/ -x -q`; manual curl of the new endpoint.
- [ ] **T17 (S8, G5 gate):** analytics extension — `memory/events_db.py` campaign/channel columns + validation, `site_analytics.py` private aggregate, rabbit-hole `analytics.ts` session-scoped UTM capture with opt-out and tag stripping.
  - Verify: both repos' tests + the spec's browser-test rehearsal step 6.
- [ ] **T18 (S9):** adversarial sweep — injection fixtures across story/source/community/platform text, path-escape fixtures, static no-fetcher/no-publisher assertions, crash-injection completeness pass.
  - Verify: `pytest tests/ -x -q` green, offline, no keys.
- [ ] **T19 (S10):** rehearsal — synthetic offline campaign end-to-end; then (owner yes on quota) real-story private rehearsal with Claude CLI + `say`; crash/restart drills; measure active minutes and render time.
  - Acceptance: the spec's seven-step safe-rehearsal list completes; owner review ≤45 min.
  - Verify: rehearsal report artifact + measured ledger; then request the separate campaign-1 launch decision.

## 8. Approval gate

This plan is approved when Tayler writes:

> I approve `2026-07-12-campaignos-phase2-plan.md`. Begin T1; gated items G2–G6 still require their own yes.

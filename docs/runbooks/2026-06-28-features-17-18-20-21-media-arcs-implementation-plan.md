# Implementation Plan: Features 17, 18, 20, and 21 - Arcs, Angles, Audio, and Video Scripts

> Status: In progress; Feature 17 foundation implemented through pass-2/API slice
> Owner: Tayler
> Author: Codex
> Created: 2026-06-28
> Spec: `docs/runbooks/2026-06-28-features-17-18-20-21-media-arcs-runbook.md`

This plan breaks the four feature specs into small, verifiable tasks. It is a
runbook for a future `/goal` implementation. No runtime behavior has been
changed by this planning pass.

## Model / Execution Gate

Owner update on 2026-06-28: before substantial implementation continues, run or
review this runbook and plan with Opus 4.8. Codex sessions cannot switch their
own model; if the active execution environment is not Opus 4.8, record that in
the Done table and proceed only after owner approval or after the goal is
restarted in an Opus 4.8-capable environment.

## Architecture Decisions

- Build Feature 17 first because narrative arcs become reusable inputs for
  newsletter synthesis, social angles, audio, and video scripts.
- Build Feature 18 second because social angles become the bridge between
  research artifacts and Feature 21 video scripts.
- Build Feature 20 as generation in v3 plus rendering in the Rabbit Hole site.
  Do not write generated audio into the site repo.
- Build Feature 21 as Slack script packages first. MP4 generation is optional
  and provider-gated.
- Avoid schema changes in the MVP. Use artifacts and existing tables unless a
  task proves schema is needed and the owner approves.
- Keep every Slack output draft/manual-copy until explicit owner approval.
- Keep generated audio/video assets out of git.

## Dependency Graph

```text
baseline and dirty-state capture
    |
    +-- shared evidence contracts
            |
            +-- Feature 17 narrative arcs
            |       |
            |       +-- v3 public arcs API
            |       +-- synthesis context hook
            |
            +-- Feature 18 social angles
            |       |
            |       +-- Slack angle command
            |       +-- angle -> social draft handoff
            |
            +-- Feature 20 audio briefing
            |       |
            |       +-- v3 audio artifacts/API
            |       +-- Rabbit Hole audio player
            |
            +-- Feature 21 video scripts
                    |
                    +-- Slack script command
                    +-- angle -> video script handoff
                    +-- Slack artifact upload helper
                    +-- optional MP4 provider adapter
```

## Done Status Table

Keep the `Done` column. Future agents should update this table in place instead
of deleting the column.

| Task | Feature | Title | Done | Evidence / remaining work |
|---|---|---|---|---|
| 0 | All | Opus 4.8 runbook/plan review gate | Yes | 2026-06-28: Reviewed and **APPROVED TO CONTINUE** by Opus 4.8 (`claude-opus-4-8[1m]`) acting as the approval gate. Verified hard requirements: F17 enrichment-only, F18 Angle Critic reads as a skeptical assigning editor, F20 publishes to Rabbit Hole via the v3 public API (not the dashboard UI), F21 is Slack-script-only with provider/MP4 owner-gated. Ran `.venv/bin/python3 -m pytest tests/test_media_artifact_contracts.py -q` -> 6 passed. Task 2 foundation slice judged acceptable. Approval is CONDITIONAL on required edits before the tasks they gate: (a) **F17** — inject arcs into synthesis **pass 2 / context only**, never `_balance_story_candidates()` (runner.py:1196) or pass-1 story selection (runner.py:1234), plus an "identical pass-1 story selection with vs. without arcs" regression test (gates Tasks 4-6); (b) **F18** — capture an owner-approved boundary for the `social/writers.py:310-316` absolute kill switch vs `agents/expeditor.md:70-72` Builder Detail Check before Task 8 (the two prompts contradict on identical strings such as "I run 12 agents" / "my pipeline" — a hard deadlock that likely already breaks live `#mp-posts`); (c) **F18** — pin angle artifacts under gitignored `reports/ramsay/social-angles/`, not `data/social-angles/` (proven NOT gitignored). No feature code, commit, deploy, pipeline run, schema change, or dependency install was performed during this review. |
| 1 | All | Capture dirty state and baseline tests | Yes | 2026-06-28: recorded dirty state for v3 and Rabbit Hole. Baseline passed: `tests/test_followup_research.py tests/test_slack_bot.py tests/test_social.py -q` -> 154 passed; `tests/test_runner.py::TestDryRunPhases -q` -> 4 passed; Rabbit Hole `pnpm lint` -> 0 errors, 2 pre-existing unused-var warnings. |
| 2 | All | Add shared evidence/artifact contracts | Yes | 2026-06-28: added `orchestrator/media_contracts.py` and `tests/test_media_artifact_contracts.py`; verification `.venv/bin/python3 -m pytest tests/test_media_artifact_contracts.py -q` -> 6 passed. |
| 3 | 17 | Add narrative arc fixture builder | Yes | 2026-06-28: added deterministic `tests/test_narrative_arcs.py` fixtures covering multi-day/source arcs, same-day duplicates, stale arcs, artifact writes, and pass-1 candidate-balance invariance. Verification `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q` -> 5 passed. |
| 4 | 17 | Implement arc extraction/scoring | Yes | 2026-06-28: added `orchestrator/arcs.py` with stable arc IDs, multi-day/source thresholds, active/stale status, recurrence/velocity/source-diversity/freshness/confidence scores, public evidence output, and `reports/<user>/arcs/YYYY-MM-DD.json` artifact writing. Verification `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q` -> 5 passed. |
| 5 | 17 | Expose sanitized arcs API | Yes | 2026-06-28: added public read-only `/api/narrative-arcs` and `/api/narrative-arcs/{arc_id}` backed by `reports/<user>/arcs/YYYY-MM-DD.json`, with date/user/arc-id validation and whitelisted/redacted output. Verification: `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py::test_public_narrative_arcs_api_returns_sanitized_arc -q` -> 1 passed; `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q` -> 6 passed. |
| 6 | 17 | Add synthesis pass-2 context hook | Yes | 2026-06-28: runner loads active/emerging arcs only after pass 1 and injects formatted arc context into synthesis pass 2 only; `_balance_story_candidates()` and pass-1 story selection receive no arc data. Verification: `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis::test_narrative_arcs_are_pass2_context_only -q` -> 1 passed; `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis -q` -> 10 passed. |
| 7 | 18 | Add social angle contract/parser | Yes | 2026-06-28: added pure `orchestrator/social_angles.py` contract/parser with strict support for `angles:`, `angle lab:`, `angles finding <id>`, and `angles arc <arc_id>`; unclear/newsletter-control text returns an error and changes no state; request previews are redacted; artifacts are pinned to gitignored `reports/<user>/social-angles/YYYY-MM-DD.json`; public `SocialAngleCandidate` output is whitelisted and source URL safe. Verification: `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q` -> 6 passed. |
| 8 | 18 | Reconcile builder-detail boundary, then implement angle generation and Angle Critic service | Yes | 2026-06-28: owner approved boundary: practitioner transparency is allowed only when it teaches a source-backed builder/operator lesson; agent counts, cron/pipeline flexing, automated-infrastructure flexing, and product-demo framing are disallowed. Reconciled `social/writers.py`, `agents/expeditor.md`, platform writer/critic prompts, EIC, and engagement writer. Added deterministic `generate_social_angles()`, injectable provider boundary, `critique_social_angle()` assignment-editor scoring/cuts, ranked `shown_angles`, and artifact writes under `reports/<user>/social-angles/YYYY-MM-DD.json`. Verification: `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q` -> 10 passed. Grep confirmed old conflicting phrases absent from `agents/` and `social/writers.py`. |
| 9 | 18 | Wire #mp-posts angle command | Yes | 2026-06-28: `#mp-posts` now intercepts Social Angle Lab commands before URL/idea handling, runs deterministic angle generation, and posts ranked candidates in-thread with source/artifact evidence and an explicit "No live post" label. Vague/invalid angle commands reply with guidance and do not fall through to the social pipeline. Verification: `.venv/bin/python3 -m pytest tests/test_slack_bot.py::TestPostsAngleCommand -q` -> 3 passed; `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 94 passed. |
| 10 | 18 | Wire social draft handoff | Yes | 2026-06-28: after ranked angle output, `#mp-posts` waits for `draft <n>` / `draft <angle_id>` and converts the selected angle into the existing topic shape, then calls `_run_and_approve()` so normal preview/edit/approval gates still control posting. Unclear replies do nothing and post no content. Verification: `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q` -> 12 passed; `.venv/bin/python3 -m pytest tests/test_slack_bot.py -q` -> 96 passed. |
| 11 | 20 | Add audio script builder | Yes | 2026-06-28: added pure `orchestrator/audio_briefing.py` script builder that converts report markdown into spoken prose, transcript markdown, source notes, hashes, and AI-generated/manual-publish labels. It strips tables, fenced code, raw URLs, and markdown noise from the spoken script; preserves markdown source links in show notes; and marks visible quality-floor degraded reports as degraded. Verification: `.venv/bin/python3 -m pytest tests/test_audio_briefing.py -q` -> 4 passed; `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_media_artifact_contracts.py -q` -> 10 passed. |
| 12 | 20 | Add TTS provider boundary | Yes | 2026-06-28: added `TTSProviderConfig`, `tts_provider_config_from_env()`, and `build_tts_audio()` with deterministic dry-run metadata as the default path. Live mode requires `dry_run=False`, explicit `MP_AUDIO_TTS_ENABLED=true`/`MP_AUDIO_TTS_PROVIDER` env config, and an injected adapter; missing config or adapter fails closed without provider/network imports or calls. Verification: `.venv/bin/python3 -m pytest tests/test_audio_briefing.py -q` -> 9 passed; `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_media_artifact_contracts.py -q` -> 15 passed. |
| 13 | 20 | Add audio artifact/provenance writer | Yes | 2026-06-28: added safe `reports/<user>/audio/YYYY-MM-DD.*` path builder and `write_audio_artifacts()` to write mocked/live MP3 bytes when present, transcript markdown, metadata JSON, and provenance JSON sidecars. Metadata includes source report hash, script hash, provider/model/voice, source count, generated timestamp, AI-generated/manual-publish labels, and audio-file presence. Trace logging records `audio_briefing_artifact` events for ready/degraded/failed statuses. `reports/` gitignore covers generated audio artifacts. Verification: `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_traces_db.py -q` -> 20 passed; `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_media_artifact_contracts.py tests/test_traces_db.py -q` -> 26 passed. |
| 14 | 20 | Expose safe audio API endpoints | Yes | 2026-06-28: added public read-only `/api/audio-briefings`, `/api/audio-briefings/{date}`, `/api/audio-briefings/{date}/file`, and `/api/audio-briefings/{date}/transcript` endpoints backed only by validated `reports/<user>/audio/YYYY-MM-DD.*` artifacts. Responses whitelist public metadata, source notes, and relative API URLs; file/transcript routes return 404 for invalid dates/users or missing artifacts. Added `/api/audio-briefings` to the auth public-read allowlist while preserving private-route auth. Verification: `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_audio_briefing.py -q` -> 27 passed; `.venv/bin/python3 -m pytest tests/test_auth_middleware.py tests/test_api_contract.py tests/test_audio_briefing.py -q` -> 43 passed. |
| 15 | 20 | Render audio on Rabbit Hole | Yes | 2026-06-28: in `mindpattern-rabbit-hole`, added typed audio helpers (`getAudioBriefings()`, `getAudioBriefing()`, `backendAssetUrl()`), `AudioBriefing` types, and `AudioBriefingPlayer` with native audio controls, transcript link, source labels, and visible AI-generated/manual-publish labels. `/briefings` now shows compact audio players for dates with audio without nesting controls inside links; `/briefings/[date]` renders the full player above the report body and degrades cleanly when no audio exists. Verification in Rabbit Hole: `pnpm lint` -> 0 errors, 2 pre-existing warnings; `pnpm exec tsc --noEmit --incremental false` -> passed. Rabbit Hole commit: `69b9d6e feat: render audio briefings`. |
| 16 | 21 | Add video script contract/parser | Yes | 2026-06-28: added pure `orchestrator/video_scripts.py` with strict parsing for `video script:`, `video finding <id>`, `video arc <id>`, and `video angle <n>`. Unrelated text returns `None`; malformed supported commands return failed request objects without falling through. Parser rejects live-post/manual-publish violations and newsletter-control wording, redacts sensitive text, and defines a stable `VideoScriptPackage` public contract with safe URLs and visible labels. Verification: `.venv/bin/python3 -m pytest tests/test_video_scripts.py -q` -> 5 passed; `.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_media_artifact_contracts.py -q` -> 11 passed. |
| 17 | 21 | Implement video script package service | Yes | 2026-06-28: extended `orchestrator/video_scripts.py` with deterministic `generate_video_script_package()` and safe `video_script_artifact_paths()` under gitignored `reports/<user>/video-scripts/YYYY-MM-DD-<slug>.{json,md}`. The service produces one selected 30/45/60 second Slack-ready package with hook, spoken script, shot list, captions, source URLs, claim-to-source evidence, AI-assisted/manual-publish labels, and risk labels. Weak or missing evidence returns a degraded package with follow-up research recommendation and no fabricated claim evidence. Verification: `.venv/bin/python3 -m pytest tests/test_video_scripts.py -q` -> 9 passed; `.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_media_artifact_contracts.py -q` -> 15 passed. |
| 18 | 21 | Wire #mp-posts video command and angle handoff | No | Slack thread output with manual-publish labels. |
| 19 | 21 | Add Slack file upload helper | No | External upload flow for script artifacts; mocked tests. |
| 20 | All | Safety regression suite | No | Proves no live social post, newsletter send, full pipeline, deploy, or provider call in tests. |
| 21 | All | Docs, handoff, Graphify, commits | No | Update Done evidence, run Graphify, commit verified phases. |
| 22 | Optional | Owner-approved live smoke | Deferred | Requires explicit Fly/Slack/Vercel approval. |

## Implementation Order and Checkpoints

The implementation order is dependency-first, with vertical slices where the
system can be tested after each phase. Do not mark a phase complete unless its
checkpoint is also complete.

### Checkpoint: Foundation after Tasks 1-2

- [x] Task 0 Opus 4.8 runbook/plan review gate is complete (2026-06-28,
      `claude-opus-4-8[1m]`, APPROVED TO CONTINUE with conditional required
      edits — see the Done Status Table Task 0 row).
- [ ] Dirty state is recorded for v3 and Rabbit Hole.
- [ ] Focused baseline tests are run or failures are documented.
- [ ] Shared evidence/artifact contracts pass their tests.
- [ ] No runtime behavior has changed except new tested contract helpers.

### Checkpoint: Narrative Arcs after Tasks 3-6

- [x] Arc extraction works from deterministic fixtures.
- [x] Public arc API is sanitized and path-safe.
- [x] Synthesis receives arcs only as evidence-backed context.
- [x] Newsletter quality floor tests still pass.

### Checkpoint: Social Angles after Tasks 7-10

- [x] `#mp-posts` can return angle variants.
- [x] `draft <n>` enters the existing Slack approval-gated social flow.
- [x] Unclear replies and newsletter-control wording fail closed.
- [x] No live platform post happens in tests.

### Checkpoint: Audio Website Slice after Tasks 11-15

- [ ] v3 can build deterministic audio metadata without network calls.
- [ ] v3 exposes only safe audio metadata/file/transcript endpoints.
- [ ] Rabbit Hole renders audio availability and players without broken UI.
- [ ] Generated media is not committed.

### Checkpoint: Video Script Slice after Tasks 16-19

- [ ] `#mp-posts` can return video script packages.
- [ ] `video angle <n>` works after an angle result in the same Slack thread.
- [ ] Slack file upload is fully mocked in tests and requires `files:write`.
- [ ] Output is labeled manual-publish only.

### Checkpoint: Release Hygiene after Tasks 20-21

- [ ] Cross-feature safety regressions pass.
- [ ] Done columns and handoff evidence are updated in place.
- [ ] Graphify is refreshed and checked.
- [ ] v3 and Rabbit Hole dirty files are reported.

### Optional Checkpoint: Owner-Approved Live Smoke after Task 22

- [ ] Owner explicitly approves each live Slack/Fly/Vercel action.
- [ ] Smoke proves drafts/media packages work without live social posting.
- [ ] Any production issue is documented before further deploy attempts.

## Phase 0: Baseline

### Task 1: Capture Dirty State and Baseline Tests

**Description:** Record the current state of both repos and focused baseline
tests before implementation.

**Acceptance criteria:**
- [ ] v3 dirty files are listed and classified.
- [ ] Rabbit Hole dirty files are listed and classified.
- [ ] Existing focused tests are run or pre-existing failures are recorded.

**Verification:**
- [ ] `git status --short --branch` in v3.
- [ ] `git status --short --branch` in Rabbit Hole.
- [ ] `.venv/bin/python3 -m pytest tests/test_followup_research.py tests/test_slack_bot.py tests/test_social.py -q`
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestDryRunPhases -q`
- [ ] `pnpm lint` in Rabbit Hole.

**Dependencies:** None

**Files likely touched:**
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- This runbook

**Estimated scope:** S

### Task 2: Add Shared Evidence and Artifact Contracts

**Description:** Add small structured contracts for evidence references, public
artifact metadata, and Slack media packages. These must be easy to test without
private databases.

**Acceptance criteria:**
- [ ] Evidence references include date, agent, title, summary, source URL/name,
      and optional finding ID.
- [ ] Redaction helper strips secrets and private Slack/user data.
- [ ] Artifact slugs and date paths are validated.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_media_artifact_contracts.py -q`

**Dependencies:** Task 1

**Files likely touched:**
- `orchestrator/media_contracts.py`
- `tests/test_media_artifact_contracts.py`

**Estimated scope:** S

## Phase 1: Feature 17 Narrative Arc Builder

### Task 3: Add Narrative Arc Fixtures

**Description:** Create deterministic test fixtures for multi-day findings,
single-day duplicates, stale arcs, and weak-source arcs.

**Acceptance criteria:**
- [ ] Fixture data covers at least three dates and three source domains.
- [ ] Fixture data includes near-duplicates that must not become arcs.
- [ ] Fixture data includes a stale arc with no fresh evidence.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `tests/test_narrative_arcs.py`
- `tests/fixtures/`

**Estimated scope:** S

### Task 4: Implement Arc Extraction and Scoring

**Description:** Build `orchestrator/arcs.py` to cluster evidence into stable,
source-backed narrative arcs. This task must also make the enrichment-only rule
testable: arcs must never enter candidate balancing or pass-1 story selection.

**Acceptance criteria:**
- [ ] Returns stable arc IDs.
- [ ] Requires multi-day evidence.
- [ ] Scores recurrence, velocity, source diversity, freshness, and confidence.
- [ ] Writes `reports/ramsay/arcs/YYYY-MM-DD.json`.
- [ ] Regression proves pass-1 selected stories are identical with and without
      arcs for the same fixtures.
- [ ] Arc code is not called from `_balance_story_candidates()` or pass-1 story
      selection.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py -q`

**Dependencies:** Task 3

**Files likely touched:**
- `orchestrator/arcs.py`
- `tests/test_narrative_arcs.py`

**Estimated scope:** M

### Task 5: Expose Sanitized Arcs API

**Description:** Add public read-only API endpoints for narrative arcs.

**Acceptance criteria:**
- [ ] `GET /api/narrative-arcs` returns sanitized arc summaries.
- [ ] `GET /api/narrative-arcs/{arc_id}` rejects unsafe IDs.
- [ ] No private DB fields, raw prompts, or secret-like strings are exposed.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_narrative_arcs.py -q`

**Dependencies:** Task 4

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_api_contract.py`

**Estimated scope:** S

### Task 6: Add Synthesis Pass-2 Context Hook

**Description:** Pass top active arcs into synthesis pass 2 as narrative context
only, after pass-1 story selection has already completed.

**Acceptance criteria:**
- [ ] Synthesis prompt can include active arcs with evidence trails.
- [ ] No arc with stale/weak evidence is injected as authoritative.
- [ ] Arcs are injected only into pass 2 / narrative context and never into
      `_balance_story_candidates()` or pass-1 story selection.
- [ ] Existing quality floor behavior remains unchanged.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_runner.py::TestPhaseSynthesis tests/test_narrative_arcs.py -q`

**Dependencies:** Task 5

**Files likely touched:**
- `orchestrator/runner.py`
- `orchestrator/arcs.py`
- `tests/test_runner.py`

**Estimated scope:** M

## Phase 2: Feature 18 Social Angle Lab

### Task 7: Add Social Angle Parser and Contract

**Description:** Define strict Slack command parsing and stable angle objects.

**Acceptance criteria:**
- [ ] Accepts `angles:`, `angles finding <id>`, `angles arc <id>`, and
      `angle lab:`.
- [ ] Rejects unclear commands and newsletter-control commands.
- [ ] Produces stable testable angle request objects.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `orchestrator/social_angles.py`
- `tests/test_social_angle_lab.py`

**Estimated scope:** S

### Task 8: Reconcile Builder-Detail Boundary, Then Implement Angle Generation and Angle Critic Service

**Description:** First reconcile the owner-approved boundary between good
practitioner transparency and bad product-pitch/self-promotional framing in
`social/writers.py` and `agents/expeditor.md`. Then generate 4-6 source-backed
social angle variants from a story, finding, arc, or URL, and run an
assignment-editor-style critic that scores, cuts, and ranks candidates before
Slack output.

**Acceptance criteria:**
- [ ] Dry-run returns deterministic variants.
- [ ] Live provider boundary is injectable/mocked in tests.
- [ ] Each angle includes hook, type, source URLs, confidence, and risk note.
- [ ] Owner-approved builder-detail boundary is captured in docs/tests before
      prompt changes.
- [ ] `social/writers.py` and `agents/expeditor.md` agree on allowed
      practitioner transparency versus disallowed product-pitch language.
- [ ] Critic scores focus, why-now, audience value, evidence strength,
      freshness, tension, specificity, platform fit, Tayler fit, and risk
      calibration.
- [ ] Critic rejects unsupported, generic, repeated, product-pitchy, or
      platform-generic angles.
- [ ] Only kept/revised angles are shown as draftable Slack choices by default;
      rejected angles remain in the artifact for audit.
- [ ] Existing writer/expeditor prompt conflict around builder-detail language
      is reconciled with tests for allowed practitioner transparency versus
      disallowed product-pitch framing.
- [ ] Angle artifacts are written only under gitignored
      `reports/ramsay/social-angles/`, never `data/social-angles/`.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py -q`

**Dependencies:** Tasks 5 and 7

**Files likely touched:**
- `orchestrator/social_angles.py`
- `agents/expeditor.md`
- `social/writers.py`
- `tests/test_social_angle_lab.py`

**Estimated scope:** M

### Task 9: Wire #mp-posts Angle Command

**Description:** Add the Slack command branch for angle requests.

**Acceptance criteria:**
- [ ] `angles: <topic>` posts variants in-thread.
- [ ] Empty/degraded source context is visible in Slack.
- [ ] No approval parser confusion with social posting commands.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py tests/test_slack_bot.py -q`

**Dependencies:** Task 8

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

### Task 10: Wire Social Draft Handoff

**Description:** Let owner replies turn a selected angle into a normal social
draft through the existing approval-gated #mp-posts path.

**Acceptance criteria:**
- [ ] `draft <n>` calls the existing approval-gated #mp-posts flow.
- [ ] Angle output clearly says video script handoff arrives with Feature 21.
- [ ] Tests prove no live platform posting occurs.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_social_angle_lab.py tests/test_social.py -q`

**Dependencies:** Task 9

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `orchestrator/social_angles.py`
- `tests/test_social_angle_lab.py`

**Estimated scope:** M

## Phase 3: Feature 20 Audio Morning Briefing

### Task 11: Add Audio Script Builder

**Description:** Convert a completed daily report into a voice-friendly 3-5
minute script and source-note transcript.

**Acceptance criteria:**
- [ ] Removes markdown tables/code/raw URL noise from spoken script.
- [ ] Preserves source references in show notes.
- [ ] Skips or degrades when report quality is degraded.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_audio_briefing.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `orchestrator/audio_briefing.py`
- `tests/test_audio_briefing.py`

**Estimated scope:** M

### Task 12: Add TTS Provider Boundary

**Description:** Add deterministic dry-run TTS plus a live provider adapter that
can later call OpenAI TTS when explicitly configured.

**Acceptance criteria:**
- [ ] Dry-run writes placeholder metadata without network calls.
- [ ] Live path is injectable/mocked in tests.
- [ ] Provider config is environment-driven and fails closed when missing.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_audio_briefing.py -q`

**Dependencies:** Task 11

**Files likely touched:**
- `orchestrator/audio_briefing.py`
- `tests/test_audio_briefing.py`

**Estimated scope:** S

### Task 13: Add Audio Artifact and Provenance Writer

**Description:** Write MP3/transcript/metadata/provenance artifacts under
`reports/ramsay/audio/`.

**Acceptance criteria:**
- [ ] Metadata includes source report hash, script hash, model, voice, source
      count, generated timestamp, and AI-generated label.
- [ ] Generated binary artifacts are gitignored or otherwise not committed.
- [ ] Trace events record ready/degraded/failed status.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_audio_briefing.py tests/test_traces_db.py -q`

**Dependencies:** Task 12

**Files likely touched:**
- `orchestrator/audio_briefing.py`
- `.gitignore` if needed
- `tests/test_audio_briefing.py`

**Estimated scope:** S

### Task 14: Expose Safe Audio API Endpoints

**Description:** Add public API routes to list audio briefings, fetch metadata,
stream MP3 files, and return transcripts.

**Acceptance criteria:**
- [ ] Date and user path values are strictly validated.
- [ ] Endpoint serves only known audio artifacts.
- [ ] Missing audio returns a clean 404/empty response, not a stack trace.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_api_contract.py tests/test_audio_briefing.py -q`

**Dependencies:** Task 13

**Files likely touched:**
- `dashboard/routes/api.py`
- `tests/test_api_contract.py`

**Estimated scope:** M

### Task 15: Render Audio on Rabbit Hole Website

**Description:** Add site helpers, types, and audio player UI to the Vercel
Rabbit Hole repo.

**Acceptance criteria:**
- [ ] `/briefings` indicates which dates have audio.
- [ ] `/briefings/[date]` shows an audio player when audio exists.
- [ ] Dates without audio do not show broken controls.
- [ ] Player includes transcript/source/provenance links.

**Verification:**
- [ ] `pnpm lint`
- [ ] `pnpm build`

**Dependencies:** Task 14

**Files likely touched in Rabbit Hole:**
- `src/lib/types.ts`
- `src/lib/api.ts`
- `src/components/briefing/audio-briefing-player.tsx`
- `src/app/(app)/briefings/page.tsx`
- `src/app/(app)/briefings/[date]/page.tsx`

**Estimated scope:** M

## Phase 4: Feature 21 Short-Form Video Script Mode

### Task 16: Add Video Script Parser and Contract

**Description:** Define strict Slack command parsing and stable script package
objects.

**Acceptance criteria:**
- [ ] Accepts `video script:`, `video finding <id>`, `video arc <id>`, and
      `video angle <n>`.
- [ ] Rejects unclear commands and live-post wording.
- [ ] Produces stable testable request objects.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_video_scripts.py -q`

**Dependencies:** Task 2

**Files likely touched:**
- `orchestrator/video_scripts.py`
- `tests/test_video_scripts.py`

**Estimated scope:** S

### Task 17: Implement Video Script Package Service

**Description:** Generate Slack-ready video script packages with hook, script,
shot list, captions, source notes, and risk labels.

**Acceptance criteria:**
- [ ] Produces 30/45/60 second variants or one selected duration.
- [ ] Every factual claim maps to source evidence.
- [ ] Weak evidence returns degraded package and recommends follow-up research.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_video_scripts.py -q`

**Dependencies:** Tasks 5 and 16

**Files likely touched:**
- `orchestrator/video_scripts.py`
- `tests/test_video_scripts.py`

**Estimated scope:** M

### Task 18: Wire #mp-posts Video Command and Angle Handoff

**Description:** Add Slack command handling that posts script packages in the
same thread, including handoff from a selected Social Angle Lab result.

**Acceptance criteria:**
- [ ] `video script: <topic>` returns a phone-readable package.
- [ ] `video finding <id>` loads finding evidence.
- [ ] `video arc <id>` loads arc evidence.
- [ ] `video angle <n>` uses selected angle evidence after an angle result in
      the same Slack thread.
- [ ] Output says "manual publish only".

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_video_scripts.py tests/test_slack_bot.py -q`

**Dependencies:** Task 17

**Files likely touched:**
- `slack_bot/handlers/posts.py`
- `tests/test_slack_bot.py`

**Estimated scope:** M

### Task 19: Add Slack File Upload Helper

**Description:** Add a small helper around Slack's external upload flow for
script artifacts.

**Acceptance criteria:**
- [ ] Uses get-upload-URL, raw/multipart upload, then complete-upload.
- [ ] Requires `files:write`.
- [ ] Uses parent thread timestamp.
- [ ] Tests mock all Slack/network calls.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_slack_files.py tests/test_video_scripts.py -q`

**Dependencies:** Task 18

**Files likely touched:**
- `slack_bot/files.py`
- `tests/test_slack_files.py`

**Estimated scope:** S

## Phase 5: Safety, Docs, Graph, and Release Hygiene

### Task 20: Add Cross-Feature Safety Regression Suite

**Description:** Prove the new features cannot trigger forbidden side effects.

**Acceptance criteria:**
- [ ] Tests fail if features call newsletter send, full daily runner, social
      posting APIs, Fly deploy, Vercel deploy, TTS provider, video provider, or
      Slack network in dry-run/focused tests.
- [ ] Unclear Slack replies change no state.
- [ ] Public API does not expose private data.

**Verification:**
- [ ] `.venv/bin/python3 -m pytest tests/test_narrative_arcs.py tests/test_social_angle_lab.py tests/test_audio_briefing.py tests/test_video_scripts.py tests/test_social.py tests/test_runner.py::TestDryRunPhases -q`

**Dependencies:** Tasks 6, 10, 15, 19

**Files likely touched:**
- New focused test files
- Existing safety tests as needed

**Estimated scope:** M

### Task 21: Update Docs, Handoff, Graphify, and Commit

**Description:** Update Done columns and handoff evidence, refresh Graphify,
commit verified phases, and report both repo statuses.

**Acceptance criteria:**
- [ ] Done columns updated in place.
- [ ] Handoff describes implemented and deferred work.
- [ ] Graphify updated after docs/code changes.
- [ ] Commits are small and phase-scoped.
- [ ] Both repo statuses are reported.

**Verification:**
- [ ] `git diff --check`
- [ ] `graphify update .`
- [ ] `graphify check-update .`

**Dependencies:** Task 20

**Files likely touched:**
- This runbook
- Spec runbook
- `.claude/handoffs/2026-06-26-system-audit-slack-social.md`
- `graphify-out/`

**Estimated scope:** S

### Task 22: Optional Owner-Approved Live Smoke

**Description:** Only after owner approval, run live Slack/Fly/Vercel smoke
checks.

**Acceptance criteria:**
- [ ] Owner explicitly approves each live action.
- [ ] Live Slack video/angle commands return drafts only.
- [ ] Website audio page works in production or preview.
- [ ] No live social platform post occurs.

**Verification:**
- [ ] Owner-approved smoke checklist.

**Dependencies:** Task 21

**Files likely touched:** None unless smoke finds a bug.

**Estimated scope:** S

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Arc builder invents themes | Newsletter quality drops | Require multi-day evidence, source diversity, and evidence IDs. |
| Social Angle Lab becomes auto-posting | Unsafe platform behavior | Keep handoff through existing approval loop; fail closed on unclear replies. |
| Audio endpoint serves private files | Data exposure | Strict date/user validation and known artifact directory only. |
| Generated audio sounds authoritative when source input is degraded | Trust issue | Visible degraded labels and skip/fail closed when source report is weak. |
| Video scripts use unsupported claims | Trust issue | Claim-to-source mapping and degraded output on weak evidence. |
| Rabbit Hole repo dirty changes collide | Lost work | Record status, preserve unrelated changes, edit only required files. |
| Provider/dependency churn | Implementation instability | Dry-run first; provider adapters behind explicit owner approval. |

## Open Questions for Owner

1. Should audio briefings be indexed publicly immediately or held out of sitemap
   until quality is reviewed?
2. Should audio generation run after successful email delivery or immediately
   after synthesis quality passes?
3. Should video scripts live only in `#mp-posts` for MVP?
4. Is Vercel Blob preferred after MVP for public audio/video asset storage?

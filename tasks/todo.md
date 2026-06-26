# TODO — Voice A/B Implementation

> Lightweight checklist for `/build` sessions. Full task details in `tasks/plan.md`.

## Phase 0 — Prep
- [ ] **Task 1**: Confirm donor list, pick fallback writer
- [ ] **Task 2**: Collect donor samples (25–32 files, anonymized, gitignored) — **research subagent gathers from online sources**

**Checkpoint**: corpus ready, Tayler signs off

## Phase 1 — Foundations
- [ ] **Task 3**: Port prose-craft markdown (5 files: prose-review, craft-review, learn-review, pass-1, pass-2)
- [ ] **Task 4**: `voice/hard_fails.py` regex scrubber + tests
- [ ] **Task 5**: `voice/register.py` loader + tests
- [ ] **Task 6**: `voice/reviewers.py` dispatch wrappers + tests
- [ ] **Task 7**: Schema migration (3 voice tables in `memory/db.py`) + tests

**Checkpoint**: all foundations land green, no runtime change yet

## Phase 2 — Extraction
- [ ] **Task 8**: `voice/extract.py` CLI + run SICO Pass 1+2 → produce `voice-register.md`
- [ ] **Task 9**: Sanity-check register, fall back to single donor if mush

**Checkpoint**: `voice-register.md` reads as operational rules

## Phase 3 — Replay benchmark
- [ ] **Task 10**: Variant flag in `agents.py:139–150` + tests
- [ ] **Task 11**: Writer-input storage (`writer_inputs` table + pipeline write site) + tests — **CRITICAL GAP CLOSURE**
- [ ] **Task 12**: `voice/benchmark.py` replay CLI + tests
- [ ] **Task 13**: Run benchmark, decide

## ╔══ MAJOR CHECKPOINT — Variant B wins? ══╗
- [ ] If yes → Phase 4
- [ ] If no → iterate Tasks 8/9/12

## Phase 4 — Live integration foundations
- [ ] **Task 14**: `voice/snapshots.py` + tests
- [ ] **Task 15**: `request_voice_draft_approval()` in `social/approval.py` + tests
- [ ] **Task 16**: `voice_gate` config block in `social-config.json` + example file

**Checkpoint**: gate path tested in isolation, no live writer using it yet

## Phase 5 — Rollout
- [ ] **Task 17**: Wire Bluesky writer to voice gate
- [ ] **Task 18**: 3-day Bluesky shake-down
- [ ] **Task 19**: Wire LinkedIn writer to voice gate

**Checkpoint**: both social writers gated, snapshots accumulating

## Phase 6 — Learning loop
- [ ] **Task 20**: `voice/accumulator.py` + tests
- [ ] **Task 21**: `learn-review` dispatch in LEARN phase + tests
- [ ] **Task 22**: Daily eval report extension + tests

## Final
- [ ] All voice tests green
- [ ] Existing test suite still green
- [ ] Tayler signs off after 7 days of accumulated snapshots

---

## Open questions before `/build`

1. Backfill historical `writer_inputs`? (Recommend: skip)
2. Pre-split Task 12 into 12a/12b? (Recommend: wait and see)
3. Skip learn-review on zero-snapshot days? (Recommend: yes)
4. Sample collection mode: research subagent gathers online — **confirmed**

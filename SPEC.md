# SPEC: Voice A/B + Prose-Craft Integration

> Status: Draft v1 — awaiting user approval
> Owner: Tayler
> Created: 2026-04-12

## 1. Objective

Make mindpattern's writing agents (newsletter, LinkedIn, Bluesky) sound less like generic AI and more like **a real human writer whose work we admire** — not Tayler. Prove the change works with a **one-shot benchmark** against the current voice on curated topics, not a multi-week shadow run.

The non-goal is beating AI detectors. Per the prose-craft post, that's a 0.74 cliff with nothing in it; chasing it kills voice. We optimize for the new voice scoring better on our own dual reviewer (prose-review + craft-review) and on Tayler's edits captured through the Slack approval gate.

### Voice donors, not autobiography

Tayler is not the writing-sample source. We extract from a **blended corpus of 16 builder/founder/creator-economy essayists** whose voice mindpattern wants to inhabit. The output is `voice-register.md` — an operational feature description of *that tribe's craft*, not any one writer's and not Tayler's.

**The donor list (resolved):**

| Writer | Source | Notes |
|---|---|---|
| Paul Graham | paulgraham.com (essays) + twitter.com/paulg | Long essays; pull from essays archive, not tweets |
| Naval Ravikant | nav.al + twitter.com/naval | Pull thread-compilations and "Almanack" style entries |
| Sahil Lavingia | sahillavingia.com + twitter.com/shl | Founder essays |
| Shaan Puri | shaanpuri.com + twitter.com/ShaanVP | Pull thread-compilations |
| Alex Hormozi | acquisition.com/blog + twitter.com/AlexHormozi | Direct, declarative |
| Lara Acosta | linkedin.com/in/laraacostaaa | LinkedIn longform |
| Justin Welsh | justinwelsh.me + linkedin.com/in/justinwelsh | Solopreneur essays |
| Wes Kao | weskao.com + linkedin.com/in/weskao | Communication-craft posts |
| Amanda Natividad | amandanat.com + twitter.com/AmandaNativ | Marketing essays |
| Dickie Bush | dickiebush.com + twitter.com/dickiebush | Writing-craft posts |
| Anne-Laure Le Cunff | nesslabs.com | Researcher-essayist |
| Packy McCormick | notboring.co | Newsletter longform — closest format to mindpattern |
| Lenny Rachitsky | lennysnewsletter.com | Product newsletter |
| Dan Shipper | every.to | AI/tools essays |
| James Clear | jamesclear.com | Atomic, concrete-first |
| Morgan Housel | collabfund.com/blog | Story-driven, narrative |
| Tiago Forte | fortelabs.com | Knowledge-work essays |

**The blend hypothesis:** these 16 writers share a coherent register — short paragraphs, declarative confidence, personal-experience-as-evidence, hooks, no academic hedging, concrete-first openings. The Phase-1 extraction should find what's *structurally constant across all of them* and ignore what's idiosyncratic to any individual. If the blend produces mush instead of signal, the fallback is to pick one writer (Packy McCormick is closest to mindpattern's newsletter format) and re-extract.

**Source rules:**
- For Twitter-primary writers: pull thread compilations or tweetstorms, not single tweets. Need length — the post you sent specifically warns "samples need more than just a few sentences."
- For blog-primary writers: pull 1–2 representative essays per writer.
- Total target: **~25–32 samples** across the 16 writers (1–2 each).
- Anonymize as `Sample 1..N`. Dedupe Dickie Bush's two entries.

### Two goals, one pipeline change

1. **Better voice** — run SICO Phase-1 extraction once against the donor writer's public corpus, produce `voice-register.md`, wire it into the four writing agents (synthesis-writer, linkedin-writer, bluesky-writer, engagement-writer) alongside the existing `voice.md`.
2. **A/B benchmark** — pick N curated topics, generate both variants on each, score with prose-review + craft-review, output a comparison table. One sitting, decide same day.

## 2. What we reuse (no new infra)

| Capability | Existing component | How we reuse it |
|---|---|---|
| Agent dispatch | `orchestrator/agents.py` `run_single_agent()` / `run_claude_prompt()` | Call new reviewer agents the same way existing critics are called |
| Voice loading | `agents.py:148–150` (loads `soul.md`, `user.md`) | Add `voice_register.md` to the same load path, gated by `voice_variant` arg |
| Drafts on disk | `data/social-drafts/{platform}-draft.md` | Variant B writes to `*-draft.variant-b.md` siblings |
| Newsletter storage | `reports/{user_id}/{date_str}.md` | Variant B writes `{date_str}.variant-b.md` |
| Quality tracking | `prompt_tracker.record_version(quality_snapshot=...)` | Add `variant_id` column; one row per variant per run |
| Learning loop | LEARN phase in `runner.py` (already exists) | Dispatch new `learn-review` agent inside LEARN, not as a new phase |
| Long-term sub-threshold memory | `memory.db` (17+ tables already) | Add one new table `voice_accumulator` instead of accumulator markdown file |
| Test pattern | `tests/test_writers.py`, `tests/test_humanizer.py` | Add `tests/test_voice_register.py`, `tests/test_prose_review.py`, `tests/test_voice_ab.py` |

## 3. What we add (minimum surface area)

### 3.1 Files (markdown — pure prompts)

```
agents/prose-review.md          ← port from /tmp/prose-craft/agents/prose-review.md
agents/craft-review.md          ← port from /tmp/prose-craft/agents/craft-review.md
agents/learn-review.md          ← port from /tmp/prose-craft/agents/learn-review.md
data/ramsay/mindpattern/voice-register.md   ← Output of one-time SICO Phase-1 extraction
```

### 3.2 Python modules (additive — no edits to existing code beyond hook points)

```
voice/__init__.py
voice/register.py        ← load voice-register.md, return as prompt context
voice/reviewers.py       ← run_prose_review(draft) → findings dict; run_craft_review(draft) → findings dict
voice/hard_fails.py      ← regex-based banned-phrase scrubber (the auto-fix step prose-craft uses)
voice/snapshots.py       ← capture (generated, approved) pairs into memory.db
voice/accumulator.py     ← sub-threshold pattern memory (SQLite-backed)
voice/benchmark.py       ← one-shot A/B benchmark CLI (pre-promotion only)
```

**Existing files extended** (no new slack_bot handler — see §5.1 for why):
```
social/approval.py       ← add request_voice_draft_approval(draft, writer_name) method
                           that wraps existing _slack_approval() and captures snapshot
```

### 3.3 Database migration

One migration on `data/ramsay/memory.db`:

```sql
CREATE TABLE voice_benchmark_runs (
  benchmark_id TEXT,
  topic_id TEXT,
  variant_id TEXT,           -- 'A' (current) | 'B' (register)
  agent TEXT,                -- synthesis-writer | linkedin-writer | bluesky-writer
  draft_path TEXT,
  prose_score REAL,          -- aggregate prose-review findings (0..1, lower=better)
  craft_score REAL,          -- aggregate craft-review (0..1, higher=better)
  hard_fails_count INTEGER,
  created_at TEXT,
  PRIMARY KEY (benchmark_id, topic_id, variant_id, agent)
);

CREATE TABLE voice_snapshots (
  run_id TEXT,
  agent TEXT,
  generated TEXT,            -- raw output from writer (post hard-fails)
  approved TEXT,             -- what Tayler approved/edited in Slack
  edit_distance REAL,        -- difflib SequenceMatcher.ratio() between the two
  approval_action TEXT,      -- 'approve' | 'edit' | 'reject' | 'auto-timeout'
  created_at TEXT,
  PRIMARY KEY (run_id, agent)
);

CREATE TABLE voice_accumulator (
  pattern_hash TEXT PRIMARY KEY,
  pattern TEXT,
  proposed_fix TEXT,
  sessions_seen INTEGER,
  last_seen_run_id TEXT,
  status TEXT,               -- 'observing' | 'promoted' | 'stale'
  instances JSON
);
```

### 3.4 Hook points in existing code

Four small additive edits, no rewrites:

| File | Edit |
|---|---|
| `orchestrator/agents.py:148` | After loading soul/user, load `voice-register.md` when `voice_variant == 'B'`. Applies to all writers including newsletter. Pass-through unchanged for variant A. |
| `social/approval.py` (mirror existing `request_draft_approval` pattern) | Add `request_voice_draft_approval(draft, writer_name) → {action, approved_text, edit_distance}`. Internally calls existing `_slack_approval()` + `_slack_poll_replies()`, then captures snapshot via `voice.snapshots`. |
| `social/pipeline.py` writer steps | Existing draft-approval call sites already exist for LinkedIn and Bluesky. Switch them to the new voice-aware method so the snapshot is captured automatically. |
| `orchestrator/runner.py` LEARN phase | After existing learn logic, dispatch `learn-review` agent with `(generated, approved)` snapshot pairs from the past day. Promote sub-threshold patterns from `voice_accumulator` when threshold met. |

**Newsletter is intentionally not gated.** Per Tayler: approval gate is only for social writer posts. The newsletter is too long to manually approve every day, and Tayler isn't editing newsletters interactively — he reads them after delivery. Newsletter still uses the voice-register variant when promoted, and still gets scored by prose-review + craft-review during the benchmark, but it skips the Slack approval gate and skips live edit-capture. The learning loop in LEARN phase only learns from social writers, not the newsletter.

**Why no new slack_bot handler:** the existing slack_bot daemon and the orchestrator pipeline are separate processes that don't IPC. The orchestrator already calls `ApprovalGateway` directly (in-process) to post to #mp-approvals and synchronously block for replies via `_slack_poll_replies()` (4-hour default timeout). That's exactly the blocking pattern the voice gate needs. The bot daemon's existing handlers are reactive (Tayler messages bot first); ours is proactive (pipeline initiates). Reusing `ApprovalGateway` keeps the new code in one module and zero changes to the daemon.

The benchmark harness (§5) is **not** a hook into existing code — it's a standalone CLI (`python3 -m voice.benchmark`) that doesn't touch the daily pipeline or Slack at all.

That's it. No new pipeline phases. No new Slack daemon code. No changes to delivery, critics, or humanizer.

## 4. Voice register extraction (one-time, from blended donor corpus)

This is the SICO Phase-1 piece. Run once before the benchmark.

1. **Collect samples.** 1–2 representative pieces from each of the 16 donor writers (§1). For Twitter-primary writers, pull thread compilations or longform tweetstorms, not individual tweets. Target: ~25–32 samples total. Anonymize as `Sample 1..N` per prose-craft's mistake-from-experience: never label by source or content. The extractor anchors on metadata otherwise. Store in `data/voice-donor/samples/` (gitignored — respects donors' content; we never republish).
2. **Generate Claude baseline.** For ~10 of the samples, give Claude the same topic prompt and let it write a default response. Store as comparison set.
3. **Run Pass 1 extraction** with `setup/extraction/pass-1.md`. Compares baseline vs samples across 4 dimensions, outputs operational "do X" features.
4. **Run Pass 2 pressure test** with `setup/extraction/pass-2.md`. Rejects vague output ("uses varied sentence lengths"), demands specifics.
5. **Sanity-check the output.** If it reads like a list of generic blogging tips ("uses concrete examples," "varies sentence length") instead of specific operational rules ("opens with a 4–7 word concrete noun phrase before any abstraction"), the blend produced mush. Fallback: re-run with one writer only (start with Packy McCormick).
6. **Save** as `data/ramsay/mindpattern/voice-register.md`. This file IS committable — it's a feature description, not the donors' text.
7. Variant B is now wired up.

Use Opus for extraction. Re-runnable later as more samples accumulate or when swapping donors.

**Ethical note:** we extract structural/stylistic features for our own writing, never republish donor text. Output is a list of techniques, not a content corpus. Samples stay local and gitignored.

## 5. A/B mechanism (replay the last 5 runs)

Forget calendar time and forget inventing topics. The benchmark replays the **last 5 already-shipped pipeline runs** with variant B, then compares head-to-head against the variant A outputs that actually shipped. Real production inputs, paired comparison.

### The replay benchmark

For each of the last 5 run dates, mindpattern already has:
- The research findings that fed synthesis-writer (in `memory.db` `findings` table, keyed by `run_date`)
- The newsletter that shipped (in `reports/{user_id}/{date_str}.md`)
- The social drafts that posted (in `data/social-drafts/{platform}-draft.md` history, plus posting logs)

The benchmark loads each of those, regenerates with variant B against the *same inputs*, and scores both sides.

```
benchmark/
└── results/
    └── {benchmark_id}/
        ├── 2026-04-08-newsletter-variantA.md  ← copied from reports/
        ├── 2026-04-08-newsletter-variantB.md  ← regenerated
        ├── 2026-04-08-bluesky-variantA.md
        ├── 2026-04-08-bluesky-variantB.md
        ├── 2026-04-08-linkedin-variantA.md
        ├── 2026-04-08-linkedin-variantB.md
        ├── 2026-04-08-scores.json
        └── REPORT.md                          ← side-by-side comparison across all 5 days × 3 writers
```

Run: `python3 -m voice.benchmark --last 5`

For each (run_date × writer) cell:
1. **Variant A** = the file that actually shipped (already on disk).
2. **Variant B** = re-run the writer agent with `voice-register.md` loaded, against the same research findings / input data from that day.
3. Both go through prose-review + craft-review in parallel.
4. Hard-fails auto-fixed before scoring; counted.
5. Aggregate into `REPORT.md`.

Final `REPORT.md` is a per-writer table:

| Date | A prose↓ | B prose↓ | A craft↑ | B craft↑ | A hard-fails | B hard-fails | Winner |
|---|---|---|---|---|---|---|---|

Plus side-by-side excerpts (first 500 chars) and aggregate verdict.

### Why this is better than curated topics

- **Real inputs** — same research findings the production pipeline used, no synthetic topics that might game one variant or the other.
- **Free variant A** — already generated, already on disk. Half the work done.
- **Auditable** — Tayler can see "this is what shipped on April 8 vs what would have shipped with the new voice."
- **Re-runnable** — every time `voice-register.md` is tweaked, re-run against the same 5 dates and watch scores move.

### Prerequisite: input replay

For variant B to be a fair regeneration, mindpattern must preserve the inputs to each writer for past runs. From the explore pass, `findings` table in `memory.db` is keyed by `run_date` — so newsletter inputs are recoverable. Need to verify the same is true for LinkedIn and Bluesky drafts (whether the brief / topic / source URL trio that fed each writer is stored, or only the final draft). **Slice 9 in §12 handles this verification first** — if any input is missing, we either store it going forward (small migration) or fall back to curated topics for the writers where replay isn't possible.

### Cost

5 days × 3 writers × 1 regeneration = 15 generation calls + 30 review calls. ~$3–5. Cheap enough to re-run every iteration.

### Promotion decision

Manual. Tayler reads the report, decides. No threshold, no calendar gate. If the answer is "obvious yes," promote (swap which variant is default in `agents.py`). If "obvious no," tweak `voice-register.md` and re-run benchmark. If "mixed," look at which writer/topic combinations B wins on and consider per-writer registers later.

### After promotion: the live edit-capture loop

Once variant B is promoted to default, the benchmark stops being the feedback source. The Slack approval gate (§5.1) becomes the live signal — every approved post captures the edit distance between what was generated and what was approved, and feeds the daily learning loop.

### 5.1 Slack approval gate (the live edit-capture mechanism)

**Most of this already exists.** The discovery from exploring `slack_bot/` and `social/approval.py`:

- `social/approval.py` has `ApprovalGateway` with existing methods `request_draft_approval()` and `request_topic_approval()`.
- It posts to #mp-approvals (channel `C0ALSRHAATH`) via `_slack_approval()`.
- It blocks the calling thread via `_slack_poll_replies()` (10-sec poll, 4-hour default timeout).
- The orchestrator pipeline already calls it during the SOCIAL phase for LinkedIn and Bluesky drafts.
- The slack_bot daemon and the orchestrator are **separate processes** — the orchestrator calls `ApprovalGateway` directly, in-process. No IPC needed.

What's missing for the voice loop is just one thing: **snapshot capture.** The existing approval flow returns approve/reject but doesn't store the (generated, approved) pair anywhere. We add a new method `request_voice_draft_approval(draft, writer_name)` that wraps the existing `_slack_approval()` and additionally writes a row to `voice_snapshots` with both texts and computed edit distance.

Newsletter is **not** gated — Tayler doesn't want to approve it every morning; it's too long for that workflow. Newsletter still uses voice-register.md when promoted, and still gets benchmarked, but skips the live edit-capture loop. Learning happens from social writers only.

The new flow (social writers only):

```
Writer produces draft (variant A or B based on config flag)
  → social/approval.py: request_voice_draft_approval(draft, writer)
  → ApprovalGateway posts draft to #mp-approvals via existing _slack_approval()
  → Tayler replies in thread with edits OR "approve as-is" (existing pattern)
  → ApprovalGateway returns the reply (existing _slack_poll_replies())
  → NEW: voice/snapshots.py records (generated, approved, edit_distance, action)
  → Approved version flows to DELIVER / posting (existing path)
  → Next day's LEARN phase: learn-review reads snapshot pairs from past 24h
```

**Timeout behavior:** existing `ApprovalGateway` defaults to 4-hour timeout, configurable per-call. We add a per-writer config in `social-config.json`:

```json
"voice_gate": {
  "linkedin-writer":  { "enabled": true, "timeout_minutes": 30 },
  "bluesky-writer":   { "enabled": true, "timeout_minutes": 30 }
}
```

On timeout: auto-approve (publish the generated text as-is) and record the snapshot with `action='auto-timeout'`. Per Tayler's answer #2 — confirmed.

**No new slack_bot handler.** No new daemon code. The bot stays untouched. Everything runs in the orchestrator process via the existing `ApprovalGateway`.

## 6. The two reviewer agents

Both ported verbatim from prose-craft, with one adaptation: they read `voice-register.md` instead of `register.md` so they speak the same language as the writers.

**prose-review** — banned phrases, voice drift, AI patterns. Two output classes:
- **Hard fails** (banned vocabulary, em dashes, "Synchrony Bank", LinkedIn engagement vocabulary, etc.) — auto-fixed by `voice/hard_fails.py` regex pass before the draft is written.
- **Advisory findings** — logged to `voice_runs.prose_score`, surfaced in the daily evaluation report. Never auto-applied.

**craft-review** — naming, aphoristic destinations, central-point dwelling, structural literary devices, human-moment anchoring. Pure advisory. Five-dimension table goes into `voice_runs.craft_score` (mean of dimension ratings).

Both run in parallel via existing `run_single_agent()`.

## 7. The learning loop

This is the part that makes the system improve over time without constant manual rule-writing. It runs inside the existing LEARN phase.

After each run with a manual edit captured:
1. Three snapshots exist for each agent: post-review (raw generation), post-fixes (after hard_fails scrubber + advisory accepts), post-manual (Tayler's final edit).
2. `learn-review` agent reads all three, produces a diff analysis: what did Tayler change that the reviewers missed?
3. Each proposed change is tiered:
   - **Apply** (≥3 instances of the same pattern across recent runs) → write into `voice-register.md` or `prose-review.md` reviewer prompt directly. Commit.
   - **Hold** (1–2 instances) → store in `voice_accumulator` with `status='observing'`. Promote when threshold hit.
   - **Reinforce** (pattern matches existing rule but slipped through) → increment a "rule effectiveness" counter, surface weak rules in the next eval report.
4. Stale entries (no new instances in 30 days) get marked `status='stale'` and dropped on the next cleanup pass.

The learn-review agent uses Opus.

## 8. Code style

Follows existing project conventions (CLAUDE.md):

- Python 3.14, `str | None` over `Optional[str]`
- `logging.getLogger(__name__)`, INFO normal / WARNING non-critical
- Context managers for SQLite, WAL mode
- stdlib → third-party → local imports
- New module names lowercase, single-word where possible
- Comments only when WHY is non-obvious. Default to none.
- No new dependencies. `python-Levenshtein` is the one possible exception for edit-distance — if avoidable with stdlib `difflib.SequenceMatcher.ratio()`, use that instead.

## 9. Testing

Every new function gets at least one test. Tests must not require network or API keys — mock all subprocess calls to `claude` CLI.

| Test file | Coverage |
|---|---|
| `tests/test_voice_register.py` | Loading voice-register.md, frontmatter parsing, missing-file fallback |
| `tests/test_prose_review.py` | Mock claude CLI, parse findings JSON, hard-fail vs advisory split |
| `tests/test_craft_review.py` | Mock claude CLI, parse 5-dimension table, score aggregation |
| `tests/test_hard_fails.py` | Regex scrubber on golden inputs (em dashes, banned words, Synchrony) |
| `tests/test_voice_ab.py` | Shadow generation calls both variants, writes both files, records both rows |
| `tests/test_voice_snapshots.py` | Snapshot capture/retrieval at each stage |
| `tests/test_voice_accumulator.py` | Threshold promotion, staleness, dedup by pattern_hash |
| `tests/test_voice_runs_table.py` | Migration runs, schema matches, indexes present |
| `tests/test_learn_review.py` | Mock claude CLI, parse Apply/Hold/Reinforce tiering, integration with accumulator |

Run: `python3 -m pytest tests/test_voice_*.py -x -q`

## 10. Boundaries

**Always:**
- Run variant A as the source of truth for delivery until promotion is explicit.
- Capture the manual-edit snapshot whenever Tayler edits a draft after generation.
- Anonymize voice samples (`Sample 1..N`) — never label by content/source.
- Honor existing memory rules: never mention Synchrony Bank, LinkedIn is posting-only (engagement-writer's variant B must respect this), no em dashes in any output.
- Use Opus for extraction and learn-review per prose-craft findings.

**Ask first:**
- Promoting variant B to default. Always a manual call after reviewing the comparison report.
- Editing `voice.md` (the existing identity file). Variant B writes to `voice-register.md` so the existing file stays untouched.
- Adding any new dependency.
- Changing the schema of `voice_runs` after first launch (migrations are cheap but break comparison continuity).

**Never:**
- Try to game GPTZero or any AI detector. The whole post is about why this fails. Optimize for our reviewers and Tayler's edit distance, full stop.
- Auto-apply advisory findings. Hard fails get fixed, advisories get logged.
- Replace the existing humanizer, critics, or expeditor — they continue to run on variant A's output unchanged. The new reviewers run on top, not instead.
- Post variant B output to LinkedIn/Bluesky/X. Shadow only.
- Commit `voice-samples/` or `voice-register.md` if it contains private content. Both go in `.gitignore`.

## 11. Resolved decisions

All open questions answered:

- ✅ **Sample source:** blended corpus of 16 builder/founder/creator-economy essayists (full list in §1). One register to start.
- ✅ **Slack gate timeout:** 30-minute auto-approve, configurable per-writer.
- ✅ **First writer gated:** Bluesky → LinkedIn → newsletter (per §12).
- ✅ **Slack bot integration:** mindpattern already has a Slack bot with channel-based handler pattern. We extend it rather than build new — exploration of `slack_bot/` is the first task in Phase 2.
- ✅ **Daily learn cadence.**
- ✅ **One-shot benchmark on curated topics, not multi-week shadow.**

**The one risk to flag:** the blended-donor extraction might produce mush (generic blogging tips) instead of operational rules. Mitigation in §4 step 5 — sanity-check the Pass 1 output, fall back to a single-writer extraction (Packy McCormick first) if the blend fails.

## 12. Implementation order (when approved)

Two phases. Phase 1 = "ship the benchmark, decide on voice." Phase 2 = "wire promoted voice into the live pipeline with Slack gate." Don't start phase 2 until phase 1 produces a winner.

### Phase 1 — Benchmark (we do this first)

1. **Pick donor writer** (Tayler decides — see §11.1).
2. **Port markdown files** — `prose-review.md`, `craft-review.md`, `learn-review.md`, extraction prompts. Tests: file existence + frontmatter validation.
3. **Collect samples** — 10–18 essays from donor's public archive. Anonymize. Store in `data/voice-donor/samples/` (gitignored).
4. **Run SICO extraction** (Pass 1 → Pass 2). Produces `data/ramsay/mindpattern/voice-register.md`. Pause: Tayler reads and edits if needed.
5. **`voice/hard_fails.py`** — regex scrubber. Standalone, golden-input tests.
6. **`voice/reviewers.py`** — wraps `run_single_agent()` for prose-review + craft-review. Mocked-subprocess tests.
7. **`voice/register.py`** — loads voice-register.md, returns as prompt-context block.
8. **Migration** for `voice_benchmark_runs` + `voice_accumulator`. Tests: schema matches.
9. **Verify input replay availability.** Check `memory.db` to confirm the inputs to each writer (research findings for newsletter, brief/topic/source for socials) are stored per run_date. If any are missing, decide: store going forward via small schema addition, or fall back to curated topics for that writer only. Report findings before writing benchmark code.
10. **`voice/benchmark.py`** — the replay CLI (`python3 -m voice.benchmark --last 5`). Loads variant A from disk, regenerates variant B from stored inputs, runs reviewers on both, writes `REPORT.md`. Tests: end-to-end with mocked claude calls.
11. **Run the benchmark.** Read `REPORT.md`. Decide: promote, tweak voice-register, or pick a different donor.

**Stop here unless variant B wins.** If it doesn't, iterate on voice-register.md and re-run step 11. If a different donor is needed, return to step 1.

### Phase 2 — Live integration (after promotion)

12. **Hook `agents.py:148`** — load voice-register.md when variant flag is set. Default flag flips to B once promoted. Tests: variant switching.
13. **`voice/snapshots.py`** — persist (generated, approved, edit_distance, action) rows to `voice_snapshots`. Standalone, tested.
14. **Extend `social/approval.py`** — add `request_voice_draft_approval(draft, writer_name)` method that wraps existing `_slack_approval()` + `_slack_poll_replies()` and calls `voice.snapshots.record()` after the reply returns. Tests: mock the Slack client at the same boundary as existing approval tests.
15. **Add `voice_gate` config block** to `social-config.json` (per-writer enabled + timeout). Loader in `social/approval.py` reads it.
16. **Wire into Bluesky writer first** (lowest stakes). Switch the existing `request_draft_approval` call site in `social/pipeline.py` to `request_voice_draft_approval`. Run for ~3 days, validate snapshot rows accumulate, edit_distance computes correctly.
17. **Expand to LinkedIn writer.** Same one-line switch in pipeline.
18. **`voice/accumulator.py` + `learn-review` dispatch** in existing LEARN phase. Tests: tiered Apply/Hold/Reinforce promotion logic. Daily cadence. Reads social-writer snapshots only.
19. **Evaluation report extension** — surface "patterns the reviewers missed but Tayler edited" in the daily eval output. Existing eval at `tests/test_orchestrator.py` and the daily briefing handler are the integration points.

**Newsletter is not in this list** — it gets the voice-register variant via the agents.py:148 hook (slice 12) and gets scored in the benchmark (Phase 1), but no Slack gate, no snapshot capture, no learning from it.

Each slice gets a commit following project convention (`feat:`, `test:`, `refactor:`).

---

## Approval

Before any code is written, confirm:

- [ ] Objective and non-goal match what you want
- [ ] Reuse list is complete (nothing critical missed)
- [ ] Hook-point edits are acceptable (3 small additive edits to existing files)
- [ ] Schema additions to `memory.db` are OK
- [ ] Open questions in §11 have answers (or "decide later" is fine for some)
- [ ] Implementation order in §12 is the right shape

When you're ready, say "approved" and I'll start with slice 1.

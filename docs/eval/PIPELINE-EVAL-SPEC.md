# Spec: MindPattern v3 Pipeline Code Evaluation

**Date:** 2026-07-24 · **Status:** DRAFT — awaiting Tayler's approval
**Trigger:** 3-day degradation incident (Jul 22–24: agent refusals, coverage floor breaches, story collapse to 1) plus usage explosion (~5M output tokens/day since ~Jul 10). RCA so far is log-based inference; this eval grounds it in code.

## Objective

Produce a sectioned, evidence-based evaluation of the daily pipeline so Tayler
understands what functions exist, how they actually work, and which problems are
real (verified in code) vs. guessed (log inference). Each section ends with a
reviewed issue list; fixes are a separate phase after all sections are agreed.

Success looks like: Tayler can read each section and know (a) what the module
does, (b) how it does it, (c) what is broken or against best practice, with
file:line evidence for every claim.

## Assumptions I'm Making

1. Target is the **daily pipeline path only** (run.py → orchestrator/* → delivery/sync).
   slack_bot/ and harness/ are out of scope unless a section drags them in.
2. The Jul 22–24 incident findings are **hypotheses, not facts**, until verified in code:
   - H1: CLI auto-update (2.1.215→217, Jul 21) changed headless behavior → refusals
   - H2: Twitter scraper broke independently on Jul 22 (X page change)
   - H3: Story collapse = finding-pool depletion + dedup, not a site_content bug
   - H4: Quality gate "fails open" by design, with no alert path that reaches Tayler
3. Evaluation is **read-only** — no code changes until the fix phase is approved.
4. "Best practices" = current agentic-pipeline patterns (structured outputs,
   model pinning, checkpointing, observability, graceful degradation), checked
   against current published guidance during the relevant section, not from memory.

→ Correct any of these now; otherwise I proceed with them.

## Section Plan (one section per review cycle, in this order)

| # | Section | Modules (loc) | Key questions |
|---|---------|---------------|---------------|
| 1 | **Spine: state machine & runner** | pipeline.py (158), runner.py (2,447), checkpoint.py (157) | How a run flows; phase error handling; where quality gates live; H4 |
| 2 | **Agent dispatch layer** | agents.py (1,140), router.py (103) | How `claude -p` is invoked; prompt framing; retry/refusal handling; model pinning; H1 |
| 3 | **Inputs & preflight** | preflight/ (1,711), trending.py (99), journal_ingest.py (118) | Source health; twitter/arxiv failure modes; H2 |
| 4 | **Synthesis & newsletter** | newsletter.py (719), evaluator.py (859), followup.py (982), analyzer.py (536) | Quality floor math; single-source dominance; publish-as-is path |
| 5 | **Site content engine** (the usage hog) | site_content.py (1,374), site_content_engine.py (1,545), site_writer.py (401), site_critic.py (313), story_related.py (463) | Per-story session fan-out; dedup; cost levers; H3 |
| 6 | **Knowledge graph & site graph** | kg/ (1,193), site_graph.py (957), site_dossiers.py (233) | What KG build does nightly; growth vs. value |
| 7 | **Delivery, sync & cross-cutting** | sync.py (917), traces_db.py (995), observability.py (457), policies/ (522), prompt_tracker.py (533) | Alerting gap; policy gate false positives; trace usefulness |

Deferred unless promoted: audio_briefing, video_scripts, social_angles (social
is disabled), site_backfill, arcs, media_contracts, site_experts, site_copy_lint.

## Method (every section, same shape)

1. Read the module code in full (not grep excerpts).
2. Map: public functions, data in/out, side effects, callers.
3. Verify or kill any incident hypothesis touching the section.
4. Issue list: `[severity] file:line — claim — evidence — best-practice reference`.
5. Deliver as a short readable writeup; Tayler reviews before next section.

## Commands

- Tests: `python3 -m pytest tests/ -x -q` (91 files; no network/keys needed)
- KG check: `python3 -m harness.knowledge_graph check`
- Logs referenced: `reports/pipeline-YYYY-MM-DD.jsonl` (dated, authoritative),
  `reports/launchd-decisions.log` (dated), `reports/launchd-std{out,err}.log` (UNDATED — never
  use alone for day attribution)

## Boundaries

- **Always:** cite file:line for every issue; separate "verified" from "suspected";
  read modules fully before judging them.
- **Ask first:** expanding scope into slack_bot/ or harness/; running the pipeline;
  any code change; adding dependencies.
- **Never:** commit/push without Tayler's ask; edit code during the eval phase;
  present log inference as code fact.

## Success Criteria

- [ ] Each delivered section names every public function in its modules with a
      one-line "what it does / how"
- [ ] Every issue has file:line evidence and a severity
- [ ] All four hypotheses (H1–H4) end the eval as VERIFIED, REFUTED, or
      UNVERIFIABLE with reasons
- [ ] Tayler has reviewed each section before the next begins
- [ ] Final rollup: prioritized issue register ready to become the fix-phase spec

## Open Questions

1. Section order OK, or start with §2 (agent dispatch) since the live incident lives there?
2. Should cost/usage analysis (tokens per phase) be added as a §8, or folded into §5?
3. Is slack_bot/ delivery (Slack notifications) in scope for the alerting question in §7?

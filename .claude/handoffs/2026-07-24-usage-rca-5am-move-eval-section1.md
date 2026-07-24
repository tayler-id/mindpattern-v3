# Handoff: usage forensics, Jul 22–24 incident RCA, 5am schedule move, code-eval §1

**Date:** 2026-07-24 · **Session base dir:** ~/Projects (next session: start from this repo)
**State:** eval §1 read complete, writeup NOT yet delivered to Tayler; one manual step pending (pmset)

## 1. Usage forensics (why limits were getting killed)

- This pipeline is the top consumer: **1 session/day before Jul 10 → 270–410/day after**,
  ~3–6M output tokens/day. Driver is the SITE_CONTENT Rabbit Hole loop: one `claude -p`
  per story write (~160/day), per judge (~120/day), per knowledge-extraction (~100/day).
- Not the cause: deep-research (one FDE run Jul 21, ~13% of that day), the job-hunt cloud
  routine (`trig_014bgCsdhru5P4NfrJY3vhTT`, **disabled since Jul 18**, cloud env has
  outbound HTTP 403-blocked), graphify (AST-only, no API calls, was 9 days stale).
- Cost lever if wanted: cap/batch the story write→judge fan-out in site_content.

## 2. Jul 22–24 incident (RCA, log-verified; code verification in progress via eval)

Chain: CLI auto-updated 2.1.215→217 (Jul 21 pm) → research-agent refusals jumped
(2→5→6→6/day; agents return `{"findings": []}` or decline: "I'd be fabricating…",
"looks like an automated prompt pasted into an interactive session") → coverage 7/13
on Jul 23 AND Jul 24 (floor 8) → 3 days of same-7-agent findings → dedup (sim>0.90,
180-day window) exhausted the fresh pool → Jul 24: 2 candidates → **1 site story**
(normal 50–70). Independent same-day break: `twitter_cli` regex crash
(`'NoneType' .group`), 5/5 trend queries failing since Jul 22. Also Jul 24: policy gate
dropped a legit finding on the 'jailbreak' keyword; Mac slept through 6:55 wake
(battery) → 10:14 start.
- Models are pinned in `orchestrator/router.py` (`research_agent` → `claude-opus-4-8[1m]`
  since Jun) — Tayler's interactive `/model` changes did NOT affect the pipeline.
- No repo commits since Jul 13 → code change ruled out; CLI update is the changed variable.

## 3. Schedule move 7am → 5am (Tayler's request)

Done:
- `~/Library/LaunchAgents/com.mindpattern.pipeline.plist` + `deploy/` copy:
  StartCalendarInterval 07:00–11:45 → **05:00–09:45**; launchd booted out + bootstrapped,
  confirmed loaded with new times.
- `run-launchd.sh` window guard: hours 06–11 → **05–09** (would have skipped 5am fires).
- `graphify update .` run after the edit per repo rules.

PENDING (needs password, Tayler must run):
```
sudo pmset repeat wakeorpoweron MTWRFSU 04:55:00
```
Current wake is still 6:55AM. CAVEAT: macOS skips scheduled wakes on battery — the 5am
run only fires on time if the Mac is on AC power overnight (this is why Jul 24 started
at 10:14). Nothing was committed/pushed.

## 4. Code eval (spec-driven, in flight)

Spec: `docs/eval/PIPELINE-EVAL-SPEC.md` — 7 sections, read-only, one section per review
cycle, every issue needs file:line. Hypotheses H1–H4 must end VERIFIED/REFUTED.
Tayler approved starting with **§1 Spine** (pipeline.py, checkpoint.py, runner.py).

§1 status: all three files read in full; verification greps done; **writeup not yet
delivered**. Verified findings ready for the §1 report:

| Sev | Where | Finding |
|-----|-------|---------|
| HIGH | runner.py:2412–2441 `_send_alert` | Slack response body never checked — chat.postMessage returns HTTP 200 with `ok:false` on bad token/channel, so alert failures are invisible. Jul 24's quality alert "fired" (12:43:56 ERROR log) but Tayler saw nothing → likely silent Slack failure. Channel hardcoded `C0ALSRHAATH`. H4 partially verified: fails open BY DESIGN (2026-07-13 incident), alert exists but delivery unverifiable. |
| HIGH | runner.py:1697 + 1817 | `fail_retryable` quality status never retries: ran-marker is written on delivery success regardless of quality, so the wrapper's backup windows (the retry mechanism) never fire for quality failures — only for delivery failures. "Retryable" is aspirational naming. |
| MED | runner.py:655 + checkpoint.py:93–101 | Failed non-critical phases are checkpointed with `{"error":…}`; `get_completed_phases()` counts every row as completed → crash-resume permanently skips a failed phase. |
| MED | runner.py:1298–1324 vs policies engine | Two conflicting security-finding mechanisms: synthesis `_sanitize_finding` wraps (title mangled into published output), storage policy gate DROPS (Jul 24: legit multi-agent-security finding lost to 'jailbreak' substring). |
| LOW | runner.py:1093 | `self.research_quality` write-only (dead state). |
| LOW | runner.py:2324 | `_collect_all_skill_files` defined, never called (dead code). |
| LOW | pipeline.py:80,97 | `_phase_start_time` set, never read; `summary()` has no caller found in repo. |
| LOW | checkpoint.py:24,72,98 | `created_at` second-granularity ordering — same-second checkpoint ties can misorder resume (benign direction). |
| INFO | run.py:136–149 | `MP_LAUNCHD_SKIP_SOCIAL` → `--skip-social` → `MP_SKIP_SOCIAL` mapping confirmed; social/engagement skipped on every scheduled run. |

Spine architecture (for the §1 writeup): pipeline.py = pure forward-only state machine
(LLM never picks phases; CRITICAL={RESEARCH, SYNTHESIS}, everything else fails open);
runner.py = phase handlers with per-phase traces/checkpoint/monitor + deterministic
fallbacks at every LLM seam (pass1 fallback selection, pass2 deterministic newsletter,
learnings fallback, preamble stripper `_WRITER_NARRATION_RE` — prior refusal incidents
all have code scars with dated comments); checkpoint.py = SQLite upsert per (run, phase),
resume re-runs TREND_SCAN when target is RESEARCH because preflight isn't checkpointed.

## 5. Next steps (in order)

1. Deliver §1 writeup to Tayler (table above is the substance), get review.
2. §2 Agent dispatch (`agents.py`, `router.py`) — verify H1 (refusals vs CLI update);
   read `run_single_agent`, `run_claude_prompt`, the "corrective headless framing" retry,
   and the headless prompt assembly. This is where the live incident fix will land.
3. Remaining sections §3–§7 per spec.
4. Fix phase (after eval sign-off). Obvious early candidates: _send_alert response check,
   twitter_cli, agent prompt framing, quality-retryable actually retrying.
5. Tayler must still run the pmset command (item 3).

## Context notes for the next session

- Follow repo CLAUDE.md: graphify before architecture questions (`graphify-out/GRAPH_REPORT.md`,
  refreshed today), `graphify update .` after code edits, pytest `-x -q`, no commits of
  data/config, commit style `type: description`.
- Dated evidence lives in `reports/pipeline-YYYY-MM-DD.jsonl` and `launchd-decisions.log`;
  `launchd-std{out,err}.log` are UNDATED append logs — never use them alone for day attribution.
- Social is OFF on scheduled runs (wrapper default `MP_LAUNCHD_SKIP_SOCIAL=1`) — Tayler
  thought it might be live; it has never posted from launchd runs.
- KG build is ON for launchd (plist sets `MP_KG_BUILD_ENABLED=1`, workers=2). memory.db:
  17,499 findings. Fly app `mindpattern` (dashboard 401s unauthenticated — expected).

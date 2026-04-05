# Handoff: Pipeline Reliability + Harness Hardening

## Session Metadata
- Created: 2026-04-02 13:45:00
- Project: /Users/taylerramsay/Projects/mindpattern-v3
- Branch: main
- Continues from: [2026-04-02-122106-harness-knowledge-graph-fixes.md](./2026-04-02-122106-harness-knowledge-graph-fixes.md)

### Recent Commits (on main, before this session's uncommitted work)
- 7c3ce4a fix: pull latest main before pipeline and harness runs
- 4719e32 Merge pull request #10 from tayler-id/harness/2026-04-01-007
- 357852e Merge pull request #9 from tayler-id/harness/2026-04-01-006

---

## What Happened

The daily research pipeline crashed at 06:26 on 2026-04-02 and did not recover. Root cause: harness ticket `2026-04-01-001` added a `user_id` column to the checkpoints table but put `CREATE INDEX ON user_id` before `ALTER TABLE ADD COLUMN user_id` in `orchestrator/checkpoint.py`. Tests passed because they use fresh in-memory SQLite, but production had the old table schema without the column. The marker file was written on failure, blocking all 30-minute retries for the rest of the day.

This exposed three systemic problems:
1. **Harness agents can break production** — no feedback loop between harness changes and pipeline health
2. **Failures are silent** — no shared log, no alerts, agents don't learn from each other's mistakes
3. **Pipeline can't self-heal** — marker written on crash, retry window too narrow, no re-run after code merges

---

## Work Completed

### 1. Pipeline Crash Fix
- **`orchestrator/checkpoint.py`** — Moved `ALTER TABLE ADD COLUMN user_id` before `CREATE INDEX ... ON checkpoints(user_id)`. Migration now works against existing databases.

### 2. Pipeline Reliability (`run-launchd.sh`)
- **Marker only on success** — Pipeline no longer marks the day as "done" when it crashes (exit != 0). The 30-minute launchd retry can now pick it up.
- **Post-merge auto-rerun** — On each launchd trigger, if the marker exists, `git fetch origin main` and compare latest commit timestamp against marker. If main moved forward (merged PRs), clears marker and re-runs with new code.
- **Wider run window** — Changed from 06:00-11:59 to 06:00-22:59 so post-merge reruns work all day.
- **Crash logging to ISSUES.md** — On failure, logs the error to the shared issue log.

### 3. Shared Issue Log (`harness/ISSUES.md` + `harness/issues.py`)
- Append-only markdown log, newest first
- **Pipeline** writes on crash, **harness fix agents** write on test failure, **harness review agents** write on rejection
- CLI: `python3 -m harness.issues log "source" "title" "details"` / `python3 -m harness.issues read`
- Included **first** in `knowledge_graph.py:summary()` — highest priority context for all agents

### 4. Daily Health Report (`harness/health_report.py`)
- Deterministic (no LLM) Slack report posted to `#mp-harness` at start of every harness run
- Reports: pipeline status, harness run stats, ticket backlog by priority/type, success rate, stale tickets, issues in last 24h, PR outcomes
- CLI: `python3 -m harness.health_report` (stdout) or `--slack` (post to Slack)

### 5. Prompt Caching for Fix Agents
- Knowledge summary (ISSUES.md + INDEX + patterns) moved from user prompt to `--append-system-prompt`
- All parallel fix agents in a round share the same system prompt prefix → agents 2 and 3 get API-level cache hits
- Per-ticket content stays in the user prompt where it varies

### 6. Knowledge Check Confirmation
- All agents (scout, codex, fix) must print `KNOWLEDGE CHECK: Read N issues, relevant: ...`
- `run.sh` greps for this in agent logs, warns if missing
- Provides auditable proof that agents read the shared issue log before acting

### 7. Codex Adversarial Ticket Gate (Stage 1.5)
- New stage between Scout and Research
- Reads every open ticket created today, challenges on 4 dimensions:
  - Is the bug already fixed in current code?
  - Is it achievable in 25 turns? (rejects >3 files, new deps, missing APIs)
  - Is it a duplicate of a completed or attempted ticket?
  - Could the fix break something on a critical path?
- Outputs `CODEX VERDICT: <id> — PASS|REJECT — <reason>`
- `run.sh` deterministically parses verdicts and calls `mark-failed` on rejected tickets
- Rejections logged to ISSUES.md
- Prompt: `harness/prompts/codex-ticket-review.md`

### 8. LinkedIn Engagement Disabled
- Removed `linkedin` from `social-config.json` engagement platforms
- LinkedIn still used for posting, just not engagement (search/replies)

### 9. Ticket Backlog Cleanup
- Archived 10 tickets: 5 done, 3 blocked/superseded, 1 too large (L-effort), 1 already fixed
- **27 open tickets remain** (1 P1, 25 P2, 1 P3)

### 10. Knowledge Graph Updates
- Updated: INDEX.md, harness-run.md, orchestrator-checkpoint.md, patterns-what-fails.md, harness-tickets.md
- Created: harness-issues.md, harness-health-report.md
- Added Knowledge Graph section to CLAUDE.md instructing all agents to update knowledge files when they change code
- Fix agent prompt now includes step 7: update knowledge graph for changed modules
- All 136 wiki-links validate clean

---

## Files Modified (ALL UNCOMMITTED)

### Critical (commit first)
| File | Changes |
|------|---------|
| `orchestrator/checkpoint.py` | Migration ordering fix (ALTER TABLE before CREATE INDEX) |
| `run-launchd.sh` | Marker-on-success, post-merge rerun, wider window, crash logging |
| `harness/run.sh` | Health report, codex gate, knowledge checks, prompt caching, issue logging |
| `social-config.json` | Removed linkedin from engagement platforms |
| `CLAUDE.md` | Added Knowledge Graph section |

### New Files
| File | Purpose |
|------|---------|
| `harness/ISSUES.md` | Shared issue log (1 entry: checkpoint crash) |
| `harness/issues.py` | Issue log Python API + CLI |
| `harness/health_report.py` | Daily Slack health report |
| `harness/prompts/codex-ticket-review.md` | Codex adversarial ticket review prompt |
| `harness/knowledge/harness-issues.md` | Knowledge file for shared issue log |
| `harness/knowledge/harness-health-report.md` | Knowledge file for health report |

### Tickets Moved to Archive
- 2026-04-01-006, 007, R013, R015 (done)
- 2026-03-31-001, 007 (done)
- 2026-03-31-R001, R002, R004 (blocked/superseded)
- 2026-04-01-R018 (L-effort, too big)

---

## Harness Flow (Updated)

```
HEALTH REPORT → SCOUT → CODEX REVIEW → RESEARCH → FIX (parallel) → REVIEW → SUMMARY
     │              │          │             │           │              │          │
     │              │          │             │           │              │          └─ Slack + stats
     │              │          │             │           │              └─ PR or reject → ISSUES.md
     │              │          │             │           └─ KNOWLEDGE CHECK, TDD, knowledge graph update
     │              │          │             └─ Web search for ideas
     │              │          └─ REJECT bad tickets → mark-failed → ISSUES.md
     │              └─ KNOWLEDGE CHECK, create tickets
     └─ Ticket stats, pipeline status, issues → Slack
```

---

## Decisions Made

| Decision | Options | Rationale |
|----------|---------|-----------|
| Marker only on success | (a) always mark, (b) mark on success only | Crash at 6:26 AM blocked all retries for the day. Success-only lets 30-min interval self-heal. |
| Post-merge rerun via git fetch | (a) GitHub webhook, (b) separate launchd job, (c) check on each trigger | No new infra. Existing 30-min interval + git fetch is simple and reliable. |
| Widen run window to 06-22 | (a) keep 06-11, (b) widen to 06-22 | If user merges a harness PR at 2 PM, pipeline needs to re-run same day. |
| Codex gate after scout, not after fix | (a) after fix (review), (b) after scout (triage) | Cheaper to reject a bad ticket (15 turns of read-only) than to let a fix agent burn 25 turns failing. |
| Knowledge in --append-system-prompt | (a) user prompt, (b) system prompt | System prompt is shared across parallel agents → API caches it. Saves tokens on agents 2 and 3. |
| LinkedIn engagement off | (a) keep trying, (b) disable | Never worked (no search API). Just noise in logs. Posting still on. |

---

## Immediate Next Steps

1. **COMMIT EVERYTHING** — All changes are uncommitted. Run:
   ```bash
   git add orchestrator/checkpoint.py run-launchd.sh harness/run.sh harness/ISSUES.md harness/issues.py harness/health_report.py harness/prompts/codex-ticket-review.md harness/prompts/scout.md harness/knowledge/ CLAUDE.md social-config.json
   git add harness/tickets/  # includes archive moves
   git commit -m "feat: pipeline reliability, shared issue log, health report, codex ticket gate, knowledge checks"
   ```

2. **Run the pipeline manually** to verify the checkpoint fix works:
   ```bash
   python3 run.py
   ```

3. **Run the harness** to test the full new flow (health report → scout → codex → research → fix → review):
   ```bash
   bash harness/run.sh
   ```

4. **Monitor Slack** for the health report and codex verdicts

5. **Curate remaining tickets** — 25 P2 tickets is a lot. Many are test coverage that the fix agents should handle, but the M-effort feature tickets (R010, R011, R014, R016, R017) may need splitting or manual review.

---

## Potential Gotchas

- **`run-launchd.sh` git fetch on every trigger** — Adds ~2-3 seconds per launchd wake. If network is down, it silently continues (the `|| true` handles it). But if the remote is unreachable for days, the marker will never clear even if local code changes.
- **Codex stage uses scout model config** — Currently `read_config scout model` (opus). Could make it its own stage in config.json for independent tuning.
- **`grep -c` returns exit code 1 when count is 0** — The `|| echo 0` handles this, but be careful if refactoring.
- **Knowledge check is grep-based** — If an agent outputs `KNOWLEDGE CHECK:` in a code block or error message, it'll match. Low risk but not bulletproof.
- **Ticket archive is a flat directory** — `harness/tickets/archive/*.json`. No expiry on archived tickets. Could grow large over months.
- **ISSUES.md grows monotonically** — No pruning. After months it could slow down the knowledge summary. May need periodic cleanup or a `--limit` on inclusion in summary.

---

## Environment State

- Pipeline: crashed today (checkpoint.py), fix applied but not yet re-run
- Harness: not run today
- Marker file: removed (pipeline can re-run)
- 27 open tickets (1 P1, 25 P2, 1 P3)
- All changes uncommitted on main

---

## Related Resources

- Previous handoff: `.claude/handoffs/2026-04-02-122106-harness-knowledge-graph-fixes.md`
- Knowledge graph entry point: `harness/knowledge/INDEX.md`
- Shared issue log: `harness/ISSUES.md`
- Harness architecture: `harness/CLAUDE.md`
- Pipeline architecture: `docs/ARCHITECTURE.md`

# Production Readiness Audit: daily-research-agent-v2

> Full line-by-line code review by 6 parallel senior-level review agents.
> Generated 2026-03-14. Covers every file in the system.

---

## CRITICAL (Will cause silent failures, data loss, or security exposure)

### 1. No authentication on public Fly.io server
**File**: `server.py`
**Impact**: Anyone on the internet can read all research data, user emails, and submit/approve social media posts via the approval API at mindpattern.fly.dev. `/api/users` exposes email addresses. CORS is `*`, amplifying the exposure. The approval API is a write path -- an attacker can inject content.

### 2. Launchd plist points to wrong directory
**File**: `com.taylerramsay.daily-research.plist`
**Impact**: Points to `/Users/taylerramsay/Projects/daily-research-agent/run-all-users.sh` (v1), not `daily-research-agent-v2`. Production may be running old code or failing silently. Log paths also point to v1.

### 3. No curl timeouts anywhere in social-post.py
**File**: `social-post.py` (all HTTP functions)
**Impact**: A hung X, Bluesky, or LinkedIn API blocks the pipeline indefinitely. No alert fires because the process never returns. This applies to ALL 18 HTTP-calling functions.

### 4. Command injection in memory.py
**File**: `memory.py` lines 1778-1793
**Impact**: `_log_evolution_to_traces` interpolates `--agents` and `--reason` CLI args into a `python3 -c` string with only single-quote escaping. A crafted `--reason` value can execute arbitrary code.

### 5. Engagement rate limits are never enforced
**File**: `social-config.json` lines 71-80, `run-engagement.sh` Phase 4
**Impact**: `max_follows_x_per_day: 75`, `max_replies_per_day: 30` exist in config but are never checked. If the finder returns 500 candidates and the user types "all", 500 posts and 500 follows execute. X will rate-limit and possibly suspend the account.

### 6. EIC retry loop has no max iteration bound
**File**: `run-social.sh` line 168
**Impact**: `while true` loop with no counter. If Gate 1 keeps returning `retry` (e.g., stale iMessage), the EIC runs infinitely at Opus billing rates.

### 7. Failure exit codes always logged as 0
**File**: `run-all-users.sh` lines 105-109, `run-engagement.sh` lines 121-122, 174-175
**Impact**: `$?` is captured after `PHASE_END=$(date +%s)`, not after the failed command. Every failure is logged as `exit code: 0`. Debugging production failures from logs is impossible.

### 8. cmd_prune crashes at >999 notes
**File**: `memory.py` line 3108
**Impact**: `",".join("?" * len(note_ids))` generates a parameterized query with N placeholders. SQLite's `SQLITE_MAX_VARIABLE_NUMBER` default is 999. At >999 old notes, `prune` crashes instead of cleaning up. The database grows unbounded.

---

## HIGH (Will cause visible failures, quality degradation, or data corruption)

### 9. No proc.wait() timeout in orchestrator
**File**: `orchestrator/agents.py` line 311
**Impact**: If the `claude` process ignores SIGTERM, `proc.wait()` blocks forever. The pipeline hangs. caffeinate keeps the Mac awake indefinitely.

### 10. social-log.json race condition
**File**: `social-post.py` lines 1621-1636
**Impact**: Concurrent engagement reply threads read-modify-write the same JSON file without locking. One thread's append overwrites another's.

### 11. Expeditor auto-passes on any failure
**File**: `run-social.sh` lines 1062-1080
**Impact**: Claude crash, missing verdict file, or malformed JSON all result in `PASS`. The quality firewall is silently bypassed when it's most needed.

### 12. post_to_x has no retry logic
**File**: `social-post.py` line 835
**Impact**: A transient X API 500 or 429 loses the post permanently. Only Bluesky and LinkedIn have retry.

### 13. 13 of 20 social-config.json values are dead
**File**: `social-config.json`, `run-social.sh`
**Impact**: `eic.model`, `writers.model`, `writers.critic_max_rounds`, `creative_director.model`, `art_pipeline.*` are all in config but hardcoded in the shell script. Config says `critic_max_rounds: 3`, code does `MAX_ITERATIONS=2`. Changing config has zero effect. Only `expeditor.*` values are actually read from config.

### 14. Bluesky character truncation is byte-based
**File**: `run-social.sh` line 1476
**Impact**: `${#CONTENT}` counts bytes in bash, not graphemes. `${CONTENT:0:297}` can truncate mid-codepoint, producing corrupted UTF-8. Bluesky rejects invalid UTF-8.

### 15. FEEDBACK_LOG produces invalid JSON
**File**: `run-social.sh` line 1554
**Impact**: Each run appends a JSON object with `>>`, producing concatenated objects, not a valid JSON array. Any consumer expecting valid JSON will fail.

### 16. printf format injection in LOG_JSON
**File**: `run-social.sh` line 52-53
**Impact**: `printf '..."msg":"%s"...'` with unescaped `$msg`. Error messages containing `%`, `"`, or `\n` produce malformed JSONL. Every downstream log parser breaks.

### 17. Hardcoded "February 2026" in agent search queries
**File**: `agents/news-researcher.md` line 36, `verticals/ai-tech/agents/news-researcher.md`
**Impact**: Agents are searching for "AI model release February 2026" in March 2026. Stale search queries miss current content.

### 18. Root vs vertical agent drift
**Files**: `agents/*.md` vs `verticals/ai-tech/agents/*.md`
**Impact**: Root `agents-researcher.md` is 3,059 bytes; vertical version is 8,499 bytes (2.8x larger). Root `vibe-coding-researcher.md` is 2,663 bytes; vertical is 6,517 bytes (2.4x larger). Root copies have no self-improvement notes, fewer security categories, no quality filters. If root copies accidentally run, quality drops dramatically.

### 19. No PATH setup in run-all-users.sh
**File**: `run-all-users.sh`
**Impact**: launchd has minimal PATH. `jq`, `python3.12`, `sqlite3`, `osascript`, `caffeinate` may not be found. Compare with `run-social.sh` which explicitly sets PATH.

### 20. CAFFEINATE_PID unbound in trap handler
**File**: `run-all-users.sh` lines 53, 65-66
**Impact**: If the script fails before line 66 (before `CAFFEINATE_PID` is set), `set -u` in the `on_exit` trap crashes the trap handler. The real error is masked.

### 21. preferences accumulate race condition
**File**: `memory.py` lines 1354-1360
**Impact**: Read-modify-write without transaction. Two concurrent callers can read the same weight, both add their delta, and one update is lost. Should use `SET weight = weight + ?`.

### 22. No concurrency guard
**File**: `run-all-users.sh`
**Impact**: No PID file or flock. If launchd fires while a previous run is still going (or manual invocation), two instances fight over SQLite databases and log files.

---

## MEDIUM (Quality issues, code smells, scaling concerns)

### 23. 50-turn budget is tight for 5 phases
**File**: `RESEARCH_PROMPT.md`, `config.json` (`max_turns: 50`)
**Impact**: Phase 1 uses ~6-9 turns, Phase 2 uses ~3-4, Phase 3 uses ~2-3, leaving ~34-39 for Phase 4+5. Phase 4 needs 10-20 turns for memory.py store calls. If the LLM doesn't batch, it exhausts turns during Phase 4 and never produces the newsletter. No batching instruction exists in the prompt.

### 24. Observation masking is unenforced
**File**: `RESEARCH_PROMPT.md` Phase 3
**Impact**: Agents are instructed to return compact summaries, but this is a prompt instruction, not programmatic enforcement. If agents return full output, the orchestrator's context explodes (~60K tokens wasted).

### 25. Agent evolution via prompt alone is high-risk
**File**: `RESEARCH_PROMPT.md` Phase 5b
**Impact**: The LLM must write valid agent .md files, update agents.json correctly, and make judgment calls about 30% overlap. The "only ONE evolution change per run" constraint is unenforceable. A bad spawn wastes Opus tokens daily until manually noticed.

### 26. memory.py is a 3,800-line monolith
**File**: `memory.py`
**Impact**: 50+ subcommands in one file. Embedding model, CLI parsing, DB operations, presentation logic, evolution system all mixed together. Every change risks breaking unrelated functionality.

### 27. Full-table-scan semantic search
**File**: `memory.py` (lines 442, 899, 1191, 2105)
**Impact**: Loads ALL embeddings into memory and computes cosine similarity in Python. At 100K findings: 150MB memory, 5-10 seconds per search. The same pattern is repeated 6 times.

### 28. Connections never closed in memory.py
**File**: `memory.py`
**Impact**: No `conn.close()`, no `with` statement. Connection closed by garbage collector on process exit. Would leak if imported as library.

### 29. datetime.utcnow() vs datetime.now() inconsistency
**File**: `memory.py` line 2260 vs everywhere else
**Impact**: Engagement timestamps use `datetime.utcnow()` (deprecated in Python 3.12+) while everything else uses `datetime.now()` (local time). Timestamps are in different timezones.

### 30. last_insert_rowid() after INSERT OR IGNORE
**File**: `memory.py` line 3040
**Impact**: If the INSERT is ignored (pattern_key collision), `last_insert_rowid()` returns the rowid of the previously inserted row. A duplicate embedding could be inserted for an unrelated pattern.

### 31. Dual execution paths
**Files**: `run-user-research.sh` and `orchestrator/runner.py`
**Impact**: Both implement the same pipeline. Prompt construction differs. Shell watchdog warns but doesn't kill; Python watchdog kills. Shell deploys to Netlify; Python doesn't. Any fix must be applied twice.

### 32. reports/ directory never created
**File**: `run-all-users.sh` line 11
**Impact**: `LOG_JSON` writes to `reports/orchestrator-{date}.jsonl`. No `mkdir -p`. If `reports/` doesn't exist, the first log call kills the script. The ERR trap fires but `LOG_JSON` inside it also fails.

### 33. Single-threaded HTTP server on Fly.io
**File**: `server.py`
**Impact**: One request at a time. A semantic search (2-10 seconds) blocks health checks (5-second timeout). Fly.io restarts the machine.

### 34. send_alert() doesn't escape messages
**File**: `run-social.sh` line 68
**Impact**: Error messages containing double quotes break the AppleScript. The alert fails silently at the moment you most need it.

### 35. Approval tokens never expire
**File**: `server.py`
**Impact**: Once created via `/api/approval/submit`, a token is valid forever. No TTL, no revocation.

### 36. No dependency pinning
**File**: `requirements.txt`
**Impact**: `fastembed>=0.4.0` allows any future version. `numpy` has no version constraint. Non-reproducible builds.

### 37. learnings.md corruption risk
**File**: `RESEARCH_PROMPT.md` Phase 5
**Impact**: The LLM updates learnings.md via the Edit tool (in-place text replacement). A malformed edit corrupts the file. Since learnings.md is read at the start of every run, corruption propagates indefinitely.

### 38. Duplicate knowledge stores
**Files**: `learnings.md`, `learnings-archive.md`, `memory.db` (patterns, sources, agent_notes tables)
**Impact**: Source quality, search strategies, and patterns are stored in both markdown files AND SQLite. The LLM must update all three during Phase 5. Inconsistency between stores gives the LLM conflicting inputs.

### 39. Newsletter sent as plain text
**File**: `orchestrator/newsletter.py` line 183
**Impact**: Markdown headers, bold text, links, and tables render as raw markup in the email.

### 40. Unbounded data export on Netlify
**File**: `build-site.py`
**Impact**: `findings.json` includes ALL findings with no date cutoff. Over months of daily operation, this file grows to megabytes, slowing page loads.

---

## Personal Data Exposure Summary

| Data | Where | Exposed How |
|------|-------|-------------|
| Phone number `+17175783243` | `run-social.sh`, `run-engagement.sh`, `run-all-users.sh`, `social-config.json`, `orchestrator/runner.py` | Hardcoded in 5 files |
| Email `ramsay.tayler@gmail.com` | `users.json` | Served via `/api/users` (no auth) |
| Email `feedback@tayler.id` | `config.json` | In repo |
| Social handles | `social-config.json` | In repo |
| Google Analytics ID | `config.json` | In repo, embedded in both sites |

---

## Dead Code / Unused Config Summary

| Item | Status |
|------|--------|
| Root `agents/` research agent copies | Stale (7 files, all superseded by vertical versions) |
| Root `SOUL.md` | Identical to vertical copy |
| Root `learnings.md` | Orphaned from pre-multi-user |
| `data/social-brief-next.json` | No code references it |
| `run-user-research.sh` | Superseded by `orchestrator/runner.py` |
| `social-config.json` `platforms.*.enabled` | Never checked (3 values) |
| `social-config.json` `platforms.*.max_chars` | Never enforced (3 values) |
| `social-config.json` `eic.*` (except threshold) | Never read (3 values) |
| `social-config.json` `creative_director.*` | Never read (2 values) |
| `social-config.json` `art_pipeline.*` | Never read (4 values) |
| `social-config.json` `writers.*` | Never read (3 values) |
| `social-config.json` `engagement.*` rate limits | Never enforced (8 values) |
| `social-config.json` `social_brief` path | Never read |
| `set_defaults(func=...)` on engagement subcommands | Dead code in memory.py |

---

## Architecture Diagram with Failure Points

```
7 AM: launchd fires
  |
  v
run-all-users.sh
  |-- [BUG: may run v1 code if plist not updated]
  |-- [BUG: no PATH setup for launchd]
  |-- [BUG: no concurrency guard]
  |-- [BUG: $? always 0 in failure logging]
  |
  +-> orchestrator/runner.py (per user, sequential)
  |     |-- [BUG: no proc.wait() timeout]
  |     |-- [BUG: no PATH for claude CLI]
  |     |-- [BUG: python3 vs sys.executable]
  |     |
  |     +-> claude -p (RESEARCH_PROMPT.md)
  |     |     |-- [RISK: 50-turn budget is tight]
  |     |     |-- [RISK: observation masking unenforced]
  |     |     |-- [RISK: agent evolution via prompt only]
  |     |     |-- [BUG: Feb 2026 hardcoded in search queries]
  |     |     |
  |     |     +-> 13 research agents (parallel Tasks)
  |     |     |     |-- [BUG: root vs vertical agent drift]
  |     |     |     +-> memory.py (subprocess per call)
  |     |     |           |-- [BUG: command injection in evolution]
  |     |     |           |-- [BUG: prune crashes at >999 notes]
  |     |     |           |-- [BUG: race condition in preferences]
  |     |     |           |-- [PERF: full-table-scan search]
  |     |     |           |-- [DEBT: 3800-line monolith]
  |     |     |
  |     |     +-> Synthesis (Phase 4)
  |     |     |     |-- [RISK: no batching instruction]
  |     |     |     |-- [RISK: no dedup before storing]
  |     |     |
  |     |     +-> Self-Improvement (Phase 5)
  |     |           |-- [RISK: Edit tool can corrupt learnings.md]
  |     |           |-- [DEBT: duplicate knowledge stores]
  |     |
  |     +-> newsletter.py (validate + send)
  |     |     |-- [ISSUE: plain text email, not HTML]
  |     |     |-- [ISSUE: macOS-only keychain]
  |     |
  |     +-> build-site.py -> Netlify
  |           |-- [ISSUE: unbounded data export]
  |
  +-> sync-to-fly.sh -> Fly.io
  |     |-- [BUG: may double-sync (runner also syncs)]
  |
  +-> run-social.sh (ramsay only)
  |     |-- [BUG: EIC infinite retry loop]
  |     |-- [BUG: 13/20 config values dead]
  |     |-- [BUG: critic_max_rounds: config=3, code=2]
  |     |-- [BUG: expeditor auto-passes on failure]
  |     |-- [BUG: Bluesky byte-based truncation]
  |     |-- [BUG: FEEDBACK_LOG is invalid JSON]
  |     |-- [BUG: printf format injection in logs]
  |     |-- [BUG: send_alert doesn't escape quotes]
  |     |-- [BUG: proof package art path wrong]
  |     |
  |     +-> social-post.py
  |           |-- [BUG: NO curl timeouts]
  |           |-- [BUG: post_to_x has no retry]
  |           |-- [BUG: social-log.json race condition]
  |           |-- [BUG: Bluesky session per-call]
  |           |-- [ISSUE: hand-rolled OAuth 1.0a]
  |
  +-> run-engagement.sh (ramsay only)
        |-- [BUG: $? always 0 in failure logging]
        |-- [BUG: rate limits never enforced]
        |-- [BUG: no timeouts on subprocess calls]
        |-- [BUG: follow caps never checked]

server.py (Fly.io, always running)
  |-- [CRITICAL: no authentication]
  |-- [CRITICAL: /api/users exposes emails]
  |-- [CRITICAL: CORS *, write endpoints open]
  |-- [BUG: single-threaded, health checks fail]
  |-- [BUG: approval tokens never expire]
```

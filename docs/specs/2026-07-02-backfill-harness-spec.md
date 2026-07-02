# Spec: Multi-agent story backfill harness

**Status:** draft for review · **Date:** 2026-07-02
**Repo:** mindpattern-v3 · **Consumers:** any operator agent (Claude Code,
Codex/OpenAI, humans with a shell)

## Decisions from review (2026-07-02)

1. **Worktrees, reconciled with data reality.** Story artifacts live under
   `reports/` which is gitignored, so a git merge moves zero story files;
   worktrees alone cannot coordinate this work. Design: each helper agent
   runs IN its own worktree (code isolation, safe to experiment), but the
   backfill always writes artifacts to the shared canonical data root
   (`--reports-root` pinned to the main checkout) under a claim. Claims are
   the merge: claim = check out stories, artifact landing = merged, claim
   deleted. No git merge step for data; a worktree merge is only ever needed
   if an agent changed code, which operators are forbidden to do.
2. **Codex provider approved and verified**: codex-cli 0.142.5 installed,
   ChatGPT auth active. Wire `codex exec` one-shot as the second writer.
3. **Daily coverage requirement (supersedes the 5-10/day cap):** the daily
   pipeline must write EVERY source-backed story unit from that day's
   newsletter as site-shaped copy — the newsletter is reformatted for the
   site in full, every day, by a new writer stage in the SITE_CONTENT phase
   (~20-25 stories/day through the same writer->critic gate). The backfill
   then only ever works history, which shrinks to zero and stays there.
4. **The agent entry point is a slash goal prompt**: a project command
   (`.claude/commands/backfill.md` in mindpattern-v3) so any Claude Code
   session can run `/backfill` and get the full goal workflow; the same text
   stays in docs/handoff for non-Claude agents.

## Objective

A repeatable process any agent can run to convert archive stories to
harness-written copy, safely in parallel with other agents, with visible
state. Success looks like:

- Anyone (you or any agent) can see at a glance: how many stories are DONE,
  IN PROGRESS (and by whom, since when), and REMAINING.
- An agent starting a batch atomically claims its stories; no other batch
  can touch a claimed story; claims from crashed agents expire on their own.
- Writers are pluggable per provider (Claude today, Codex/OpenAI next) so
  each agent spends its own quota; the quality gate (mechanical validator +
  Claude critic + rules spec) is identical no matter who wrote the draft.
- The whole flow is driven by three commands an agent can be told verbatim.

## Tech Stack

Python 3.14 (existing v3 venv), stdlib only (no new dependencies). State is
files under `reports/{user}/` — same artifact philosophy as everything else,
readable by `ls`, synced by the existing Fly bundle.

## Commands (the whole agent-facing API)

```
# See the world: done / in-progress / remaining counts + stale claims
.venv/bin/python -m orchestrator.site_backfill status

# Atomically claim a batch (prints claim id + slugs). Claims expire in 3h.
.venv/bin/python -m orchestrator.site_backfill claim --size 50 --agent codex-1

# Work a claim (only its stories; releases each on completion)
MP_SITE_STORY_WRITER=claude .venv/bin/python -m orchestrator.site_backfill run --claim <id>

# Manual release (normally automatic; for aborted batches)
.venv/bin/python -m orchestrator.site_backfill release --claim <id>
```

Existing flags stay: `--workers`, `--limit`, `--dry-run` (legacy no-claim
mode keeps working for single-agent use).

## Claim design (the "tagging")

- `reports/{user}/site-backfill-claims/{slug}.json`, created with O_EXCL
  (atomic on APFS/ext4): `{"claim_id", "agent", "claimed_at", "expires_at"}`.
- A story is claimable iff: no artifact exists AND no unexpired claim file.
- Claims expire after 3 hours (configurable); `status` lists stale claims
  and `claim` silently reaps them. Completing a story deletes its claim.
- Done-tracking is unchanged and remains the source of truth: artifact file
  exists with `provenance.writer` set.
- The claims dir is git-ignored and excluded from the Fly sync bundle.

## Provider plug-in design

- `MP_SITE_STORY_WRITER` selects the writer provider:
  - `claude` (today's behavior, `claude -p`)
  - `codex` — Codex CLI one-shot (`codex exec`), same prompt, same JSON
    output contract
  - `cmd:<shell template>` — escape hatch: any CLI that reads the prompt on
    stdin and prints the JSON copy (lets future agents plug in without code
    changes)
- The prompt (rules spec + voice guide + evidence pack) and the output
  contract are provider-independent — they live in files, not in Python.
- The gate is NOT pluggable: mechanical validator (em dashes, banned words,
  invented URLs, field caps) + Claude critic + revision loop run identically
  on every draft regardless of writer provider. A provider only replaces the
  drafting call.
- Critic stays on Claude (`MP_SITE_STORY_CRITIC_MODEL`), cost ~1-2 small
  calls per story; this is what keeps voice/quality uniform across fleets.

## Project structure

```
orchestrator/site_backfill.py   → claim/run/release/status subcommands
orchestrator/site_writer.py     → provider adapters (claude, codex, cmd:)
orchestrator/site_critic.py     → unchanged (gate)
reports/{user}/site-backfill-claims/  → claim files (gitignored, not synced)
docs/handoff/backfill-goal-prompt.md  → updated for claim workflow
tests/test_backfill_claims.py   → claim atomicity, expiry, status
```

## Code style

Match existing v3: stdlib, type hints, small pure functions, fail closed.
Claim file example:

```json
{"claim_id": "c-20260702-1832-codex1", "agent": "codex-1",
 "claimed_at": "2026-07-02T18:32:04Z", "expires_at": "2026-07-02T21:32:04Z"}
```

## Testing strategy

pytest, `tests/test_backfill_claims.py`:
- two concurrent claimers over the same pool get disjoint sets (thread test)
- claimed stories are excluded from another agent's `claim`
- expired claims are reaped and re-claimable
- `run --claim` touches only claimed slugs; completion deletes claim files
- `status` counts done/claimed/remaining correctly on a fixture tree
- provider adapter: `cmd:` template invoked with prompt on stdin (fake cmd)
Provider live calls are never tested in CI (fakes only), same as today.

## Boundaries

- **Always:** claims before writes in claim mode; gate every draft through
  validator+critic; stay resumable (artifact existence = done).
- **Ask first:** adding any dependency; changing artifact schema; letting a
  non-Claude model act as critic; raising claim TTL beyond 6h.
- **Never:** sync claim files to Fly; let a writer bypass the critic; two
  agents share one claim id; touch the newsletter pipeline.

## Success criteria

1. `status` shows done/in-progress/remaining and stale claims. (testable)
2. Two agents claiming concurrently never overlap (test proves it).
3. A killed agent's stories become claimable again within TTL + 0. (test)
4. A Codex-written story passes through the same critic gate and lands with
   `provenance.writer: "codex"` — verified with one live story.
5. The goal prompt updated so an agent only ever needs: status → claim →
   run → report.

## Additional success criteria (from review)

6. Daily: after the pipeline runs, every source-backed story unit in that
   day's issue has a written artifact (writer or clean fallback) — verified
   by a pipeline test on a fixture issue.
7. The graph connects everything ever added: every story artifact (daily and
   backfilled) carries graph_connectors and surfaces related paths computed
   over the full story corpus at read time (existing engine; asserted by
   test).
8. `/backfill` slash command exists in mindpattern-v3 and contains the goal
   workflow (status -> claim -> run -> report).

## Open questions

None blocking. Per-provider budgets: Claude writer stays at 150/day; the
Codex writer runs until its own quota errors (its failures are per-story and
resumable).

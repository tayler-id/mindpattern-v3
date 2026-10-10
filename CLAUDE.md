# MindPattern v3

> Autonomous AI research pipeline. Runs daily through a guarded launcher. Gathers data from 8 sources, dispatches 13 research agents, writes a newsletter, supports optional social posting, and improves itself after every run. Scheduled runs skip social posting and engagement by default.

## Architecture

See `docs/ARCHITECTURE.md` for full diagrams. Key facts:

- **Python 3.14** codebase, no type stubs needed
- **SQLite databases**: `data/ramsay/memory.db` (user data, 17+ tables), `data/ramsay/traces.db` (observability, 14 tables)
- **Pipeline**: `orchestrator/pipeline.py` defines the `Phase` state machine (INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → SITE_CONTENT → LEARN → SOCIAL → ENGAGEMENT → IDENTITY → MIRROR → SYNC → COMPLETED); `orchestrator/runner.py` executes the phases
- **Agent dispatch**: `orchestrator/agents.py` (`run_single_agent()`, `run_claude_prompt()`, `dispatch_research_agents()`). Every model call, Claude or Codex, goes through `core/model_cli.py`, which reads its provider, model, effort, turns, and timeout from `config/models.json` and records the call in `traces.db` (`model_calls`, `model_call_steps`) with the raw event stream in `data/<user>/traces/`.
- **Slack bot**: `slack_bot/` — Socket Mode daemon with channel-based handler pattern. Runs 24/7 on Fly.io (app `mindpattern`, alongside the dashboard via `start.sh`); harness commands stay Mac-only. Secrets come from Fly secrets (env vars) in the container, macOS Keychain locally.
- **Social posting**: `run-launchd.sh` defaults `MP_LAUNCHD_SKIP_SOCIAL` to `1` and passes `--skip-social`. In `run.py`, that flag sets `MP_SKIP_SOCIAL=1`; `orchestrator/runner.py` then skips both SOCIAL and ENGAGEMENT, not newsletter delivery or site publishing. This is a scheduled-run default, not a global posting ban. Manual runs and Slack's `#mp-posts` workflow in `slack_bot/handlers/posts.py` remain optional posting paths, subject to approval and outbound/platform controls. Keep the scheduled default unchanged unless the owner explicitly approves enabling posting.
- **Dashboard**: FastAPI newsletter viewer on the same Fly machine (`mindpattern.fly.dev` / `mindpattern.ai`)
- **Scheduling**: macOS launchd via `run-launchd.sh`. See [Scheduling](docs/ARCHITECTURE.md#scheduling) for the checked-in calendar, retry guards, and the distinction between repository configuration and loaded job state.
- **Deploy**: `deploy/deploy.sh` runs the 3.11 compile gate, tests, `flyctl deploy`, then the site warm crawl. Never deploy with a bare `flyctl deploy`: a deploy empties the dashboard's in-memory caches (and a Vercel deploy drops the whole ISR cache), and nothing else refills them. Run `deploy/deploy.sh --warm-only` after a Vercel deploy. See `deploy/README.md`.

## Config, policies, and contracts

Behavior that changes without a code edit lives in files, checked when loaded:

| File | Holds |
|------|-------|
| `config/models.json` | Provider, model, effort, turns, timeout, and fallback per task. `python -m core.config check` validates it. |
| `policies/writing.json` | Banned and capped phrases, budgets. Feeds the gates and the writer prompts. |
| `policies/editorial.json` | Story counts and caps, and the newsletter length the writer is asked for and the eval scores against. |
| `policies/research.json` | Finding fields, age, injection patterns. |
| `policies/observability.json` | Trace retention and the per-run soft budget. |
| `contracts/*.schema.json` | The JSON shape a model must answer in. Codex enforces it; `core/contracts.py` checks it for every provider. |

## Tools

- `python -m orchestrator.trace runs | show <run> --steps | call <id> --full | grep | usage`: what every agent did.
- `tools/replay_day.py --date D --stage synthesis|research --state-root ~/Projects/mindpattern-v3 --out DIR`: rerun a stage on real data in a scratch copy. Real model calls; `--dry-run` makes none.
- `tools/usage_report.py --date D`: usage by task and model from Claude transcripts.
- `bin/mp`: the research agents' tools (`finding add`, `findings list`, `seen`, `fetch`, `evidence add`, `lint`, `tells`).
- `tools/health.py --since 7`: one row per day (run, delivery, agents, findings, duplicates, eval, site stories, cost, Codex, failures) plus per-agent output and problems. Exits 1 on any problem.
- `tools/mutate.py --file F --old X --new Y --test T` (or `--plan`): break a guard, run its tests, restore byte for byte. RED means a test caught it.
- `tools/site_backfill.py --dates D1,D2 [--claude-critic]`: write the site stories past issues should have had.

## Code Conventions

- **Logging**: `logging.getLogger(__name__)`, INFO for normal, WARNING for non-critical failures
- **Error handling**: critical phases raise, non-critical phases catch and log
- **DB access**: always use context managers or explicit `close()`. WAL mode for all SQLite.
- **Imports**: stdlib first, then third-party, then local
- **Type hints**: `str | None` not `Optional[str]`

## Testing

- Run: `python3 -m pytest tests/ -x -q`
- Tests must not require network access or API keys
- Mock subprocess calls to claude CLI
- Every new function gets at least one test
- Test files: `tests/test_*.py`

## Git Conventions

- Commit messages: `type: description` (feat, fix, refactor, test, docs)
- One logical change per commit
- Never commit `.env`, credentials, database files, or `social-config.json`

## File Locations

| What | Where |
|------|-------|
| Research agent skills | `verticals/ai-tech/agents/*.md` (13 files) |
| Social/synthesis agent skills | `agents/*.md` |
| Identity files | `data/ramsay/mindpattern/` (soul.md, user.md, voice.md, decisions.md) |
| Harness tickets | `harness/tickets/*.json` |
| Knowledge graph files | `harness/knowledge/*.md` (41 files) |
| Knowledge algorithms | `harness/knowledge_sections.py` |
| Knowledge graph module | `harness/knowledge_graph.py` |
| Tests | `tests/test_*.py` |
| Social config | `social-config.json` (do not commit) |

## Knowledge Graph

The knowledge graph (`harness/knowledge/`) is a set of interconnected markdown files documenting every module. Wiki-link syntax `[[slug]]` creates edges between documents. Supports section-level references: `[[orchestrator/runner#Error Handling]]`.

**CLI**: `python3 -m harness.knowledge_graph <command>`

| Command | Description |
|---------|-------------|
| `check` | Validate links, sections, index completeness, code refs (4 passes) |
| `search <query>` | 5-tier fuzzy search: exact → stem → tail → subsequence → Levenshtein |
| `expand <slug>` | Expand file + linked content (supports `slug#Section`) |
| `parse <slug>` | Show hierarchical section tree for a file |
| `locate <query>` | Find sections via tiered matching |
| `refs <slug>` | Show incoming/outgoing wiki-link references |
| `list` | List all knowledge files |

**Code references**: Add `# @know: [[slug#Section]]` comments in Python source to create bidirectional links. Files with `require-code-mention: true` frontmatter enforce that all leaf sections have code references.

**Auto-evolution**: `evolve(stage, data)` updates knowledge after harness stages (scout_done, fix_done, review_done, run_complete).

## Autonomous Harness

The harness (`harness/`) is a self-improving outer loop. See `harness/CLAUDE.md` for ticket schema and agent workflows. Agents in the harness use TDD: write failing tests first, then implement.

## graphify (code navigation — for coding agents, not the pipeline)

`graphify-out/` is an AST-derived graph of this repo's Python source, built so a **coding
agent can navigate the codebase** without grepping 505 files. No pipeline code imports it.

This repo has four different "graphs" — do not confuse them:

| Graph | Built from | Who consumes it |
|-------|-----------|-----------------|
| `graphify-out/` | this repo's Python source | **coding agents (you)** |
| `harness/knowledge/` | 41 hand-written `.md` files | harness self-improvement agents |
| `kg/` | research **findings** (newsletter content) | the pipeline (`MP_KG_BUILD_ENABLED=1`) |
| `orchestrator/site_graph.py` | published stories | the public website |

Rules:
- Symbol-anchored commands are precise and beat grep. Use them first:
  - `graphify explain "<symbol>"` — file:line, community, and every caller/callee
  - `graphify affected "<symbol>" --depth 2` — reverse deps with file:line (blast radius)
  - `graphify path "<A>" "<B>"` — shortest call/import chain between two symbols
- `graphify query "<question>"` is weak: it picks start nodes by naive keyword match and
  frequently traverses from the wrong ones. Prefer the three commands above, or grep.
- `GRAPH_REPORT.md` is ~190KB. **Never read it whole.** Grep it for a named community
  (`### <name>`) or use the CLI commands above.
- After modifying code files, run `graphify update .` (AST-only, no LLM, no API cost).
- **Never run `graphify label` or pass `--force-relabel`.** No LLM backend is configured
  (no API key, by design — this machine runs on the Claude subscription), so a forced
  relabel silently overwrites every community name with a `Community N` placeholder.
  Names live in `graphify-out/.graphify_labels.json` and are re-attached across
  re-clustering by node overlap, so `cluster-only`/`update` are safe.
- `graphify-out/` files are marked `skip-worktree`, so `git status` will not show changes
  to them. That is intentional; the graph is regenerated locally.

## Agent skills

### Issue tracker

GitHub Issues at `tayler-id/mindpattern-v3` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical labels — defaults (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Start at [README.md](README.md). Use [docs/agents/domain.md](docs/agents/domain.md) to find existing architecture, specs, and runbooks for vocabulary and decisions.

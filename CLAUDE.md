# MindPattern v3

> Autonomous AI research pipeline. Runs daily at 7 AM. Gathers data from 8 sources, dispatches 13 research agents, writes a newsletter, posts to social media, and improves itself after every run.

## Architecture

See `docs/ARCHITECTURE.md` for full diagrams. Key facts:

- **Python 3.14** codebase, no type stubs needed
- **SQLite databases**: `data/ramsay/memory.db` (user data, 17+ tables), `data/ramsay/traces.db` (observability, 14 tables)
- **Pipeline**: `orchestrator/runner.py` — 12 phases in fixed order (INIT → TREND_SCAN → RESEARCH → SYNTHESIS → DELIVER → LEARN → SOCIAL → ENGAGEMENT → EVOLVE → IDENTITY → MIRROR → SYNC)
- **Agent dispatch**: `orchestrator/agents.py` — `run_single_agent()`, `run_claude_prompt()`, `dispatch_research_agents()`
- **Slack bot**: `slack_bot/` — Socket Mode daemon with channel-based handler pattern
- **Dashboard**: FastAPI on Fly.io (`mindpattern.fly.dev`)
- **Scheduling**: macOS launchd via `run-launchd.sh` (7 AM daily)

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
| Tests | `tests/test_*.py` |
| Social config | `social-config.json` (do not commit) |

## Autonomous Harness

The harness (`harness/`) is a self-improving outer loop. See `harness/CLAUDE.md` for ticket schema and agent workflows. Agents in the harness use TDD: write failing tests first, then implement.

# MindPattern v3 development guide

## Scope

This repository is the Python backend, autonomous research pipeline, FastAPI API/dashboard, Slack bot, and local improvement harness.

The public Next.js site is a separate repository at `/Users/taylerramsay/Projects/mindpattern-rabbit-hole`. This repository has no `package.json`, `pyproject.toml`, Makefile, or JavaScript build step. Do not run `pnpm` from this root.

Rabbit Hole archive backfill is an explicit operator workflow, not the default repository role. Use the dedicated `rabbit-hole-backfill` skill only when the task asks for backfill operations.

## Before changing anything

- Work from this repository root and inspect `git status --short`.
- Preserve unrelated user changes and generated/runtime state.
- Read the relevant spec or runbook under `docs/` before changing a subsystem.
- For `harness/`, also read `harness/CLAUDE.md`.
- Instructions in `knowledge/AGENTS.md` apply inside `knowledge/`.
- For cross-module architecture questions, consult `graphify-out/GRAPH_REPORT.md` and `docs/ARCHITECTURE.md`.

## Project map

- `run.py`: single local pipeline entry point and concurrency guard.
- `orchestrator/`: pipeline phases, agent dispatch, newsletter, sync, site content, backfill, media, and observability.
- `preflight/` and `tools/`: source collection and normalization.
- `core/`: shared database, migrations, time, LLM, and outbound-receipt helpers.
- `memory/` and `kg/`: SQLite-backed memory and knowledge-graph logic.
- `social/`: drafting, approvals, engagement, and posting.
- `slack_bot/`: Socket Mode service and Slack handlers.
- `dashboard/`: canonical FastAPI/Jinja dashboard and public API. Production runs `dashboard.app`; `dashboard/server.ts` is not the deployed frontend.
- `harness/`: Mac-only autonomous engineering harness.
- `agents/` and `verticals/ai-tech/agents/`: runtime agent prompt files.
- `tests/`: offline pytest suite, with files named `test_*.py`.
- `data/` and `reports/`: personal/runtime state and generated artifacts; treat them as user-owned unless the task explicitly targets them.
- `docs/specs/` and `docs/runbooks/`: product decisions and implementation state. See [README.md](README.md) for navigation and [docs/agents/domain.md](docs/agents/domain.md) for source-selection guidance.

## Environment setup

Use Python 3.14 and the repository virtual environment. Do not use the system `python3` for project commands.

```sh
python3.14 -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install -r requirements.txt pytest
```

Tests must run without API keys or network access. Mock Claude CLI subprocesses and external services.

## Backend commands

Focused test:

```sh
.venv/bin/python3 -m pytest tests/test_<area>.py -x -q
```

Full local suite:

```sh
.venv/bin/python3 -m pytest tests/ -x -q
```

`.github/workflows/test.yml` is the source of truth for the exact CI split and critical runner/backfill contract tests.

Run the FastAPI service locally:

```sh
.venv/bin/python3 -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8010
```

There is no general backend build step. The Docker image and Fly process are deployment concerns, not ordinary local development. When a deploy is authorized, it runs through `deploy/deploy.sh` (tests, 3.11 compile gate, `flyctl deploy`, then the site purge and warm crawl) rather than a bare `flyctl deploy`, which leaves the public site cold.

A pipeline smoke can write local databases, reports, and checkpoints even when outbound calls are disabled. Run one only when the task requires it:

```sh
MP_DISABLE_OUTBOUND=1 .venv/bin/python3 run.py --user ramsay --dry-run --skip-social
```

Never use `run-launchd.sh` or `start.sh` as local development commands. `run-launchd.sh` can pull Git and run the scheduled pipeline; `start.sh` is the Fly container entrypoint and starts both Uvicorn and the live Slack bot.

## Public frontend

For public-site work, switch to the sibling repository and obey its `CLAUDE.md`:

```sh
cd /Users/taylerramsay/Projects/mindpattern-rabbit-hole
pnpm install
pnpm lint
pnpm exec tsc --noEmit --incremental false
pnpm build
```

That package currently has no automated test script. For a production-style local smoke, first run this backend on port 8010, then from the site repository:

```sh
BACKEND_API_URL=http://127.0.0.1:8010 pnpm start --hostname 127.0.0.1 --port 3010
```

Use `pnpm dev --hostname 127.0.0.1 --port 3010` during normal interactive UI development.

## Engineering conventions

- Use `logging.getLogger(__name__)`.
- Use context managers or explicit `close()` for database connections; retain SQLite WAL behavior.
- Order imports as standard library, third party, then local.
- Prefer `str | None` to `Optional[str]`.
- Use parameterized SQL and numbered `user_version` migrations.
- Give every new behavior a focused regression test.
- Keep tests deterministic, offline, and independent of personal state.
- Preserve public API response contracts used by the Rabbit Hole site.

## Safety and ownership boundaries

- Do not run the full live pipeline, send newsletters, post to social media, connect a live Slack bot, deploy Fly/Vercel, alter launchd, or enable live providers unless the task explicitly authorizes it.
- Ask before adding dependencies, changing database or KG schemas, or changing a frontend-consumed API response shape.
- Preserve unrelated files under `data/`, `reports/`, and local identity or editorial state. Never clean or rewrite them as incidental work.
- Never commit secrets, `.env`, credentials, PII, databases, `users.json`, `social-config.json`, logs, or generated reports.
- Make every outbound side effect honor `MP_DISABLE_OUTBOUND=1` and use the receipt/idempotency boundary.
- Keep private routes default-deny. Never serve `data/` as static files or add unauthenticated state-changing endpoints.
- Do not commit, push, merge, deploy, or change external services unless the task includes that action.

## Verification

- Run the smallest relevant tests while iterating.
- Before commit or merge, run the full local suite unless a documented baseline failure prevents it.
- For API/auth work, include the relevant contract and auth tests.
- For public-site work, run lint, TypeScript checking, build, and a browser smoke against the local backend.
- After Python code changes, run `graphify update .` and `graphify check-update .`.
- Finish with `git diff --check` and `git status --short`.
- Report exact commands, outcomes, and anything not run.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

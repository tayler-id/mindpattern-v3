# MindPattern v3

Contributor and operator documentation for the Python research pipeline, FastAPI API/dashboard, Slack bot, and local improvement harness. The public Rabbit Hole Next.js site lives in the separate `mindpattern-rabbit-hole` repository.

## Start here

- [Development guide](AGENTS.md): environment setup, tests, repository map, and safety boundaries.
- [Agent reference](CLAUDE.md): code conventions and navigation commands.
- [Architecture](docs/ARCHITECTURE.md): module and pipeline diagrams.
- [System overview](docs/SYSTEM-OVERVIEW.md): broader workflow descriptions. Check implementation details against the source before operating the system.
- [Domain documentation](docs/agents/domain.md): where to find vocabulary, specs, and decision history.
- [Specs](docs/specs/) and [runbooks](docs/runbooks/): scoped plans and implementation records. Dated plans are not proof that a feature is implemented or enabled.
- [Scheduling](docs/ARCHITECTURE.md#scheduling): checked-in launcher behavior and limits on live-state evidence.
- [Deployment guide](deploy/README.md): production procedures, only for explicitly authorized deployment work.

For local development, follow the development guide. Do not use `run-launchd.sh` or `start.sh` as smoke tests; they can run publishing or live services.

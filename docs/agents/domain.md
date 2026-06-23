# Domain docs

This repo uses **single-context** layout — one shared vocabulary across the whole project.

## Layout

- `CONTEXT.md` (repo root) — the project's working glossary. Domain nouns and what they mean.
- `docs/adr/` (repo root) — architecture decision records. One file per decision.

`CONTEXT.md` does not yet exist at the time this skill ran. `docs/adr/` was created as an empty directory. Skills that read these files MUST handle absence gracefully (treat as empty rather than erroring).

## Consumer rules

When a skill needs domain vocabulary or prior decisions:

1. **Read `CONTEXT.md` first.** Use the project's nouns (Pipeline, Phase, Finding, Newsletter, Verdict, Vault, Donor Voice, Mirror, Skill, etc.) instead of generic terms ("component", "service", "module-X-handler"). If a term is missing from `CONTEXT.md` but the skill needs it, the skill should ADD it inline as the decision crystallizes — same discipline `grill-with-docs` follows.

2. **Read `docs/adr/` second.** Each ADR records one decision the project has made. If a candidate proposal contradicts an existing ADR, only surface it when the friction is real enough to warrant reopening the ADR. Mark it clearly: _"contradicts ADR-NNNN — but worth reopening because…"_

3. **Don't backfill.** When this skill ran, the project had ~year of history with no `CONTEXT.md` and no ADRs. The right move is to capture decisions made *from now on*, not invent retrospective ADRs for past changes.

## ADR format

Use [adr-tools](https://github.com/npryce/adr-tools)-style numbering: `docs/adr/0001-short-title.md`. Each ADR has:

- **Status** — Proposed | Accepted | Superseded by NNNN | Deprecated
- **Context** — what's true about the world that forced this decision
- **Decision** — what was chosen
- **Consequences** — what becomes easier and what becomes harder

## Other architectural inputs already in this repo

These are not ADRs but are domain-relevant and should be read for context:

- `SPEC.md` — major feature spec (Voice A/B + Prose-Craft)
- `SAAS-AGENT-TECH.md` — research notes on agent platform landscape
- `harness/knowledge/` — 31 hand-written architectural docs ("knowledge graph") covering each module
- `data/ramsay/mindpattern/decisions.md` — **editorial** decisions per pipeline run (not architectural; do not confuse with ADRs)
- `graphify-out/GRAPH_REPORT.md` — auto-generated knowledge graph showing god nodes, communities, and surprising connections

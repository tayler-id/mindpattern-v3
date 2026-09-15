# Domain docs

Start with the [repository navigation](../../README.md). This checkout has no `CONTEXT.md` or `docs/adr/`; neither is a prerequisite for working here.

## Maintained sources

- [Architecture](../ARCHITECTURE.md) and [system overview](../SYSTEM-OVERVIEW.md) describe the pipeline vocabulary and module relationships. Check current behavior against the source files they name.
- [Specs](../specs/) record scoped product and architecture proposals. [Runbooks](../runbooks/) record implementation plans, checks, and handoffs. Read their dates and status before treating a proposal as implemented.
- [v4 spec](../spec-v4.md) describes the v4 plan. The root `SPEC.md` and `V4-SPEC.md` are older documents, not substitutes for that plan or evidence of current runtime behavior.
- [Harness guide](../../harness/CLAUDE.md) points to the harness's module documentation and workflows.
- `graphify-out/GRAPH_REPORT.md` is generated code-navigation output, not a decision record. Follow the navigation guidance in [CLAUDE.md](../../CLAUDE.md).

## Consumer rules

1. Use the vocabulary in the relevant subsystem docs and implementation, such as Pipeline, Phase, Finding, and Newsletter.
2. Read the relevant spec or runbook before proposing a change. If it disagrees with the implementation, distinguish intended behavior from observed behavior and name both sources.
3. Keep new decisions with the relevant maintained spec or runbook. Do not invent retrospective ADRs or create a duplicate glossary just to satisfy a missing path.
4. Keep private runtime identity and editorial decisions separate from architecture documentation. Do not copy personal state into contributor docs.

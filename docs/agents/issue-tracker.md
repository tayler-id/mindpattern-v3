# Issue tracker

This repo uses **GitHub Issues** at https://github.com/tayler-id/mindpattern-v3.

## Tooling

Use the `gh` CLI for all issue operations.

## Common operations

- Create: `gh issue create --title "..." --body "..." --label "..."`
- List: `gh issue list --label "ready-for-agent" --state open`
- View: `gh issue view <number>`
- Comment: `gh issue comment <number> --body "..."`
- Close: `gh issue close <number>`
- Add label: `gh issue edit <number> --add-label "..."`
- Remove label: `gh issue edit <number> --remove-label "..."`

## Notes for skills

- This repo also has a separate ticket system at `harness/tickets/*.json` — that is the **autonomous harness** ticket queue, NOT the human-tracked issue tracker. Do not confuse the two. Human-tracked work goes in GitHub Issues.
- The first time `triage` runs, it will need to create the four custom labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`). `wontfix` already exists in GitHub's default label set. See `docs/agents/triage-labels.md` for the one-time setup commands.
- Use `gh issue create --label "needs-triage"` for any newly-arrived issue that hasn't been evaluated yet.

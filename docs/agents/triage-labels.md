# Triage labels

The `triage` skill moves issues through a five-state machine. Each state maps to a GitHub label.

| Role | Label | Meaning |
|------|-------|---------|
| `needs-triage` | `needs-triage` | Newly arrived; maintainer needs to evaluate |
| `needs-info` | `needs-info` | Waiting on reporter for clarification |
| `ready-for-agent` | `ready-for-agent` | Fully specified — an AFK agent can pick it up with no further human context |
| `ready-for-human` | `ready-for-human` | Needs human judgment, design, or implementation |
| `wontfix` | `wontfix` | Will not be actioned (closed with reason) |

## First-time setup

The `wontfix` label exists in every GitHub repo by default. The other four must be created manually before `triage` can apply them. Run once:

```bash
gh label create "needs-triage"     --color "fbca04" --description "Maintainer needs to evaluate"
gh label create "needs-info"       --color "d4c5f9" --description "Waiting on reporter for clarification"
gh label create "ready-for-agent"  --color "0e8a16" --description "Fully specified — AFK agent can pick up"
gh label create "ready-for-human"  --color "1d76db" --description "Needs human implementation"
```

## State transitions

- New issue arrives → `needs-triage`
- After evaluation, one of:
  - More info needed from reporter → `needs-info`
  - Spec is complete enough for AFK work → `ready-for-agent`
  - Needs human judgment → `ready-for-human`
  - Out of scope → `wontfix` + close
- When `needs-info` reporter replies → back to `needs-triage`
- When work starts → assignee set, label stays
- When work completes → close

Only one of the five labels should be on an open issue at a time.

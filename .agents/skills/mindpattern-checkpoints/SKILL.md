---
name: mindpattern-checkpoints
description: Structure a requested MindPattern feature or migration into small checkpoints with behavior evidence and independent review, following the Helix pattern. Use when the user asks for Helix-style work, checkpoint delivery, or a reviewable multi-step implementation. Read-only investigations remain read-only.
---

# MindPattern checkpoints

Use this workflow for the feature or migration the user requested. Keep repository working agreements and existing session authorization in force. This skill does not authorize commits, publishing, or production operations.

## Define the checkpoint

Read the relevant [feature-map entry](../verify-mindpattern/references/features/README.md) and current source. If the behavior is absent from the map, add an entry with its real user path and observable result.

Choose the smallest slice that a reviewer can run and assess independently. A checkpoint states:

- The user action and expected outcome.
- The files and behavior it changes.
- The mapped scenario, relevant tests, and any required browser check.
- The result that would make the checkpoint fail.

Keep a short record in the task's runbook under `docs/runbooks/`. Use the [checkpoint record](references/checkpoint-record.md) as a starting format. Do not create a second task tracker when the current runbook already holds this information.

## Implement and prove

Use the repository's pstack implementation workflow. Extend an existing backend operation when it can serve both the app and CLI. Keep business decisions in production code and synthetic setup in verification code.

Run the relevant tests, then use [verify-mindpattern](../verify-mindpattern/SKILL.md) to exercise the changed path. If the change affects a rendered interface, inspect that interface too. Record the response or visual evidence and any unavailable checks.

An ASGI pass proves route behavior for the fixture. An HTTP pass adds transport evidence. A browser check proves the rendered interaction. Select the checks the change needs and label the result accurately.

## Review and continue

For requested Helix-style delivery, get two independent code reviews of the completed checkpoint when agents are available. Give reviewers the user outcome, actual diff, feature-map entry, and evidence. Ask one to challenge behavior and integration, and the other to challenge ownership, maintainability, and uncovered failure paths.

Resolve concrete defects and rerun the affected proof. Record dismissals with evidence. If two reviewers are unavailable, state that limitation instead of claiming two reviews.

Present the concrete checkpoint for human review at the agreed boundary. Shopify's described workflow uses a human decision before each commit. Apply that cadence when the user asks for it; otherwise follow the user's existing authorization and continue reversible work. Do not add a new CI gate or require repeated permission for actions already authorized.

Carry review lessons into the affected fixture, feature entry, or narrow instruction when they recur. Avoid a growing list of generic rules.

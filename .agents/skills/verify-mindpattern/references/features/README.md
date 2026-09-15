# MindPattern feature map

Use this inventory to select a user flow and the evidence that proves it. It describes the Python backend in this repository. The public Next.js interface lives in the sibling `mindpattern-rabbit-hole` repository.

## Runnable CLI scenarios

Each command creates a fresh synthetic instance. `verify all` runs these five scenarios against one instance.

| Feature | User outcome | Command |
| --- | --- | --- |
| [Stories](stories.md) | Read published stories with their evidence; draft and invalid stories stay unavailable. | `verify stories` |
| [Story search](story-search.md) | Find a published story by title terms and receive an empty result for absent terms. | `verify story-search` |
| [Site artifacts](site-artifacts.md) | Inspect public run and corpus summaries without private fields. | `verify site-artifacts` |
| [Sitemap](sitemap.md) | Discover published story URLs without exposing draft artifacts. | `verify sitemap` |
| [Private access](private-access.md) | Private routes reject anonymous access and accept the synthetic owner credential. | `verify private-access` |

Prefix each command with `.venv/bin/python3 -m verification`. `features` lists the executable registry. Open one feature file before selecting its proof.

## Other product workflows

The [remaining workflows](other-workflows.md) inventory covers research, newsletter reading and delivery, findings and graph exploration, editorial approvals, operational dashboards, and the public frontend. These need existing tests, operational skills, or browser checks. They are not included in `verify all`.

## Shared proof rules

- Record source identity and synthetic fixture scope with each run.
- Check successful, absent, and rejected paths affected by the change.
- Keep response evidence after the temporary instance stops.
- Distinguish a response assertion from a real HTTP check and a rendered browser check.
- Document any route or feature that remains unsupported. Do not turn an empty response into a pass merely because its status is 200.

Follow the [maintenance procedure](../maintenance.md) when routes, behavior, or driver commands change. This map is a maintained inventory, not a generated list of every endpoint.

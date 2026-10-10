# orchestrator/issue_format.py

> The issue's layout, counted in code. Bullets, lists and tables per Top story and per section, held to `newsletter.layout` in `policies/editorial.json`.

## What It Does

`measure(markdown)` returns one `Unit` per Top story (each `###` under the Top section) and one per other `##` section, with its words, bullets, list blocks, tables, longest list, and whether it ends on a list. `report(markdown)` prints them as a table.

`violations(markdown, layout)` names every breach of the layout as the fix the editor should make. A Top story may end on one list of up to four items and has no other list. Section items are prose. No tables. Skills of the day is exempt and stays a numbered list.

## Why It Exists

On 2026-10-10 one writer input produced 117, 10 and 60 bullets on three runs, the last with the writer prompt from before the lead-story change. The layout is a draw, not a property of the prompt, the same way em dashes were in July. A count at the choke point holds it where a prompt line cannot.

## Behavior

The writer gets the rule as the Layout section of its task, rendered by `Layout.block()` in [[policies/files]]. After the writer, [[orchestrator/newsletter_editor]] gets every breach with the word-bank hits and folds extra lists and tables into prose under its fact guard. Whatever breach survives is logged as a `layout_violations` event by [[orchestrator/runner]].

`tools/rerun_call.py` reruns one traced call with another system prompt on the same input and prints this report, which is how the cause was found.

## Depends On

`orchestrator/editorial.py` (`Layout`). Called by [[orchestrator/newsletter_editor]].

## Last Updated

2026-10-10. Created.

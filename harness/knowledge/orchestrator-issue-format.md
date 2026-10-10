# orchestrator/issue_format.py

> The issue's layout, counted in code. Bullets, lists and tables per Top story and per section, held to `newsletter.layout` in `policies/editorial.json`.

## What It Does

`measure(markdown)` returns one `Unit` per Top story and per other section. `report(markdown)` prints them as a table.

A Top story is each `###` under the Top section. A `Unit` holds the words, bullets, list blocks, tables, longest list, and whether the text ends on a list.

`violations(markdown, layout)` names every breach of the layout as the fix the editor should make. A Top story may end on one list of up to four items and has no other list. Section items are prose. No tables. Skills of the day is exempt and stays a numbered list.

## Why It Exists

On 2026-10-10 one writer input produced 117, 10 and 60 bullets on three runs. The layout is a draw, not a property of the prompt. A count at the choke point holds it where a prompt line cannot.

The 60 came from the writer prompt before the lead-story change. Em dashes behaved the same way in July.

## Behavior

The writer gets the rule as the Layout section of its task, rendered by `Layout.block()` in [[policies/files]]. Any breach left after [[orchestrator/newsletter_editor]] is logged as a `layout_violations` event.

The editor gets every breach with the word-bank hits and folds extra lists and tables into prose under its fact guard. [[orchestrator/runner]] logs the event.

`tools/rerun_call.py` reruns one traced call with another system prompt on the same input and prints this report, which is how the cause was found.

## Depends On

`orchestrator/editorial.py` (`Layout`). Called by [[orchestrator/newsletter_editor]].

## Last Updated

2026-10-10. Created.

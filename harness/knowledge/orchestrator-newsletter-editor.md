# orchestrator/newsletter_editor.py

> A GPT-6.1 Sol line edit of the finished issue, applied by code that refuses any edit that would change a fact.

## What It Does

`edit_newsletter(text)` sends the issue and its word-bank hits to the `newsletter_editor` route (Codex, Sol, with a Sonnet 5.5 fallback). Sol answers with find-and-replace edits in the `editor_edits` contract, at most 40.

`apply_edits` runs `check_edit` on each one and applies only those that pass. The runner logs a `newsletter_editor` event with counts and rejections.

## The Guard

`check_edit` rejects an edit when:

- the find text does not occur exactly once, or touches a heading
- it drops or adds a number or URL, or drops a link, a quote, or a name
- it adds an em dash or a banned term
- it grows the text past 1.5 times plus 40 characters

## Behavior

Runs after pass 2 and before the prose gate. Fails open. Skipped on dry runs. Sep 30 replay: 10 of 10 edits applied, writing-policy violations 3 to 2.

## Depends On

[[core/model_cli]], [[policies/files]], `agents/newsletter-editor.md`. Called by [[orchestrator/runner]].

## Last Updated

2026-10-02. Created with the models harness.

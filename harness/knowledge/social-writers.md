# social/writers.py

> Draft generation per platform. Uses voice guide from identity files.

## What It Does

Generates social media drafts (Bluesky, LinkedIn) using Claude. Applies voice.md constraints: contractions mandatory, no em dashes, banned words list (91 words), first-person perspective.

## Depends On

[[orchestrator/router]] for model selection. Reads voice.md from data/ramsay/mindpattern/.

## Called By

[[social/pipeline]].

## Last Modified By Harness

Never — created 2026-04-01.

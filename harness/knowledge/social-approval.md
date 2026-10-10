# social/approval.py

> Gate 1 / Gate 2 / Expeditor approval chain for social posts.

## What It Does

Three gates approve a post. Gate 1 approves the topic, Gate 2 the content, and the Expeditor decides to post now, schedule, or hold.

Gate 1's 'custom' action can add a counter-narrative. Each gate polls for human approval with a configurable timeout, 4 hours by default.

## Known Patterns

- Gate 1 'custom' triggers for compound narratives (counter-narrative injection)
- Three-actor convergence passes clean
- Government/geopolitics + security with CVEs clean approves

## Depends On

[[data/memory-db]] (approval_reviews, approval_items tables). Slack integration for notifications.

## Called By

[[social/pipeline]].

## Last Modified By Harness

Never — created 2026-04-01.

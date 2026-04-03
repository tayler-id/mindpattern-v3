# social/approval.py

> Gate 1 / Gate 2 / Expeditor approval chain for social posts.

## What It Does

Three-stage approval: Gate 1 (topic approval — can inject counter-narratives via 'custom' action), Gate 2 (content quality), Expeditor (distribution decision — post now, schedule, or hold). Polls for human approval with configurable timeout (default 4h).

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

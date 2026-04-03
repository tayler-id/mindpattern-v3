# social/pipeline.py

> Social posting orchestration. Runs the approval chain, generates drafts, posts to platforms.

## What It Does

Coordinates the social posting flow: select topics from findings -> generate drafts via [[social/writers]] -> Gate 1 + Gate 2 approval via [[social/approval]] -> post via [[social/posting]].

## Depends On

[[social/writers]], [[social/approval]], [[social/posting]], [[data/memory-db]] (social_posts, pending_posts tables).

## Called By

[[orchestrator/runner]] _phase_social.

## Last Modified By Harness

Never — created 2026-04-01.

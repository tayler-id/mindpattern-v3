# memory/findings.py

> Findings CRUD, dedup, embeddings, FTS search.

## What It Does

Stores and retrieves research findings in [[data/memory-db]]. Handles embedding generation for dedup (0.90 similarity threshold), FTS5 full-text search, and finding lifecycle.

## Key Operations

- Store findings from agent results
- Dedup via embedding similarity (threshold 0.90)
- Search via FTS5 (findings_fts virtual table)
- Track claimed_topics to prevent duplicate agent coverage

## Depends On

[[data/memory-db]] (findings, findings_embeddings, claimed_topics tables).

## Called By

[[orchestrator/runner]] _phase_research.

## Last Modified By Harness

Never — created 2026-04-01.

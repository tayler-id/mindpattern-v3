"""Temporal knowledge graph for MindPattern.

Builds a typed, bi-temporal knowledge graph from research findings (the
"episodes"). Findings → typed entities → bi-temporal edges → communities.
Contradicted facts are invalidated (invalid_at set), never deleted, so story
timelines come for free.

Design: docs/v4-research.md §2. Storage lives in the existing memory.db
(namespaced kg_*), reusing bge-small embeddings + numpy for similarity and the
claude-CLI wrapper for extraction/adjudication — no new dependencies.
"""

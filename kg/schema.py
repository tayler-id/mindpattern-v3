"""Knowledge-graph schema: bi-temporal entities, aliases, edges, communities.

Tables live inside the existing memory.db (namespaced ``kg_*``) so entity
resolution can join against ``findings`` / ``findings_embeddings`` without a
cross-database query. The schema is idempotent (IF NOT EXISTS) and applied at
the top of every KG operation — same pattern as ``memory.db._init_schema`` —
so there is no separate migration step that can silently fail to run (the
lesson of 2026-06-12).

Bi-temporal model (Graphiti/Zep, docs/v4-research.md §2):
  - ``valid_at``     — when the fact became true (the event date)
  - ``invalid_at``   — when it stopped being true; NULL means currently valid
  - ``invalidated_by`` — the edge that superseded this one (NULL unless contradicted)

The "current view" of the graph is therefore ``edges WHERE invalid_at IS NULL``.
"""

import sqlite3
from pathlib import Path

# 6-8 typed entity types and a closed predicate vocabulary keep extraction
# constrained (no open extraction → no node fabrication). Enforced at the
# extraction layer; recorded here as the canonical vocabulary.
ENTITY_TYPES = (
    "Company",
    "Product",  # also models
    "Person",
    "Technology",
    "Paper",
    "Event",
    "Funding",
    "Other",
)

PREDICATES = (
    "RELEASED",
    "ACQUIRED",
    "RAISED",
    "INVESTED_IN",
    "COMPETES_WITH",
    "PARTNERS_WITH",
    "PREDICTS",
    "USES",
    "BUILT_BY",
    "WORKS_AT",
    "BENCHMARKED_AGAINST",
    "DEPRECATES",
    "SUPPORTS",
    "CRITICIZES",
    "MENTIONS",
)

# Atomic facts are tagged so opinion/prediction never reads as established fact
# (OpenAI temporal-agents staging, docs/v4-research.md §2).
FACT_TYPES = ("Fact", "Opinion", "Prediction")

_SCHEMA = """
    -- ── Entities ─────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS kg_entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_name TEXT NOT NULL,
        entity_type TEXT NOT NULL DEFAULT 'Other',
        description TEXT,
        embedding BLOB,                 -- 384-dim bge-small, for resolution shortlist
        mention_count INTEGER DEFAULT 0,
        importance REAL DEFAULT 0.0,    -- f(PageRank, mentions, recency); set during consolidation
        first_seen TEXT,
        last_seen TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_kg_entities_type ON kg_entities(entity_type);
    CREATE INDEX IF NOT EXISTS idx_kg_entities_name ON kg_entities(canonical_name);

    -- ── Aliases (the first, cheapest resolution tier: exact match) ───
    CREATE TABLE IF NOT EXISTS kg_entity_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id INTEGER NOT NULL,
        alias TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE (entity_id, alias),
        FOREIGN KEY (entity_id) REFERENCES kg_entities(id) ON DELETE CASCADE
    );

    -- alias text is the lookup key for exact-match resolution; collation
    -- NOCASE so "Anthropic" and "anthropic" match without lowercasing at query time.
    CREATE INDEX IF NOT EXISTS idx_kg_aliases_alias ON kg_entity_aliases(alias COLLATE NOCASE);

    -- ── Edges (bi-temporal typed facts, with finding provenance) ─────
    CREATE TABLE IF NOT EXISTS kg_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        predicate TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        fact_text TEXT NOT NULL,        -- the atomic fact in natural language
        fact_type TEXT NOT NULL DEFAULT 'Fact',
        confidence REAL DEFAULT 1.0,
        finding_id INTEGER,             -- provenance: the episode this came from
        valid_at TEXT,                  -- when the fact became true (event date)
        invalid_at TEXT,                -- when it stopped being true; NULL = current
        invalidated_by INTEGER,         -- edge that superseded this one
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (subject_id) REFERENCES kg_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (object_id) REFERENCES kg_entities(id) ON DELETE CASCADE,
        FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE SET NULL,
        FOREIGN KEY (invalidated_by) REFERENCES kg_edges(id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_kg_edges_subject ON kg_edges(subject_id);
    CREATE INDEX IF NOT EXISTS idx_kg_edges_object ON kg_edges(object_id);
    CREATE INDEX IF NOT EXISTS idx_kg_edges_predicate ON kg_edges(predicate);
    CREATE INDEX IF NOT EXISTS idx_kg_edges_finding ON kg_edges(finding_id);
    -- the hot path is "currently-valid edges between a pair"
    CREATE INDEX IF NOT EXISTS idx_kg_edges_current ON kg_edges(subject_id, object_id, invalid_at);

    -- ── Communities (populated weekly by Louvain consolidation) ──────
    CREATE TABLE IF NOT EXISTS kg_communities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        label TEXT,
        summary TEXT,
        member_ids_json TEXT NOT NULL DEFAULT '[]',
        algorithm TEXT DEFAULT 'louvain',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_kg_communities_run ON kg_communities(run_date);
"""


def init_kg_schema(conn: sqlite3.Connection) -> None:
    """Create all kg_* tables and indexes. Idempotent; safe to call repeatedly."""
    conn.executescript(_SCHEMA)
    conn.commit()


def open_kg(db_path: str | Path | None = None, user_id: str = "ramsay") -> sqlite3.Connection:
    """Open memory.db (WAL + foreign keys + full memory schema) with the KG
    tables ensured. Returns a connection with ``row_factory = sqlite3.Row``.

    Reuses ``memory.db.get_db`` so the KG shares the same connection management,
    WAL settings, and the findings/embeddings tables it resolves against.
    """
    from memory.db import get_db

    conn = get_db(db_path, user_id)
    init_kg_schema(conn)
    return conn

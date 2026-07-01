import sqlite3
import struct

from kg.schema import init_kg_schema
from orchestrator.site_graph import CorpusGraphReadModel


def _embedding_blob(x: float, y: float = 0.0) -> bytes:
    return struct.pack("2f", x, y)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            agent TEXT,
            title TEXT,
            summary TEXT,
            importance TEXT,
            category TEXT,
            source_url TEXT,
            source_name TEXT,
            created_at TEXT
        );
        CREATE TABLE findings_embeddings (
            finding_id INTEGER PRIMARY KEY,
            embedding BLOB
        );
        CREATE TABLE entity_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT NOT NULL,
            entity_a_type TEXT,
            relationship TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            entity_b_type TEXT,
            finding_id INTEGER,
            created_at TEXT
        );
        """
    )
    init_kg_schema(conn)
    conn.executemany(
        """INSERT INTO findings
           (id, run_date, agent, title, summary, importance, category, source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                101,
                "2026-07-01",
                "fixture-agent",
                "OpenAI agent runtime reliability",
                "OpenAI made runtime reliability a buyer-visible benchmark.",
                "high",
                "agents",
                "https://openai.com/news/agents",
                "OpenAI",
                "2026-07-01T12:00:00",
            ),
            (
                102,
                "2026-06-30",
                "fixture-agent",
                "Anthropic agent runtime reliability",
                "Anthropic pushed Claude Code reliability in the same stack layer.",
                "medium",
                "agents",
                "https://anthropic.com/news/claude-code",
                "Anthropic",
                "2026-06-30T12:00:00",
            ),
            (
                103,
                "2026-07-01",
                "fixture-agent",
                "Top 5 Stories Today",
                "Source story section newsletter https://example.com should not become a connector.",
                "low",
                "source",
                "https://example.com/raw-newsletter",
                "Example",
                "2026-07-01T12:05:00",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)",
        [
            (101, _embedding_blob(1.0, 0.0)),
            (102, _embedding_blob(0.82, 0.0)),
            (103, _embedding_blob(0.1, 0.1)),
        ],
    )
    conn.executemany(
        """INSERT INTO entity_graph
           (entity_a, entity_a_type, relationship, entity_b, entity_b_type, finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ("OpenAI", "company", "mentions", "Agent Runtime", "technology", 101, "2026-07-01T12:00:00"),
            ("Anthropic", "company", "mentions", "Agent Runtime", "technology", 102, "2026-06-30T12:00:00"),
        ],
    )
    conn.commit()
    return conn


def test_related_paths_use_multiple_evidence_backed_connectors():
    model = CorpusGraphReadModel(
        _conn(),
        arc_memberships={
            101: {"agent-runtime-control-plane"},
            102: {"agent-runtime-control-plane"},
        },
    )

    related = model.get_related_paths_for_finding(101, limit=5)
    assert related is not None
    item = next(item for item in related["items"] if item["id"] == 102)
    labels = set(item["connector_labels"])

    assert "Shared entity" in labels
    assert "Semantic neighbor" in labels
    assert "Same arc" in labels
    assert item["reason"].startswith("Related by")
    assert all(connector["evidence"] for connector in item["connectors"])


def test_related_topic_overlap_ignores_generic_newsletter_labels():
    model = CorpusGraphReadModel(_conn())

    related = model.get_related_paths_for_finding(101, limit=5)
    raw_chunk = next((item for item in related["items"] if item["id"] == 103), None)
    if raw_chunk is None:
        return

    topic_connectors = [
        connector
        for connector in raw_chunk["connectors"]
        if connector["kind"] == "shared_topic"
    ]
    terms = {
        evidence["term"]
        for connector in topic_connectors
        for evidence in connector["evidence"]
        if evidence.get("kind") == "topic_term"
    }
    assert "top" not in terms
    assert "stories" not in terms
    assert "source" not in terms
    assert "example.com" not in terms

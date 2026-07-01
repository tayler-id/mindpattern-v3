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
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY,
            url_domain TEXT,
            display_name TEXT,
            hit_count INTEGER,
            high_value_count INTEGER,
            last_seen TEXT,
            created_at TEXT
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
                "OpenAI made agent runtime reliability a buyer-visible benchmark.",
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
                "Anthropic agent reliability",
                "Anthropic pushed Claude Code reliability in the same stack layer.",
                "medium",
                "agents",
                "https://anthropic.com/news/claude-code",
                "Anthropic",
                "2026-06-30T12:00:00",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)",
        [(101, _embedding_blob(1.0)), (102, _embedding_blob(0.8))],
    )
    conn.executemany(
        """INSERT INTO sources
           (id, url_domain, display_name, hit_count, high_value_count, last_seen, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (1, "openai.com", "OpenAI", 12, 5, "2026-07-01", "2026-07-01T12:00:00"),
            (2, "anthropic.com", "Anthropic", 8, 3, "2026-06-30", "2026-06-30T12:00:00"),
        ],
    )
    openai = conn.execute(
        "INSERT INTO kg_entities (canonical_name, entity_type, mention_count, importance, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        ("OpenAI", "Company", 9, 0.91, "2026-06-01", "2026-07-01"),
    ).lastrowid
    runtime = conn.execute(
        "INSERT INTO kg_entities (canonical_name, entity_type, mention_count, importance, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
        ("Agent Runtime", "Technology", 4, 0.72, "2026-06-20", "2026-07-01"),
    ).lastrowid
    conn.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)", (openai, "OpenAI"))
    conn.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)", (runtime, "Agent Runtime"))
    conn.execute(
        "INSERT INTO kg_edges (subject_id, predicate, object_id, fact_text, fact_type, confidence, finding_id, valid_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (openai, "RELEASED", runtime, "OpenAI released agent runtime reliability updates.", "Fact", 0.94, 101, "2026-07-01"),
    )
    conn.execute(
        """INSERT INTO entity_graph
           (entity_a, entity_a_type, relationship, entity_b, entity_b_type, finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("OpenAI", "company", "mentions", "Agent Runtime", "technology", 101, "2026-07-01T12:00:00"),
    )
    conn.commit()
    return conn


def test_list_entities_uses_kg_and_legacy_graph_with_pagination():
    model = CorpusGraphReadModel(_conn())
    page = model.list_entities(limit=1, offset=0)

    assert page["kind"] == "entities"
    assert page["total"] >= 2
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert page["has_more"] is True
    assert page["items"][0]["slug"] == "openai"
    assert page["items"][0]["target_url"] == "/e/openai"
    assert "kg_entities" in page["graph_sources"]

    search = model.list_entities(q="runtime", limit=10, offset=0)
    assert [item["slug"] for item in search["items"]] == ["agent-runtime"]


def test_entity_detail_returns_counts_edges_findings_and_sources():
    model = CorpusGraphReadModel(_conn())
    detail = model.get_entity("openai", limit=10, offset=0)

    assert detail["kind"] == "entity"
    assert detail["slug"] == "openai"
    assert detail["name"] == "OpenAI"
    assert detail["counts"]["findings"] >= 1
    assert detail["pagination"]["has_more"] is False
    assert detail["findings"][0]["id"] == 101
    assert detail["findings"][0]["target_url"] == "/f/101"
    assert detail["relationships"][0]["evidence_edges"]
    assert detail["source_trail"][0]["domain"] == "openai.com"
    assert "kg_edges" in detail["graph_sources"]
    assert "entity_graph" in detail["graph_sources"]


def test_source_and_finding_details_are_public_safe():
    model = CorpusGraphReadModel(_conn())

    source = model.get_source("openai.com", limit=10, offset=0)
    assert source["kind"] == "source"
    assert source["domain"] == "openai.com"
    assert source["counts"]["findings"] == 1
    assert source["findings"][0]["id"] == 101
    assert source["entities"][0]["slug"] == "openai"

    finding = model.get_finding(101)
    assert finding["kind"] == "finding"
    assert finding["source_refs"][0]["domain"] == "openai.com"
    assert any(entity["slug"] == "openai" for entity in finding["entities"])
    assert finding["provenance"]["generated_by"] == "mindpattern.site_graph.read_model"


def test_missing_tables_degrade_to_empty_public_shapes():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    model = CorpusGraphReadModel(conn)

    page = model.list_entities(limit=10, offset=0)
    assert page["items"] == []
    assert page["total"] == 0
    assert page["status"] == "degraded"
    assert "missing table" in page["degraded_reasons"][0]

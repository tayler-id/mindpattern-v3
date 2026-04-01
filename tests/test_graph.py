"""Tests for memory/graph.py — entity graph operations.

Uses an in-memory SQLite database with the real schema.
No network, no API keys, no embeddings required.
"""

import sqlite3

import pytest

from memory.graph import (
    entity_stats,
    find_path,
    query_entity,
    related_entities,
    store_relationship,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Fresh in-memory database with entity_graph table."""
    from memory.db import _init_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    yield conn
    conn.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestStoreRelationship:
    """Tests for store_relationship (add entity relationship)."""

    def test_add_entity_relationship(self, db):
        """Basic insert returns a positive row ID and persists data."""
        row_id = store_relationship(
            db,
            entity_a="OpenAI",
            relationship="competes_with",
            entity_b="Anthropic",
            entity_a_type="company",
            entity_b_type="company",
        )
        assert row_id is not None
        assert row_id > 0

        # Verify the row landed in the table
        row = db.execute(
            "SELECT * FROM entity_graph WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["entity_a"] == "OpenAI"
        assert row["relationship"] == "competes_with"
        assert row["entity_b"] == "Anthropic"
        assert row["entity_a_type"] == "company"
        assert row["entity_b_type"] == "company"
        assert row["created_at"] is not None

    def test_add_relationship_with_finding_id(self, db):
        """finding_id foreign key is stored correctly (NULL-safe)."""
        # Without finding_id
        r1 = store_relationship(db, "Alice", "knows", "Bob")
        row1 = db.execute(
            "SELECT finding_id FROM entity_graph WHERE id = ?", (r1,)
        ).fetchone()
        assert row1["finding_id"] is None

        # With finding_id (no FK enforcement since findings table may be empty)
        db.execute("PRAGMA foreign_keys=OFF")
        r2 = store_relationship(
            db, "Alice", "manages", "Charlie", finding_id=42
        )
        row2 = db.execute(
            "SELECT finding_id FROM entity_graph WHERE id = ?", (r2,)
        ).fetchone()
        assert row2["finding_id"] == 42

    def test_duplicate_relationship_handling(self, db):
        """Duplicate relationships are allowed — each insert creates a new row."""
        r1 = store_relationship(db, "X", "relates_to", "Y")
        r2 = store_relationship(db, "X", "relates_to", "Y")
        assert r1 != r2

        count = db.execute(
            "SELECT COUNT(*) as cnt FROM entity_graph "
            "WHERE entity_a = 'X' AND entity_b = 'Y'"
        ).fetchone()["cnt"]
        assert count == 2


class TestQueryEntity:
    """Tests for query_entity (get connections for an entity)."""

    def test_get_entity_connections(self, db):
        """query_entity returns relationships in both directions."""
        store_relationship(db, "Alice", "works_at", "Acme", "person", "company")
        store_relationship(db, "Bob", "reports_to", "Alice", "person", "person")

        result = query_entity(db, "Alice")

        assert result["entity"] == "Alice"
        assert len(result["relationships"]) == 2

        related_names = {r["related_entity"] for r in result["relationships"]}
        assert related_names == {"Acme", "Bob"}

    def test_empty_graph_query(self, db):
        """Querying an entity that does not exist returns empty results."""
        result = query_entity(db, "Ghost")

        assert result["entity"] == "Ghost"
        assert result["relationships"] == []
        assert result["findings_count"] == 0

    def test_findings_count(self, db):
        """findings_count reflects distinct non-null finding IDs."""
        db.execute("PRAGMA foreign_keys=OFF")
        store_relationship(db, "A", "r1", "B", finding_id=1)
        store_relationship(db, "A", "r2", "C", finding_id=1)  # same finding
        store_relationship(db, "A", "r3", "D", finding_id=2)
        store_relationship(db, "A", "r4", "E")  # no finding

        result = query_entity(db, "A")
        assert result["findings_count"] == 2  # findings 1 and 2


class TestEntitySearch:
    """Tests for related_entities (N-hop neighborhood search)."""

    def test_entity_search_depth_1(self, db):
        """Direct neighbors are returned at depth 1."""
        store_relationship(db, "Root", "connects", "Leaf1")
        store_relationship(db, "Root", "connects", "Leaf2")
        store_relationship(db, "Leaf1", "connects", "Leaf3")  # 2 hops from Root

        neighbors = related_entities(db, "Root", depth=1)

        entities = {n["entity"] for n in neighbors}
        assert entities == {"Leaf1", "Leaf2"}
        assert all(n["depth"] == 1 for n in neighbors)

    def test_entity_search_depth_2(self, db):
        """Depth-2 search includes indirect connections."""
        store_relationship(db, "A", "links", "B")
        store_relationship(db, "B", "links", "C")
        store_relationship(db, "C", "links", "D")

        neighbors = related_entities(db, "A", depth=2)

        entities = {n["entity"] for n in neighbors}
        assert "B" in entities  # 1 hop
        assert "C" in entities  # 2 hops
        assert "D" not in entities  # 3 hops — too far

    def test_entity_search_no_neighbors(self, db):
        """Isolated entity returns empty list."""
        store_relationship(db, "X", "links", "Y")

        neighbors = related_entities(db, "Z", depth=1)
        assert neighbors == []


class TestFindPath:
    """Tests for find_path (shortest path via recursive CTE)."""

    def test_direct_path(self, db):
        """Direct edge yields a 2-node path."""
        store_relationship(db, "Start", "direct", "End")

        path = find_path(db, "Start", "End")

        assert path is not None
        assert len(path) == 2
        assert path[0]["entity"] == "Start"
        assert path[-1]["entity"] == "End"
        assert path[1]["relationship"] == "direct"

    def test_multi_hop_path(self, db):
        """Path through intermediate nodes is discovered."""
        store_relationship(db, "A", "step1", "B")
        store_relationship(db, "B", "step2", "C")
        store_relationship(db, "C", "step3", "D")

        path = find_path(db, "A", "D")

        assert path is not None
        node_names = [p["entity"] for p in path]
        assert node_names[0] == "A"
        assert node_names[-1] == "D"
        assert len(node_names) == 4  # A -> B -> C -> D

    def test_no_path_exists(self, db):
        """Disconnected entities return None."""
        store_relationship(db, "Island1", "self", "Island2")
        store_relationship(db, "Mainland1", "road", "Mainland2")

        path = find_path(db, "Island1", "Mainland1")
        assert path is None

    def test_path_respects_max_depth(self, db):
        """Path longer than max_depth returns None."""
        store_relationship(db, "N1", "e", "N2")
        store_relationship(db, "N2", "e", "N3")
        store_relationship(db, "N3", "e", "N4")
        store_relationship(db, "N4", "e", "N5")

        # 4 hops: N1->N2->N3->N4->N5, max_depth=2 should fail
        path = find_path(db, "N1", "N5", max_depth=2)
        assert path is None

        # max_depth=4 should succeed
        path = find_path(db, "N1", "N5", max_depth=4)
        assert path is not None
        assert path[-1]["entity"] == "N5"


class TestEntityStats:
    """Tests for entity_stats (graph-wide statistics)."""

    def test_empty_graph_stats(self, db):
        """Empty graph returns zeros and empty top list."""
        stats = entity_stats(db)

        assert stats["total_entities"] == 0
        assert stats["total_relationships"] == 0
        assert stats["top_entities"] == []

    def test_populated_graph_stats(self, db):
        """Stats reflect actual entity and relationship counts."""
        store_relationship(db, "A", "r1", "B")
        store_relationship(db, "A", "r2", "C")
        store_relationship(db, "B", "r3", "C")

        stats = entity_stats(db)

        assert stats["total_entities"] == 3  # A, B, C
        assert stats["total_relationships"] == 3

        # A appears in all 3 relationships, so it should be top
        top_names = [t["entity"] for t in stats["top_entities"]]
        assert "A" in top_names

    def test_top_entities_ordering(self, db):
        """Top entities are sorted by connection count descending."""
        # Hub connects to many spokes
        for i in range(5):
            store_relationship(db, "Hub", f"spoke_{i}", f"Spoke{i}")
        # One isolated pair
        store_relationship(db, "Lone1", "pair", "Lone2")

        stats = entity_stats(db)
        top = stats["top_entities"]

        assert top[0]["entity"] == "Hub"
        assert top[0]["connection_count"] == 5

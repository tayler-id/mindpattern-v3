"""Tests for the knowledge-graph schema (kg/schema.py).

Pure-SQLite, no network/model deps. Validates table creation, idempotency,
alias resolution semantics, and — the important part — the bi-temporal
"current view": contradicted facts are invalidated, never deleted.
"""

import sqlite3

import pytest

from kg.schema import ENTITY_TYPES, FACT_TYPES, PREDICATES, init_kg_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    # minimal findings stub so the kg_edges.finding_id provenance FK can resolve
    c.execute("CREATE TABLE findings (id INTEGER PRIMARY KEY, title TEXT)")
    init_kg_schema(c)
    yield c
    c.close()


def _tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_creates_all_kg_tables(conn):
    assert {"kg_entities", "kg_entity_aliases", "kg_edges", "kg_communities"} <= _tables(conn)


def test_idempotent(conn):
    init_kg_schema(conn)
    init_kg_schema(conn)  # must not raise
    assert "kg_entities" in _tables(conn)


def test_alias_lookup_is_case_insensitive(conn):
    eid = conn.execute(
        "INSERT INTO kg_entities (canonical_name, entity_type) VALUES (?, ?)",
        ("Anthropic", "Company"),
    ).lastrowid
    conn.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)", (eid, "Anthropic"))
    conn.commit()

    row = conn.execute(
        "SELECT entity_id FROM kg_entity_aliases WHERE alias = ? COLLATE NOCASE",
        ("anthropic",),
    ).fetchone()
    assert row is not None and row["entity_id"] == eid


def test_alias_uniqueness_enforced(conn):
    eid = conn.execute(
        "INSERT INTO kg_entities (canonical_name, entity_type) VALUES (?, ?)",
        ("OpenAI", "Company"),
    ).lastrowid
    conn.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)", (eid, "OpenAI"))
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)", (eid, "OpenAI"))


def test_bitemporal_current_view_and_invalidation(conn):
    conn.execute("INSERT INTO findings (id, title) VALUES (1, 't')")
    a = conn.execute("INSERT INTO kg_entities (canonical_name, entity_type) VALUES ('A','Company')").lastrowid
    b = conn.execute("INSERT INTO kg_entities (canonical_name, entity_type) VALUES ('B','Product')").lastrowid

    e1 = conn.execute(
        "INSERT INTO kg_edges (subject_id, predicate, object_id, fact_text, fact_type, finding_id, valid_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (a, "RELEASED", b, "A released B", "Fact", 1, "2026-01-01"),
    ).lastrowid
    conn.commit()

    # current view = invalid_at IS NULL
    current = conn.execute("SELECT id FROM kg_edges WHERE invalid_at IS NULL").fetchall()
    assert {r["id"] for r in current} == {e1}

    # a contradicting fact arrives → supersede e1, never delete it
    e2 = conn.execute(
        "INSERT INTO kg_edges (subject_id, predicate, object_id, fact_text, fact_type, finding_id, valid_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (a, "DEPRECATES", b, "A deprecated B", "Fact", 1, "2026-06-01"),
    ).lastrowid
    conn.execute(
        "UPDATE kg_edges SET invalid_at = ?, invalidated_by = ? WHERE id = ?",
        ("2026-06-01", e2, e1),
    )
    conn.commit()

    current = conn.execute("SELECT id FROM kg_edges WHERE invalid_at IS NULL").fetchall()
    assert {r["id"] for r in current} == {e2}

    # the timeline retains both edges (nothing deleted)
    all_ids = {r["id"] for r in conn.execute("SELECT id FROM kg_edges").fetchall()}
    assert all_ids == {e1, e2}

    # the invalidated edge points at its successor
    assert conn.execute("SELECT invalidated_by FROM kg_edges WHERE id=?", (e1,)).fetchone()["invalidated_by"] == e2


def test_finding_provenance_is_nullable(conn):
    a = conn.execute("INSERT INTO kg_entities (canonical_name) VALUES ('X')").lastrowid
    b = conn.execute("INSERT INTO kg_entities (canonical_name) VALUES ('Y')").lastrowid
    # an edge with no single source episode (e.g. from synthesis) is allowed
    conn.execute(
        "INSERT INTO kg_edges (subject_id, predicate, object_id, fact_text) VALUES (?,?,?,?)",
        (a, "MENTIONS", b, "X mentions Y"),
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS c FROM kg_edges").fetchone()["c"] == 1


def test_cascade_delete_entity_removes_its_aliases(conn):
    eid = conn.execute("INSERT INTO kg_entities (canonical_name) VALUES ('Temp')").lastrowid
    conn.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)", (eid, "Temp"))
    conn.commit()
    conn.execute("DELETE FROM kg_entities WHERE id=?", (eid,))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) AS c FROM kg_entity_aliases").fetchone()["c"] == 0


def test_vocabulary_constants():
    assert "Company" in ENTITY_TYPES and "Funding" in ENTITY_TYPES
    assert "RELEASED" in PREDICATES and "ACQUIRED" in PREDICATES
    assert set(FACT_TYPES) == {"Fact", "Opinion", "Prediction"}

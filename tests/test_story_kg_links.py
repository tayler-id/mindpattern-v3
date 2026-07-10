"""KG-backed story-to-story links (dashboard/routes/api.py kg pair index)."""

import sqlite3

import pytest

from kg.schema import init_kg_schema


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_kg_schema(conn)
    anthropic = conn.execute(
        """INSERT INTO kg_entities (canonical_name, slug, entity_type, mention_count, importance)
           VALUES ('Anthropic', 'anthropic', 'Company', 9, 1.0)"""
    ).lastrowid
    humanloop = conn.execute(
        """INSERT INTO kg_entities (canonical_name, slug, entity_type, mention_count, importance)
           VALUES ('Humanloop', 'humanloop', 'Company', 2, 0.4)"""
    ).lastrowid
    legacy = conn.execute(
        """INSERT INTO kg_entities (canonical_name, entity_type, mention_count, importance)
           VALUES ('Node.js', 'Technology', 3, 0.5)"""
    ).lastrowid
    conn.executemany(
        """INSERT INTO kg_edges
           (subject_id, predicate, object_id, fact_text, fact_type, confidence, finding_id, valid_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (anthropic, "ACQUIRED", humanloop,
             "Anthropic acquired Humanloop.", "Fact", 0.95, 11, "2026-07-01"),
            # below the confidence floor: must not appear
            (anthropic, "USES", humanloop, "", "Fact", 0.4, 12, "2026-07-01"),
            # MENTIONS is hub noise: must not appear
            (anthropic, "MENTIONS", humanloop, "", "Fact", 1.0, 13, "2026-07-01"),
            # opinion never links stories as if it were fact
            (anthropic, "CRITICIZES", humanloop, "", "Opinion", 1.0, 14, "2026-07-01"),
            # legacy NULL-slug entity resolves via the name normalizer
            (anthropic, "SUPPORTS", legacy,
             "Anthropic supports Node.js tooling.", "Fact", 0.9, 15, "2026-07-01"),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def kg_api(tmp_path, monkeypatch):
    from dashboard.routes import api as api_routes

    user_dir = tmp_path / "data" / "ramsay"
    user_dir.mkdir(parents=True)
    _make_db(user_dir / "memory.db")
    monkeypatch.setattr(api_routes, "DATA_DIR", tmp_path / "data")
    api_routes._KG_PAIR_EDGE_CACHE.clear()
    yield api_routes


def test_pair_index_keeps_only_linkable_facts(kg_api):
    index = kg_api._kg_pair_edge_index("ramsay")
    edges = index[("anthropic", "humanloop")]
    assert [e["predicate"] for e in edges] == ["ACQUIRED"]
    assert edges[0]["subject_slug"] == "anthropic"
    assert edges[0]["object_slug"] == "humanloop"
    assert edges[0]["finding_id"] == 11


def test_pair_index_resolves_legacy_null_slug_rows(kg_api):
    index = kg_api._kg_pair_edge_index("ramsay")
    edges = index[("anthropic", "node-js")]
    assert edges[0]["predicate"] == "SUPPORTS"
    assert edges[0]["object_slug"] == "node-js"


def test_pair_index_fails_open_without_db(kg_api, monkeypatch):
    monkeypatch.setattr(kg_api, "get_memory_db", lambda user: None)
    assert kg_api._kg_pair_edge_index("ramsay") == {}


def test_edges_between_story_slug_sets(kg_api):
    index = kg_api._kg_pair_edge_index("ramsay")
    edges = kg_api._kg_edges_between(index, {"anthropic"}, {"humanloop", "node-js"})
    assert {e["predicate"] for e in edges} == {"ACQUIRED", "SUPPORTS"}
    # best-confidence first, deduped, capped at 3
    assert edges[0]["predicate"] == "ACQUIRED"
    assert kg_api._kg_edges_between(index, {"anthropic"}, {"anthropic"}) == []
    assert kg_api._kg_edges_between({}, {"anthropic"}, {"humanloop"}) == []


def test_repeated_claims_collapse_to_one_slot(kg_api):
    index = {
        ("anthropic", "openai"): [
            {"id": i, "predicate": "PARTNERS_WITH", "confidence": 1.0,
             "subject_slug": "anthropic", "object_slug": "openai"}
            for i in (1, 2, 3)
        ]
        + [{"id": 4, "predicate": "COMPETES_WITH", "confidence": 0.9,
            "subject_slug": "anthropic", "object_slug": "openai"}]
    }
    edges = kg_api._kg_edges_between(index, {"anthropic"}, {"openai"})
    assert [e["predicate"] for e in edges] == ["PARTNERS_WITH", "COMPETES_WITH"]


def test_story_related_paths_gain_kg_link_end_to_end(kg_api):
    story = {
        "slug": "a", "id": "a", "title": "Anthropic story", "issue_date": "2026-07-01",
        "target_url": "/s/a",
        "entity_refs": [{"id": "anthropic", "slug": "anthropic", "name": "Anthropic"}],
        "graph_connectors": {"entity_ids": ["anthropic"]},
    }
    candidate = {
        "slug": "b", "id": "b", "title": "Humanloop story", "issue_date": "2026-07-02",
        "target_url": "/s/b",
        "entity_refs": [{"id": "humanloop", "slug": "humanloop", "name": "Humanloop"}],
        "graph_connectors": {"entity_ids": ["humanloop"]},
    }
    enriched = kg_api._story_with_graph_related(story, [candidate], user="ramsay")
    paths = enriched["related_paths"]
    assert len(paths) == 1
    assert "Anthropic acquired Humanloop" in paths[0]["connector_labels"]

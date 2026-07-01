import json
import sqlite3
import struct

import pytest
from fastapi.testclient import TestClient

from kg.schema import init_kg_schema


def _embedding_blob(x: float, y: float = 0.0) -> bytes:
    return struct.pack("2f", x, y)


def _create_graph_db(path):
    conn = sqlite3.connect(path)
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
                "2026-06-29",
                "policy-agent",
                "OpenAI policy dependency widens",
                "A Commerce Department policy dependency changes how OpenAI ships models.",
                "medium",
                "policy",
                "https://commerce.gov/ai/export-controls",
                "Commerce Department",
                "2026-06-29T12:00:00",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)",
        [
            (101, _embedding_blob(1.0, 0.0)),
            (102, _embedding_blob(0.86, 0.0)),
            (103, _embedding_blob(0.2, 0.7)),
        ],
    )
    conn.executemany(
        """INSERT INTO sources
           (id, url_domain, display_name, hit_count, high_value_count, last_seen, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (1, "openai.com", "OpenAI", 12, 5, "2026-07-01", "2026-07-01T12:00:00"),
            (2, "anthropic.com", "Anthropic", 8, 3, "2026-06-30", "2026-06-30T12:00:00"),
            (3, "commerce.gov", "Commerce Department", 3, 2, "2026-06-29", "2026-06-29T12:00:00"),
        ],
    )
    openai = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("OpenAI", "Company", 9, 0.91, "2026-06-01", "2026-07-01"),
    ).lastrowid
    runtime = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Agent Runtime", "Technology", 4, 0.72, "2026-06-20", "2026-07-01"),
    ).lastrowid
    anthropic = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Anthropic", "Company", 5, 0.7, "2026-06-01", "2026-06-30"),
    ).lastrowid
    conn.executemany(
        "INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)",
        [(openai, "OpenAI"), (runtime, "Agent Runtime"), (anthropic, "Anthropic")],
    )
    conn.executemany(
        """INSERT INTO kg_edges
           (subject_id, predicate, object_id, fact_text, fact_type, confidence, finding_id, valid_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                openai,
                "RELEASED",
                runtime,
                "OpenAI released agent runtime reliability updates.",
                "Fact",
                0.94,
                101,
                "2026-07-01",
            ),
            (
                anthropic,
                "SUPPORTS",
                runtime,
                "Anthropic positioned Claude Code around runtime reliability.",
                "Fact",
                0.81,
                102,
                "2026-06-30",
            ),
        ],
    )
    conn.executemany(
        """INSERT INTO entity_graph
           (entity_a, entity_a_type, relationship, entity_b, entity_b_type, finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ("OpenAI", "company", "mentions", "Agent Runtime", "technology", 101, "2026-07-01T12:00:00"),
            ("Anthropic", "company", "mentions", "Agent Runtime", "technology", 102, "2026-06-30T12:00:00"),
            ("OpenAI", "company", "depends_on", "Commerce Department", "policy", 103, "2026-06-29T12:00:00"),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def graph_client(tmp_path, monkeypatch):
    from dashboard.routes import api as api_routes

    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    user_dir = data_dir / "ramsay"
    user_dir.mkdir(parents=True)
    _create_graph_db(user_dir / "memory.db")

    arcs_dir = reports_dir / "ramsay" / "arcs"
    arcs_dir.mkdir(parents=True)
    (arcs_dir / "2026-07-01.json").write_text(
        json.dumps(
            {
                "date": "2026-07-01",
                "user": "ramsay",
                "arcs": [
                    {
                        "id": "agent-runtime-control-plane",
                        "title": "Agent runtime reliability becomes a control plane",
                        "summary": "OpenAI and Anthropic both moved reliability into the buying criteria.",
                        "status": "active",
                        "first_seen": "2026-06-30",
                        "last_seen": "2026-07-01",
                        "evidence_count": 2,
                        "date_count": 2,
                        "source_domain_count": 2,
                        "agent_count": 1,
                        "scores": {
                            "recurrence": 0.7,
                            "velocity": 0.8,
                            "source_diversity": 0.6,
                            "freshness": 1.0,
                            "confidence": 0.82,
                        },
                        "evidence": [
                            {
                                "finding_id": 101,
                                "run_date": "2026-07-01",
                                "agent": "fixture-agent",
                                "title": "OpenAI agent runtime reliability",
                                "summary": "OpenAI made agent runtime reliability a benchmark.",
                                "source_url": "https://openai.com/news/agents",
                                "source_name": "OpenAI",
                            }
                        ],
                    }
                ],
            }
        )
    )

    monkeypatch.setattr(api_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)

    from dashboard.app import app

    with TestClient(app) as client:
        yield client


def test_entity_index_api_uses_full_corpus_graph(graph_client):
    resp = graph_client.get("/api/entities?user=ramsay&limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "entities"
    assert body["total"] >= 3
    assert body["limit"] == 2
    assert body["has_more"] is True
    assert body["items"][0]["slug"] == "openai"
    assert body["items"][0]["target_url"] == "/e/openai"
    assert "kg_entities" in body["graph_sources"]

    search = graph_client.get("/api/entities?q=runtime&user=ramsay&limit=10")
    assert search.status_code == 200
    assert [item["slug"] for item in search.json()["items"]] == ["agent-runtime"]

    unsafe = graph_client.get("/api/entities?user=../ramsay")
    assert unsafe.status_code == 200
    assert unsafe.json()["items"] == []


def test_entity_detail_and_neighbors_are_evidence_backed(graph_client):
    resp = graph_client.get("/api/entities/openai?user=ramsay&limit=5")
    assert resp.status_code == 200
    entity = resp.json()
    assert entity["kind"] == "entity"
    assert entity["slug"] == "openai"
    assert entity["counts"]["findings"] >= 2
    assert entity["pagination"]["limit"] == 5
    assert entity["findings"][0]["target_url"].startswith("/f/")
    assert any(rel["evidence_edges"] for rel in entity["relationships"])
    assert "openai.com" in {source["domain"] for source in entity["source_trail"]}
    assert "kg_edges" in entity["graph_sources"]
    assert "entity_graph" in entity["graph_sources"]

    neighbors = graph_client.get("/api/entities/openai/neighbors?user=ramsay&limit=10")
    assert neighbors.status_code == 200
    body = neighbors.json()
    assert body["kind"] == "entity_neighbors"
    assert {item["slug"] for item in body["items"]} >= {"agent-runtime", "commerce-department"}
    assert all(item["evidence_edges"] for item in body["items"])

    assert graph_client.get("/api/entities/and?user=ramsay").status_code == 404
    assert graph_client.get("/api/entities/openai?user=../ramsay").status_code == 404


def test_source_and_finding_detail_apis_are_public_safe(graph_client):
    source = graph_client.get("/api/sources/openai.com?user=ramsay&limit=5")
    assert source.status_code == 200
    source_body = source.json()
    assert source_body["kind"] == "source"
    assert source_body["domain"] == "openai.com"
    assert source_body["counts"]["findings"] == 1
    assert source_body["findings"][0]["id"] == 101
    assert source_body["entities"][0]["target_url"].startswith("/e/")
    assert source_body["pagination"]["has_more"] is False

    finding = graph_client.get("/api/findings/101?user=ramsay")
    assert finding.status_code == 200
    finding_body = finding.json()
    assert finding_body["kind"] == "finding"
    assert finding_body["source_refs"][0]["domain"] == "openai.com"
    assert {entity["slug"] for entity in finding_body["entities"]} >= {"openai", "agent-runtime"}
    assert finding_body["provenance"]["redaction_status"] == "passed"

    legacy = graph_client.get("/api/finding/101?user=ramsay")
    assert legacy.status_code == 200
    assert legacy.json()["source_refs"][0]["domain"] == "openai.com"

    assert graph_client.get("/api/sources/..%2Fsecret?user=ramsay").status_code == 404
    assert graph_client.get("/api/findings/999999?user=ramsay").status_code == 404


def test_arc_detail_and_related_paths_expose_readable_connectors(graph_client):
    arc = graph_client.get("/api/narrative-arcs/agent-runtime-control-plane?date=2026-07-01&user=ramsay")
    assert arc.status_code == 200
    assert arc.json()["id"] == "agent-runtime-control-plane"
    assert arc.json()["evidence"][0]["finding_id"] == 101

    related = graph_client.get("/api/related/101?mode=blended&limit=5&user=ramsay")
    assert related.status_code == 200
    body = related.json()
    assert body["kind"] == "related"
    assert body["finding_id"] == 101
    assert body["mode"] == "blended"
    assert body["items"]
    labels = {label for item in body["items"] for label in item["connector_labels"]}
    assert "Shared entity" in labels
    assert "Semantic neighbor" in labels
    assert all(item["reason"] for item in body["items"])
    assert all("Top 5 Stories Today" not in item["title"] for item in body["items"])

    assert graph_client.get("/api/related/101?mode=graph&user=ramsay").status_code == 400
    assert graph_client.get("/api/related/101?mode=blended&user=../ramsay").status_code == 404

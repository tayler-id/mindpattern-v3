"""Entity/source dossier artifacts (orchestrator/site_dossiers.py) + API."""

import json
import sqlite3
from pathlib import Path

import pytest

from orchestrator.site_dossiers import (
    build_entity_dossier,
    build_source_dossier,
    run_dossier_generation,
)
from orchestrator.site_graph import CorpusGraphReadModel


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE findings (
            id INTEGER PRIMARY KEY, run_date TEXT, agent TEXT, title TEXT,
            summary TEXT, importance TEXT, category TEXT, source_url TEXT,
            source_name TEXT, created_at TEXT)"""
    )
    rows = [
        (101, "2026-07-01", "agent", "OpenAI hardened agent runtime reliability",
         "OpenAI made agent runtime reliability a buyer-visible benchmark.",
         "high", "ai", "https://openai.com/news/agents", "OpenAI", "2026-07-01"),
        (102, "2026-06-30", "agent", "OpenAI runtime pricing shifts",
         "OpenAI moved agent runtime pricing to per-token.",
         "high", "ai", "https://openai.com/news/pricing", "OpenAI", "2026-06-30"),
    ]
    conn.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.execute(
        """CREATE TABLE sources (
            id INTEGER PRIMARY KEY, url_domain TEXT, display_name TEXT,
            hit_count INTEGER, high_value_count INTEGER, last_seen TEXT, created_at TEXT)"""
    )
    conn.execute(
        "INSERT INTO sources VALUES (1, 'openai.com', 'OpenAI', 12, 5, '2026-07-01', '2026-06-01')"
    )
    conn.commit()
    return conn


def test_entity_dossier_builds_from_corpus_evidence(conn):
    model = CorpusGraphReadModel(conn)
    dossier = build_entity_dossier(model, "openai", date="2026-07-01", user="ramsay")
    assert dossier is not None
    assert dossier["kind"] == "entity_dossier"
    assert dossier["slug"] == "openai"
    assert dossier["confidence"] == "source-backed"
    assert dossier["timeline"]
    assert dossier["timeline"][0]["date"] >= dossier["timeline"][-1]["date"]
    assert dossier["top_sources"][0]["domain"] == "openai.com"
    assert dossier["target_url"] == "/e/openai"
    assert dossier["provenance"]["redaction_status"] == "passed"


def test_entity_dossier_returns_none_without_evidence(conn):
    model = CorpusGraphReadModel(conn)
    assert build_entity_dossier(model, "unknown-entity", date="2026-07-01", user="ramsay") is None


def test_source_dossier_builds_from_corpus_evidence(conn):
    model = CorpusGraphReadModel(conn)
    dossier = build_source_dossier(model, "openai.com", date="2026-07-01", user="ramsay")
    assert dossier is not None
    assert dossier["kind"] == "source_dossier"
    assert dossier["domain"] == "openai.com"
    assert dossier["recent_findings"]
    assert dossier["target_url"] == "/source/openai.com"


def test_run_dossier_generation_writes_artifacts(conn, tmp_path):
    result = run_dossier_generation(
        conn, date="2026-07-01", user="ramsay", reports_root=tmp_path
    )
    assert result["written"] >= 1
    entity_files = list((tmp_path / "ramsay" / "site-dossiers" / "entities").glob("*.json"))
    source_files = list((tmp_path / "ramsay" / "site-dossiers" / "sources").glob("*.json"))
    assert source_files, "source dossiers must be written"
    for path in entity_files + source_files:
        payload = json.loads(path.read_text())
        assert payload["provenance"]["redaction_status"] == "passed"
        serialized = json.dumps(payload).lower()
        assert "xoxb-" not in serialized
        assert "subscriber" not in serialized


def test_dossier_api_endpoints(conn, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from dashboard.app import app
    from dashboard.routes import api as api_routes

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    run_dossier_generation(conn, date="2026-07-01", user="ramsay", reports_root=reports_dir)
    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    client = TestClient(app)

    resp = client.get("/api/dossiers/sources/openai.com?user=ramsay")
    assert resp.status_code == 200
    dossier = resp.json()
    assert dossier["kind"] == "source_dossier"
    assert dossier["domain"] == "openai.com"

    assert client.get("/api/dossiers/entities/announced?user=ramsay").status_code == 404
    assert client.get("/api/dossiers/entities/missing-entity?user=ramsay").status_code == 404
    assert client.get("/api/dossiers/sources/unknown.example?user=ramsay").status_code == 404


def test_dossier_entity_filter_rejects_sentence_slugs():
    from orchestrator.site_dossiers import _is_dossier_entity

    assert _is_dossier_entity("openai", "OpenAI")
    assert _is_dossier_entity("adversa-ai", "Adversa AI")
    assert not _is_dossier_entity("unknown", "Unknown")
    assert not _is_dossier_entity(
        "adversa-ai-march-2026-roundup-43-of-mcp-servers-vulnerable", ""
    )
    assert not _is_dossier_entity("announced", "Announced")

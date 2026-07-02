"""Unified site search endpoint (/api/search/site)."""

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routes import api as api_routes


@pytest.fixture
def client(monkeypatch):
    stories = [
        {"slug": "2026-07-01-webkit-ships-mcp", "title": "WebKit ships an MCP server",
         "dek": "Safari joins the agent era.", "summary": "WebKit shipped MCP support.",
         "issue_date": "2026-07-01", "target_url": "/s/2026-07-01-webkit-ships-mcp",
         "take": "A take.", "section_id": "agents",
         "graph_connectors": {"source_domains": ["webkit.org"]}},
        {"slug": "2026-06-01-old-mcp-story", "title": "MCP early days",
         "dek": "", "summary": "Early MCP coverage.", "issue_date": "2026-06-01",
         "target_url": "/s/2026-06-01-old-mcp-story", "take": "", "section_id": "research",
         "graph_connectors": {"source_domains": ["arxiv.org"]}},
    ]

    async def fake_stories(user):
        return stories
    monkeypatch.setattr(api_routes, "_all_public_stories", fake_stories)

    async def fake_findings(q, limit, user):
        return [{"id": 42, "title": "MCP finding", "summary": "About MCP.",
                 "run_date": "2026-07-01", "source_url": "https://webkit.org/x",
                 "similarity": 0.71}]
    monkeypatch.setattr(api_routes, "search_findings", fake_findings)
    monkeypatch.setattr(api_routes, "_open_graph_model", lambda user: None)
    monkeypatch.setattr(api_routes, "get_memory_db", lambda user: None)
    return TestClient(app)


def test_empty_query_returns_empty_groups(client):
    assert client.get("/api/search/site?q=").json()["groups"] == {}


def test_grouped_results_across_types(client):
    payload = client.get("/api/search/site?q=mcp").json()
    assert payload["kind"] == "site_search"
    assert [s["slug"] for s in payload["groups"]["stories"]] == [
        "2026-07-01-webkit-ships-mcp", "2026-06-01-old-mcp-story",
    ]
    assert payload["groups"]["stories"][0]["has_take"] is True
    assert payload["groups"]["findings"][0]["target_url"] == "/f/42"
    assert payload["groups"]["entities"] == []
    assert payload["groups"]["sources"] == []


def test_filters_narrow_stories(client):
    by_section = client.get("/api/search/site?q=mcp&section=agents").json()
    assert len(by_section["groups"]["stories"]) == 1
    by_date = client.get("/api/search/site?q=mcp&from=2026-06-15").json()
    assert len(by_date["groups"]["stories"]) == 1
    by_domain = client.get("/api/search/site?q=mcp&domain=arxiv.org").json()
    assert by_domain["groups"]["stories"][0]["slug"] == "2026-06-01-old-mcp-story"


def test_types_param_limits_groups(client):
    payload = client.get("/api/search/site?q=mcp&types=stories").json()
    assert set(payload["groups"].keys()) == {"stories"}


def test_take_filter_lists_takes_archive_wide(client):
    payload = client.get("/api/search/site?q=&take=1").json()
    slugs = [s["slug"] for s in payload["groups"]["stories"]]
    assert slugs == ["2026-07-01-webkit-ships-mcp"]
    assert payload["totals"]["stories"] == 1
    with_query = client.get("/api/search/site?q=mcp&take=1").json()
    assert len(with_query["groups"]["stories"]) == 1


def test_story_offset_pages_through_matches(client):
    first = client.get("/api/search/site?q=mcp&types=stories&limit=1&offset=0").json()
    second = client.get("/api/search/site?q=mcp&types=stories&limit=1&offset=1").json()
    assert first["groups"]["stories"][0]["slug"] != second["groups"]["stories"][0]["slug"]
    assert first["totals"]["stories"] == 2

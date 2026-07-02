import json

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routes import api as api_routes


@pytest.fixture()
def client_with_site_artifacts(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    user_dir = reports_dir / "ramsay"
    story_dir = user_dir / "site-stories" / "2026-07-01"
    run_dir = user_dir / "site-runs"
    corpus_dir = user_dir / "site-corpus"
    story_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    corpus_dir.mkdir(parents=True)

    (story_dir / "openai-agent-runtime.json").write_text(
        json.dumps(
            {
                "kind": "site_story",
                "id": "openai-agent-runtime",
                "slug": "openai-agent-runtime",
                "status": "published",
                "confidence": "high",
                "issue_date": "2026-07-01",
                "title": "OpenAI agent runtime reliability becomes a public benchmark",
                "dek": "A source-backed Rabbit Hole story artifact.",
                "summary": "OpenAI made agent runtime reliability a buyer-visible benchmark.",
                "take": "Runtime reliability is moving from internal plumbing to public buying criteria.",
                "why_now": "The July 1 corpus connected product updates, source evidence, and graph recurrence.",
                "body_markdown": "OpenAI made agent runtime reliability a buyer-visible benchmark.",
                "source_refs": [
                    {
                        "url": "https://openai.com/news/agents",
                        "domain": "openai.com",
                        "title": "OpenAI agent update",
                    }
                ],
                "entity_refs": [
                    {"id": "openai", "slug": "openai", "name": "OpenAI", "kind": "company"}
                ],
                "primary_finding_ids": [101],
                "supporting_finding_ids": [102],
                "arc_ids": ["agent-runtime-reliability"],
                "graph_edges": [
                    {
                        "kind": "entity",
                        "relationship": "same_entity",
                        "id": "openai",
                        "label": "OpenAI",
                        "target_url": "/e/openai",
                        "evidence": "finding:101",
                    }
                ],
                "related_paths": [],
                "claim_evidence": [
                    {
                        "claim": "OpenAI made runtime reliability a buyer-visible benchmark.",
                        "source_url": "https://openai.com/news/agents",
                        "finding_id": 101,
                    }
                ],
                "provenance": {
                    "generated_by": "mindpattern.site_content.story_engine",
                    "generated_at": "2026-07-01T12:00:00+00:00",
                    "input_artifacts": ["reports/ramsay/site-graph-packs/2026-07-01/openai-agent-runtime.json"],
                    "source_finding_ids": [101, 102],
                    "source_issue_dates": ["2026-07-01"],
                    "redaction_status": "passed",
                    "ai_generated": True,
                    "human_approved": False,
                },
                "json_ld_ready": True,
            }
        )
    )
    (story_dir / "bad-published-parser-chunk.json").write_text(
        json.dumps(
            {
                "kind": "site_story",
                "slug": "bad-published-parser-chunk",
                "status": "published",
                "confidence": "high",
                "issue_date": "2026-07-01",
                "title": "Top 5 Stories Today",
                "why_now": "Parser chunk leaked.",
                "source_refs": [{"url": "https://example.com", "domain": "example.com"}],
                "claim_evidence": [{"claim": "Bad parser chunk."}],
                "graph_edges": [],
                "provenance": {"redaction_status": "passed"},
            }
        )
    )
    (story_dir / "draft-story.json").write_text(
        json.dumps(
            {
                "kind": "site_story",
                "slug": "draft-story",
                "status": "draft",
                "confidence": "high",
                "issue_date": "2026-07-01",
                "title": "Draft story",
            }
        )
    )
    (run_dir / "2026-07-01.json").write_text(
        json.dumps(
            {
                "kind": "site_run",
                "date": "2026-07-01",
                "status": "completed",
                "generated_story_count": 1,
                "raw_slack_body": "must not leak",
                "summary": "Contact owner@example.test token=fake-token-value",
            }
        )
    )
    (corpus_dir / "2026-07-01.json").write_text(
        json.dumps(
            {
                "kind": "site_corpus",
                "date": "2026-07-01",
                "status": "ready",
                "counts": {"findings": 300, "entities": 14000, "edges": 42000},
                "coverage": {"has_embeddings": True},
                "subscriber_email": "reader@example.com",
            }
        )
    )

    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    with TestClient(app) as client:
        yield client


def test_story_api_reads_dated_site_story_artifacts_only(client_with_site_artifacts):
    listing = client_with_site_artifacts.get("/api/stories?user=ramsay&limit=10")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert [item["slug"] for item in body["items"]] == ["openai-agent-runtime"]
    assert body["items"][0]["kind"] == "story"
    assert body["items"][0]["status"] == "published"
    assert body["items"][0]["confidence"] == "high"
    assert body["items"][0]["graph_edges"]
    assert "Top 5 Stories Today" not in {item["title"] for item in body["items"]}

    detail = client_with_site_artifacts.get("/api/stories/openai-agent-runtime?user=ramsay")
    assert detail.status_code == 200
    story = detail.json()
    assert story["slug"] == "openai-agent-runtime"
    assert story["issue_date"] == "2026-07-01"
    assert story["source_refs"][0]["domain"] == "openai.com"
    assert story["provenance"]["redaction_status"] == "passed"

    assert client_with_site_artifacts.get("/api/stories/bad-published-parser-chunk?user=ramsay").status_code == 404
    assert client_with_site_artifacts.get("/api/stories/draft-story?user=ramsay").status_code == 404
    assert client_with_site_artifacts.get("/api/stories/%2E%2E%2Fsecret?user=ramsay").status_code == 404


def test_site_run_and_corpus_api_return_safe_public_artifacts(client_with_site_artifacts):
    run = client_with_site_artifacts.get("/api/site/runs/2026-07-01?user=ramsay")
    assert run.status_code == 200
    run_body = run.json()
    assert run_body["kind"] == "site_run"
    assert run_body["date"] == "2026-07-01"
    serialized_run = json.dumps(run_body)
    assert "owner@example.test" not in serialized_run
    assert "fake-token-value" not in serialized_run
    assert "raw_slack_body" not in serialized_run

    corpus = client_with_site_artifacts.get("/api/site/corpus/2026-07-01?user=ramsay")
    assert corpus.status_code == 200
    corpus_body = corpus.json()
    assert corpus_body["kind"] == "site_corpus"
    assert corpus_body["counts"]["entities"] == 14000
    assert "subscriber_email" not in json.dumps(corpus_body)

    missing = client_with_site_artifacts.get("/api/site/runs/2026-07-02?user=ramsay")
    assert missing.status_code == 200
    assert missing.json()["status"] == "missing"
    assert client_with_site_artifacts.get("/api/site/runs/2026-99-99?user=ramsay").status_code == 404
    assert client_with_site_artifacts.get("/api/site/corpus/2026-07-01?user=../ramsay").status_code == 404


def test_site_sitemap_lists_substantive_pages(client_with_site_artifacts):
    client = client_with_site_artifacts
    resp = client.get("/api/site/sitemap?user=ramsay")
    assert resp.status_code == 200
    sitemap = resp.json()
    assert sitemap["kind"] == "site_sitemap"
    slugs = {item["slug"] for item in sitemap["stories"]}
    assert "openai-agent-runtime" in slugs
    for item in sitemap["stories"]:
        assert item["slug"]
    assert isinstance(sitemap["entities"], list)
    assert isinstance(sitemap["sources"], list)
    assert isinstance(sitemap["briefings"], list)

    missing_user = client.get("/api/site/sitemap?user=../ramsay")
    assert missing_user.json()["stories"] == []


def test_source_backed_writer_artifacts_pass_the_public_gate():
    from dashboard.routes.api import _public_story_artifact

    artifact = {
        "kind": "site_story",
        "id": "2026-07-02-webkit-story",
        "slug": "2026-07-02-webkit-story",
        "status": "published",
        "confidence": "source-backed",
        "issue_date": "2026-07-02",
        "title": "WebKit shipped an official Safari MCP server",
        "dek": "Agents can drive Safari through the browser itself.",
        "take": "MCP only wins if the other engines follow.",
        "why_now": "Shipped with the July 2 briefing cycle.",
        "summary": "WebKit shipped an MCP server.",
        "body_markdown": "WebKit shipped an MCP server for Safari.",
        "source_refs": [{"url": "https://webkit.org/blog/mcp", "domain": "webkit.org", "title": "WebKit Blog"}],
        "entity_refs": [{"id": "webkit", "slug": "webkit", "name": "WebKit", "kind": "org"}],
        "claim_evidence": [{"claim": "WebKit shipped an MCP server", "source_url": "https://webkit.org/blog/mcp"}],
        "graph_edges": [{"kind": "source_domain", "relationship": "cites_source_domain",
                         "id": "webkit.org", "label": "webkit.org", "target_url": "/source/webkit.org"}],
        "provenance": {"generated_by": "mindpattern.site_backfill.writer_harness",
                       "ai_generated": True, "writer": "claude-cli", "redaction_status": "passed"},
    }
    public = _public_story_artifact(artifact, fallback_slug="2026-07-02-webkit-story")
    assert public is not None
    assert public["take"] == "MCP only wins if the other engines follow."
    assert public["provenance"]["writer"] == "claude-cli"

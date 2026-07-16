"""Exact story-revision identity endpoint (CampaignOS pilot spec 6.1, gate G4).

/api/stories/{slug}/revision exposes the SHA-256 of the exact raw story file
bytes served for /s/<slug> — the file is never rewritten or re-serialized.
Slug resolution is deterministic and date-scoped: bare-slug and date-prefixed
filenames are the same story, and a slug matching more than one file (across
archive dates or within one date) is an explicit rejection, never first-match.
The public story route applies the same rule.
"""

import hashlib
import json
import logging

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routes import api as api_routes


def _story_payload(slug: str, date: str, title: str) -> dict:
    """A minimal artifact that passes the public site-story gate."""
    return {
        "kind": "site_story",
        "id": slug,
        "slug": slug,
        "status": "published",
        "confidence": "high",
        "issue_date": date,
        "title": title,
        "dek": "A source-backed fixture story.",
        "summary": f"Fixture summary for {title}.",
        "take": "Fixture take.",
        "why_now": f"The {date} corpus surfaced it.",
        "body_markdown": f"Fixture body for {title}.",
        "source_refs": [
            {"url": "https://example.com/source", "domain": "example.com", "title": "Source"}
        ],
        "entity_refs": [],
        "graph_edges": [
            {
                "kind": "source_domain",
                "relationship": "cites_source_domain",
                "id": "example.com",
                "label": "example.com",
                "target_url": "/source/example.com",
            }
        ],
        "related_paths": [],
        "claim_evidence": [
            {"claim": f"Fixture claim for {title}.", "source_url": "https://example.com/source"}
        ],
        "provenance": {
            "generated_by": "mindpattern.site_content.story_engine",
            "redaction_status": "passed",
            "ai_generated": True,
        },
    }


def _write_story(path, payload: dict) -> bytes:
    """Write a story file with distinctive raw formatting; return its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return raw


@pytest.fixture()
def revision_client(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    stories = reports_dir / "ramsay" / "site-stories"

    fixtures: dict[str, bytes] = {}
    # Unique bare-slug story.
    fixtures["alpha"] = _write_story(
        stories / "2026-07-01" / "alpha-story.json",
        _story_payload("alpha-story", "2026-07-01", "Alpha story lands"),
    )
    # Unique story stored only under its date-prefixed filename.
    fixtures["beta"] = _write_story(
        stories / "2026-07-02" / "2026-07-02-beta-story.json",
        _story_payload("2026-07-02-beta-story", "2026-07-02", "Beta story lands"),
    )
    # Same-date duplicate pair: bare and date-prefixed variants, differing bytes.
    fixtures["dup_bare"] = _write_story(
        stories / "2026-07-03" / "dup-story.json",
        _story_payload("dup-story", "2026-07-03", "Dup story, bare variant"),
    )
    fixtures["dup_prefixed"] = _write_story(
        stories / "2026-07-03" / "2026-07-03-dup-story.json",
        _story_payload("2026-07-03-dup-story", "2026-07-03", "Dup story, prefixed variant"),
    )
    # Cross-date duplicate: the same bare slug under two archive dates.
    fixtures["cross_old"] = _write_story(
        stories / "2026-07-01" / "cross-dup.json",
        _story_payload("cross-dup", "2026-07-01", "Cross dup, old revision"),
    )
    fixtures["cross_new"] = _write_story(
        stories / "2026-07-02" / "cross-dup.json",
        _story_payload("cross-dup", "2026-07-02", "Cross dup, new revision"),
    )
    # Draft: on disk but never publicly served.
    draft = _story_payload("draft-story", "2026-07-01", "Draft story")
    draft["status"] = "draft"
    _write_story(stories / "2026-07-01" / "draft-story.json", draft)
    # Legacy layout: a story file directly under site-stories/ (no date dir).
    fixtures["legacy"] = _write_story(
        stories / "legacy-story.json",
        _story_payload("legacy-story", "2026-06-01", "Legacy story lands"),
    )

    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(api_routes, "_STORY_RESPONSE_CACHE", {})
    monkeypatch.setattr(api_routes, "_STORY_LIST_CACHE", {})
    with TestClient(app) as client:
        yield client, fixtures


def test_revision_reports_sha256_of_exact_raw_bytes(revision_client):
    client, fixtures = revision_client
    resp = client.get("/api/stories/alpha-story/revision?user=ramsay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "story_revision"
    assert body["story_revision_sha256"] == hashlib.sha256(fixtures["alpha"]).hexdigest()
    assert body["story_date"] == "2026-07-01"
    assert body["story_slug"] == "alpha-story"
    assert body["story_filename"] == "alpha-story.json"
    # The hash is of the raw bytes on disk, not a re-serialization: the same
    # JSON document with different whitespace must yield a different hash.
    reserialized = json.dumps(json.loads(fixtures["alpha"])).encode()
    assert body["story_revision_sha256"] != hashlib.sha256(reserialized).hexdigest()


def test_bare_and_date_prefixed_slugs_are_the_same_story(revision_client):
    client, fixtures = revision_client
    expected = hashlib.sha256(fixtures["beta"]).hexdigest()
    for slug in ("beta-story", "2026-07-02-beta-story"):
        resp = client.get(f"/api/stories/{slug}/revision?user=ramsay")
        assert resp.status_code == 200, slug
        body = resp.json()
        assert body["story_revision_sha256"] == expected
        assert body["story_date"] == "2026-07-02"
        # The canonical identity is the file actually on disk.
        assert body["story_slug"] == "2026-07-02-beta-story"
        assert body["story_filename"] == "2026-07-02-beta-story.json"


def test_same_date_duplicate_pair_is_rejected_and_logged(revision_client, caplog):
    client, _ = revision_client
    with caplog.at_level(logging.WARNING, logger="dashboard.routes.api"):
        for slug in ("dup-story", "2026-07-03-dup-story"):
            resp = client.get(f"/api/stories/{slug}/revision?user=ramsay")
            assert resp.status_code == 409, slug
            body = resp.json()
            assert body["error"] == "Ambiguous story slug"
            assert sorted(body["matches"]) == [
                "2026-07-03/2026-07-03-dup-story.json",
                "2026-07-03/dup-story.json",
            ]
    assert any("dup-story" in record.message for record in caplog.records)


def test_cross_date_duplicate_is_rejected(revision_client):
    client, _ = revision_client
    resp = client.get("/api/stories/cross-dup/revision?user=ramsay")
    assert resp.status_code == 409
    assert sorted(resp.json()["matches"]) == [
        "2026-07-01/cross-dup.json",
        "2026-07-02/cross-dup.json",
    ]


def test_public_story_route_rejects_duplicates_instead_of_first_match(revision_client):
    client, _ = revision_client
    assert client.get("/api/stories/dup-story?user=ramsay").status_code == 404
    assert client.get("/api/stories/cross-dup?user=ramsay").status_code == 404


def test_public_story_route_serves_unique_variants_and_legacy_files(revision_client):
    client, _ = revision_client
    assert client.get("/api/stories/alpha-story?user=ramsay").status_code == 200
    # Bare and date-prefixed forms resolve to the one date-prefixed file.
    for slug in ("beta-story", "2026-07-02-beta-story"):
        resp = client.get(f"/api/stories/{slug}?user=ramsay")
        assert resp.status_code == 200, slug
        assert resp.json()["title"] == "Beta story lands"
    # Legacy files directly under site-stories/ still serve publicly...
    assert client.get("/api/stories/legacy-story?user=ramsay").status_code == 200


def test_legacy_undated_file_has_no_revision_identity(revision_client):
    client, _ = revision_client
    # ...but they carry no date-scoped revision identity.
    assert client.get("/api/stories/legacy-story/revision?user=ramsay").status_code == 404


def test_unknown_draft_and_unsafe_slugs_have_no_revision(revision_client):
    client, _ = revision_client
    assert client.get("/api/stories/no-such-story/revision?user=ramsay").status_code == 404
    assert client.get("/api/stories/draft-story/revision?user=ramsay").status_code == 404
    assert client.get("/api/stories/%2E%2E%2Fsecret/revision?user=ramsay").status_code == 404
    assert (
        client.get("/api/stories/alpha-story/revision?user=../ramsay").status_code == 404
    )


def test_revision_route_is_public(revision_client):
    from dashboard.auth import is_public_route

    assert is_public_route("/api/stories/alpha-story/revision")

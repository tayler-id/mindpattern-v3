import json

import pytest

from orchestrator.site_content import (
    is_publishable_site_story,
    site_artifact_path,
    write_site_artifact,
)


def test_site_artifact_path_supports_all_content_machine_artifacts(tmp_path):
    root = tmp_path / "reports"

    cases = [
        (
            {"kind": "site_run", "date": "2026-07-01"},
            root / "ramsay" / "site-runs" / "2026-07-01.json",
        ),
        (
            {"kind": "site_corpus", "date": "2026-07-01"},
            root / "ramsay" / "site-corpus" / "2026-07-01.json",
        ),
        (
            {"kind": "site_candidate", "date": "2026-07-01", "slug": "OpenAI Agent Runtime"},
            root / "ramsay" / "site-candidates" / "2026-07-01" / "openai-agent-runtime.json",
        ),
        (
            {"kind": "site_graph_pack", "date": "2026-07-01", "slug": "OpenAI Agent Runtime"},
            root / "ramsay" / "site-graph-packs" / "2026-07-01" / "openai-agent-runtime.json",
        ),
        (
            {"kind": "site_story", "date": "2026-07-01", "slug": "OpenAI Agent Runtime"},
            root / "ramsay" / "site-stories" / "2026-07-01" / "openai-agent-runtime.json",
        ),
        (
            {"kind": "entity_dossier", "slug": "OpenAI"},
            root / "ramsay" / "site-dossiers" / "entities" / "openai.json",
        ),
        (
            {"kind": "source_dossier", "slug": "openai.com"},
            root / "ramsay" / "site-dossiers" / "sources" / "openai-com.json",
        ),
        (
            {"kind": "site_collection", "date": "2026-07-01", "slug": "Agent Runtime Reliability"},
            root / "ramsay" / "site-collections" / "2026-07-01" / "agent-runtime-reliability.json",
        ),
    ]

    for kwargs, expected in cases:
        assert site_artifact_path(user="ramsay", reports_root=root, **kwargs) == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "site_story", "date": "2026-07-01", "slug": "../secret"},
        {"kind": "site_story", "date": "../2026-07-01", "slug": "story"},
        {"kind": "site_story", "date": "2026-99-99", "slug": "story"},
        {"kind": "site_story", "date": "2026-07-01", "slug": ""},
        {"kind": "site_story", "date": "2026-07-01", "slug": "story", "user": "../ramsay"},
        {"kind": "unknown", "date": "2026-07-01", "slug": "story"},
        {"kind": "site_run", "slug": "story"},
        {"kind": "entity_dossier", "date": "2026-07-01"},
    ],
)
def test_site_artifact_path_rejects_unsafe_or_invalid_segments(tmp_path, kwargs):
    kwargs.setdefault("user", "ramsay")
    with pytest.raises(ValueError):
        site_artifact_path(reports_root=tmp_path / "reports", **kwargs)


def test_is_publishable_site_story_requires_high_confidence_evidence_and_redaction():
    story = {
        "kind": "site_story",
        "status": "published",
        "confidence": "high",
        "title": "OpenAI agent reliability becomes a control-plane story",
        "dek": "A public artifact with evidence.",
        "take": "Reliability is becoming buyer-visible infrastructure.",
        "why_now": "The signal changed today.",
        "source_refs": [{"url": "https://openai.com/news/agents", "domain": "openai.com"}],
        "claim_evidence": [{"claim": "OpenAI changed runtime reliability.", "source_url": "https://openai.com/news/agents"}],
        "graph_edges": [{"kind": "entity", "relationship": "same_entity", "id": "openai"}],
        "provenance": {"redaction_status": "passed"},
    }
    assert is_publishable_site_story(story) is True

    for key, value in [
        ("kind", "story"),
        ("status", "draft"),
        ("confidence", "medium"),
        ("why_now", ""),
        ("source_refs", []),
        ("claim_evidence", []),
        ("graph_edges", []),
    ]:
        candidate = dict(story)
        candidate[key] = value
        assert is_publishable_site_story(candidate) is False

    redaction_failed = dict(story)
    redaction_failed["provenance"] = {"redaction_status": "redacted"}
    assert is_publishable_site_story(redaction_failed) is False


def test_write_site_artifact_redacts_text_and_drops_private_fields(tmp_path):
    path = write_site_artifact(
        kind="site_run",
        user="ramsay",
        date="2026-07-01",
        reports_root=tmp_path / "reports",
        artifact={
            "kind": "site_run",
            "status": "completed",
            "summary": "Contact owner@example.test token=fake-token-value api_key=fake-api-key-value",
            "raw_slack_body": "private slack message",
            "subscriber_email": "reader@example.com",
            "nested": {
                "secret": "do-not-commit",
                "safe": "OpenAI source-backed story",
            },
        },
    )

    assert path == tmp_path / "reports" / "ramsay" / "site-runs" / "2026-07-01.json"
    data = json.loads(path.read_text())
    serialized = json.dumps(data)
    assert "owner@example.test" not in serialized
    assert "fake-token-value" not in serialized
    assert "fake-api-key-value" not in serialized
    assert "raw_slack_body" not in serialized
    assert "subscriber_email" not in serialized
    assert "do-not-commit" not in serialized
    assert data["summary"].count("[redacted]") >= 2
    assert data["nested"]["safe"] == "OpenAI source-backed story"

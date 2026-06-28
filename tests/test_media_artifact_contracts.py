import pytest

from orchestrator.media_contracts import (
    EvidenceReference,
    PublicArtifactMetadata,
    normalize_artifact_slug,
    redact_sensitive_text,
    safe_artifact_path,
    validate_run_date,
)


def test_evidence_reference_from_finding_exposes_only_public_fields():
    finding = {
        "id": 123,
        "run_date": "2026-06-28",
        "agent": "vibe-coding-researcher",
        "title": "Agent Reach source reliability improved",
        "summary": "Contact tayler@example.com or <@U123ABC> for raw notes.",
        "source_url": "https://example.com/story",
        "source_name": "Example",
        "raw_slack_body": "private message body must not leak",
        "subscriber_email": "subscriber@example.com",
    }

    ref = EvidenceReference.from_finding(finding)

    assert ref.to_public_dict() == {
        "finding_id": 123,
        "run_date": "2026-06-28",
        "agent": "vibe-coding-researcher",
        "title": "Agent Reach source reliability improved",
        "summary": "Contact [redacted] or [redacted] for raw notes.",
        "source_url": "https://example.com/story",
        "source_name": "Example",
    }


def test_redact_sensitive_text_handles_tokens_private_ids_and_contact_data():
    text = (
        "email tayler@example.com, call +1 212 555 0199, token xoxb-123-456, "
        "key sk-proj-secret, github ghp_abcdefghijklmnop, slack <@U123ABC>."
    )

    redacted = redact_sensitive_text(text)

    assert "tayler@example.com" not in redacted
    assert "212 555 0199" not in redacted
    assert "xoxb-" not in redacted
    assert "sk-proj" not in redacted
    assert "ghp_" not in redacted
    assert "<@U123ABC>" not in redacted
    assert redacted.count("[redacted]") >= 6


def test_validate_run_date_rejects_invalid_or_path_like_values():
    assert validate_run_date("2026-06-28") == "2026-06-28"

    for value in ["2026-6-28", "../2026-06-28", "2026-99-99", "2026-06-28.md"]:
        with pytest.raises(ValueError):
            validate_run_date(value)


def test_normalize_artifact_slug_returns_safe_stable_slug():
    assert normalize_artifact_slug("AI IDEs consolidate!") == "ai-ides-consolidate"
    assert normalize_artifact_slug("../../secrets/users.json") == "secrets-users-json"
    assert normalize_artifact_slug("   ") == "artifact"


def test_safe_artifact_path_stays_inside_root(tmp_path):
    root = tmp_path / "reports" / "ramsay" / "audio"

    path = safe_artifact_path(
        root=root,
        user="ramsay",
        date="2026-06-28",
        slug="Morning Briefing",
        suffix=".json",
    )

    assert path == root / "ramsay" / "2026-06-28" / "morning-briefing.json"

    for kwargs in [
        {"user": "../ramsay"},
        {"date": "../../2026-06-28"},
        {"slug": "../../users"},
        {"suffix": "../json"},
    ]:
        params = {
            "root": root,
            "user": "ramsay",
            "date": "2026-06-28",
            "slug": "safe",
            "suffix": ".json",
        }
        params.update(kwargs)
        with pytest.raises(ValueError):
            safe_artifact_path(**params)


def test_public_artifact_metadata_serializes_redacted_evidence():
    artifact = PublicArtifactMetadata(
        artifact_id="2026-06-28-audio",
        date="2026-06-28",
        artifact_type="audio_briefing",
        title="Morning Briefing for tayler@example.com",
        status="ready",
        evidence=[
            EvidenceReference.from_finding(
                {
                    "id": 9,
                    "run_date": "2026-06-28",
                    "agent": "agent",
                    "title": "Story",
                    "summary": "Token sk-proj-secret should redact.",
                    "source_url": "javascript:alert(1)",
                    "source_name": "Source",
                }
            )
        ],
        source_count=1,
        ai_generated=True,
    )

    public = artifact.to_public_dict()

    assert public["id"] == "2026-06-28-audio"
    assert public["title"] == "Morning Briefing for [redacted]"
    assert public["evidence"][0]["source_url"] == ""
    assert public["evidence"][0]["summary"] == "Token [redacted] should redact."
    assert public["ai_generated"] is True
    assert public["source_count"] == 1

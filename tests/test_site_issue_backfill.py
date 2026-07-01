import json

from orchestrator.site_content import (
    issue_artifact_path,
    is_publishable_site_story,
    run_site_issue_backfill,
    site_artifact_path,
)
from orchestrator.site_content_engine import run_historical_site_seed_generation


def test_site_issue_backfill_writes_idempotent_audit_and_structured_issues(tmp_path):
    reports_root = tmp_path / "reports"
    user_dir = reports_root / "ramsay"
    user_dir.mkdir(parents=True)

    (user_dir / "2026-06-17.md").write_text(
        "# Ramsay Research Agent — June 17, 2026\n\n"
        "Opening note.\n\n"
        "## Top 5 Stories Today\n\n"
        "**1. OpenAI ships agent controls.** OpenAI described new runtime "
        "controls in [OpenAI](https://openai.com/news/agents).\n\n"
        "**2. Anthropic updates Claude Code.** Anthropic updated workflows in "
        "[Anthropic](https://anthropic.com/news/code).\n"
    )
    (user_dir / "2026-06-17-dry-run.md").write_text(
        "# Dry-Run Report — 2026-06-17\n\nThis is a dry-run placeholder.\n"
    )
    (user_dir / "2026-06-18.md").write_text(
        "# Ramsay Research Agent — June 18, 2026\n\n"
        "## Notes\n\n"
        "This issue mentions tayler@example.com but has no source links.\n"
    )
    (user_dir / "2026-06-19.md").write_text("Prompt is too long")

    first = run_site_issue_backfill(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
        generated_at="2026-07-01T00:00:00+00:00",
    )

    assert first["kind"] == "site_issue_backfill"
    assert first["status"] == "completed"
    assert first["counts"]["reports_seen"] == 4
    assert first["counts"]["parsed"] == 2
    assert first["counts"]["skipped"] == 2
    assert first["counts"]["redacted"] == 1
    assert first["counts"]["degraded"] == 1
    assert first["counts"]["unresolved"] >= 2
    assert {item["date"] for item in first["parsed"]} == {"2026-06-17", "2026-06-18"}
    assert {item["reason"] for item in first["skipped"]} >= {
        "non_canonical_variant",
        "placeholder_or_too_small",
    }

    issue_path = issue_artifact_path(
        date="2026-06-17",
        user="ramsay",
        reports_root=reports_root,
    )
    redacted_issue_path = issue_artifact_path(
        date="2026-06-18",
        user="ramsay",
        reports_root=reports_root,
    )
    audit_path = site_artifact_path(
        kind="site_issue_backfill",
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
    )

    assert issue_path.exists()
    assert redacted_issue_path.exists()
    assert audit_path.exists()

    issue = json.loads(issue_path.read_text())
    assert issue["story_units"][0]["title"] == "1. OpenAI ships agent controls."
    assert issue["story_units"][0]["source_refs"][0]["domain"] == "openai.com"
    assert all(story["finding_ids"] == [] for story in issue["story_units"])
    assert issue["provenance"]["source_finding_ids"] == []

    redacted_issue = json.loads(redacted_issue_path.read_text())
    assert "tayler@example.com" not in json.dumps(redacted_issue)
    assert redacted_issue["provenance"]["redaction_status"] == "redacted"

    serialized_before = {
        "audit": audit_path.read_text(),
        "issue": issue_path.read_text(),
        "redacted_issue": redacted_issue_path.read_text(),
    }
    second = run_site_issue_backfill(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
        generated_at="2026-07-01T00:00:00+00:00",
    )
    serialized_after = {
        "audit": audit_path.read_text(),
        "issue": issue_path.read_text(),
        "redacted_issue": redacted_issue_path.read_text(),
    }

    assert second == first
    assert serialized_after == serialized_before


def test_historical_seed_generation_uses_backfill_audit_and_publishes_only_high_confidence_stories(tmp_path):
    reports_root = tmp_path / "reports"
    user_dir = reports_root / "ramsay"
    user_dir.mkdir(parents=True)

    (user_dir / "2026-06-17.md").write_text(
        "# Ramsay Research Agent — June 17, 2026\n\n"
        "## Top 5 Stories Today\n\n"
        "**1. OpenAI ships agent controls.** OpenAI described new runtime "
        "controls in [OpenAI](https://openai.com/news/agents).\n\n"
        "**2. Unsourced internal note.** This paragraph has no source link and "
        "should not become a public site story.\n"
    )
    run_site_issue_backfill(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
        generated_at="2026-07-01T00:00:00+00:00",
    )

    result = run_historical_site_seed_generation(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
        max_stories=3,
        generated_at="2026-07-01T00:00:00+00:00",
    )

    assert result["kind"] == "site_historical_seed"
    assert result["status"] == "completed"
    assert result["counts"]["issues_scanned"] == 1
    assert result["counts"]["candidates_considered"] == 2
    assert result["counts"]["published"] == 1
    assert result["counts"]["degraded"] == 1
    assert result["counts"]["skipped"] == 0
    assert {decision["action"] for decision in result["decisions"]} == {"published", "degraded"}

    published = next(decision for decision in result["decisions"] if decision["action"] == "published")
    degraded = next(decision for decision in result["decisions"] if decision["action"] == "degraded")
    assert published["story_artifact"].endswith(
        "/site-stories/2026-06-17/2026-06-17-1-openai-ships-agent-controls.json"
    )
    assert "missing_source_evidence" in degraded["reasons"]

    story_path = site_artifact_path(
        kind="site_story",
        date="2026-06-17",
        slug="2026-06-17-1-openai-ships-agent-controls",
        user="ramsay",
        reports_root=reports_root,
    )
    no_source_story_path = site_artifact_path(
        kind="site_story",
        date="2026-06-17",
        slug="2026-06-17-2-unsourced-internal-note",
        user="ramsay",
        reports_root=reports_root,
    )
    seed_path = site_artifact_path(
        kind="site_historical_seed",
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
    )

    assert story_path.exists()
    assert no_source_story_path.exists() is False
    assert seed_path.exists()

    story = json.loads(story_path.read_text())
    assert story["kind"] == "site_story"
    assert story["status"] == "published"
    assert story["confidence"] == "high"
    assert story["issue_date"] == "2026-06-17"
    assert story["source_refs"][0]["domain"] == "openai.com"
    assert story["primary_finding_ids"] == []
    assert story["provenance"]["source_finding_ids"] == []
    assert story["provenance"]["source_issue_dates"] == ["2026-06-17"]
    assert is_publishable_site_story(story)


def test_historical_seed_generation_fails_closed_without_backfill_audit(tmp_path):
    reports_root = tmp_path / "reports"
    result = run_historical_site_seed_generation(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
    )

    assert result["status"] == "degraded"
    assert result["counts"]["published"] == 0
    assert result["degraded_reasons"] == ["missing_backfill_audit"]

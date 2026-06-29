import json

import pytest

from orchestrator.site_content import (
    build_structured_issue,
    issue_artifact_path,
    normalize_slug,
)


SAMPLE_REPORT = """# MindPattern Daily Briefing

Opening note.

## Agent Platforms

### OpenAI ships agent tools

OpenAI released a new agent runtime. See [OpenAI](https://openai.com/news/agents).

Why it matters: builders can connect tools with less glue code.

### Anthropic updates Claude Code

Anthropic improved Claude Code workflows via [Anthropic](https://anthropic.com/news/code).

## Market Moves

### Cerebras expands AI infrastructure

Cerebras announced new infrastructure work via [TechCrunch](https://techcrunch.com/ai).
"""


def test_build_structured_issue_splits_sections_story_units_sources_and_entities():
    issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="MindPattern Daily Briefing",
        content=SAMPLE_REPORT,
    )

    assert issue["date"] == "2026-06-28"
    assert issue["slug"] == "2026-06-28"
    assert issue["provenance"]["generated_by"] == "mindpattern.site_content.issue_splitter"
    assert issue["provenance"]["redaction_status"] == "passed"
    assert [section["title"] for section in issue["sections"]] == [
        "Agent Platforms",
        "Market Moves",
    ]
    assert [story["title"] for story in issue["story_units"]] == [
        "OpenAI ships agent tools",
        "Anthropic updates Claude Code",
        "Cerebras expands AI infrastructure",
    ]
    assert issue["story_units"][0]["section_id"] == "agent-platforms"
    assert issue["story_units"][0]["source_refs"] == [
        {
            "url": "https://openai.com/news/agents",
            "domain": "openai.com",
            "title": "OpenAI",
        }
    ]
    entity_names = {entity["name"] for entity in issue["entities"]}
    assert {"OpenAI", "Anthropic", "Claude Code", "Cerebras"} <= entity_names


def test_build_structured_issue_creates_story_units_for_h2_only_sections():
    issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Top Stories\n\n"
            "**OpenAI ships agent tools.** The story cites [OpenAI](https://openai.com/news).\n\n"
            "## Security\n\n"
            "**Linux kernel patch lands.** The story cites [Ars](https://arstechnica.com/security).\n"
        ),
    )

    assert [story["title"] for story in issue["story_units"]] == ["Top Stories", "Security"]
    assert issue["sections"][0]["story_unit_ids"] == ["2026-06-28-top-stories"]
    assert issue["story_units"][0]["source_refs"][0]["domain"] == "openai.com"


def test_build_structured_issue_filters_sentence_noise_from_entities():
    issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Top Stories\n\n"
            "**OpenAI and Anthropic shipped agent updates.** And Because The New Work "
            "made OpenAI Codex and Claude Code more important.\n"
        ),
    )

    names = {entity["name"] for entity in issue["entities"]}
    assert {"OpenAI", "Anthropic", "OpenAI Codex", "Claude Code"} <= names
    assert {"And", "Because", "The", "New", "Work"} & names == set()
    assert "And Because The New Work" not in names


def test_structured_issue_redacts_private_data():
    issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="Private note",
        content="## Test\n\n### Contact\n\nEmail tayler@example.com and token sk-test123.",
    )

    dumped = json.dumps(issue)
    assert "tayler@example.com" not in dumped
    assert "sk-test123" not in dumped
    assert "[redacted]" in dumped
    assert issue["provenance"]["redaction_status"] == "redacted"


def test_issue_artifact_path_stays_under_reports_root(tmp_path):
    path = issue_artifact_path(
        date="2026-06-28",
        user="ramsay",
        reports_root=tmp_path / "reports",
    )
    assert path == tmp_path / "reports" / "ramsay" / "site-issues" / "2026-06-28.json"

    with pytest.raises(ValueError):
        issue_artifact_path(date="../2026-06-28", user="ramsay", reports_root=tmp_path)
    with pytest.raises(ValueError):
        issue_artifact_path(date="2026-06-28", user="../ramsay", reports_root=tmp_path)


def test_normalize_slug_rejects_empty_or_path_like_values():
    assert normalize_slug("OpenAI ships agent tools") == "openai-ships-agent-tools"
    with pytest.raises(ValueError):
        normalize_slug("../secret")
    with pytest.raises(ValueError):
        normalize_slug("!!!")

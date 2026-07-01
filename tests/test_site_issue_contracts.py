import json

import pytest

from orchestrator.site_content import (
    build_public_story,
    build_structured_issue,
    issue_artifact_path,
    normalize_slug,
    story_artifact_path,
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

    assert [story["title"] for story in issue["story_units"]] == [
        "OpenAI ships agent tools.",
        "Linux kernel patch lands.",
    ]
    assert issue["sections"][0]["story_unit_ids"] == ["2026-06-28-openai-ships-agent-tools"]
    assert issue["story_units"][0]["source_refs"][0]["domain"] == "openai.com"


def test_structured_issue_promotes_container_section_bold_leads_to_story_titles():
    issue = build_structured_issue(
        date="2026-06-17",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Top 5 Stories Today\n\n"
            "**1. Loop engineering gets a name.** Addy Osmani wrote about "
            "[loop engineering](https://addyo.substack.com/p/loop-engineering).\n"
        ),
    )

    story = issue["story_units"][0]
    assert story["title"] == "1. Loop engineering gets a name."
    assert story["slug"] == "1-loop-engineering-gets-a-name"
    assert story["id"] == "2026-06-17-1-loop-engineering-gets-a-name"
    assert story["summary"].startswith("Addy Osmani wrote")
    assert "Top 5 Stories Today" not in story["title"]


def test_structured_issue_splits_generic_sections_into_bold_lead_stories():
    issue = build_structured_issue(
        date="2026-06-17",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Security\n\n"
            "**cPanel Zero-Day Weaponized Within 24 Hours.** "
            "The first story cites [Wiz](https://wiz.io/blog/cpanel-zero-day).\n\n"
            "**Bleeding Llama: Your Ollama Server Is Leaking Memory.** "
            "The second story cites [Cyera](https://www.cyera.com/research/bleeding-llama).\n\n"
            "**GitHub RCE CVE-2026-3854.** "
            "The third story cites [Wiz Research](https://www.wiz.io/blog/github-rce-vulnerability-cve-2026-3854).\n"
        ),
    )

    titles = [story["title"] for story in issue["story_units"]]
    assert titles == [
        "cPanel Zero-Day Weaponized Within 24 Hours.",
        "Bleeding Llama: Your Ollama Server Is Leaking Memory.",
        "GitHub RCE CVE-2026-3854.",
    ]
    assert "Security" not in titles
    assert issue["story_units"][0]["summary"].startswith("The first story cites")
    assert issue["story_units"][1]["source_refs"][0]["domain"] == "cyera.com"


def test_structured_issue_topic_terms_exclude_source_and_url_noise():
    issue = build_structured_issue(
        date="2026-06-17",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Security\n\n"
            "**Agent runtime isolation improves.** "
            "The story cites [Primary Source](https://example.com/security/source). "
            "Source: https://example.com/another-link\n"
        ),
    )

    topics = set(issue["story_units"][0]["topic_terms"])
    assert {"agent", "runtime", "isolation", "improv"} & topics
    assert {"source", "sources", "primary", "example", "https", "url", "link"} & topics == set()


def test_structured_issue_allows_slashes_in_story_titles_without_path_slugs():
    issue = build_structured_issue(
        date="2026-06-17",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Security\n\n"
            "**cPanel/WHM zero-day lands.** "
            "The story cites [Wiz](https://wiz.io/blog/cpanel-zero-day).\n"
        ),
    )

    story = issue["story_units"][0]
    assert story["title"] == "cPanel/WHM zero-day lands."
    assert story["slug"] == "cpanel-whm-zero-day-lands"
    assert "/" not in story["id"]


def test_build_structured_issue_filters_sentence_noise_from_entities():
    issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="Briefing",
        content=(
            "# Briefing\n\n"
            "## Top Stories\n\n"
            "**OpenAI and Anthropic shipped agent updates.** And Because The New Work "
            "made OpenAI Codex and Claude Code more important. That is what they said "
            "it was worth.\n"
        ),
    )

    names = {entity["name"] for entity in issue["entities"]}
    assert {"OpenAI", "Anthropic", "OpenAI Codex", "Claude Code"} <= names
    assert {"And", "Because", "The", "New", "Work"} & names == set()
    assert {"That", "What", "They", "Worth"} & names == set()
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


def test_build_public_story_requires_sources_and_keeps_provenance():
    issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="Briefing",
        content=SAMPLE_REPORT,
    )

    story = build_public_story(issue=issue, story_unit=issue["story_units"][0])
    assert story is not None
    assert story["kind"] == "story"
    assert story["slug"] == "2026-06-28-openai-ships-agent-tools"
    assert story["target_url"] == "/s/2026-06-28-openai-ships-agent-tools"
    assert story["issue_url"] == "/briefings/2026-06-28"
    assert story["confidence"] == "source-backed"
    assert story["source_refs"][0]["domain"] == "openai.com"
    assert story["entity_refs"][0]["slug"]
    assert story["graph_connectors"]["source_domains"] == ["openai.com"]
    assert "openai" in story["graph_connectors"]["entity_ids"]
    assert {edge["kind"] for edge in story["graph_edges"]} >= {"issue", "source_url", "source_domain", "entity"}
    assert {edge["relationship"] for edge in story["graph_edges"]} >= {
        "part_of_issue",
        "cites_source_url",
        "cites_source_domain",
        "mentions_entity",
    }
    assert story["related_paths"] == []
    assert story["provenance"]["generated_by"] == "mindpattern.site_content.public_story"
    assert story["provenance"]["ai_generated"] is False
    assert story["json_ld_ready"] is True

    no_source_issue = build_structured_issue(
        date="2026-06-28",
        user="ramsay",
        title="Briefing",
        content="# Briefing\n\n## Notes\n\nThis has no cited source.\n",
    )
    assert build_public_story(
        issue=no_source_issue,
        story_unit=no_source_issue["story_units"][0],
    ) is None


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


def test_story_artifact_path_stays_under_reports_root(tmp_path):
    path = story_artifact_path(
        slug="2026-06-28-openai-ships-agent-tools",
        user="ramsay",
        reports_root=tmp_path / "reports",
    )
    assert (
        path
        == tmp_path
        / "reports"
        / "ramsay"
        / "site-stories"
        / "2026-06-28-openai-ships-agent-tools.json"
    )

    with pytest.raises(ValueError):
        story_artifact_path(slug="../secret", user="ramsay", reports_root=tmp_path)
    with pytest.raises(ValueError):
        story_artifact_path(slug="2026-06-28-story", user="../ramsay", reports_root=tmp_path)


def test_normalize_slug_rejects_empty_or_path_like_values():
    assert normalize_slug("OpenAI ships agent tools") == "openai-ships-agent-tools"
    with pytest.raises(ValueError):
        normalize_slug("../secret")
    with pytest.raises(ValueError):
        normalize_slug("!!!")

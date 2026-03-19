"""Tests for Jinja2 Obsidian mirror templates in memory/templates/.

Validates that each template renders correctly with sample data, produces
valid YAML frontmatter, and includes expected [[wiki-links]] for Obsidian
graph view.
"""

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "memory" / "templates"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def jinja_env():
    """Jinja2 Environment pointing at memory/templates/."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _has_frontmatter(text: str) -> bool:
    """Check that rendered text starts with YAML frontmatter delimiters."""
    return text.startswith("---\n") and "\n---\n" in text[4:]


def _wiki_links(text: str) -> list[str]:
    """Extract all [[wiki-links]] from rendered text."""
    return re.findall(r"\[\[([^\]]+)\]\]", text)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Daily template
# ══════════════════════════════════════════════════════════════════════════════


class TestDailyTemplate:
    @pytest.fixture
    def daily_data(self):
        return {
            "date": "2026-03-15",
            "tags": ["daily", "ai-research"],
            "agents": [
                {
                    "name": "news-researcher",
                    "findings": [
                        {
                            "title": "GPT-5 Released",
                            "importance": "high",
                            "topic_slug": "gpt-5",
                            "source_slug": "techcrunch-com",
                        },
                        {
                            "title": "New Agent Framework",
                            "importance": "medium",
                            "topic_slug": "agent-frameworks",
                            "source_slug": "github-com",
                        },
                    ],
                },
                {
                    "name": "vibe-coding-researcher",
                    "findings": [],
                },
            ],
            "findings": [
                {"title": "GPT-5 Released"},
                {"title": "New Agent Framework"},
            ],
            "posts": [
                {
                    "platform": "twitter",
                    "content": "Big news: GPT-5 just dropped with major improvements in reasoning and tool use.",
                    "gate_outcome": "approved",
                },
            ],
            "engagements": [
                {
                    "platform": "twitter",
                    "type": "reply",
                    "target_author": "@openai",
                },
            ],
            "evolution_actions": [
                {
                    "action": "spawn",
                    "agents": "gpt5-researcher",
                    "reason": "High user interest in GPT-5 topic",
                },
            ],
        }

    def test_renders_with_agents_and_findings(self, jinja_env, daily_data):
        """Daily template renders with full agent and findings data."""
        template = jinja_env.get_template("daily.md.j2")
        result = template.render(**daily_data)

        assert "news-researcher" in result
        assert "GPT-5 Released" in result
        assert "New Agent Framework" in result
        assert "vibe-coding-researcher" in result
        assert "No findings this run." in result

    def test_renders_with_empty_data(self, jinja_env):
        """Daily template renders gracefully with empty collections."""
        template = jinja_env.get_template("daily.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["daily"],
            agents=[],
            findings=[],
            posts=[],
            engagements=[],
            evolution_actions=[],
        )

        assert "2026-03-15" in result
        assert "No posts today." in result
        assert "No engagements today." in result
        assert "No evolution actions today." in result

    def test_has_frontmatter(self, jinja_env, daily_data):
        """Daily template output starts with valid YAML frontmatter."""
        template = jinja_env.get_template("daily.md.j2")
        result = template.render(**daily_data)

        assert _has_frontmatter(result)
        assert "type: daily" in result
        assert "date: 2026-03-15" in result
        assert "agents_run: 2" in result
        assert "findings_count: 2" in result

    def test_has_wiki_links(self, jinja_env, daily_data):
        """Daily template includes wiki-links to topics and sources."""
        template = jinja_env.get_template("daily.md.j2")
        result = template.render(**daily_data)

        links = _wiki_links(result)
        assert any("topics/gpt-5" in link for link in links)
        assert any("sources/techcrunch-com" in link for link in links)
        assert any("topics/agent-frameworks" in link for link in links)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Topic template
# ══════════════════════════════════════════════════════════════════════════════


class TestTopicTemplate:
    @pytest.fixture
    def topic_data(self):
        return {
            "date": "2026-03-15",
            "tags": ["topic", "ai"],
            "name": "Agent Frameworks",
            "description": "Frameworks for building autonomous AI agents.",
            "first_seen": "2026-02-01",
            "findings": [
                {
                    "title": "LangGraph 2.0 Released",
                    "importance": "high",
                    "run_date": "2026-03-14",
                    "summary": "Major update to LangGraph with new features.",
                },
                {
                    "title": "CrewAI Goes Open Source",
                    "importance": "medium",
                    "run_date": "2026-03-10",
                    "summary": "CrewAI framework now fully open source.",
                },
            ],
            "sources": [
                {"slug": "github-com", "count": 5},
                {"slug": "arxiv-org", "count": 2},
            ],
            "related_topics": [
                {"slug": "langchain"},
                {"slug": "autonomous-agents"},
            ],
            "posts": [
                {
                    "platform": "twitter",
                    "date": "2026-03-14",
                    "content": "LangGraph 2.0 is out! Major improvements to the agent framework.",
                },
            ],
        }

    def test_renders_with_findings_and_links(self, jinja_env, topic_data):
        """Topic template renders findings with daily links."""
        template = jinja_env.get_template("topic.md.j2")
        result = template.render(**topic_data)

        assert "Agent Frameworks" in result
        assert "LangGraph 2.0 Released" in result
        assert "CrewAI Goes Open Source" in result

        links = _wiki_links(result)
        assert any("daily/2026-03-14" in link for link in links)
        assert any("daily/2026-03-10" in link for link in links)

    def test_has_source_links(self, jinja_env, topic_data):
        """Topic template links to source pages."""
        template = jinja_env.get_template("topic.md.j2")
        result = template.render(**topic_data)

        links = _wiki_links(result)
        assert any("sources/github-com" in link for link in links)
        assert any("sources/arxiv-org" in link for link in links)

    def test_has_topic_cross_links(self, jinja_env, topic_data):
        """Topic template links to related topics."""
        template = jinja_env.get_template("topic.md.j2")
        result = template.render(**topic_data)

        links = _wiki_links(result)
        assert any("topics/langchain" in link for link in links)
        assert any("topics/autonomous-agents" in link for link in links)

    def test_has_frontmatter(self, jinja_env, topic_data):
        """Topic template output has valid frontmatter."""
        template = jinja_env.get_template("topic.md.j2")
        result = template.render(**topic_data)

        assert _has_frontmatter(result)
        assert "type: topic" in result
        assert "first_seen: 2026-02-01" in result

    def test_renders_with_empty_data(self, jinja_env):
        """Topic template renders gracefully with empty collections."""
        template = jinja_env.get_template("topic.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["topic"],
            name="Empty Topic",
            first_seen="2026-03-15",
            findings=[],
            sources=[],
            related_topics=[],
            posts=[],
        )

        assert "No findings yet." in result
        assert "No sources yet." in result
        assert "No related topics yet." in result


# ══════════════════════════════════════════════════════════════════════════════
# 3. Source template
# ══════════════════════════════════════════════════════════════════════════════


class TestSourceTemplate:
    @pytest.fixture
    def source_data(self):
        return {
            "date": "2026-03-15",
            "tags": ["source", "news"],
            "name": "TechCrunch",
            "url": "https://techcrunch.com",
            "eic_selection_rate": 0.75,
            "findings": [
                {
                    "title": "GPT-5 Released",
                    "importance": "high",
                    "run_date": "2026-03-15",
                    "summary": "OpenAI releases GPT-5.",
                },
            ],
            "topics": [
                {"slug": "gpt-5", "count": 3},
                {"slug": "ai-safety", "count": 1},
            ],
            "recent_findings": [
                {
                    "title": "GPT-5 Released",
                    "run_date": "2026-03-15",
                },
            ],
        }

    def test_renders_with_url_and_topics(self, jinja_env, source_data):
        """Source template renders URL and topic links."""
        template = jinja_env.get_template("source.md.j2")
        result = template.render(**source_data)

        assert "TechCrunch" in result
        assert "https://techcrunch.com" in result
        assert "GPT-5 Released" in result

    def test_url_quoted_in_frontmatter(self, jinja_env, source_data):
        """Source template quotes URL in frontmatter (contains colons)."""
        template = jinja_env.get_template("source.md.j2")
        result = template.render(**source_data)

        assert 'url: "https://techcrunch.com"' in result

    def test_has_topic_links(self, jinja_env, source_data):
        """Source template links to topic pages."""
        template = jinja_env.get_template("source.md.j2")
        result = template.render(**source_data)

        links = _wiki_links(result)
        assert any("topics/gpt-5" in link for link in links)
        assert any("topics/ai-safety" in link for link in links)

    def test_has_daily_links(self, jinja_env, source_data):
        """Source template links to daily logs via findings."""
        template = jinja_env.get_template("source.md.j2")
        result = template.render(**source_data)

        links = _wiki_links(result)
        assert any("daily/2026-03-15" in link for link in links)

    def test_has_frontmatter(self, jinja_env, source_data):
        """Source template output has valid frontmatter."""
        template = jinja_env.get_template("source.md.j2")
        result = template.render(**source_data)

        assert _has_frontmatter(result)
        assert "type: source" in result
        assert "eic_selection_rate: 0.75" in result

    def test_renders_with_empty_data(self, jinja_env):
        """Source template renders gracefully with empty collections."""
        template = jinja_env.get_template("source.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["source"],
            name="Empty Source",
            url="https://example.com",
            findings=[],
            topics=[],
            recent_findings=[],
        )

        assert "No findings from this source yet." in result
        assert "No topics yet." in result


# ══════════════════════════════════════════════════════════════════════════════
# 4. Posts template
# ══════════════════════════════════════════════════════════════════════════════


class TestPostsTemplate:
    def test_renders_with_posts(self, jinja_env):
        """Posts template renders post list with gate outcomes."""
        template = jinja_env.get_template("posts.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["social"],
            posts=[
                {
                    "date": "2026-03-15",
                    "platform": "twitter",
                    "content": "Test post content here.",
                    "gate1_outcome": "approved",
                    "gate2_outcome": "approved",
                    "posted": True,
                },
                {
                    "date": "2026-03-14",
                    "platform": "linkedin",
                    "content": "Earlier post.",
                    "gate1_outcome": "approved",
                    "gate2_outcome": "skip",
                    "posted": False,
                },
            ],
        )

        assert "twitter" in result
        assert "linkedin" in result
        assert "Test post content here." in result
        links = _wiki_links(result)
        assert any("daily/" in link for link in links)

    def test_has_frontmatter(self, jinja_env):
        """Posts template output has valid frontmatter."""
        template = jinja_env.get_template("posts.md.j2")
        result = template.render(date="2026-03-15", tags=["social"], posts=[])

        assert _has_frontmatter(result)
        assert "type: social" in result


# ══════════════════════════════════════════════════════════════════════════════
# 5. Corrections template
# ══════════════════════════════════════════════════════════════════════════════


class TestCorrectionsTemplate:
    def test_renders_with_corrections(self, jinja_env):
        """Corrections template renders before/after pairs."""
        template = jinja_env.get_template("corrections.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["social", "corrections"],
            corrections=[
                {
                    "date": "2026-03-15",
                    "platform": "twitter",
                    "reason": "Too promotional",
                    "original_text": "BUY NOW! Amazing AI tool!",
                    "approved_text": "Interesting new AI tool worth checking out.",
                },
            ],
        )

        assert "Too promotional" in result
        assert "BUY NOW!" in result
        assert "worth checking out" in result
        links = _wiki_links(result)
        assert any("daily/" in link for link in links)

    def test_has_frontmatter(self, jinja_env):
        """Corrections template output has valid frontmatter."""
        template = jinja_env.get_template("corrections.md.j2")
        result = template.render(
            date="2026-03-15", tags=["social"], corrections=[]
        )

        assert _has_frontmatter(result)
        assert "type: social" in result


# ══════════════════════════════════════════════════════════════════════════════
# 6. Engagement log template
# ══════════════════════════════════════════════════════════════════════════════


class TestEngagementLogTemplate:
    def test_renders_with_replies(self, jinja_env):
        """Engagement log template renders reply data."""
        template = jinja_env.get_template("engagement-log.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["social", "engagement"],
            replies=[
                {
                    "platform": "twitter",
                    "date": "2026-03-15",
                    "target_author": "@researcher",
                    "target_content": "Great thread on agent patterns.",
                    "our_reply": "Thanks for sharing! We covered this in our latest research.",
                    "status": "posted",
                },
            ],
            follows=[],
            outcomes=[],
        )

        assert "@researcher" in result
        assert "posted" in result
        links = _wiki_links(result)
        assert any("daily/" in link for link in links)

    def test_has_frontmatter(self, jinja_env):
        """Engagement log template output has valid frontmatter."""
        template = jinja_env.get_template("engagement-log.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["social"],
            replies=[],
            follows=[],
            outcomes=[],
        )

        assert _has_frontmatter(result)
        assert "type: social" in result


# ══════════════════════════════════════════════════════════════════════════════
# 7. Engaged authors template
# ══════════════════════════════════════════════════════════════════════════════


class TestEngagedAuthorsTemplate:
    def test_renders_with_authors(self, jinja_env):
        """Engaged authors template renders author groups by platform."""
        template = jinja_env.get_template("engaged-authors.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["people", "engagement"],
            platforms=[
                {
                    "name": "twitter",
                    "authors": [
                        {
                            "name": "Dr. Smith",
                            "id": "@drsmith",
                            "interaction_count": 3,
                            "first_seen": "2026-02-01",
                            "last_seen": "2026-03-15",
                            "interactions": [
                                {
                                    "date": "2026-03-15",
                                    "type": "reply",
                                    "content": "Great paper on multi-agent systems!",
                                },
                            ],
                        },
                    ],
                },
            ],
        )

        assert "Dr. Smith" in result
        assert "@drsmith" in result
        assert "twitter" in result
        links = _wiki_links(result)
        assert any("daily/" in link for link in links)

    def test_has_frontmatter(self, jinja_env):
        """Engaged authors template output has valid frontmatter."""
        template = jinja_env.get_template("engaged-authors.md.j2")
        result = template.render(
            date="2026-03-15", tags=["people"], platforms=[]
        )

        assert _has_frontmatter(result)
        assert "type: people" in result


# ══════════════════════════════════════════════════════════════════════════════
# 8. Index template
# ══════════════════════════════════════════════════════════════════════════════


class TestIndexTemplate:
    def test_renders_with_files(self, jinja_env):
        """Index template renders file list with wiki-links."""
        template = jinja_env.get_template("index.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["index"],
            title="Topics",
            folder="topics",
            description="All research topics tracked by MindPattern.",
            files=[
                {"slug": "agent-frameworks", "name": "Agent Frameworks"},
                {"slug": "vibe-coding", "name": "Vibe Coding"},
            ],
        )

        assert "Topics" in result
        assert "Agent Frameworks" in result
        links = _wiki_links(result)
        assert any("topics/agent-frameworks" in link for link in links)
        assert any("topics/vibe-coding" in link for link in links)

    def test_has_frontmatter(self, jinja_env):
        """Index template output has valid frontmatter."""
        template = jinja_env.get_template("index.md.j2")
        result = template.render(
            date="2026-03-15",
            tags=["index"],
            title="Empty Index",
            folder="topics",
            files=[],
        )

        assert _has_frontmatter(result)
        assert "type: index" in result

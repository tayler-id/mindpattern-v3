"""Tests for LinkedIn engagement discovery via Jina Reader search.

Covers:
- search_via_jina() returns normalized results on success
- search_via_jina() returns empty list on failure/timeout
- LinkedIn draft-only mode saves to JSON file instead of posting
- LinkedIn wired into _find_candidates() when in engagement platforms
"""

import json
import subprocess
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from social.engagement import EngagementPipeline, search_via_jina


# ── Fixtures ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

JINA_MARKDOWN_RESPONSE = """# Search Results

## [1] AI Agents Are Changing How We Build Software
**URL:** https://www.linkedin.com/posts/johndoe_ai-agents-changing-software-activity-123456
John Doe - Senior Engineer at Acme Corp

AI agents are fundamentally changing how developers build and ship software. Here's what I've learned deploying them in production over the last 6 months...

---

## [2] The Future of Developer Tools
**URL:** https://www.linkedin.com/posts/janesmith_future-developer-tools-activity-789012
Jane Smith - CTO at DevToolsCo

The next generation of developer tools will be agent-native. What does that mean practically? Let me break it down...

---

## [3] Why MCP Matters for AI Integration
**URL:** https://www.linkedin.com/posts/bobbuilder_mcp-ai-integration-activity-345678
Bob Builder - Founder at BuildAI

Model Context Protocol is one of the most underrated developments in AI tooling this year. Here's why...
"""

JINA_EMPTY_RESPONSE = """# Search Results

No results found for this query.
"""


@pytest.fixture
def mock_config():
    """Minimal social-config.json for testing."""
    return {
        "gate_timeout_seconds": 10,
        "platforms": {
            "bluesky": {
                "enabled": True,
                "handle": "test.bsky.social",
                "api_base": "https://bsky.social/xrpc",
                "keychain": {"app_password": "test-password"},
                "max_chars": 300,
            },
            "linkedin": {
                "enabled": True,
                "keychain": {"access_token": "test-token"},
                "api_base": "https://api.linkedin.com",
                "target_chars": 1350,
            },
        },
        "engagement": {
            "platforms": ["bluesky", "linkedin"],
            "max_replies_per_day": 30,
            "search_queries_per_platform": 8,
            "candidates_per_platform": 20,
            "min_follower_count": 10,
            "min_likes": 0,
            "max_likes": 5000,
        },
    }


@pytest.fixture
def mock_db():
    """In-memory SQLite database with minimal schema."""
    db = sqlite3.connect(":memory:")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS engagements (
            id INTEGER PRIMARY KEY,
            user_id TEXT,
            platform TEXT,
            engagement_type TEXT,
            target_post_url TEXT,
            target_author TEXT,
            target_author_id TEXT,
            target_content TEXT,
            our_reply TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.commit()
    return db


@pytest.fixture
def drafts_dir(tmp_path):
    """Create a temporary drafts directory."""
    d = tmp_path / "social-drafts"
    d.mkdir()
    return d


# ── search_via_jina tests ─────────────────────────────────────────────────


class TestSearchViaJina:
    """Tests for the search_via_jina() standalone function."""

    @patch("subprocess.run")
    def test_returns_normalized_results_on_success(self, mock_run):
        """search_via_jina returns list of dicts with normalized fields."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=JINA_MARKDOWN_RESPONSE,
            stderr="",
        )

        results = search_via_jina("AI agents developer tools")

        assert len(results) >= 1
        for r in results:
            assert "url" in r
            assert "text" in r
            assert "author_handle" in r
            assert "author_name" in r
            assert r["platform"] == "linkedin"
            assert "linkedin.com" in r["url"]
            # Numeric fields present (may be 0 for search-discovered posts)
            assert "followers_count" in r
            assert "like_count" in r
            assert "reply_count" in r

    @patch("subprocess.run")
    def test_extracts_urls_correctly(self, mock_run):
        """Extracted URLs are LinkedIn post URLs."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=JINA_MARKDOWN_RESPONSE,
            stderr="",
        )

        results = search_via_jina("AI agents")

        urls = [r["url"] for r in results]
        for url in urls:
            assert "linkedin.com/posts/" in url

    @patch("subprocess.run")
    def test_extracts_content(self, mock_run):
        """Extracted text content is non-empty."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=JINA_MARKDOWN_RESPONSE,
            stderr="",
        )

        results = search_via_jina("AI agents")

        for r in results:
            assert len(r["text"]) > 0

    @patch("subprocess.run")
    def test_returns_empty_on_subprocess_failure(self, mock_run):
        """Returns empty list when curl subprocess fails."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=1,
            stdout="",
            stderr="Connection refused",
        )

        results = search_via_jina("AI agents")
        assert results == []

    @patch("subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        """Returns empty list when subprocess times out."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="curl", timeout=30)

        results = search_via_jina("AI agents")
        assert results == []

    @patch("subprocess.run")
    def test_returns_empty_on_no_results(self, mock_run):
        """Returns empty list when Jina returns no matching results."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=JINA_EMPTY_RESPONSE,
            stderr="",
        )

        results = search_via_jina("obscure nonexistent query xyzzy")
        assert results == []

    @patch("subprocess.run")
    def test_max_results_parameter(self, mock_run):
        """Respects max_results parameter."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=JINA_MARKDOWN_RESPONSE,
            stderr="",
        )

        results = search_via_jina("AI agents", max_results=1)
        assert len(results) <= 1

    @patch("subprocess.run")
    def test_calls_jina_search_endpoint(self, mock_run):
        """Verifies the correct Jina search URL is called."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout=JINA_MARKDOWN_RESPONSE,
            stderr="",
        )

        search_via_jina("AI agents")

        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert "curl" in cmd_args[0]
        # Should contain s.jina.ai and site:linkedin.com
        url_arg = cmd_args[-1] if isinstance(cmd_args, list) else str(cmd_args)
        assert "s.jina.ai" in str(cmd_args)


# ── LinkedIn draft-only mode tests ────────────────────────────────────────


class TestLinkedInDraftOnly:
    """Tests for LinkedIn engagement draft-only mode (no auto-posting)."""

    @patch("social.engagement.memory")
    @patch("social.posting.keychain_get", return_value="fake-secret")
    def test_linkedin_saves_draft_to_json(
        self, mock_keychain, mock_memory, mock_config, mock_db, tmp_path
    ):
        """LinkedIn engagement saves draft to JSON file instead of posting."""
        pipeline = EngagementPipeline("test-user", mock_config, mock_db)

        # Override the drafts directory to use tmp_path
        drafts_dir = tmp_path / "social-drafts"
        drafts_dir.mkdir(exist_ok=True)
        pipeline._linkedin_drafts_dir = drafts_dir

        candidate = {
            "platform": "linkedin",
            "post_id": "urn:li:activity:123456",
            "post_cid": "",
            "author": "johndoe",
            "author_id": "john-doe-id",
            "content": "AI agents are changing everything",
            "target_post_url": "https://linkedin.com/posts/johndoe_ai-agents-activity-123456",
            "target_author": "John Doe",
            "target_author_id": "john-doe-id",
            "target_content": "AI agents are changing everything",
            "our_reply": "Great insight on agent deployment. We found similar patterns...",
            "should_follow": False,
            "relevance": 0.8,
        }

        result = pipeline._post_engagement(candidate)

        # Should NOT actually post (no client.reply call)
        assert result["reply_posted"] is False

        # Should save draft
        assert result.get("draft_saved") is True

        # Verify JSON file was created
        draft_files = list(drafts_dir.glob("engagement-linkedin*.json"))
        assert len(draft_files) >= 1

        # Verify draft content
        with open(draft_files[0]) as f:
            draft = json.load(f)
        assert draft["platform"] == "linkedin"
        assert draft["our_reply"] == candidate["our_reply"]
        assert draft["target_post_url"] == candidate["target_post_url"]

    @patch("social.engagement.memory")
    @patch("social.posting.keychain_get", return_value="fake-secret")
    def test_linkedin_logs_as_drafted_not_posted(
        self, mock_keychain, mock_memory, mock_config, mock_db, tmp_path
    ):
        """LinkedIn engagement logs with status='drafted' not 'posted'."""
        pipeline = EngagementPipeline("test-user", mock_config, mock_db)

        drafts_dir = tmp_path / "social-drafts"
        drafts_dir.mkdir(exist_ok=True)
        pipeline._linkedin_drafts_dir = drafts_dir

        candidate = {
            "platform": "linkedin",
            "post_id": "urn:li:activity:123456",
            "post_cid": "",
            "author": "johndoe",
            "author_id": "john-doe-id",
            "content": "AI agents are changing everything",
            "target_post_url": "https://linkedin.com/posts/johndoe_ai-agents-activity-123456",
            "target_author": "John Doe",
            "target_author_id": "john-doe-id",
            "target_content": "AI agents are changing everything",
            "our_reply": "Great insight on agent deployment.",
            "should_follow": False,
        }

        pipeline._post_engagement(candidate)

        # Verify memory.store_engagement was called with status="drafted"
        mock_memory.store_engagement.assert_called_once()
        call_kwargs = mock_memory.store_engagement.call_args
        assert call_kwargs.kwargs.get("status") == "drafted" or (
            len(call_kwargs.args) > 0 and "drafted" in str(call_kwargs)
        )

    @patch("social.engagement.memory")
    @patch("social.posting.keychain_get", return_value="fake-secret")
    def test_linkedin_sends_slack_notification(
        self, mock_keychain, mock_memory, mock_config, mock_db, tmp_path
    ):
        """LinkedIn draft sends Slack notification for manual posting."""
        pipeline = EngagementPipeline("test-user", mock_config, mock_db)

        drafts_dir = tmp_path / "social-drafts"
        drafts_dir.mkdir(exist_ok=True)
        pipeline._linkedin_drafts_dir = drafts_dir

        # Mock the approval gateway's Slack methods
        pipeline.approval._get_slack_token = MagicMock(return_value="xoxb-fake")
        pipeline.approval._slack_post = MagicMock(return_value={"ok": True})

        candidate = {
            "platform": "linkedin",
            "post_id": "urn:li:activity:123456",
            "post_cid": "",
            "author": "johndoe",
            "author_id": "john-doe-id",
            "content": "AI agents are changing everything",
            "target_post_url": "https://linkedin.com/posts/johndoe_ai-agents-activity-123456",
            "target_author": "John Doe",
            "target_author_id": "john-doe-id",
            "target_content": "AI agents are changing everything",
            "our_reply": "Great insight on agent deployment.",
            "should_follow": False,
        }

        pipeline._post_engagement(candidate)

        # Should have sent a Slack notification
        pipeline.approval._slack_post.assert_called_once()
        sent_message = pipeline.approval._slack_post.call_args[0][1]
        assert "linkedin" in sent_message.lower()
        assert "draft" in sent_message.lower()

    @patch("social.engagement.memory")
    @patch("social.posting.keychain_get", return_value="fake-secret")
    def test_bluesky_still_posts_normally(
        self, mock_keychain, mock_memory, mock_config, mock_db
    ):
        """Bluesky engagement still posts via client.reply() as before."""
        pipeline = EngagementPipeline("test-user", mock_config, mock_db)

        # Mock the Bluesky client
        mock_bsky_client = MagicMock()
        mock_bsky_client.reply.return_value = {"success": True, "uri": "at://...", "cid": "abc"}
        pipeline._platform_clients["bluesky"] = mock_bsky_client

        candidate = {
            "platform": "bluesky",
            "post_id": "at://did:plc:xyz/app.bsky.feed.post/abc",
            "post_cid": "bafyrei...",
            "author": "test.bsky.social",
            "author_id": "did:plc:xyz",
            "content": "Interesting take on AI agents",
            "target_post_url": "https://bsky.app/profile/test.bsky.social/post/abc",
            "target_author": "Test User",
            "target_author_id": "did:plc:xyz",
            "target_content": "Interesting take on AI agents",
            "our_reply": "Here's what we've seen in production...",
            "should_follow": False,
        }

        result = pipeline._post_engagement(candidate)

        # Bluesky should still call client.reply()
        mock_bsky_client.reply.assert_called_once()
        assert result["reply_posted"] is True


# ── LinkedIn wired into _find_candidates tests ────────────────────────────


class TestLinkedInInFindCandidates:
    """Tests that LinkedIn search is wired into _find_candidates()."""

    @patch("social.engagement.search_via_jina")
    @patch("social.engagement.memory")
    @patch("social.posting.keychain_get", return_value="fake-secret")
    def test_find_candidates_calls_jina_for_linkedin(
        self, mock_keychain, mock_memory, mock_search, mock_config, mock_db
    ):
        """_find_candidates uses search_via_jina for LinkedIn platform."""
        mock_memory.get_context.return_value = {}
        mock_memory.search_findings.return_value = [
            {"title": "AI agents in production"},
            {"title": "Developer tools evolution"},
        ]

        mock_search.return_value = [
            {
                "url": "https://linkedin.com/posts/johndoe_ai-activity-123",
                "text": "AI agents are great for building tools" * 3,
                "author_handle": "johndoe",
                "author_name": "John Doe",
                "followers_count": 500,
                "like_count": 10,
                "reply_count": 3,
                "platform": "linkedin",
            }
        ]

        pipeline = EngagementPipeline("test-user", mock_config, mock_db)

        # Mock bluesky client search to return empty (focus on LinkedIn)
        mock_bsky = MagicMock()
        mock_bsky.search.return_value = []
        pipeline._platform_clients["bluesky"] = mock_bsky

        # Mock _generate_search_queries and _rank_candidates to simplify
        pipeline._generate_search_queries = MagicMock(
            return_value=["AI agents", "developer tools"]
        )
        pipeline._rank_candidates = MagicMock(
            side_effect=lambda posts, topics, platform: [
                pipeline._post_to_candidate(p, platform) for p in posts
            ]
        )

        candidates = pipeline._find_candidates("2026-03-15")

        # search_via_jina should have been called for LinkedIn
        mock_search.assert_called()

        # Should have LinkedIn candidates in results
        linkedin_candidates = [
            c for c in candidates if c["platform"] == "linkedin"
        ]
        assert len(linkedin_candidates) >= 1

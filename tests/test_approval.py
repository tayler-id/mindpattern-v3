"""Tests for social/approval.py — Slack-only approval system.

All network calls (Slack API) are mocked.
No real HTTP requests or subprocess calls are made.
"""

import json
import subprocess
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from social.approval import ApprovalGateway

# ────────────────────────────────────────────────────────────────────────
# FIXTURES
# ────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def gateway():
    """ApprovalGateway with a minimal config."""
    return ApprovalGateway({
        "gate_timeout_seconds": 5,  # short for tests
    })


@pytest.fixture()
def sample_topics():
    """Sample topic dicts for topic approval tests."""
    return [
        {
            "title": "GPT-5 Released",
            "anchor": "GPT-5 Released",
            "summary": "OpenAI releases GPT-5 with major improvements.",
            "score": 8.5,
            "angle": "Impact on developer productivity",
            "editorial_scores": {"composite": 8.5},
            "source_urls": ["https://openai.com/blog/gpt5"],
            "reasoning": "Major industry shift",
        },
        {
            "title": "Claude 4 Launch",
            "anchor": "Claude 4 Launch",
            "summary": "Anthropic announces Claude 4 with extended context.",
            "score": 7.2,
            "editorial_scores": {"composite": 7.2},
            "source_urls": ["https://anthropic.com/claude-4"],
        },
        {
            "title": "Open Source LLM Breakthrough",
            "anchor": "Open Source LLM Breakthrough",
            "summary": "Llama 4 matches GPT-5 on benchmarks.",
            "score": 6.8,
            "editorial_scores": {"composite": 6.8},
        },
    ]


@pytest.fixture()
def sample_drafts():
    """Sample drafts dict for draft approval tests."""
    return {
        "bluesky": "Check out GPT-5's new capabilities. https://openai.com/blog/gpt5",
        "linkedin": "The release of GPT-5 marks a significant shift in AI development.",
    }


@pytest.fixture()
def sample_candidates():
    """Sample engagement candidates for engagement approval tests."""
    return [
        {
            "platform": "bluesky",
            "author": "alice",
            "content": "Great thread on transformer architectures.",
            "our_reply": "Interesting point about attention mechanisms.",
        },
        {
            "platform": "linkedin",
            "author": "bob",
            "content": "AI tooling is evolving fast.",
            "our_reply": "Agreed, the toolchain improvements are impressive.",
        },
        {
            "platform": "bluesky",
            "author": "carol",
            "content": "Open source models are catching up.",
            "our_reply": "The benchmarks support that trend.",
        },
    ]


# ════════════════════════════════════════════════════════════════════════
# Reply Parsers — _parse_topic_reply()
# ════════════════════════════════════════════════════════════════════════


class TestParseTopicReply:
    """Tests for ApprovalGateway._parse_topic_reply()."""

    def test_go_keywords(self, gateway):
        """'go', 'yes', 'approve', 'ok', 'approved' all map to action=go."""
        for word in ("go", "yes", "approve", "ok", "approved", "GO", "Yes"):
            result = gateway._parse_topic_reply(word, 3)
            assert result["action"] == "go", f"Failed for '{word}'"
            assert result["topic_index"] == 0
            assert result["guidance"] == ""

    def test_skip_keywords(self, gateway):
        """'skip', 'kill', 'no', 'pass' all map to action=skip."""
        for word in ("skip", "kill", "no", "pass", "SKIP", "No"):
            result = gateway._parse_topic_reply(word, 3)
            assert result["action"] == "skip", f"Failed for '{word}'"
            assert result["topic_index"] == 0

    def test_retry_keywords(self, gateway):
        """'retry', 'again', 'redo' all map to action=retry."""
        for word in ("retry", "again", "redo", "RETRY"):
            result = gateway._parse_topic_reply(word, 3)
            assert result["action"] == "retry", f"Failed for '{word}'"

    def test_number_selects_topic(self, gateway):
        """Numeric reply selects the corresponding topic (1-based)."""
        result = gateway._parse_topic_reply("1", 3)
        assert result["action"] == "go"
        assert result["topic_index"] == 0  # 1-based -> 0-based

        result = gateway._parse_topic_reply("2", 3)
        assert result["action"] == "go"
        assert result["topic_index"] == 1

        result = gateway._parse_topic_reply("3", 3)
        assert result["action"] == "go"
        assert result["topic_index"] == 2

    def test_number_with_guidance(self, gateway):
        """Number followed by text captures guidance."""
        result = gateway._parse_topic_reply("2 focus on the developer angle", 3)
        assert result["action"] == "go"
        assert result["topic_index"] == 1
        assert "focus on the developer angle" in result["guidance"]

    def test_out_of_range_number_becomes_custom(self, gateway):
        """Number outside 1..num_topics is treated as custom topic."""
        result = gateway._parse_topic_reply("5", 3)
        assert result["action"] == "custom"
        assert result["guidance"] == "5"

    def test_zero_becomes_custom(self, gateway):
        """'0' is out of range and treated as custom."""
        result = gateway._parse_topic_reply("0", 3)
        assert result["action"] == "custom"

    def test_none_returns_skip_with_timeout(self, gateway):
        """None reply (timed out) returns skip with 'Timed out' guidance."""
        result = gateway._parse_topic_reply(None, 3)
        assert result["action"] == "skip"
        assert result["topic_index"] == 0
        assert "Timed out" in result["guidance"]

    def test_empty_string_returns_skip(self, gateway):
        """Empty string returns skip with timeout."""
        result = gateway._parse_topic_reply("", 3)
        assert result["action"] == "skip"
        assert "Timed out" in result["guidance"]

    def test_custom_topic_text(self, gateway):
        """Free-text reply becomes a custom topic."""
        result = gateway._parse_topic_reply("Write about Rust in production", 3)
        assert result["action"] == "custom"
        assert result["guidance"] == "Write about Rust in production"

    def test_custom_topic_preserves_case(self, gateway):
        """Custom topic preserves original casing."""
        result = gateway._parse_topic_reply("LLM Fine-Tuning Best Practices", 3)
        assert result["action"] == "custom"
        assert result["guidance"] == "LLM Fine-Tuning Best Practices"

    def test_whitespace_stripped(self, gateway):
        """Leading/trailing whitespace is stripped."""
        result = gateway._parse_topic_reply("  go  ", 3)
        assert result["action"] == "go"


# ════════════════════════════════════════════════════════════════════════
# Reply Parsers — _parse_draft_reply()
# ════════════════════════════════════════════════════════════════════════


class TestParseDraftReply:
    """Tests for ApprovalGateway._parse_draft_reply()."""

    def test_all_keywords(self, gateway):
        """'all', 'go', 'yes', 'approve', 'send', 'post' all approve all platforms."""
        platforms = ["bluesky", "linkedin"]
        for word in ("all", "go", "yes", "approve", "send", "post", "ALL"):
            result = gateway._parse_draft_reply(word, platforms)
            assert result["action"] == "all", f"Failed for '{word}'"
            assert result["platforms"] == platforms
            assert result["edits"] == {}

    def test_skip_keywords(self, gateway):
        """'skip', 'kill', 'no', 'pass', 'cancel' all skip."""
        platforms = ["bluesky", "linkedin"]
        for word in ("skip", "kill", "no", "pass", "cancel", "SKIP"):
            result = gateway._parse_draft_reply(word, platforms)
            assert result["action"] == "skip", f"Failed for '{word}'"
            assert result["platforms"] == []

    def test_single_platform_selection(self, gateway):
        """Naming a single platform approves only that one."""
        platforms = ["bluesky", "linkedin"]
        result = gateway._parse_draft_reply("bluesky", platforms)
        assert result["action"] == "approve_selected"
        assert result["platforms"] == ["bluesky"]

    def test_multiple_platform_selection(self, gateway):
        """Naming multiple platforms approves all named."""
        platforms = ["bluesky", "linkedin"]
        result = gateway._parse_draft_reply("bluesky linkedin", platforms)
        assert result["action"] == "approve_selected"
        assert set(result["platforms"]) == {"bluesky", "linkedin"}

    def test_none_returns_skip(self, gateway):
        """None reply (timed out) returns skip."""
        result = gateway._parse_draft_reply(None, ["bluesky"])
        assert result["action"] == "skip"
        assert result["platforms"] == []

    def test_ambiguous_reply_biases_toward_action(self, gateway):
        """Ambiguous reply (not starting with n/s/k/c) defaults to all."""
        platforms = ["bluesky", "linkedin"]
        result = gateway._parse_draft_reply("looks good", platforms)
        assert result["action"] == "all"
        assert result["platforms"] == platforms

    def test_reply_starting_with_n_skips(self, gateway):
        """Reply starting with 'n' is treated as skip."""
        platforms = ["bluesky", "linkedin"]
        result = gateway._parse_draft_reply("nah", platforms)
        assert result["action"] == "skip"

    def test_empty_string_returns_skip(self, gateway):
        """Empty string returns skip."""
        result = gateway._parse_draft_reply("", ["bluesky"])
        assert result["action"] == "skip"


# ════════════════════════════════════════════════════════════════════════
# Reply Parsers — _parse_engagement_reply()
# ════════════════════════════════════════════════════════════════════════


class TestParseEngagementReply:
    """Tests for ApprovalGateway._parse_engagement_reply()."""

    def test_all_keywords(self, gateway):
        """'all', 'yes', 'go', 'approve' approve all candidates."""
        for word in ("all", "yes", "go", "approve"):
            result = gateway._parse_engagement_reply(word, 3)
            assert result["approved_indices"] == [0, 1, 2], f"Failed for '{word}'"
            assert "All approved" in result["reason"]

    def test_none_keywords(self, gateway):
        """'skip', 'no', 'cancel', 'none' reject all candidates."""
        for word in ("skip", "no", "cancel", "none"):
            result = gateway._parse_engagement_reply(word, 3)
            assert result["approved_indices"] == [], f"Failed for '{word}'"
            assert "Rejected" in result["reason"]

    def test_number_selection(self, gateway):
        """Number-based selection approves specific candidates."""
        result = gateway._parse_engagement_reply("1 3", 3)
        assert result["approved_indices"] == [0, 2]  # 1-based -> 0-based

    def test_comma_separated_numbers(self, gateway):
        """Comma-separated numbers are parsed by splitting on whitespace."""
        # Note: the parser splits on whitespace, so "1,2,3" is one token
        result = gateway._parse_engagement_reply("1 2 3", 3)
        assert result["approved_indices"] == [0, 1, 2]

    def test_out_of_range_numbers_ignored(self, gateway):
        """Numbers outside 1..num_candidates are ignored."""
        result = gateway._parse_engagement_reply("1 5 2", 3)
        assert result["approved_indices"] == [0, 1]

    def test_duplicate_numbers_deduped(self, gateway):
        """Duplicate numbers are deduplicated."""
        result = gateway._parse_engagement_reply("1 1 2 2", 3)
        assert result["approved_indices"] == [0, 1]

    def test_none_reply_returns_timeout(self, gateway):
        """None reply (timed out) returns empty with 'Timed out' reason."""
        result = gateway._parse_engagement_reply(None, 3)
        assert result["approved_indices"] == []
        assert "Timed out" in result["reason"]

    def test_unparseable_text(self, gateway):
        """Unparseable text returns empty with explanation."""
        result = gateway._parse_engagement_reply("what do you mean", 3)
        assert result["approved_indices"] == []
        assert "Could not parse" in result["reason"]

    def test_mixed_numbers_and_text(self, gateway):
        """Numbers are extracted even when mixed with text."""
        result = gateway._parse_engagement_reply("approve 1 and 3 please", 3)
        assert result["approved_indices"] == [0, 2]


# ════════════════════════════════════════════════════════════════════════
# Format Functions
# ════════════════════════════════════════════════════════════════════════


class TestFormatTopicMessage:
    """Tests for ApprovalGateway._format_topic_message()."""

    def test_header_present(self, gateway, sample_topics):
        """Message starts with the 'Topic Approval' header."""
        msg = gateway._format_topic_message(sample_topics)
        assert "MindPattern Social - Topic Approval" in msg

    def test_topics_numbered(self, gateway, sample_topics):
        """Each topic is numbered 1, 2, 3."""
        msg = gateway._format_topic_message(sample_topics)
        assert "1. GPT-5 Released" in msg
        assert "2. Claude 4 Launch" in msg
        assert "3. Open Source LLM Breakthrough" in msg

    def test_includes_score(self, gateway, sample_topics):
        """Score values appear in the message."""
        msg = gateway._format_topic_message(sample_topics)
        assert "8.5" in msg
        assert "7.2" in msg

    def test_includes_angle(self, gateway, sample_topics):
        """Angle text appears when present."""
        msg = gateway._format_topic_message(sample_topics)
        assert "Impact on developer productivity" in msg

    def test_includes_source_urls(self, gateway, sample_topics):
        """Source URLs appear when present."""
        msg = gateway._format_topic_message(sample_topics)
        assert "https://openai.com/blog/gpt5" in msg

    def test_includes_reply_instructions(self, gateway, sample_topics):
        """Message ends with reply instructions."""
        msg = gateway._format_topic_message(sample_topics)
        assert "Reply GO to approve" in msg
        assert "SKIP to kill" in msg
        assert "custom topic" in msg

    def test_empty_topics_list(self, gateway):
        """Empty topics list produces header and instructions only."""
        msg = gateway._format_topic_message([])
        assert "MindPattern Social - Topic Approval" in msg
        assert "Reply GO to approve" in msg


class TestFormatDraftMessage:
    """Tests for ApprovalGateway._format_draft_message()."""

    def test_header_present(self, gateway, sample_drafts):
        """Message starts with 'Draft Approval' header."""
        msg = gateway._format_draft_message(sample_drafts, {})
        assert "MindPattern Social - Draft Approval" in msg

    def test_platform_sections(self, gateway, sample_drafts):
        """Each platform has a labeled section."""
        msg = gateway._format_draft_message(sample_drafts, {})
        assert "BLUESKY" in msg
        assert "LINKEDIN" in msg

    def test_image_indicator(self, gateway, sample_drafts):
        """Image indicator shows 'yes' or 'no'."""
        images = {"bluesky": "https://example.com/image.png"}
        msg = gateway._format_draft_message(sample_drafts, images)
        assert "(image: yes)" in msg
        assert "(image: no)" in msg

    def test_draft_content_included(self, gateway, sample_drafts):
        """Draft text appears in the message."""
        msg = gateway._format_draft_message(sample_drafts, {})
        assert "GPT-5" in msg

    def test_long_draft_truncated(self, gateway):
        """Drafts longer than 500 chars are truncated with char count."""
        long_drafts = {"bluesky": "A" * 600}
        msg = gateway._format_draft_message(long_drafts, {})
        assert "600 chars total" in msg

    def test_reply_instructions(self, gateway, sample_drafts):
        """Reply instructions appear at the end."""
        msg = gateway._format_draft_message(sample_drafts, {})
        assert "Reply ALL to post all" in msg

    def test_dict_content_extraction(self, gateway):
        """Drafts that are dicts (not strings) have their content extracted."""
        drafts = {"bluesky": {"content": "Extracted text", "metadata": "ignored"}}
        msg = gateway._format_draft_message(drafts, {})
        assert "Extracted text" in msg


class TestFormatEngagementMessage:
    """Tests for ApprovalGateway._format_engagement_message()."""

    def test_header_includes_count(self, gateway, sample_candidates):
        """Header includes the number of candidates."""
        msg = gateway._format_engagement_message(sample_candidates)
        assert "3 Reply Candidates" in msg

    def test_candidates_numbered(self, gateway, sample_candidates):
        """Each candidate is numbered."""
        msg = gateway._format_engagement_message(sample_candidates)
        assert "1. [bluesky] @alice" in msg
        assert "2. [linkedin] @bob" in msg
        assert "3. [bluesky] @carol" in msg

    def test_content_and_reply_shown(self, gateway, sample_candidates):
        """Both original content and our reply are shown."""
        msg = gateway._format_engagement_message(sample_candidates)
        assert "Their post:" in msg
        assert "Our reply:" in msg
        assert "attention mechanisms" in msg

    def test_reply_instructions(self, gateway, sample_candidates):
        """Reply instructions appear at the end."""
        msg = gateway._format_engagement_message(sample_candidates)
        assert "'all' to approve all" in msg
        assert "'skip' to cancel all" in msg

    def test_empty_candidates(self, gateway):
        """Empty candidates list produces header with 0 count."""
        msg = gateway._format_engagement_message([])
        assert "0 Reply Candidates" in msg


# ════════════════════════════════════════════════════════════════════════
# Slack Approval Flow
# ════════════════════════════════════════════════════════════════════════


class TestSlackApproval:
    """Tests for ApprovalGateway._slack_approval() with mocked urllib."""

    @patch.object(ApprovalGateway, "_slack_poll_replies", return_value="go")
    @patch.object(ApprovalGateway, "_slack_post", return_value={
        "ok": True,
        "message": {"ts": "1234567890.123456"},
    })
    @patch.object(ApprovalGateway, "_get_slack_token", return_value="xoxb-fake-token")
    def test_successful_slack_approval(self, mock_token, mock_post, mock_poll, gateway):
        """Slack approval succeeds: get token, post, poll for reply."""
        result = gateway._slack_approval("Test message", timeout_seconds=5)

        assert result == "go"
        mock_token.assert_called_once()
        mock_post.assert_called_once_with("xoxb-fake-token", "Test message")
        mock_poll.assert_called_once()

    @patch.object(ApprovalGateway, "_get_slack_token", return_value=None)
    def test_no_slack_token_returns_none(self, mock_token, gateway):
        """Returns None when Slack token is not available."""
        result = gateway._slack_approval("Test message")
        assert result is None

    @patch.object(ApprovalGateway, "_slack_post", return_value=None)
    @patch.object(ApprovalGateway, "_get_slack_token", return_value="xoxb-fake-token")
    def test_slack_post_failure_returns_none(self, mock_token, mock_post, gateway):
        """Returns None when Slack post fails."""
        result = gateway._slack_approval("Test message")
        assert result is None

    @patch.object(ApprovalGateway, "_slack_poll_replies", return_value=None)
    @patch.object(ApprovalGateway, "_slack_post", return_value={
        "ok": True,
        "message": {"ts": "1234567890.123456"},
    })
    @patch.object(ApprovalGateway, "_get_slack_token", return_value="xoxb-fake-token")
    def test_slack_poll_timeout_returns_none(self, mock_token, mock_post, mock_poll, gateway):
        """Returns None when polling times out."""
        result = gateway._slack_approval("Test message", timeout_seconds=5)
        assert result is None

    @patch.object(ApprovalGateway, "_slack_post", return_value={"ok": True, "ts": "123.456"})
    @patch.object(ApprovalGateway, "_get_slack_token", return_value="xoxb-fake-token")
    @patch.object(ApprovalGateway, "_slack_poll_replies", return_value="2")
    def test_thread_ts_fallback_to_top_level_ts(self, mock_poll, mock_token, mock_post, gateway):
        """Uses top-level 'ts' when 'message.ts' is not present."""
        result = gateway._slack_approval("Test message", timeout_seconds=5)
        assert result == "2"
        # Verify poll was called with the top-level ts
        mock_poll.assert_called_once_with("xoxb-fake-token", "123.456", 5)


# ════════════════════════════════════════════════════════════════════════
# Request Topic Approval — Slack only
# ════════════════════════════════════════════════════════════════════════


class TestRequestTopicApproval:
    """Tests for ApprovalGateway.request_topic_approval()."""

    @patch.object(ApprovalGateway, "_slack_approval", return_value="go")
    def test_slack_success_returns_go(self, mock_slack, gateway, sample_topics):
        """When Slack returns a reply, approval succeeds."""
        result = gateway.request_topic_approval(sample_topics)

        assert result["action"] == "go"
        mock_slack.assert_called_once()

    @patch.object(ApprovalGateway, "_slack_approval", return_value=None)
    def test_slack_timeout_returns_skip(self, mock_slack, gateway, sample_topics):
        """When Slack times out, returns skip."""
        result = gateway.request_topic_approval(sample_topics)

        assert result["action"] == "skip"
        assert "Timed out" in result["guidance"]

    @patch.object(ApprovalGateway, "_slack_approval", return_value="2 with a developer focus")
    def test_number_with_guidance_parsed(self, mock_slack, gateway, sample_topics):
        """Numeric reply with guidance is properly parsed."""
        result = gateway.request_topic_approval(sample_topics)

        assert result["action"] == "go"
        assert result["topic_index"] == 1
        assert "developer focus" in result["guidance"]

    @patch.object(ApprovalGateway, "_slack_approval", return_value="Write about Rust adoption instead")
    def test_custom_topic_from_slack(self, mock_slack, gateway, sample_topics):
        """Custom text from Slack becomes custom action."""
        result = gateway.request_topic_approval(sample_topics)

        assert result["action"] == "custom"
        assert "Rust adoption" in result["guidance"]


class TestRequestDraftApproval:
    """Tests for ApprovalGateway.request_draft_approval()."""

    @patch.object(ApprovalGateway, "_slack_approval", return_value="all")
    def test_slack_all_approves_all_platforms(self, mock_slack, gateway, sample_drafts):
        """'all' from Slack approves all platforms."""
        result = gateway.request_draft_approval(sample_drafts, {})

        assert result["action"] == "all"
        assert set(result["platforms"]) == {"bluesky", "linkedin"}

    @patch.object(ApprovalGateway, "_slack_approval", return_value=None)
    def test_slack_timeout_returns_skip(self, mock_slack, gateway, sample_drafts):
        """When Slack times out, returns skip."""
        result = gateway.request_draft_approval(sample_drafts, {})

        assert result["action"] == "skip"
        assert result["platforms"] == []


class TestRequestEngagementApproval:
    """Tests for ApprovalGateway.request_engagement_approval()."""

    def test_empty_candidates_returns_immediately(self, gateway):
        """Empty candidates list returns without calling Slack."""
        result = gateway.request_engagement_approval([])
        assert result["approved_indices"] == []
        assert "No candidates" in result["reason"]

    @patch.object(ApprovalGateway, "_slack_approval", return_value="1 3")
    def test_selective_approval(self, mock_slack, gateway, sample_candidates):
        """Selective number reply approves only those candidates."""
        result = gateway.request_engagement_approval(sample_candidates)

        assert result["approved_indices"] == [0, 2]

    @patch.object(ApprovalGateway, "_slack_approval", return_value=None)
    def test_slack_timeout_returns_empty(self, mock_slack, gateway, sample_candidates):
        """When Slack times out, returns empty with timeout reason."""
        result = gateway.request_engagement_approval(sample_candidates)

        assert result["approved_indices"] == []
        assert "Timed out" in result["reason"]

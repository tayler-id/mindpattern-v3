"""M0 Task 11 — strict approval parsing (audit C4).

Approval requires an explicit affirmative token from the owner, thread-scoped.
"wait", "hold on", "why?", "skip linkedin", and pasted text must never post.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from social.approval import ApprovalGateway


@pytest.fixture
def gateway():
    return ApprovalGateway({"gate_timeout_seconds": 5})


PLATFORMS = ["bluesky", "linkedin"]


class TestParseDraftReply:
    """Table-test the draft approval parser."""

    @pytest.mark.parametrize("reply", [
        "wait", "hold on", "why?", "skip linkedin", "hmm let me think",
        "what does the expeditor say", "looks interesting", "edit the first one",
        "skip", "no", "kill", "cancel", "pass", "don't post", "stop",
        "Here is my edited draft:\nSomething long that I pasted...",
    ])
    def test_non_affirmative_replies_never_post(self, gateway, reply):
        result = gateway._parse_draft_reply(reply, PLATFORMS)
        assert result["action"] == "skip"
        assert result["platforms"] == []

    @pytest.mark.parametrize("reply", [
        "go", "GO", "all", "yes", "approve", "post", "send", "ok", "ship it",
    ])
    def test_affirmative_tokens_approve_all(self, gateway, reply):
        result = gateway._parse_draft_reply(reply, PLATFORMS)
        assert result["action"] == "all"
        assert result["platforms"] == PLATFORMS

    @pytest.mark.parametrize("reply,expected", [
        ("bluesky", ["bluesky"]),
        ("linkedin", ["linkedin"]),
        ("bluesky linkedin", ["bluesky", "linkedin"]),
        ("bluesky, linkedin", ["bluesky", "linkedin"]),
        ("bluesky and linkedin", ["bluesky", "linkedin"]),
        ("LINKEDIN", ["linkedin"]),
    ])
    def test_platform_only_replies_approve_selected(self, gateway, reply, expected):
        result = gateway._parse_draft_reply(reply, PLATFORMS)
        assert result["action"] == "approve_selected"
        assert result["platforms"] == expected

    def test_timeout_is_skip(self, gateway):
        result = gateway._parse_draft_reply(None, PLATFORMS)
        assert result["action"] == "skip"

    def test_platform_name_buried_in_sentence_does_not_post(self, gateway):
        result = gateway._parse_draft_reply(
            "the linkedin one reads badly", PLATFORMS
        )
        assert result["action"] == "skip"


class TestBotParseApproval:
    """Same strictness in the Slack bot's posts handler."""

    def _parser(self):
        from slack_bot.handlers.posts import PostsHandler

        handler = PostsHandler.__new__(PostsHandler)  # skip __init__ (no Slack)
        return handler._parse_approval

    @pytest.mark.parametrize("reply", [
        "skip linkedin", "wait", "hold on", "why?", "skip", "no",
        "post it later", "maybe bluesky",
    ])
    def test_non_affirmative_never_posts(self, reply):
        assert self._parser()(reply, PLATFORMS) == []

    @pytest.mark.parametrize("reply", ["all", "go", "ship it", "post"])
    def test_affirmative_posts_all(self, reply):
        assert self._parser()(reply, PLATFORMS) == PLATFORMS

    def test_platform_only_selects(self):
        assert self._parser()("bluesky", PLATFORMS) == ["bluesky"]
        assert self._parser()("bluesky linkedin", PLATFORMS) == PLATFORMS


class TestThreadScopedOwnerOnlyPolling:
    """Replies outside the thread or from non-owners are never approvals."""

    def _poll_with_messages(self, gateway, messages, owner="U_OWNER"):
        """Run one poll iteration against a mocked Slack replies API."""
        api_response = json.dumps({"ok": True, "messages": messages}).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = api_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("social.approval.urllib.request.urlopen", return_value=mock_resp), \
             patch("social.approval.time.sleep"), \
             patch.object(gateway, "_get_owner_user_id", return_value=owner):
            return gateway._slack_poll_replies("token", "100.0", timeout_seconds=1)

    def test_owner_threaded_reply_accepted(self, gateway):
        messages = [
            {"ts": "100.0", "text": "approval request", "bot_id": "B1"},
            {"ts": "101.0", "text": "go", "user": "U_OWNER"},
        ]
        assert self._poll_with_messages(gateway, messages) == "go"

    def test_non_owner_reply_ignored(self, gateway):
        messages = [
            {"ts": "100.0", "text": "approval request", "bot_id": "B1"},
            {"ts": "101.0", "text": "go", "user": "U_STRANGER"},
        ]
        assert self._poll_with_messages(
            gateway, messages, owner="U_OWNER_ONLY"
        ) is None

    def test_no_owner_configured_fails_closed(self, gateway):
        messages = [
            {"ts": "100.0", "text": "approval request", "bot_id": "B1"},
            {"ts": "101.0", "text": "go", "user": "U_ANYONE"},
        ]
        assert self._poll_with_messages(gateway, messages, owner="") is None

    def test_reply_before_our_message_ignored(self, gateway):
        messages = [
            {"ts": "100.0", "text": "approval request", "bot_id": "B1"},
            {"ts": "099.0", "text": "go", "user": "U_OWNER"},
        ]
        assert self._poll_with_messages(gateway, messages) is None


class TestDraftMessageFormatting:
    def test_full_draft_text_no_truncation(self, gateway):
        long_draft = "x" * 1200
        message = gateway._format_draft_message({"bluesky": long_draft}, {})
        assert long_draft in message
        assert "chars total" not in message  # old truncation marker

    def test_expeditor_verdict_displayed(self, gateway):
        message = gateway._format_draft_message(
            {"bluesky": "draft"}, {},
            expeditor={"verdict": "AUTO_APPROVED", "feedback": "gate errored"},
        )
        assert "AUTO_APPROVED" in message
        assert "gate errored" in message
        assert ":rotating_light:" in message

    def test_expeditor_pass_displayed_calmly(self, gateway):
        message = gateway._format_draft_message(
            {"bluesky": "draft"}, {}, expeditor={"verdict": "PASS"}
        )
        assert "Expeditor: PASS" in message
        assert ":rotating_light:" not in message

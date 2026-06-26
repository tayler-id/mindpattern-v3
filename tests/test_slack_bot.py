"""Tests for Slack bot resilience: API error handling, reply timeout defaults.

Tests use AST parsing and mock-based validation so slack_sdk is not required
in the test environment.
"""

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# slack_sdk isn't installed in the test env; stub it so base.py imports cleanly.
if "slack_sdk" not in sys.modules:
    slack_sdk_stub = MagicMock()
    sys.modules["slack_sdk"] = slack_sdk_stub
    sys.modules["slack_sdk.errors"] = MagicMock()

SLACK_BOT_DIR = Path(__file__).parent.parent / "slack_bot"


class TestReadUrlRejectsJinaErrorBody:
    """read_url() must not return Jina's SecurityCompromiseError JSON as content."""

    def test_jina_blocked_response_returns_none(self):
        from slack_bot.handlers.base import BaseHandler

        blocked_body = (
            '{"data":null,"code":451,"name":"SecurityCompromiseError",'
            '"status":45102,"message":"Anonymous access to domain '
            'www.bostonglobe.com blocked until Mon May 11 2026 14:49:07 GMT+0000"}'
        )
        fake_proc = MagicMock(returncode=0, stdout=blocked_body, stderr="")
        with patch("slack_bot.handlers.base.subprocess.run", return_value=fake_proc):
            assert BaseHandler.read_url("https://www.bostonglobe.com/foo") is None

    def test_normal_markdown_passes_through(self):
        from slack_bot.handlers.base import BaseHandler

        fake_proc = MagicMock(
            returncode=0,
            stdout="Title: Hello\n\nSome article body here.",
            stderr="",
        )
        with patch("slack_bot.handlers.base.subprocess.run", return_value=fake_proc):
            out = BaseHandler.read_url("https://example.com/")
            assert out is not None and "Some article body" in out


class TestKeychainEnvFallback:
    """Slack secrets use env vars on non-macOS hosts such as Fly.io."""

    def test_non_macos_reads_matching_env_var(self):
        from slack_bot.registry import _keychain_get

        with patch("slack_bot.registry.sys.platform", "linux"):
            with patch.dict("slack_bot.registry.os.environ", {"SLACK_BOT_TOKEN": "xoxb-test"}):
                assert _keychain_get("slack-bot-token") == "xoxb-test"


class TestReplyErrorHandling:
    """reply() must catch Slack API errors instead of crashing the handler."""

    def test_reply_catches_exceptions(self):
        """reply() should have a try/except around chat_postMessage."""
        source = (SLACK_BOT_DIR / "handlers" / "base.py").read_text()
        tree = ast.parse(source)

        # Find the reply method
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "reply":
                # Check if it contains a Try node
                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                assert has_try, "reply() must wrap chat_postMessage in try/except"
                return
        pytest.fail("Could not find reply() method in base.py")


class TestGetThreadRepliesErrorHandling:
    """get_thread_replies() must catch Slack API errors."""

    def test_get_thread_replies_catches_exceptions(self):
        """get_thread_replies() should have a try/except around conversations_replies."""
        source = (SLACK_BOT_DIR / "handlers" / "base.py").read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_thread_replies":
                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                assert has_try, "get_thread_replies() must wrap conversations_replies in try/except"
                return
        pytest.fail("Could not find get_thread_replies() method in base.py")


class TestWaitForReplyDefaultTimeout:
    """wait_for_reply() must have a reasonable default timeout."""

    def test_default_timeout_is_not_none(self):
        """wait_for_reply timeout parameter must not default to None (infinite)."""
        source = (SLACK_BOT_DIR / "handlers" / "base.py").read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "wait_for_reply":
                for arg in node.args.defaults + node.args.kw_defaults:
                    pass  # walk through defaults
                # Find the 'timeout' parameter and its default
                args = node.args
                # timeout is a keyword argument with a default
                all_args = args.args + args.kwonlyargs
                defaults_offset = len(args.args) - len(args.defaults)
                for i, arg in enumerate(args.args):
                    if arg.arg == "timeout":
                        default_idx = i - defaults_offset
                        if default_idx >= 0:
                            default = args.defaults[default_idx]
                            is_none = isinstance(default, ast.Constant) and default.value is None
                            assert not is_none, (
                                "wait_for_reply timeout must not default to None. "
                                "Use a concrete default like 300 (5 min) to prevent infinite waits."
                            )
                        return
        pytest.fail("Could not find timeout parameter in wait_for_reply()")


class TestBotAutoReconnect:
    """Socket Mode client should be configured for auto-reconnect."""

    def test_socket_client_has_auto_reconnect(self):
        """SocketModeClient must be initialized with auto_reconnect_enabled=True."""
        source = (SLACK_BOT_DIR / "bot.py").read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_socket_client = (
                    (isinstance(func, ast.Name) and func.id == "SocketModeClient")
                    or (isinstance(func, ast.Attribute) and func.attr == "SocketModeClient")
                )
                if is_socket_client:
                    for kw in node.keywords:
                        if kw.arg == "auto_reconnect_enabled":
                            assert isinstance(kw.value, ast.Constant) and kw.value.value is True, (
                                "auto_reconnect_enabled must be True"
                            )
                            return
                    pytest.fail(
                        "SocketModeClient missing auto_reconnect_enabled=True parameter"
                    )

        pytest.fail("Could not find SocketModeClient() constructor call in bot.py")


class TestBotPingInterval:
    """Socket Mode client should have a ping interval for connection health."""

    def test_socket_client_has_ping_interval(self):
        """SocketModeClient must be initialized with a ping_interval."""
        source = (SLACK_BOT_DIR / "bot.py").read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                is_socket_client = (
                    (isinstance(func, ast.Name) and func.id == "SocketModeClient")
                    or (isinstance(func, ast.Attribute) and func.attr == "SocketModeClient")
                )
                if is_socket_client:
                    for kw in node.keywords:
                        if kw.arg == "ping_interval":
                            return  # Found it
                    pytest.fail("SocketModeClient missing ping_interval parameter")

        pytest.fail("Could not find SocketModeClient() constructor call in bot.py")


class TestSkillsTipsShortInputFeedback:
    """Skills/tips channels must never silently ignore visible owner tests."""

    def test_skills_short_input_replies_with_guidance(self):
        from slack_bot.handlers.skills import SkillsHandler

        client = MagicMock()
        handler = SkillsHandler(client=client, channel_id="C_SKILLS", owner_user_id="U_OWNER")

        handler.handle({"text": "test", "ts": "123.456"})

        client.chat_postMessage.assert_called_once()
        kwargs = client.chat_postMessage.call_args.kwargs
        assert kwargs["channel"] == "C_SKILLS"
        assert kwargs["thread_ts"] == "123.456"
        assert "skill tip" in kwargs["text"].lower()

    def test_tips_short_input_replies_with_guidance(self):
        from slack_bot.handlers.tips import TipsHandler

        client = MagicMock()
        handler = TipsHandler(client=client, channel_id="C_TIPS", owner_user_id="U_OWNER")

        handler.handle({"text": "test", "ts": "123.456"})

        client.chat_postMessage.assert_called_once()
        kwargs = client.chat_postMessage.call_args.kwargs
        assert kwargs["channel"] == "C_TIPS"
        assert kwargs["thread_ts"] == "123.456"
        assert "tip" in kwargs["text"].lower()


class TestSharedSlackApprovalParser:
    """All Slack content channels should share one fail-closed parser."""

    platforms = ["bluesky", "linkedin"]

    @pytest.mark.parametrize("reply", [
        "all", "yes", "y", "go", "post", "approve", "approved", "ok",
        "ship", "ship it", "post it",
    ])
    def test_affirmative_replies_approve_all(self, reply):
        from slack_bot.approval import parse_platform_approval

        assert parse_platform_approval(reply, self.platforms) == self.platforms

    @pytest.mark.parametrize("reply,expected", [
        ("bluesky", ["bluesky"]),
        ("linkedin", ["linkedin"]),
        ("bluesky linkedin", ["bluesky", "linkedin"]),
        ("linkedin, bluesky", ["linkedin", "bluesky"]),
        ("bluesky and linkedin", ["bluesky", "linkedin"]),
        ("LINKEDIN", ["linkedin"]),
    ])
    def test_platform_only_replies_approve_selected(self, reply, expected):
        from slack_bot.approval import parse_platform_approval

        assert parse_platform_approval(reply, self.platforms) == expected

    @pytest.mark.parametrize("reply", [
        "", "skip", "no", "cancel", "n", "wait", "hold on", "why?",
        "skip linkedin", "maybe bluesky", "post it later",
        "Here is my edited draft:\nSomething long that I pasted...",
    ])
    def test_unclear_replies_post_nothing(self, reply):
        from slack_bot.approval import parse_platform_approval

        assert parse_platform_approval(reply, self.platforms) == []


class TestSkillsTipsStrictApproval:
    """Skills/tips handlers must use fail-closed approval semantics."""

    @staticmethod
    def _handler_with_drafts(handler_class, channel_id):
        client = MagicMock()
        handler = handler_class(
            client=client,
            channel_id=channel_id,
            owner_user_id="U_OWNER",
        )
        handler._create_drafts = MagicMock(return_value={
            "bluesky": "Bluesky draft",
            "linkedin": "LinkedIn draft",
        })
        handler.react = MagicMock()
        handler.wait_for_reply = MagicMock()
        handler._post = MagicMock(return_value={})
        return handler, client

    @pytest.mark.parametrize("reply", [
        "wait", "hold on", "skip linkedin", "maybe bluesky",
        "Here is my edited draft:\nReplacement copy",
    ])
    @pytest.mark.parametrize("handler_class,channel_id", [
        pytest.param(
            __import__("slack_bot.handlers.skills", fromlist=["SkillsHandler"]).SkillsHandler,
            "C_SKILLS",
            id="skills",
        ),
        pytest.param(
            __import__("slack_bot.handlers.tips", fromlist=["TipsHandler"]).TipsHandler,
            "C_TIPS",
            id="tips",
        ),
    ])
    def test_unclear_replies_do_not_post(self, handler_class, channel_id, reply):
        handler, client = self._handler_with_drafts(handler_class, channel_id)
        handler.wait_for_reply.return_value = reply

        handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        handler._post.assert_not_called()
        assert "skipped" in client.chat_postMessage.call_args_list[-1].kwargs["text"].lower()

    @pytest.mark.parametrize("reply,expected", [
        ("all", ["bluesky", "linkedin"]),
        ("bluesky", ["bluesky"]),
        ("linkedin", ["linkedin"]),
        ("linkedin bluesky", ["linkedin", "bluesky"]),
    ])
    @pytest.mark.parametrize("handler_class,channel_id", [
        pytest.param(
            __import__("slack_bot.handlers.skills", fromlist=["SkillsHandler"]).SkillsHandler,
            "C_SKILLS",
            id="skills",
        ),
        pytest.param(
            __import__("slack_bot.handlers.tips", fromlist=["TipsHandler"]).TipsHandler,
            "C_TIPS",
            id="tips",
        ),
    ])
    def test_explicit_replies_post_selected_platforms(
        self, handler_class, channel_id, reply, expected
    ):
        handler, _client = self._handler_with_drafts(handler_class, channel_id)
        handler.wait_for_reply.return_value = reply

        handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        handler._post.assert_called_once_with(
            {"bluesky": "Bluesky draft", "linkedin": "LinkedIn draft"},
            expected,
        )


class TestDraftEditHelpers:
    """Draft edits are revisions, not approvals."""

    platforms = ["bluesky", "linkedin"]

    def test_parse_platform_edit(self):
        from slack_bot.drafts import parse_draft_edit

        edit, error = parse_draft_edit(
            "edit bluesky: New bluesky copy",
            self.platforms,
        )

        assert error is None
        assert edit is not None
        assert edit.platform == "bluesky"
        assert edit.content == "New bluesky copy"

    def test_parse_edit_is_case_insensitive(self):
        from slack_bot.drafts import parse_draft_edit

        edit, error = parse_draft_edit(
            "EDIT LINKEDIN: New LinkedIn copy",
            self.platforms,
        )

        assert error is None
        assert edit is not None
        assert edit.platform == "linkedin"
        assert edit.content == "New LinkedIn copy"

    def test_unknown_platform_edit_returns_error(self):
        from slack_bot.drafts import parse_draft_edit

        edit, error = parse_draft_edit(
            "edit mastodon: New copy",
            self.platforms,
        )

        assert edit is None
        assert "unknown platform" in error.lower()

    def test_empty_edit_returns_error(self):
        from slack_bot.drafts import parse_draft_edit

        edit, error = parse_draft_edit("edit bluesky:", self.platforms)

        assert edit is None
        assert "replacement" in error.lower()

    def test_non_edit_reply_returns_no_decision(self):
        from slack_bot.drafts import parse_draft_edit

        edit, error = parse_draft_edit("go", self.platforms)

        assert edit is None
        assert error is None

    def test_apply_draft_edit_copies_and_updates_one_platform(self):
        from slack_bot.drafts import DraftEdit, apply_draft_edit

        drafts = {"bluesky": "Old bluesky", "linkedin": "Old linkedin"}
        updated = apply_draft_edit(
            drafts,
            DraftEdit(platform="bluesky", content="New bluesky"),
        )

        assert updated == {"bluesky": "New bluesky", "linkedin": "Old linkedin"}
        assert drafts == {"bluesky": "Old bluesky", "linkedin": "Old linkedin"}

    def test_edit_command_is_not_approval(self):
        from slack_bot.approval import parse_platform_approval

        assert parse_platform_approval("edit bluesky: New copy", self.platforms) == []


class TestPostsEditFlow:
    """#mp-posts edits must re-preview before any posting can happen."""

    @staticmethod
    def _handler():
        from slack_bot.handlers.posts import PostsHandler

        client = MagicMock()
        handler = PostsHandler(
            client=client,
            channel_id="C_POSTS",
            owner_user_id="U_OWNER",
        )
        handler._run_social_pipeline = MagicMock(return_value=(
            {"bluesky": "Old bluesky", "linkedin": "Old linkedin"},
            {},
        ))
        handler._format_drafts = MagicMock(
            side_effect=lambda drafts, _errors: (
                f"preview bluesky={drafts['bluesky']} linkedin={drafts['linkedin']}"
            )
        )
        handler.wait_for_reply = MagicMock()
        handler._post_to_platforms = MagicMock(return_value={
            "bluesky": {"success": True, "url": "https://bsky.app/post/1"},
        })
        return handler, client

    def test_edit_repreviews_and_requires_second_approval(self):
        handler, client = self._handler()
        handler.wait_for_reply.side_effect = [
            "edit bluesky: New bluesky",
            "bluesky",
        ]

        handler._run_and_approve({"anchor": "topic"}, "123.456")

        assert handler._format_drafts.call_count == 2
        handler._post_to_platforms.assert_called_once_with(
            {"bluesky": "New bluesky", "linkedin": "Old linkedin"},
            ["bluesky"],
        )
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("New bluesky" in message for message in messages)

    def test_edit_then_skip_posts_nothing(self):
        handler, _client = self._handler()
        handler.wait_for_reply.side_effect = [
            "edit linkedin: New linkedin",
            "skip",
        ]

        handler._run_and_approve({"anchor": "topic"}, "123.456")

        assert handler._format_drafts.call_count == 2
        handler._post_to_platforms.assert_not_called()

    def test_bad_edit_replies_with_error_and_waits_again(self):
        handler, client = self._handler()
        handler.wait_for_reply.side_effect = [
            "edit mastodon: New copy",
            "skip",
        ]

        handler._run_and_approve({"anchor": "topic"}, "123.456")

        handler._post_to_platforms.assert_not_called()
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("unknown platform" in message.lower() for message in messages)

"""Tests for Slack bot resilience: API error handling, reply timeout defaults.

Tests use AST parsing and mock-based validation so slack_sdk is not required
in the test environment.
"""

import ast
import json
import sqlite3
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

    def test_followup_reply_runs_research_and_keeps_waiting(self):
        handler, client = self._handler()
        handler.wait_for_reply.side_effect = [
            "follow up: compare agent-reach and opencli",
            "skip",
        ]
        result = {
            "status": "completed",
            "degraded": False,
            "findings": [
                {
                    "title": "Agent Reach comparison",
                    "summary": "Agent Reach can route across backends.",
                    "source_name": "Dry Run",
                }
            ],
            "why_this_matters": "This helps decide the social angle.",
            "next_action": "Revise the draft.",
        }

        with patch(
            "slack_bot.handlers.followup.run_followup_research",
            return_value=result,
            create=True,
        ) as run_followup, patch(
            "slack_bot.handlers.followup.open_traces_db",
            create=True,
        ):
            handler._run_and_approve({"anchor": "topic"}, "123.456")

        run_followup.assert_called_once()
        handler._post_to_platforms.assert_not_called()
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("Agent Reach comparison" in message for message in messages)
        assert "Skipped. Nothing posted." in messages[-1]


class TestSkillsTipsEditFlow:
    """#mp-skills and #mp-tips must support safe draft edits."""

    @staticmethod
    def _handler(handler_class, channel_id):
        client = MagicMock()
        handler = handler_class(
            client=client,
            channel_id=channel_id,
            owner_user_id="U_OWNER",
        )
        handler._create_drafts = MagicMock(return_value={
            "bluesky": "Old bluesky",
            "linkedin": "Old linkedin",
        })
        handler.react = MagicMock()
        handler.wait_for_reply = MagicMock()
        handler._post = MagicMock(return_value={
            "bluesky": {"success": True, "url": "https://bsky.app/post/1"},
        })
        return handler, client

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
    def test_edit_repreviews_and_requires_second_approval(self, handler_class, channel_id):
        handler, client = self._handler(handler_class, channel_id)
        handler.wait_for_reply.side_effect = [
            "edit bluesky: New bluesky",
            "bluesky",
        ]

        handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        handler._post.assert_called_once_with(
            {"bluesky": "New bluesky", "linkedin": "Old linkedin"},
            ["bluesky"],
        )
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("Updated bluesky draft" in message for message in messages)
        assert any("New bluesky" in message for message in messages)

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
    def test_edit_then_skip_posts_nothing(self, handler_class, channel_id):
        handler, client = self._handler(handler_class, channel_id)
        handler.wait_for_reply.side_effect = [
            "edit linkedin: New linkedin",
            "skip",
        ]

        handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        handler._post.assert_not_called()
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("New linkedin" in message for message in messages)

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
    def test_bad_edit_replies_with_error_and_waits_again(self, handler_class, channel_id):
        handler, client = self._handler(handler_class, channel_id)
        handler.wait_for_reply.side_effect = [
            "edit mastodon: New copy",
            "skip",
        ]

        handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        handler._post.assert_not_called()
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("unknown platform" in message.lower() for message in messages)

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
    def test_followup_reply_runs_research_and_keeps_waiting(self, handler_class, channel_id):
        handler, client = self._handler(handler_class, channel_id)
        handler.wait_for_reply.side_effect = [
            "follow up: compare agent-reach and opencli",
            "skip",
        ]
        result = {
            "status": "completed",
            "degraded": False,
            "findings": [
                {
                    "title": "Agent Reach comparison",
                    "summary": "Agent Reach can route across backends.",
                    "source_name": "Dry Run",
                }
            ],
            "why_this_matters": "This helps decide the social angle.",
            "next_action": "Revise the draft.",
        }

        with patch(
            "slack_bot.handlers.followup.run_followup_research",
            return_value=result,
            create=True,
        ) as run_followup, patch(
            "slack_bot.handlers.followup.open_traces_db",
            create=True,
        ):
            handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        run_followup.assert_called_once()
        handler._post.assert_not_called()
        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("Agent Reach comparison" in message for message in messages)
        assert "Skipped. Nothing posted." in messages[-1]


class TestDisabledPlatformManualCopy:
    """Disabled platforms should return copyable drafts, not live-post attempts."""

    disabled_config = {
        "platforms": {
            "bluesky": {"enabled": False, "max_chars": 300},
            "linkedin": {"enabled": False, "max_chars": 3000},
        }
    }

    def test_posts_disabled_platforms_return_manual_copy_and_skip_clients(self):
        from slack_bot.handlers.posts import PostsHandler

        handler = PostsHandler(
            client=MagicMock(),
            channel_id="C_POSTS",
            owner_user_id="U_OWNER",
        )
        handler._load_social_config = MagicMock(return_value=self.disabled_config)

        with patch("social.posting.BlueskyClient") as bluesky_client:
            with patch("social.posting.LinkedInClient") as linkedin_client:
                results = handler._post_to_platforms(
                    {"bluesky": "Bluesky copy", "linkedin": "LinkedIn copy"},
                    ["bluesky", "linkedin"],
                )

        assert results["bluesky"]["manual_only"] is True
        assert results["bluesky"]["success"] is False
        assert results["bluesky"]["content"] == "Bluesky copy"
        assert results["linkedin"]["manual_only"] is True
        assert results["linkedin"]["success"] is False
        assert results["linkedin"]["content"] == "LinkedIn copy"
        bluesky_client.assert_not_called()
        linkedin_client.assert_not_called()

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
    def test_skills_tips_disabled_platforms_return_manual_copy_and_skip_clients(
        self, handler_class, channel_id
    ):
        handler = handler_class(
            client=MagicMock(),
            channel_id=channel_id,
            owner_user_id="U_OWNER",
        )
        handler._load_social_config = MagicMock(return_value=self.disabled_config)

        with patch("social.posting.BlueskyClient") as bluesky_client:
            with patch("social.posting.LinkedInClient") as linkedin_client:
                results = handler._post(
                    {"bluesky": "Bluesky copy", "linkedin": "LinkedIn copy"},
                    ["bluesky", "linkedin"],
                )

        assert results["bluesky"]["manual_only"] is True
        assert results["bluesky"]["success"] is False
        assert results["bluesky"]["content"] == "Bluesky copy"
        assert results["linkedin"]["manual_only"] is True
        assert results["linkedin"]["success"] is False
        assert results["linkedin"]["content"] == "LinkedIn copy"
        bluesky_client.assert_not_called()
        linkedin_client.assert_not_called()

    def test_posts_manual_copy_result_is_reported_as_copy_block(self):
        from slack_bot.handlers.posts import PostsHandler

        client = MagicMock()
        handler = PostsHandler(
            client=client,
            channel_id="C_POSTS",
            owner_user_id="U_OWNER",
        )
        handler._run_social_pipeline = MagicMock(return_value=(
            {"bluesky": "Bluesky copy"},
            {},
        ))
        handler.wait_for_reply = MagicMock(return_value="bluesky")
        handler._post_to_platforms = MagicMock(return_value={
            "bluesky": {
                "success": False,
                "manual_only": True,
                "content": "Bluesky copy",
                "error": "bluesky is disabled",
            }
        })

        handler._run_and_approve({"anchor": "topic"}, "123.456")

        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("manual copy" in message.lower() for message in messages)
        assert any("Bluesky copy" in message for message in messages)
        assert not any(":x: bluesky" in message for message in messages)

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
    def test_skills_tips_manual_copy_result_is_reported_as_copy_block(
        self, handler_class, channel_id
    ):
        client = MagicMock()
        handler = handler_class(
            client=client,
            channel_id=channel_id,
            owner_user_id="U_OWNER",
        )
        handler._create_drafts = MagicMock(return_value={"bluesky": "Bluesky copy"})
        handler.react = MagicMock()
        handler.wait_for_reply = MagicMock(return_value="bluesky")
        handler._post = MagicMock(return_value={
            "bluesky": {
                "success": False,
                "manual_only": True,
                "content": "Bluesky copy",
                "error": "bluesky is disabled",
            }
        })

        handler.handle({"text": "This is a concrete tip long enough to draft.", "ts": "123.456"})

        messages = [
            call.kwargs["text"]
            for call in client.chat_postMessage.call_args_list
        ]
        assert any("manual copy" in message.lower() for message in messages)
        assert any("Bluesky copy" in message for message in messages)
        assert not any(":x: bluesky" in message.lower() for message in messages)


class TestSlackBotDoctorStatus:
    """Bot doctor output should prove wiring without leaking secrets."""

    def test_build_handlers_records_redacted_registry_report(self):
        from slack_bot import registry

        with patch("slack_bot.registry.load_channel_config", return_value={
            "posts": "C_POSTS",
            "briefing": "C_BRIEFING",
        }):
            registry.build_handlers(MagicMock(), "U_OWNER")

        with patch.dict("slack_bot.registry.os.environ", {
            "SLACK_BOT_TOKEN": "bot-sensitive-value",
            "SLACK_APP_TOKEN": "app-sensitive-value",
        }):
            report = registry.get_bot_doctor_report("U_OWNER")

        assert set(report["registered_names"]) == {"posts", "briefing"}
        assert report["configured_count"] == 2
        assert "skills" in report["missing_names"]
        assert "tips" in report["missing_names"]
        assert report["owner_configured"] is True
        assert report["token_sources"]["bot_token"] == "environment"
        assert report["token_sources"]["app_token"] == "environment"

        serialized = repr(report)
        assert "C_POSTS" not in serialized
        assert "C_BRIEFING" not in serialized
        assert "U_OWNER" not in serialized
        assert "bot-sensitive-value" not in serialized
        assert "app-sensitive-value" not in serialized

    def test_briefing_doctor_reports_safe_bot_health(self, tmp_path):
        from slack_bot.handlers.briefing import BriefingHandler

        heartbeat_file = tmp_path / "bot-heartbeat"
        heartbeat_file.write_text("")
        now = heartbeat_file.stat().st_mtime + 42

        fake_report = {
            "expected_names": ["posts", "skills", "tips", "briefing"],
            "registered_names": ["posts", "briefing"],
            "missing_names": ["skills", "tips"],
            "failed_names": [],
            "configured_count": 2,
            "registered_count": 2,
            "owner_configured": True,
            "token_sources": {
                "bot_token": "environment",
                "app_token": "environment",
            },
        }

        client = MagicMock()
        handler = BriefingHandler(
            client=client,
            channel_id="C_BRIEFING",
            owner_user_id="U_OWNER",
        )

        with patch("slack_bot.handlers.briefing.get_bot_doctor_report", return_value=fake_report):
            with patch("slack_bot.handlers.briefing.heartbeat.heartbeat_path", return_value=heartbeat_file):
                with patch("slack_bot.handlers.briefing.heartbeat.is_stale", return_value=False):
                    with patch("slack_bot.handlers.briefing.time.time", return_value=now):
                        handler.handle({"text": "doctor", "ts": "123.456"})

        text = client.chat_postMessage.call_args.kwargs["text"]
        lower = text.lower()
        assert "slack bot doctor" in lower
        assert "registered handlers (2/4): posts, briefing" in lower
        assert "configured channels: 2" in lower
        assert "missing channel config: skills, tips" in lower
        assert "owner: configured" in lower
        assert "bot token: environment" in lower
        assert "app token: environment" in lower
        assert "heartbeat: fresh" in lower
        assert "42s" in lower

        assert "C_BRIEFING" not in text
        assert "U_OWNER" not in text
        assert "bot-sensitive-value" not in lower
        assert "app-sensitive-value" not in lower


class TestBriefingSocialState:
    """Briefing summaries should distinguish social states safely."""

    @staticmethod
    def _handler():
        from slack_bot.handlers.briefing import BriefingHandler

        client = MagicMock()
        handler = BriefingHandler(
            client=client,
            channel_id="C_BRIEFING",
            owner_user_id="U_OWNER",
        )
        return handler, client

    def test_pipeline_summary_reports_manual_copy_without_content(self):
        handler, client = self._handler()

        handler.post_pipeline_summary({
            "findings_count": 12,
            "newsletter_generated": True,
            "social": {
                "publish_mode": "manual_only",
                "manual_copy": [
                    {
                        "platform": "bluesky",
                        "status": "manual_only",
                        "content": "Do not leak this draft copy",
                    }
                ],
            },
        })

        text = client.chat_postMessage.call_args.kwargs["text"]
        assert "Social: Manual-copy drafts for bluesky" in text
        assert "No posts" not in text
        assert "Do not leak this draft copy" not in text

    def test_pipeline_summary_reports_skipped_reason(self):
        handler, client = self._handler()

        handler.post_pipeline_summary({
            "social": {
                "skipped": True,
                "reason": "no draft-capable platforms",
            },
        })

        text = client.chat_postMessage.call_args.kwargs["text"]
        assert "Social: Skipped - no draft-capable platforms" in text

    def test_pipeline_summary_reports_social_error(self):
        handler, client = self._handler()

        handler.post_pipeline_summary({
            "social": {
                "errors": ["Writing: writer died"],
            },
        })

        text = client.chat_postMessage.call_args.kwargs["text"]
        assert "Social: Error - Writing: writer died" in text

    def test_status_reports_source_health_from_latest_trace(self, tmp_path):
        handler, client = self._handler()

        data_dir = tmp_path / "data" / "ramsay"
        data_dir.mkdir(parents=True)
        db = sqlite3.connect(data_dir / "memory.db")
        db.executescript("""
            CREATE TABLE findings (run_date TEXT, agent TEXT);
            CREATE TABLE social_posts (date TEXT, platform TEXT, content TEXT, posted INTEGER);
            CREATE TABLE engagements (created_at TEXT);
        """)
        db.commit()
        db.close()

        traces = sqlite3.connect(data_dir / "traces.db")
        traces.execute(
            "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "pipeline_run_id TEXT, event_type TEXT, payload TEXT)"
        )
        traces.execute(
            "INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
            (
                "run-1",
                "preflight_complete",
                json.dumps({
                    "run_date": "2026-06-26",
                    "source_health": {
                        "rss": {"status": "empty", "count": 0, "reason": "no items"},
                        "reddit": {"status": "unavailable", "count": 0, "reason": "backend off"},
                        "youtube": {"status": "timeout", "count": 0, "reason": "timed out"},
                    },
                    "source_health_summary": {
                        "expected_source_count": 2,
                        "responsive_source_count": 1,
                        "unavailable_sources": ["reddit"],
                        "degraded_sources": ["youtube"],
                    },
                }),
            ),
        )
        traces.execute(
            "INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
            (
                "run-1",
                "newsletter_quality_floor_degraded",
                json.dumps({
                    "run_date": "2026-06-26",
                    "status": "degraded",
                    "reasons": ["coverage score 0.55 below floor 0.6"],
                }),
            ),
        )
        traces.commit()
        traces.close()

        with patch("slack_bot.handlers.briefing.PROJECT_ROOT", tmp_path):
            handler._post_status("123.456", date_str="2026-06-26")

        text = client.chat_postMessage.call_args.kwargs["text"]
        assert "Sources: 1/2 responsive" in text
        assert "Unavailable: reddit" in text
        assert "Degraded: youtube (timeout)" in text
        assert "Quality: degraded - coverage score 0.55 below floor 0.6" in text
        assert "backend off" not in text


class TestBriefingFollowupCommand:
    """#mp-briefing should run scoped follow-up research in-thread."""

    @staticmethod
    def _handler():
        from slack_bot.handlers.briefing import BriefingHandler

        client = MagicMock()
        handler = BriefingHandler(
            client=client,
            channel_id="C_BRIEFING",
            owner_user_id="U_OWNER",
        )
        return handler, client

    def test_briefing_followup_command_acknowledges_and_posts_result(self):
        handler, client = self._handler()
        handler.wait_for_reply = MagicMock(return_value=None)
        result = {
            "status": "completed",
            "degraded": False,
            "agent_count": 4,
            "successful_agent_count": 4,
            "findings": [
                {
                    "title": "Agent Reach source routing",
                    "summary": "OpenCLI can cover Reddit while direct X search is degraded.",
                    "source_name": "Dry Run",
                    "source_url": "https://example.com/source",
                }
            ],
            "why_this_matters": "Source routing decides newsletter quality.",
            "next_action": "Turn into a social angle.",
            "action_help": "Reply `cover`, `draft`, `archive`, or `ignore`.",
            "artifact": "reports/ramsay/followups/example.md",
        }

        with patch(
            "slack_bot.handlers.briefing.run_followup_research",
            return_value=result,
            create=True,
        ) as run_followup, patch(
            "slack_bot.handlers.briefing.open_traces_db",
            create=True,
        ):
            handler.handle({
                "text": "follow up: compare agent-reach and opencli for social search",
                "ts": "123.456",
            })

        run_followup.assert_called_once()
        assert client.chat_postMessage.call_count == 2
        first = client.chat_postMessage.call_args_list[0].kwargs
        second = client.chat_postMessage.call_args_list[1].kwargs

        assert first["thread_ts"] == "123.456"
        assert "running follow-up research" in first["text"].lower()
        assert second["thread_ts"] == "123.456"
        assert "Agent Reach source routing" in second["text"]
        assert "Agents: 4/4 returned usable findings" in second["text"]
        assert "Source routing decides newsletter quality." in second["text"]
        assert "Suggested next step" in second["text"]
        assert "Next action" not in second["text"]
        assert "Turn into a social angle." in second["text"]
        assert "Reply `cover`, `draft`, `archive`, or `ignore`." in second["text"]
        handler.wait_for_reply.assert_called_once()

    def test_briefing_followup_cover_reply_saves_candidate(self):
        handler, client = self._handler()
        handler.wait_for_reply = MagicMock(return_value="cover")
        result = {
            "status": "completed",
            "degraded": False,
            "findings": [
                {
                    "title": "Agent Reach source routing",
                    "summary": "OpenCLI can cover Reddit while direct X search is degraded.",
                    "source_name": "Dry Run",
                }
            ],
            "why_this_matters": "Source routing decides newsletter quality.",
            "next_action": "Consider this tomorrow.",
            "artifact": "reports/ramsay/followups/example.md",
        }

        with patch(
            "slack_bot.handlers.briefing.run_followup_research",
            return_value=result,
            create=True,
        ), patch(
            "slack_bot.handlers.briefing.open_traces_db",
            create=True,
        ), patch(
            "slack_bot.handlers.followup.apply_followup_action",
            return_value={
                "status": "completed",
                "action": "cover",
                "message": "Saved 1 follow-up finding(s) as next-day coverage candidates for 2026-06-27.",
            },
        ) as apply_action:
            handler.handle({
                "text": "follow up: compare agent-reach and opencli for social search",
                "ts": "123.456",
            })

        apply_action.assert_called_once_with(result, "cover")
        messages = [call.kwargs["text"] for call in client.chat_postMessage.call_args_list]
        assert any("next-day coverage candidates" in message for message in messages)

    def test_briefing_rejects_vague_followup_without_running_service(self):
        handler, client = self._handler()

        with patch(
            "slack_bot.handlers.briefing.run_followup_research",
            create=True,
        ) as run_followup:
            handler.handle({"text": "follow up: more", "ts": "123.456"})

        run_followup.assert_not_called()
        client.chat_postMessage.assert_called_once()
        kwargs = client.chat_postMessage.call_args.kwargs
        assert kwargs["thread_ts"] == "123.456"
        assert "specific" in kwargs["text"].lower()

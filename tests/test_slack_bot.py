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

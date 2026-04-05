"""Tests for Slack bot resilience: API error handling, reply timeout defaults.

Tests use AST parsing and mock-based validation so slack_sdk is not required
in the test environment.
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SLACK_BOT_DIR = Path(__file__).parent.parent / "slack_bot"


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

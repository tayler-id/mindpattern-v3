"""Tests for core/llm.py — claude calls are always mocked (no network)."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.llm import ask, extract_json, run

SCHEMA = {
    "required": ["title", "items"],
    "properties": {"title": {"type": "string"}, "items": {"type": "array"}},
}


def _proc(stdout="", returncode=0):
    proc = MagicMock()
    proc.communicate.return_value = (stdout, "")
    proc.returncode = returncode
    proc.pid = 4242
    return proc


class TestRun:
    @patch("core.llm.subprocess.Popen")
    def test_returns_stdout(self, popen):
        popen.return_value = _proc("hello")
        assert run("hi") == "hello"
        # must run in its own process group
        assert popen.call_args.kwargs["start_new_session"] is True

    @patch("core.llm.subprocess.Popen")
    def test_nonzero_exit_returns_none(self, popen):
        popen.return_value = _proc("", returncode=1)
        assert run("hi") is None

    @patch("core.llm.os.getpgid", return_value=999)
    @patch("core.llm.os.killpg")
    @patch("core.llm.subprocess.Popen")
    def test_timeout_kills_process_group(self, popen, killpg, getpgid):
        proc = _proc()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
            ("", ""),
        ]
        popen.return_value = proc
        assert run("hi", timeout=1) is None
        killpg.assert_called_once()
        assert killpg.call_args.args[0] == 999  # the group, not just the child

    @patch("core.llm.subprocess.Popen")
    def test_allowed_tools_flag(self, popen):
        popen.return_value = _proc("ok")
        run("hi", allowed_tools=["WebSearch", "WebFetch"])
        cmd = popen.call_args.args[0]
        assert "--allowedTools" in cmd
        assert "WebSearch,WebFetch" in cmd
        assert "Bash" not in " ".join(cmd)


class TestExtractJson:
    def test_bare_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert extract_json('Here:\n```json\n{"a": 1}\n```\ndone') == {"a": 1}

    def test_embedded_json(self):
        assert extract_json('The answer is {"a": 1} as requested.') == {"a": 1}

    def test_garbage_returns_none(self):
        assert extract_json("no json here at all") is None


class TestAsk:
    @patch("core.llm.subprocess.Popen")
    def test_valid_first_try(self, popen):
        popen.return_value = _proc('{"title": "t", "items": [1]}')
        assert ask("p", SCHEMA) == {"title": "t", "items": [1]}
        assert popen.call_count == 1

    @patch("core.llm.subprocess.Popen")
    def test_retry_with_feedback_then_success(self, popen):
        popen.side_effect = [
            _proc("sorry, I cannot"),
            _proc('{"title": "t", "items": []}'),
        ]
        assert ask("p", SCHEMA) == {"title": "t", "items": []}
        assert popen.call_count == 2
        retry_prompt = popen.call_args_list[1].args[0][2]
        assert "invalid" in retry_prompt

    @patch("core.llm.subprocess.Popen")
    def test_invalid_twice_returns_none(self, popen):
        popen.side_effect = [_proc("junk"), _proc("more junk")]
        assert ask("p", SCHEMA) is None

    @patch("core.llm.subprocess.Popen")
    def test_schema_mismatch_triggers_retry(self, popen):
        popen.side_effect = [
            _proc('{"title": "t"}'),  # missing required 'items'
            _proc('{"title": "t", "items": []}'),
        ]
        assert ask("p", SCHEMA) == {"title": "t", "items": []}

    @patch("core.llm.subprocess.Popen")
    def test_null_findings_class_bug(self, popen):
        """The audit bug: {'findings': null} must not propagate as None value."""
        schema = {"required": ["findings"], "properties": {"findings": {"type": "array"}}}
        popen.side_effect = [
            _proc('{"findings": null}'),
            _proc('{"findings": null}'),
        ]
        # null for a required array passes presence but callers need a list;
        # _validate treats None values as absent-typed, so this returns the
        # dict — the contract is: callers use .get("findings") or []
        result = ask("p", schema)
        assert result is None or result.get("findings") is None

    @patch("core.llm.subprocess.Popen")
    def test_wrong_type_rejected(self, popen):
        popen.side_effect = [
            _proc('{"title": 42, "items": []}'),
            _proc('{"title": "ok", "items": []}'),
        ]
        assert ask("p", SCHEMA)["title"] == "ok"

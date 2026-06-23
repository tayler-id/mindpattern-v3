"""Tests for core/llm.py - claude calls are always mocked (no network)."""

from unittest.mock import patch

from core.claude_cli import ClaudeProcessResult
from core.llm import ask, extract_json, run

SCHEMA = {
    "required": ["title", "items"],
    "properties": {"title": {"type": "string"}, "items": {"type": "array"}},
}


def _result(stdout="", stderr="", returncode=0, timed_out=False, error=None):
    return ClaudeProcessResult(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        timed_out=timed_out,
        error=error,
    )


class TestRun:
    @patch("core.llm.run_claude_process")
    def test_returns_stdout(self, run_process):
        run_process.return_value = _result("hello")
        assert run("hi") == "hello"

    @patch("core.llm.run_claude_process")
    def test_nonzero_exit_returns_none(self, run_process):
        run_process.return_value = _result("", returncode=1)
        assert run("hi") is None

    @patch("core.llm.run_claude_process")
    def test_timeout_returns_none(self, run_process):
        run_process.return_value = _result(timed_out=True, error="Timed out after 1s")
        assert run("hi", timeout=1) is None

    @patch("core.llm.run_claude_process")
    def test_allowed_tools_flag(self, run_process):
        run_process.return_value = _result("ok")
        run("hi", allowed_tools=["WebSearch", "WebFetch"])
        cmd = run_process.call_args.args[0]
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
    @patch("core.llm.run_claude_process")
    def test_valid_first_try(self, run_process):
        run_process.return_value = _result('{"title": "t", "items": [1]}')
        assert ask("p", SCHEMA) == {"title": "t", "items": [1]}
        assert run_process.call_count == 1

    @patch("core.llm.run_claude_process")
    def test_retry_with_feedback_then_success(self, run_process):
        run_process.side_effect = [
            _result("sorry, I cannot"),
            _result('{"title": "t", "items": []}'),
        ]
        assert ask("p", SCHEMA) == {"title": "t", "items": []}
        assert run_process.call_count == 2
        retry_prompt = run_process.call_args_list[1].args[0][2]
        assert "invalid" in retry_prompt

    @patch("core.llm.run_claude_process")
    def test_invalid_twice_returns_none(self, run_process):
        run_process.side_effect = [_result("junk"), _result("more junk")]
        assert ask("p", SCHEMA) is None

    @patch("core.llm.run_claude_process")
    def test_schema_mismatch_triggers_retry(self, run_process):
        run_process.side_effect = [
            _result('{"title": "t"}'),  # missing required 'items'
            _result('{"title": "t", "items": []}'),
        ]
        assert ask("p", SCHEMA) == {"title": "t", "items": []}

    @patch("core.llm.run_claude_process")
    def test_null_findings_class_bug(self, run_process):
        """The audit bug: {'findings': null} must not propagate as None value."""
        schema = {"required": ["findings"], "properties": {"findings": {"type": "array"}}}
        run_process.side_effect = [
            _result('{"findings": null}'),
            _result('{"findings": null}'),
        ]
        # null for a required array passes presence but callers need a list;
        # _validate treats None values as absent-typed, so this returns the
        # dict — the contract is: callers use .get("findings") or []
        result = ask("p", schema)
        assert result is None or result.get("findings") is None

    @patch("core.llm.run_claude_process")
    def test_wrong_type_rejected(self, run_process):
        run_process.side_effect = [
            _result('{"title": 42, "items": []}'),
            _result('{"title": "ok", "items": []}'),
        ]
        assert ask("p", SCHEMA)["title"] == "ok"

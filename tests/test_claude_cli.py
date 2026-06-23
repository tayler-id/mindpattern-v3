"""Tests for the shared Claude CLI process primitive."""

import subprocess
from unittest.mock import MagicMock, patch

from core.claude_cli import run_claude_process


def _proc(stdout="", stderr="", returncode=0):
    proc = MagicMock()
    proc.communicate.return_value = (stdout, stderr)
    proc.returncode = returncode
    proc.pid = 4242
    return proc


class TestRunClaudeProcess:
    @patch("core.claude_cli.subprocess.Popen")
    def test_returns_process_result(self, popen):
        popen.return_value = _proc(stdout="hello", stderr="warn", returncode=7)

        result = run_claude_process(["claude", "-p", "hi"], timeout=30)

        assert result.stdout == "hello"
        assert result.stderr == "warn"
        assert result.returncode == 7
        assert result.timed_out is False
        assert result.error is None
        assert popen.call_args.kwargs["start_new_session"] is True

    @patch("core.claude_cli.subprocess.Popen")
    def test_passes_stdin_text(self, popen):
        proc = _proc(stdout="ok")
        popen.return_value = proc

        result = run_claude_process(
            ["claude", "-p", "-"],
            timeout=30,
            input_text="large prompt",
        )

        assert result.returncode == 0
        assert popen.call_args.kwargs["stdin"] == subprocess.PIPE
        assert proc.communicate.call_args.kwargs["input"] == "large prompt"

    @patch("core.claude_cli.os.getpgid", return_value=999)
    @patch("core.claude_cli.os.killpg")
    @patch("core.claude_cli.subprocess.Popen")
    def test_timeout_kills_process_group(self, popen, killpg, _getpgid):
        proc = _proc()
        proc.communicate.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"], timeout=1
        )
        popen.return_value = proc

        result = run_claude_process(["claude", "-p", "hi"], timeout=1)

        assert result.stdout == ""
        assert result.stderr == ""
        assert result.returncode == 1
        assert result.timed_out is True
        assert result.error == "Timed out after 1s"
        killpg.assert_called_once()
        assert killpg.call_args.args[0] == 999

    @patch("core.claude_cli.subprocess.Popen")
    def test_startup_error_returns_result(self, popen):
        popen.side_effect = OSError("missing claude")

        result = run_claude_process(["claude", "-p", "hi"], timeout=30)

        assert result.returncode == 1
        assert result.timed_out is False
        assert "missing claude" in result.error

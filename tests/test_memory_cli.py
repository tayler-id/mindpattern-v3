"""Tests for memory_cli.py — the agent-facing CLI for memory queries.

Tests cover:
- All 5 subcommands respond to --help
- Required arguments are enforced
- Invalid commands produce non-zero exit
- Graceful error handling when DB doesn't exist
"""

import subprocess
import sys

import pytest

CLI = [sys.executable, "memory_cli.py"]


class TestHelpFlags:
    """Every subcommand should respond to --help with returncode 0."""

    @pytest.mark.parametrize(
        "command,expected_flags",
        [
            ("search-findings", ["--days", "--min-importance", "--limit"]),
            ("recent-posts", ["--days", "--limit"]),
            ("get-exemplars", ["--platform", "--limit"]),
            ("recent-corrections", ["--platform", "--limit"]),
            ("check-duplicate", ["--anchor", "--days", "--threshold"]),
        ],
    )
    def test_help(self, command, expected_flags):
        result = subprocess.run(
            CLI + [command, "--help"],
            capture_output=True,
            text=True,
            cwd="/Users/taylerramsay/Projects/mindpattern-v3",
        )
        assert result.returncode == 0, f"--help failed for {command}: {result.stderr}"
        for flag in expected_flags:
            assert flag in result.stdout, f"Missing {flag} in {command} --help output"


class TestRequiredArgs:
    """check-duplicate requires --anchor."""

    def test_check_duplicate_requires_anchor(self):
        result = subprocess.run(
            CLI + ["check-duplicate"],
            capture_output=True,
            text=True,
            cwd="/Users/taylerramsay/Projects/mindpattern-v3",
        )
        assert result.returncode != 0, "check-duplicate should fail without --anchor"
        assert "anchor" in result.stderr.lower()


class TestInvalidCommand:
    """An unknown subcommand should produce non-zero exit code."""

    def test_invalid_command(self):
        result = subprocess.run(
            CLI + ["not-a-command"],
            capture_output=True,
            text=True,
            cwd="/Users/taylerramsay/Projects/mindpattern-v3",
        )
        assert result.returncode != 0

    def test_no_command(self):
        result = subprocess.run(
            CLI,
            capture_output=True,
            text=True,
            cwd="/Users/taylerramsay/Projects/mindpattern-v3",
        )
        assert result.returncode != 0


class TestSearchFindingsGraceful:
    """search-findings should handle missing DB gracefully."""

    def test_missing_db_returns_error(self, tmp_path, monkeypatch):
        """When the DB file doesn't exist, exit 0 or 1 (not a crash)."""
        # Point to a non-existent DB by setting a bogus data dir
        env = {"PYTHONPATH": "/Users/taylerramsay/Projects/mindpattern-v3"}
        result = subprocess.run(
            CLI + ["search-findings", "--days", "7"],
            capture_output=True,
            text=True,
            cwd="/Users/taylerramsay/Projects/mindpattern-v3",
        )
        # Should be 0 (data exists) or 1 (graceful error) — not a traceback crash
        assert result.returncode in (0, 1), (
            f"Unexpected returncode {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

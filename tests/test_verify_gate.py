"""Tests for the /verify extension of harness/gates.py."""

import subprocess

import pytest

from harness.gates import (
    _verify_env,
    format_truth_table,
    gate_repro_flips,
    run_verify,
)
from harness.sandbox import GUARD_ENV

# The repro: passes only when flag.txt says "fixed".
REPRO = (
    "python3 -c \"import sys; "
    "sys.exit(0 if open('flag.txt').read().strip() == 'fixed' else 1)\""
)


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


@pytest.fixture
def buggy_repo(tmp_path):
    """A repo whose main commit has the bug and whose tree has the fix."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "flag.txt").write_text("bug\n")
    _git(repo, "add", "flag.txt")
    _git(repo, "commit", "-m", "base with bug")
    (repo / "flag.txt").write_text("fixed\n")  # uncommitted fix
    return repo


class TestGateReproFlips:
    def test_fail_pre_pass_post_is_a_pass(self, buggy_repo):
        result = gate_repro_flips(REPRO, base_ref="main", cwd=str(buggy_repo))
        assert result["pass"], result
        assert result["pre_exit"] != 0
        assert result["post_exit"] == 0

    def test_repro_passing_on_base_fails_the_gate(self, buggy_repo):
        _git(buggy_repo, "add", "flag.txt")
        _git(buggy_repo, "commit", "-m", "fix committed to base")
        result = gate_repro_flips(REPRO, base_ref="main", cwd=str(buggy_repo))
        assert not result["pass"]
        assert any("pre-fix" in f for f in result["failures"])

    def test_repro_failing_post_fix_fails_the_gate(self, buggy_repo):
        (buggy_repo / "flag.txt").write_text("still broken\n")
        result = gate_repro_flips(REPRO, base_ref="main", cwd=str(buggy_repo))
        assert not result["pass"]
        assert any("post-fix" in f for f in result["failures"])

    def test_bad_base_ref_fails_cleanly(self, buggy_repo):
        result = gate_repro_flips(REPRO, base_ref="no-such-ref", cwd=str(buggy_repo))
        assert not result["pass"]
        assert any("worktree" in f for f in result["failures"])

    @pytest.mark.parametrize("hostile_ref", [
        'main"; touch pwned; "',
        "main$(touch pwned)",
        "-upload-pack=touch pwned",
        "main; rm -rf .",
        "",
    ])
    def test_hostile_base_ref_rejected_before_any_command(self, buggy_repo, hostile_ref):
        """Audit I-18: agent-influenced strings must not alter command structure."""
        result = gate_repro_flips(REPRO, base_ref=hostile_ref, cwd=str(buggy_repo))
        assert not result["pass"]
        assert any("rejected" in f for f in result["failures"])
        assert not (buggy_repo / "pwned").exists()

    def test_no_worktree_left_behind(self, buggy_repo):
        gate_repro_flips(REPRO, base_ref="main", cwd=str(buggy_repo))
        listed = subprocess.run(
            ["git", "worktree", "list"], cwd=buggy_repo,
            capture_output=True, text=True,
        ).stdout
        assert "mp-verify-" not in listed


class TestVerifyEnv:
    def test_repro_env_carries_sandbox_guards(self):
        env = _verify_env()
        for key, value in GUARD_ENV.items():
            assert env[key] == value


class TestTruthTable:
    def test_rows_render_in_contract_format(self):
        table = format_truth_table([
            {"input": "empty feed, 0 items", "expected": "skip",
             "pre": "CRASH", "post": "skip"},
        ])
        assert "| # | Input / state | Expected | Pre-fix | Post-fix |" in table
        assert "| 1 | empty feed, 0 items | skip | CRASH | skip |" in table

    def test_empty_rows_render_empty(self):
        assert format_truth_table([]) == ""


class TestRunVerify:
    def test_bundle_passes_with_flip_and_table(self, buggy_repo):
        result = run_verify(
            REPRO,
            truth_rows=[{"input": "flag=bug", "expected": "exit 0",
                         "pre": "exit 1", "post": "exit 0"}],
            base_ref="main",
            cwd=str(buggy_repo),
            graphify=False,
        )
        assert result["pass"], result
        assert "Pre-fix" in result["results"]["truth_table"]
        assert result["results"]["graphify"]["skipped"] is True

    def test_bundle_fails_when_repro_does_not_flip(self, buggy_repo):
        (buggy_repo / "flag.txt").write_text("still broken\n")
        result = run_verify(REPRO, base_ref="main", cwd=str(buggy_repo), graphify=False)
        assert not result["pass"]

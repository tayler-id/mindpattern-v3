"""Tests for harness/sandbox.py — fail-closed side-effect isolation."""

import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harness.sandbox import (
    GUARD_ENV,
    Budget,
    SandboxNotActive,
    SandboxViolation,
    assert_sandbox,
    is_violation,
    sandbox,
    sandbox_active,
)


@pytest.fixture(autouse=True)
def clean_guard_env(monkeypatch):
    """Every test starts outside a sandbox."""
    for key in GUARD_ENV:
        monkeypatch.delenv(key, raising=False)


class TestSandboxEnv:
    def test_guard_env_set_inside_and_restored_after(self):
        assert not sandbox_active()
        with sandbox():
            for key, value in GUARD_ENV.items():
                assert os.environ.get(key) == value
        for key in GUARD_ENV:
            assert key not in os.environ

    def test_preexisting_values_restored_exactly(self, monkeypatch):
        monkeypatch.setenv("MP_DRY_RUN", "0")
        with sandbox():
            assert os.environ["MP_DRY_RUN"] == "1"
        assert os.environ["MP_DRY_RUN"] == "0"

    def test_env_restored_after_exception(self):
        with pytest.raises(ValueError):
            with sandbox():
                raise ValueError("routine crashed")
        for key in GUARD_ENV:
            assert key not in os.environ

    def test_assert_sandbox_raises_outside(self):
        with pytest.raises(SandboxNotActive):
            assert_sandbox()

    def test_assert_sandbox_passes_inside(self):
        with sandbox():
            assert_sandbox()

    def test_assert_sandbox_rejects_partial_isolation(self, monkeypatch):
        monkeypatch.setenv("MP_SANDBOX", "1")  # flag up, kill switches missing
        with pytest.raises(SandboxNotActive):
            assert_sandbox()


class TestSandboxDatabases:
    def test_databases_copied_with_content(self, tmp_path):
        data_dir = tmp_path / "ramsay"
        data_dir.mkdir()
        conn = sqlite3.connect(data_dir / "memory.db")
        conn.execute("CREATE TABLE findings (id INTEGER PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO findings (title) VALUES ('real row')")
        conn.commit()
        conn.close()

        with sandbox(data_dir=data_dir) as box:
            assert box.memory_db != data_dir / "memory.db"
            copy = sqlite3.connect(box.memory_db)
            rows = copy.execute("SELECT title FROM findings").fetchall()
            copy.close()
            assert rows == [("real row",)]

    def test_missing_source_yields_empty_valid_db(self, tmp_path):
        with sandbox(data_dir=tmp_path) as box:
            conn = sqlite3.connect(box.traces_db)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()
            assert tables == []

    def test_writes_to_copy_never_touch_source(self, tmp_path):
        data_dir = tmp_path / "ramsay"
        data_dir.mkdir()
        conn = sqlite3.connect(data_dir / "memory.db")
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.commit()
        conn.close()

        with sandbox(data_dir=data_dir) as box:
            copy = sqlite3.connect(box.memory_db)
            copy.execute("INSERT INTO t (v) VALUES ('sandbox write')")
            copy.commit()
            copy.close()

        source = sqlite3.connect(data_dir / "memory.db")
        rows = source.execute("SELECT v FROM t").fetchall()
        source.close()
        assert rows == []


class TestBudget:
    def test_charge_within_budget(self):
        budget = Budget(max_claude_calls=3)
        budget.charge()
        budget.charge(2)
        assert budget.remaining() == 0

    def test_exceeding_budget_raises_before_spending(self):
        budget = Budget(max_claude_calls=2)
        budget.charge(2)
        with pytest.raises(SandboxViolation):
            budget.charge()
        assert budget.spent == 2

    def test_sandbox_carries_budget(self):
        with sandbox(max_claude_calls=5) as box:
            box.budget.charge(5)
            with pytest.raises(SandboxViolation):
                box.budget.charge()


class TestIsViolation:
    def test_sandbox_violation_instance(self):
        assert is_violation(SandboxViolation("over budget"))

    def test_inline_guard_message_form(self):
        assert is_violation(RuntimeError("MP_SANDBOX=1: refusing Fly sync"))

    def test_ordinary_runtime_error_is_not(self):
        assert not is_violation(RuntimeError("connection refused"))


class TestBoundaryGuards:
    """The dependency-free guards at each outbound boundary."""

    def test_newsletter_send_refused(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MP_SANDBOX", "1")
        from orchestrator.newsletter import send_newsletter

        report = tmp_path / "2026-08-14.md"
        report.write_text("# report")
        with pytest.raises(RuntimeError) as excinfo:
            send_newsletter(report, {"email": "x@example.com"}, "2026-08-14")
        assert is_violation(excinfo.value)

    def test_social_api_call_refused(self, monkeypatch):
        monkeypatch.setenv("MP_SANDBOX", "1")
        from social.posting import _api_call_with_retry

        with pytest.raises(RuntimeError) as excinfo:
            _api_call_with_retry(MagicMock(), "POST", "https://example.com/api")
        assert is_violation(excinfo.value)

    def test_social_api_call_proceeds_outside_sandbox(self):
        from social.posting import _api_call_with_retry

        session = MagicMock()
        session.request.return_value = MagicMock(status_code=200)
        resp = _api_call_with_retry(session, "GET", "https://example.com/api")
        assert resp.status_code == 200

    @pytest.mark.parametrize("call", [
        lambda sync: sync.upload_bundle_http(Path("/nonexistent"), user_id="ramsay"),
        lambda sync: sync.sync_to_fly("ramsay", Path("/nonexistent")),
        lambda sync: sync.restart_app("mindpattern"),
        lambda sync: sync._fly_ssh("mindpattern", "ls"),
        lambda sync: sync._fly_sftp_put("mindpattern", "/a", "/b"),
    ])
    def test_fly_boundaries_refused(self, monkeypatch, call):
        monkeypatch.setenv("MP_SANDBOX", "1")
        from orchestrator import sync

        with pytest.raises(RuntimeError) as excinfo:
            call(sync)
        assert is_violation(excinfo.value)

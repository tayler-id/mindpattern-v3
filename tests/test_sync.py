"""Tests for orchestrator/sync.py — Fly.io synchronization.

All subprocess calls are mocked. No real flyctl or sqlite3 CLI invocations.
"""

import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from orchestrator.sync import (
    _fly_sftp_put,
    _fly_ssh,
    _wal_checkpoint,
    create_bundle,
    restart_app,
    sync_to_fly,
    upload_bundle,
)

# ────────────────────────────────────────────────────────────────────────
# FIXTURES
# ────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def data_tree(tmp_path):
    """Create a realistic data/reports directory tree.

    Returns dict with keys: data_dir, reports_dir, db_path, traces_path, user_id.
    """
    user_id = "testuser"
    data_dir = tmp_path / "data"
    db_dir = data_dir / user_id
    db_dir.mkdir(parents=True)

    reports_dir = tmp_path / "reports" / user_id
    reports_dir.mkdir(parents=True)
    agents_dir = reports_dir / "agents"
    agents_dir.mkdir()

    # Create a minimal SQLite database file (just bytes, we mock the CLI)
    db_path = db_dir / "memory.db"
    db_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)

    traces_path = db_dir / "traces.db"
    traces_path.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)

    # Create report files
    (reports_dir / "2026-03-14.md").write_text("# Report 2026-03-14\n\nContent.\n")
    (reports_dir / "2026-03-15.md").write_text("# Report 2026-03-15\n\nContent.\n")
    (agents_dir / "agent-ai.md").write_text("# Agent AI\n\nFindings.\n")
    (agents_dir / "agent-web.md").write_text("# Agent Web\n\nFindings.\n")

    return {
        "data_dir": data_dir,
        "reports_dir": reports_dir,
        "db_path": db_path,
        "traces_path": traces_path,
        "user_id": user_id,
        "tmp_path": tmp_path,
    }


# ────────────────────────────────────────────────────────────────────────
# _wal_checkpoint()
# ────────────────────────────────────────────────────────────────────────


class TestWalCheckpoint:
    """Tests for _wal_checkpoint()."""

    @patch("orchestrator.sync.subprocess.run")
    def test_success_returns_success_dict(self, mock_run):
        """Successful checkpoint returns {success: True, error: None}."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="0|0|0", stderr=""
        )
        result = _wal_checkpoint(Path("/fake/memory.db"))

        assert result == {"success": True, "error": None}
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "sqlite3"
        assert "/fake/memory.db" in cmd[1]
        assert "PRAGMA wal_checkpoint(TRUNCATE);" in cmd[2]

    @patch("orchestrator.sync.subprocess.run")
    def test_nonzero_return_code(self, mock_run):
        """Non-zero return code returns {success: False} with stderr."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="database is locked"
        )
        result = _wal_checkpoint(Path("/fake/memory.db"))

        assert result["success"] is False
        assert "database is locked" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sqlite3", timeout=30))
    def test_timeout_returns_error(self, mock_run):
        """Timeout returns {success: False} with error message."""
        result = _wal_checkpoint(Path("/fake/memory.db"))

        assert result["success"] is False
        assert result["error"] is not None

    @patch("orchestrator.sync.subprocess.run", side_effect=FileNotFoundError("sqlite3 not found"))
    def test_missing_sqlite3_binary(self, mock_run):
        """FileNotFoundError when sqlite3 is missing returns graceful error."""
        result = _wal_checkpoint(Path("/fake/memory.db"))

        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=OSError("Permission denied"))
    def test_os_error(self, mock_run):
        """OSError returns {success: False} with error string."""
        result = _wal_checkpoint(Path("/fake/memory.db"))

        assert result["success"] is False
        assert "Permission denied" in result["error"]


# ────────────────────────────────────────────────────────────────────────
# create_bundle()
# ────────────────────────────────────────────────────────────────────────


class TestCreateBundle:
    """Tests for create_bundle()."""

    def test_bundle_created_with_all_files(self, data_tree):
        """Bundle contains memory.db, traces.db, reports, and agent reports."""
        bundle = create_bundle(
            data_tree["user_id"],
            data_tree["data_dir"],
            data_tree["reports_dir"],
            "2026-03-14",
        )

        assert bundle.exists()
        assert bundle.stat().st_size > 0

        with tarfile.open(bundle, "r:gz") as tf:
            names = sorted(tf.getnames())

        user = data_tree["user_id"]
        assert f"{user}/memory.db" in names
        assert f"{user}/traces.db" in names
        assert f"reports/{user}/2026-03-14.md" in names
        assert f"reports/{user}/2026-03-15.md" in names
        assert f"reports/{user}/agents/agent-ai.md" in names
        assert f"reports/{user}/agents/agent-web.md" in names
        assert len(names) == 6

        bundle.unlink()

    def test_bundle_without_traces_db(self, data_tree):
        """Bundle works when traces.db does not exist."""
        data_tree["traces_path"].unlink()

        bundle = create_bundle(
            data_tree["user_id"],
            data_tree["data_dir"],
            data_tree["reports_dir"],
            "2026-03-14",
        )

        with tarfile.open(bundle, "r:gz") as tf:
            names = tf.getnames()

        user = data_tree["user_id"]
        assert f"{user}/memory.db" in names
        assert f"{user}/traces.db" not in names

        bundle.unlink()

    def test_bundle_with_missing_reports_dir(self, data_tree):
        """Bundle works when reports directory does not exist."""
        bundle = create_bundle(
            data_tree["user_id"],
            data_tree["data_dir"],
            data_tree["tmp_path"] / "nonexistent-reports",
            "2026-03-14",
        )

        with tarfile.open(bundle, "r:gz") as tf:
            names = tf.getnames()

        # Only DBs, no reports
        assert len(names) == 2
        bundle.unlink()

    def test_bundle_with_no_agents_subdir(self, data_tree):
        """Bundle works when agents/ subdirectory does not exist."""
        import shutil
        shutil.rmtree(data_tree["reports_dir"] / "agents")

        bundle = create_bundle(
            data_tree["user_id"],
            data_tree["data_dir"],
            data_tree["reports_dir"],
            "2026-03-14",
        )

        with tarfile.open(bundle, "r:gz") as tf:
            names = tf.getnames()

        # DBs + date reports, no agent reports
        assert not any("agents/" in n for n in names)
        bundle.unlink()

    def test_bundle_arcname_structure(self, data_tree):
        """Archive paths mirror remote /data/ layout."""
        bundle = create_bundle(
            data_tree["user_id"],
            data_tree["data_dir"],
            data_tree["reports_dir"],
            "2026-03-14",
        )

        with tarfile.open(bundle, "r:gz") as tf:
            for name in tf.getnames():
                # All paths should be relative (no leading /)
                assert not name.startswith("/")
                # Paths should start with user_id/ or reports/
                assert name.startswith(data_tree["user_id"] + "/") or name.startswith("reports/")

        bundle.unlink()


# ────────────────────────────────────────────────────────────────────────
# upload_bundle()
# ────────────────────────────────────────────────────────────────────────


class TestUploadBundle:
    """Tests for upload_bundle()."""

    @patch("orchestrator.sync.subprocess.run")
    def test_success_with_bytes_written_in_stdout(self, mock_run, tmp_path):
        """Upload succeeds when stdout contains 'bytes written'."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="1234 bytes written",
            stderr="",
        )
        bundle = tmp_path / "test.tar.gz"
        bundle.write_bytes(b"fake")

        result = upload_bundle(bundle, "/data/test/sync-bundle.tar.gz", "myapp")

        assert result == {"success": True, "error": None}
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["flyctl", "ssh", "sftp", "shell", "-a", "myapp"]
        assert f'put "{bundle}" /data/test/sync-bundle.tar.gz' in mock_run.call_args[1]["input"]

    @patch("orchestrator.sync.subprocess.run")
    def test_success_with_zero_return_code(self, mock_run, tmp_path):
        """Upload succeeds when returncode is 0 even without 'bytes written'."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        bundle = tmp_path / "test.tar.gz"
        bundle.write_bytes(b"fake")

        result = upload_bundle(bundle, "/data/test.tar.gz", "myapp")
        assert result["success"] is True

    @patch("orchestrator.sync.subprocess.run")
    def test_failure_nonzero_return_code(self, mock_run, tmp_path):
        """Upload fails when returncode is non-zero."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout="",
            stderr="connection refused",
        )
        bundle = tmp_path / "test.tar.gz"
        bundle.write_bytes(b"fake")

        result = upload_bundle(bundle, "/data/test.tar.gz", "myapp")
        assert result["success"] is False
        assert "connection refused" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="flyctl", timeout=300))
    def test_timeout_after_5_minutes(self, mock_run, tmp_path):
        """Upload returns timeout error."""
        bundle = tmp_path / "test.tar.gz"
        bundle.write_bytes(b"fake")

        result = upload_bundle(bundle, "/data/test.tar.gz", "myapp")
        assert result["success"] is False
        assert "timed out" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=FileNotFoundError("flyctl"))
    def test_missing_flyctl(self, mock_run, tmp_path):
        """Upload returns helpful error when flyctl is missing."""
        bundle = tmp_path / "test.tar.gz"
        bundle.write_bytes(b"fake")

        result = upload_bundle(bundle, "/data/test.tar.gz", "myapp")
        assert result["success"] is False
        assert "flyctl not found" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=OSError("disk full"))
    def test_os_error(self, mock_run, tmp_path):
        """Upload returns error string on OSError."""
        bundle = tmp_path / "test.tar.gz"
        bundle.write_bytes(b"fake")

        result = upload_bundle(bundle, "/data/test.tar.gz", "myapp")
        assert result["success"] is False
        assert "disk full" in result["error"]


# ────────────────────────────────────────────────────────────────────────
# restart_app()
# ────────────────────────────────────────────────────────────────────────


class TestRestartApp:
    """Tests for restart_app()."""

    @patch("orchestrator.sync.subprocess.run")
    def test_successful_restart(self, mock_run):
        """Restart succeeds: list machines, then restart the first one."""
        machines_json = json.dumps([{"id": "machine-abc123", "state": "started"}])
        list_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=machines_json, stderr=""
        )
        restart_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Restarting", stderr=""
        )
        mock_run.side_effect = [list_result, restart_result]

        result = restart_app("myapp")

        assert result == {"success": True, "error": None}
        assert mock_run.call_count == 2

        # Verify list command
        list_cmd = mock_run.call_args_list[0][0][0]
        assert list_cmd == ["flyctl", "machines", "list", "-a", "myapp", "--json"]

        # Verify restart command
        restart_cmd = mock_run.call_args_list[1][0][0]
        assert restart_cmd == ["flyctl", "machine", "restart", "machine-abc123", "-a", "myapp"]

    @patch("orchestrator.sync.subprocess.run")
    def test_list_machines_failure(self, mock_run):
        """Restart fails when machine list fails."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="auth error"
        )

        result = restart_app("myapp")
        assert result["success"] is False
        assert "Failed to list machines" in result["error"]

    @patch("orchestrator.sync.subprocess.run")
    def test_no_machines_found(self, mock_run):
        """Restart fails when no machines are returned."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="[]", stderr=""
        )

        result = restart_app("myapp")
        assert result["success"] is False
        assert "No machines found" in result["error"]

    @patch("orchestrator.sync.subprocess.run")
    def test_machine_id_missing_in_response(self, mock_run):
        """Restart fails when machine JSON lacks 'id' field."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps([{"state": "started"}]),  # no "id"
            stderr="",
        )

        result = restart_app("myapp")
        assert result["success"] is False
        assert "Machine ID not found" in result["error"]

    @patch("orchestrator.sync.subprocess.run")
    def test_restart_command_fails(self, mock_run):
        """Restart fails when the restart subprocess returns non-zero."""
        list_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps([{"id": "m-1"}]),
            stderr="",
        )
        restart_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="machine not responding"
        )
        mock_run.side_effect = [list_result, restart_result]

        result = restart_app("myapp")
        assert result["success"] is False
        assert "Restart failed" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="flyctl", timeout=60))
    def test_timeout(self, mock_run):
        """Restart returns timeout error."""
        result = restart_app("myapp")
        assert result["success"] is False
        assert "timed out" in result["error"]

    @patch("orchestrator.sync.subprocess.run", side_effect=FileNotFoundError("flyctl"))
    def test_missing_flyctl(self, mock_run):
        """Restart returns error when flyctl is missing."""
        result = restart_app("myapp")
        assert result["success"] is False
        assert "flyctl not found" in result["error"]

    @patch("orchestrator.sync.subprocess.run")
    def test_invalid_json_from_machines_list(self, mock_run):
        """Restart handles invalid JSON from machines list."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not valid json", stderr=""
        )

        result = restart_app("myapp")
        assert result["success"] is False
        assert result["error"] is not None


# ────────────────────────────────────────────────────────────────────────
# sync_to_fly() — integration test
# ────────────────────────────────────────────────────────────────────────


class TestSyncToFly:
    """Integration tests for sync_to_fly() with all subprocess mocked."""

    @patch("orchestrator.sync._fly_sftp_put")
    @patch("orchestrator.sync._fly_ssh")
    @patch("orchestrator.sync.upload_bundle")
    @patch("orchestrator.sync.subprocess.run")
    def test_full_sync_success(self, mock_subprocess, mock_upload, mock_ssh, mock_sftp, data_tree):
        """Full sync flow: checkpoint, bundle, mkdir, upload, extract."""
        # WAL checkpoint succeeds
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        # Upload succeeds
        mock_upload.return_value = {"success": True, "error": None}
        # SSH commands succeed (mkdir, extract)
        mock_ssh.return_value = {"success": True, "output": "", "error": None}

        result = sync_to_fly(
            data_tree["user_id"],
            data_tree["data_dir"],
            app_name="testapp",
        )

        assert result["success"] is True
        assert result["bytes_uploaded"] > 0
        assert result["files_included"] > 0
        assert result["error"] is None

    def test_missing_db_returns_error(self, tmp_path):
        """sync_to_fly fails immediately if memory.db does not exist."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        result = sync_to_fly("nonexistent", data_dir)

        assert result["success"] is False
        assert result["bytes_uploaded"] == 0
        assert "No memory.db" in result["error"]

    @patch("orchestrator.sync._fly_sftp_put")
    @patch("orchestrator.sync._fly_ssh")
    @patch("orchestrator.sync.upload_bundle")
    @patch("orchestrator.sync.subprocess.run")
    def test_upload_failure(self, mock_subprocess, mock_upload, mock_ssh, mock_sftp, data_tree):
        """sync_to_fly returns error when upload fails."""
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        mock_upload.return_value = {"success": False, "error": "connection refused"}
        mock_ssh.return_value = {"success": True, "output": "", "error": None}

        result = sync_to_fly(
            data_tree["user_id"],
            data_tree["data_dir"],
            app_name="testapp",
        )

        assert result["success"] is False
        assert "Upload failed" in result["error"]

    @patch("orchestrator.sync._fly_sftp_put")
    @patch("orchestrator.sync._fly_ssh")
    @patch("orchestrator.sync.upload_bundle")
    @patch("orchestrator.sync.subprocess.run")
    def test_extraction_failure_triggers_fallback(self, mock_subprocess, mock_upload, mock_ssh, mock_sftp, data_tree):
        """When tar extraction fails, sync falls back to direct SFTP uploads."""
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        mock_upload.return_value = {"success": True, "error": None}

        # First SSH call (mkdir) succeeds, second (extract) fails
        mock_ssh.side_effect = [
            {"success": True, "output": "", "error": None},
            {"success": False, "output": "", "error": "tar not found"},
        ]
        mock_sftp.return_value = True

        result = sync_to_fly(
            data_tree["user_id"],
            data_tree["data_dir"],
            app_name="testapp",
        )

        # Still succeeds overall (fallback worked)
        assert result["success"] is True
        # SFTP fallback should have been called for reports + DBs
        assert mock_sftp.call_count > 0

    @patch("orchestrator.sync._fly_sftp_put")
    @patch("orchestrator.sync._fly_ssh")
    @patch("orchestrator.sync.upload_bundle")
    @patch("orchestrator.sync.subprocess.run")
    def test_wal_checkpoint_failure_continues(self, mock_subprocess, mock_upload, mock_ssh, mock_sftp, data_tree):
        """Pipeline continues even when WAL checkpoint fails."""
        # Checkpoint fails
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="db locked"
        )
        mock_upload.return_value = {"success": True, "error": None}
        mock_ssh.return_value = {"success": True, "output": "", "error": None}

        result = sync_to_fly(
            data_tree["user_id"],
            data_tree["data_dir"],
            app_name="testapp",
        )

        # Should succeed despite checkpoint failure
        assert result["success"] is True

    @patch("orchestrator.sync._fly_sftp_put")
    @patch("orchestrator.sync._fly_ssh")
    @patch("orchestrator.sync.upload_bundle")
    @patch("orchestrator.sync.subprocess.run")
    def test_traces_conn_logging(self, mock_subprocess, mock_upload, mock_ssh, mock_sftp, data_tree):
        """sync_to_fly logs to traces_conn when provided."""
        import sqlite3
        traces_conn = sqlite3.connect(":memory:")
        traces_conn.execute(
            "CREATE TABLE events (pipeline_run_id TEXT, event_type TEXT, payload TEXT)"
        )

        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        mock_upload.return_value = {"success": True, "error": None}
        mock_ssh.return_value = {"success": True, "output": "", "error": None}

        sync_to_fly(
            data_tree["user_id"],
            data_tree["data_dir"],
            app_name="testapp",
            traces_conn=traces_conn,
        )

        row = traces_conn.execute("SELECT * FROM events WHERE event_type = 'fly_sync'").fetchone()
        assert row is not None
        payload = json.loads(row[2])
        assert payload["user_id"] == data_tree["user_id"]
        assert payload["bytes_uploaded"] > 0

        traces_conn.close()

    @patch("orchestrator.sync._fly_sftp_put")
    @patch("orchestrator.sync._fly_ssh")
    @patch("orchestrator.sync.upload_bundle")
    @patch("orchestrator.sync.subprocess.run")
    def test_bundle_cleanup_on_success(self, mock_subprocess, mock_upload, mock_ssh, mock_sftp, data_tree):
        """Local bundle is cleaned up after successful sync."""
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        mock_upload.return_value = {"success": True, "error": None}
        mock_ssh.return_value = {"success": True, "output": "", "error": None}

        # Run sync
        sync_to_fly(data_tree["user_id"], data_tree["data_dir"], app_name="testapp")

        # No lingering tar.gz files in temp
        import glob
        leftover = glob.glob(f"/tmp/sync-{data_tree['user_id']}-*.tar.gz")
        # The bundle should have been cleaned up
        assert len(leftover) == 0


# ────────────────────────────────────────────────────────────────────────
# _fly_ssh() helper
# ────────────────────────────────────────────────────────────────────────


class TestFlySsh:
    """Tests for _fly_ssh() helper."""

    @patch("orchestrator.sync.subprocess.run")
    def test_wraps_command_in_sh_c(self, mock_run):
        """_fly_ssh wraps the command in sh -c for shell builtins."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr=""
        )

        result = _fly_ssh("myapp", "cd /data && ls")

        assert result["success"] is True
        cmd = mock_run.call_args[0][0]
        assert "flyctl" in cmd[0]
        assert "ssh" in cmd
        assert "console" in cmd
        # The -C argument should contain sh -c
        c_index = cmd.index("-C")
        wrapped = cmd[c_index + 1]
        assert wrapped.startswith("sh -c '")
        assert "cd /data && ls" in wrapped

    @patch("orchestrator.sync.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="flyctl", timeout=60))
    def test_timeout(self, mock_run):
        """_fly_ssh returns error on timeout."""
        result = _fly_ssh("myapp", "sleep 999")
        assert result["success"] is False
        assert "timed out" in result["error"]


# ────────────────────────────────────────────────────────────────────────
# _fly_sftp_put() helper
# ────────────────────────────────────────────────────────────────────────


class TestFlySftpPut:
    """Tests for _fly_sftp_put() helper."""

    @patch("orchestrator.sync.subprocess.run")
    def test_success(self, mock_run):
        """Returns True on successful SFTP put."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        result = _fly_sftp_put("myapp", "/local/file.db", "/remote/file.db")
        assert result is True

    @patch("orchestrator.sync.subprocess.run")
    def test_failure(self, mock_run):
        """Returns False on failed SFTP put."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )

        result = _fly_sftp_put("myapp", "/local/file.db", "/remote/file.db")
        assert result is False

    @patch("orchestrator.sync.subprocess.run", side_effect=Exception("network error"))
    def test_exception_returns_false(self, mock_run):
        """Returns False on exception."""
        result = _fly_sftp_put("myapp", "/local/file.db", "/remote/file.db")
        assert result is False

"""M0 Task 16 — safe sync.

Databases are snapshotted via the SQLite backup API (not live-file tar),
stale -wal/-shm sidecars are removed on Fly in the same remote command as
extraction, and the app restarts after a successful sync.
"""

import sqlite3
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.sync import _snapshot_db, create_bundle, sync_to_fly

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def wal_db(tmp_path):
    """A WAL-mode database with committed rows still sitting in the WAL."""
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE findings (id INTEGER PRIMARY KEY, title TEXT)")
    for i in range(50):
        conn.execute("INSERT INTO findings (title) VALUES (?)", (f"finding {i}",))
    conn.commit()
    # No checkpoint, connection stays open: rows live in the -wal file.
    yield db_path, conn
    conn.close()


class TestSnapshotDb:
    def test_snapshot_captures_wal_content(self, wal_db, tmp_path):
        """A raw file copy would miss WAL-resident rows; backup() must not."""
        db_path, _writer = wal_db
        snap = tmp_path / "snap.db"

        _snapshot_db(db_path, snap)

        conn = sqlite3.connect(snap)
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        assert count == 50
        assert integrity == "ok"

    def test_snapshot_consistent_while_writer_open(self, wal_db, tmp_path):
        """Snapshot taken while a writer holds the db is a valid database."""
        db_path, writer = wal_db
        writer.execute("INSERT INTO findings (title) VALUES ('mid-write')")
        # Uncommitted — must not appear in the snapshot
        snap = tmp_path / "snap.db"

        _snapshot_db(db_path, snap)

        conn = sqlite3.connect(snap)
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        conn.close()
        assert count == 50  # committed state only

    def test_bundle_contains_valid_snapshot(self, wal_db, tmp_path):
        db_path, _writer = wal_db
        user_dir = tmp_path / "data" / "u1"
        user_dir.mkdir(parents=True)
        (tmp_path / "reports" / "u1").mkdir(parents=True)
        # Place the WAL db as the user's memory.db
        _snapshot_db(db_path, user_dir / "memory.db")  # seed
        conn = sqlite3.connect(user_dir / "memory.db")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO findings (title) VALUES ('extra')")
        conn.commit()

        bundle = create_bundle(
            "u1", tmp_path / "data", tmp_path / "reports" / "u1", "2026-06-11"
        )
        conn.close()

        with tarfile.open(bundle, "r:gz") as tf:
            member = tf.extractfile("u1/memory.db")
            extracted = tmp_path / "extracted.db"
            extracted.write_bytes(member.read())
        check = sqlite3.connect(extracted)
        count = check.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        assert count == 51
        check.close()
        bundle.unlink(missing_ok=True)


class TestStaleSidecarRemoval:
    def test_extraction_removes_wal_shm_in_same_command(self, tmp_path):
        """The rm of -wal/-shm must be IN the extraction command — a second
        command can race the dashboard reopening the database."""
        user_id = "u1"
        data_dir = tmp_path / "data"
        (data_dir / user_id).mkdir(parents=True)
        conn = sqlite3.connect(data_dir / user_id / "memory.db")
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        conn.close()
        (tmp_path / "reports" / user_id).mkdir(parents=True)

        commands = []

        def fake_ssh(app, cmd):
            commands.append(cmd)
            if cmd.startswith("wc -c"):
                # Report the true local bundle size so verification passes
                import tempfile as tf_mod

                bundles = sorted(
                    Path(tf_mod.gettempdir()).glob(f"sync-{user_id}-*.tar.gz"),
                    key=lambda p: p.stat().st_mtime,
                )
                size = bundles[-1].stat().st_size if bundles else 0
                return {"success": True, "output": str(size), "error": None}
            return {"success": True, "output": "", "error": None}

        with patch("orchestrator.sync._fly_ssh", side_effect=fake_ssh), \
             patch("orchestrator.sync.upload_bundle",
                   return_value={"success": True, "error": None}), \
             patch("orchestrator.sync._wal_checkpoint",
                   return_value={"success": True, "error": None}):
            sync_to_fly(user_id, data_dir, app_name="testapp")

        extract_cmds = [c for c in commands if "tar xzf" in c]
        assert extract_cmds, f"no extraction command issued: {commands}"
        cmd = extract_cmds[0]
        for sidecar in ("memory.db-wal", "memory.db-shm",
                        "traces.db-wal", "traces.db-shm"):
            assert sidecar in cmd, f"{sidecar} not removed in: {cmd}"


class TestRestartAfterSync:
    def test_runner_calls_restart_app_on_success(self):
        """restart_app existed but was never called (audit sync.py:291)."""
        source = (PROJECT_ROOT / "orchestrator" / "runner.py").read_text()
        phase = source.split("def _phase_sync")[1].split("def _")[1 - 1]
        assert "restart_app(" in phase
        # And it must be gated on success, after sync_to_fly
        assert phase.index("sync_to_fly(") < phase.index("restart_app(")

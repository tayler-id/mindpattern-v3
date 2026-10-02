"""A corrupt memory.db must degrade the dashboard, not kill it.

2026-08-23: an SFTP fallback wrote a truncated memory.db onto the Fly volume.
`get_memory_db` is annotated `Optional[sqlite3.Connection]` and returns None for
a missing file, but its `PRAGMA journal_mode=WAL` raises
`sqlite3.DatabaseError: database disk image is malformed` for a corrupt one.
That escaped every one of its callers, including /healthz, so the health check
500'd, Fly's proxy stopped routing to the machine, and the only safe way to
upload a replacement database was through that same proxy. The site was down
and the repair path was locked behind the thing that was broken.

A data file being unreadable is a degraded state, not a dead process.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def corrupt_db(tmp_path, monkeypatch):
    """Point the dashboard at a user directory holding a malformed db."""
    from dashboard.routes import api as api_mod

    user_dir = tmp_path / "ramsay"
    user_dir.mkdir()
    # A real SQLite header followed by garbage: opens, then fails on first read.
    db = user_dir / "memory.db"
    db.write_bytes(b"SQLite format 3\x00" + b"\xde\xad\xbe\xef" * 4096)

    monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path)
    return db


class TestGetMemoryDb:
    def test_a_corrupt_database_returns_none_instead_of_raising(self, corrupt_db):
        from dashboard.routes import api as api_mod

        assert api_mod.get_memory_db("ramsay") is None

    def test_a_missing_database_still_returns_none(self, tmp_path, monkeypatch):
        from dashboard.routes import api as api_mod

        (tmp_path / "ramsay").mkdir()
        monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path)
        assert api_mod.get_memory_db("ramsay") is None

    def test_a_healthy_database_still_opens(self, tmp_path, monkeypatch):
        """The guard must not swallow a working database."""
        from dashboard.routes import api as api_mod

        user_dir = tmp_path / "ramsay"
        user_dir.mkdir()
        conn = sqlite3.connect(str(user_dir / "memory.db"))
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.commit()
        conn.close()

        monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path)
        opened = api_mod.get_memory_db("ramsay")
        assert opened is not None
        assert opened.execute("SELECT 1").fetchone()[0] == 1
        opened.close()


class TestHealthzSurvivesCorruption:
    def test_healthz_returns_200_degraded_not_500(self, corrupt_db, monkeypatch):
        """Fly stops routing to the machine when this 500s."""
        from dashboard.app import app
        from dashboard.routes import api as api_mod

        monkeypatch.setattr(api_mod, "bot_heartbeat_stale", lambda: False)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/healthz")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["database"] == "unavailable"

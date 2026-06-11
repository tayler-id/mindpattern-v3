"""Tests for core/db.py and core/time.py."""

import re
import sqlite3
from datetime import datetime, timezone

import pytest

from core.db import connect, open_db
from core.time import now_utc, today_utc


class TestConnect:
    def test_wal_mode_enabled(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        conn.close()

    def test_foreign_keys_enabled(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        conn.close()

    def test_row_factory(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        conn.execute("CREATE TABLE x (a TEXT)")
        conn.execute("INSERT INTO x VALUES ('hi')")
        row = conn.execute("SELECT a FROM x").fetchone()
        assert row["a"] == "hi"
        conn.close()

    def test_transaction_rolls_back_on_exception(self, tmp_path):
        """The orphan-row bug class: a failed multi-statement write must
        leave nothing behind."""
        conn = connect(tmp_path / "t.db")
        conn.execute("CREATE TABLE x (a TEXT)")
        conn.commit()
        with pytest.raises(RuntimeError):
            with conn:
                conn.execute("INSERT INTO x VALUES ('orphan')")
                raise RuntimeError("embedding failed")
        assert conn.execute("SELECT COUNT(*) FROM x").fetchone()[0] == 0
        conn.close()

    def test_transaction_commits_on_success(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        conn.execute("CREATE TABLE x (a TEXT)")
        conn.commit()
        with conn:
            conn.execute("INSERT INTO x VALUES ('kept')")
        assert conn.execute("SELECT COUNT(*) FROM x").fetchone()[0] == 1
        conn.close()


class TestOpenDb:
    def test_closes_on_exit(self, tmp_path):
        with open_db(tmp_path / "t.db") as conn:
            conn.execute("CREATE TABLE x (a TEXT)")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_closes_on_exception(self, tmp_path):
        with pytest.raises(ValueError):
            with open_db(tmp_path / "t.db") as conn:
                raise ValueError("boom")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


class TestTime:
    def test_now_utc_format(self):
        ts = now_utc()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", ts)

    def test_now_utc_is_utc(self):
        ts = now_utc()
        parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        delta = abs((datetime.now(timezone.utc) - parsed).total_seconds())
        assert delta < 5

    def test_today_utc_format(self):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", today_utc())

    def test_now_sorts_with_sqlite_format(self, tmp_path):
        """New timestamps must interleave correctly with datetime('now') rows."""
        conn = connect(tmp_path / "t.db")
        conn.execute("CREATE TABLE x (ts TEXT)")
        conn.execute("INSERT INTO x VALUES (datetime('now'))")
        conn.execute("INSERT INTO x VALUES (?)", (now_utc(),))
        rows = [r["ts"] for r in conn.execute("SELECT ts FROM x ORDER BY ts")]
        assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", t) for t in rows)
        conn.close()

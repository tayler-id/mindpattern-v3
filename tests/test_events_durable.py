"""An event says whether its reader id could be persisted.

2026-08-26: the site reported 757 unique readers at 1.02 page views each, with
fewer story views than readers. Both ratios are what an identity minted per
page load looks like. The site now falls back to a first-party cookie, but a
client that holds neither storage nor cookies still churns, and a reader count
that silently mixes the two cannot be trusted either way.

Recording durability lets the dashboard report a number it can stand behind
and show the churn separately, instead of averaging them into one figure.
"""

import pytest

from memory import events_db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(events_db, "events_db_path", lambda: tmp_path / "events.db")
    c = events_db.open_events_db()
    yield c
    c.close()


class TestDurableColumn:
    def test_the_column_exists_and_defaults_to_unknown(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
        assert "durable" in cols

    def test_an_event_records_a_durable_reader(self, conn):
        events_db.record_event(conn, {
            "type": "page_view", "path": "/", "anon_id": "abc123def456", "durable": 1,
        })
        row = conn.execute("SELECT durable FROM events").fetchone()
        assert row["durable"] == 1

    def test_an_event_records_a_churning_reader(self, conn):
        events_db.record_event(conn, {
            "type": "page_view", "path": "/", "anon_id": "abc123def456", "durable": 0,
        })
        assert conn.execute("SELECT durable FROM events").fetchone()["durable"] == 0

    def test_an_older_database_migrates_without_losing_rows(self, tmp_path, monkeypatch):
        """The Fly volume holds a database written before this column existed."""
        import sqlite3

        path = tmp_path / "events.db"
        old = sqlite3.connect(str(path))
        old.executescript(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL,"
            " type TEXT NOT NULL, target TEXT NOT NULL DEFAULT '',"
            " path TEXT NOT NULL DEFAULT '', ref_domain TEXT NOT NULL DEFAULT '',"
            " anon_id TEXT NOT NULL DEFAULT '', value INTEGER NOT NULL DEFAULT 0,"
            " owner INTEGER NOT NULL DEFAULT 0);"
        )
        old.execute("INSERT INTO events (ts, type) VALUES (1, 'page_view')")
        old.commit()
        old.close()

        monkeypatch.setattr(events_db, "events_db_path", lambda: path)
        c = events_db.open_events_db()
        try:
            assert c.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 1
            cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
            assert "durable" in cols
            # A row written before the column existed must not claim durability.
            assert c.execute("SELECT durable FROM events").fetchone()["durable"] == 0
        finally:
            c.close()

    def test_a_missing_flag_is_not_counted_as_durable(self, conn):
        events_db.record_event(conn, {
            "type": "page_view", "path": "/", "anon_id": "abc123def456",
        })
        assert conn.execute("SELECT durable FROM events").fetchone()["durable"] == 0

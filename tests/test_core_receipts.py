"""Tests for core/migrations.py and core/receipts.py."""

import sqlite3

import pytest

from core.db import connect
from core.migrations import MIGRATIONS, current_version, migrate
from core.receipts import claim, content_key, outbound_allowed, release


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    yield conn
    conn.close()


class TestMigrations:
    def test_fresh_db_reaches_latest(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        assert current_version(conn) == 0
        version = migrate(conn)
        assert version == MIGRATIONS[-1][0]
        conn.close()

    def test_idempotent(self, db):
        before = current_version(db)
        assert migrate(db) == before

    def test_partial_version_applies_remainder(self, tmp_path):
        conn = connect(tmp_path / "t.db")
        conn.execute("PRAGMA user_version = 1")
        migrate(conn)
        # migration 2's table must exist
        conn.execute("SELECT action_key FROM receipts")
        conn.close()

    def test_versions_are_ordered_and_unique(self):
        versions = [v for v, _ in MIGRATIONS]
        assert versions == sorted(set(versions))


class TestReceipts:
    def test_first_claim_succeeds(self, db):
        assert claim(db, "newsletter:2026-06-12") is True

    def test_second_claim_fails(self, db):
        claim(db, "newsletter:2026-06-12")
        assert claim(db, "newsletter:2026-06-12") is False

    def test_different_keys_independent(self, db):
        assert claim(db, "post:bluesky:2026-06-12:abc") is True
        assert claim(db, "post:linkedin:2026-06-12:abc") is True

    def test_release_allows_reclaim(self, db):
        claim(db, "newsletter:2026-06-12")
        release(db, "newsletter:2026-06-12")
        assert claim(db, "newsletter:2026-06-12") is True

    def test_content_key_stable_and_short(self):
        assert content_key("hello") == content_key("hello")
        assert content_key("hello") != content_key("hello2")
        assert len(content_key("hello")) == 12


class TestKillSwitch:
    def test_allowed_by_default(self, monkeypatch):
        monkeypatch.delenv("MP_DISABLE_OUTBOUND", raising=False)
        assert outbound_allowed() is True

    def test_blocked_when_set(self, monkeypatch):
        monkeypatch.setenv("MP_DISABLE_OUTBOUND", "1")
        assert outbound_allowed() is False

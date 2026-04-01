"""Tests for orchestrator/checkpoint.py — user_id filtering in find_resumable_run."""

import sqlite3

import pytest

from orchestrator.checkpoint import Checkpoint
from orchestrator.pipeline import Phase


@pytest.fixture
def ckpt(tmp_path):
    """In-memory checkpoint backed by a fresh SQLite connection."""
    conn = sqlite3.connect(":memory:")
    return Checkpoint(conn)


class TestFindResumableRunFiltersByUserId:
    """find_resumable_run must only return runs belonging to the given user_id."""

    def test_find_resumable_run_filters_by_user_id(self, ckpt):
        """Insert runs for two users on the same date.

        Querying for user_a must NOT return user_b's run.
        """
        # user_a has an incomplete run
        ckpt.save("research-2026-03-14-aaa111", Phase.INIT, user_id="user_a")
        ckpt.save("research-2026-03-14-aaa111", Phase.TREND_SCAN, user_id="user_a")

        # user_b also has an incomplete run on the same date
        ckpt.save("research-2026-03-14-bbb222", Phase.INIT, user_id="user_b")

        # Asking for user_a should return user_a's run, NOT user_b's
        result = ckpt.find_resumable_run("user_a", "2026-03-14")
        assert result == "research-2026-03-14-aaa111"

        # Asking for user_b should return user_b's run
        result_b = ckpt.find_resumable_run("user_b", "2026-03-14")
        assert result_b == "research-2026-03-14-bbb222"

    def test_find_resumable_run_returns_none_when_no_runs(self, ckpt):
        """When no runs exist at all, find_resumable_run returns None."""
        result = ckpt.find_resumable_run("ramsay", "2026-03-14")
        assert result is None

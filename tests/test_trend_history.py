"""Tests for trend history tracking — the learning loop for trends.

Tracks which detected trends led to findings, which findings made the
newsletter, and uses that history to weight future trend scoring.
"""

import sqlite3
from unittest.mock import patch

import pytest

from memory.db import get_db


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory database with full schema."""
    db_path = tmp_path / "test.db"
    conn = get_db(db_path=str(db_path))
    return conn


class TestStoreTrends:
    """store_trends() saves detected trends for a run date."""

    def test_stores_trends_and_returns_count(self, db):
        from memory.trends import store_trends
        trends = [
            {"topic": "Claude Code launch", "score": 1.8, "source_count": 3,
             "item_count": 5, "sources": ["hn", "reddit", "rss"],
             "evidence": "HN (450 points); r/ML (800 upvotes)"},
            {"topic": "GPT-5 benchmarks", "score": 1.2, "source_count": 2,
             "item_count": 3, "sources": ["twitter", "hn"],
             "evidence": "X (5000 likes); HN (300 points)"},
        ]
        count = store_trends(db, "2026-04-05", trends)
        assert count == 2

    def test_stored_trends_retrievable(self, db):
        from memory.trends import store_trends, get_trends_for_date
        trends = [
            {"topic": "AI agents", "score": 1.5, "source_count": 2,
             "item_count": 4, "sources": ["hn", "rss"],
             "evidence": "HN; RSS"},
        ]
        store_trends(db, "2026-04-05", trends)
        rows = get_trends_for_date(db, "2026-04-05")
        assert len(rows) == 1
        assert rows[0]["topic"] == "AI agents"
        assert rows[0]["score"] == 1.5
        assert rows[0]["source_count"] == 2

    def test_empty_trends_stores_nothing(self, db):
        from memory.trends import store_trends
        count = store_trends(db, "2026-04-05", [])
        assert count == 0

    def test_duplicate_date_topic_does_not_crash(self, db):
        """Storing the same trend twice for the same date should upsert or skip."""
        from memory.trends import store_trends
        trends = [{"topic": "X", "score": 1.0, "source_count": 1,
                    "item_count": 1, "sources": ["hn"], "evidence": "HN"}]
        store_trends(db, "2026-04-05", trends)
        store_trends(db, "2026-04-05", trends)  # should not raise


class TestBackfillTrendResults:
    """backfill_trend_results() records which trends led to newsletter findings."""

    def test_backfills_findings_count(self, db):
        from memory.trends import store_trends, backfill_trend_results
        from memory.findings import store_finding

        # Store a trend
        store_trends(db, "2026-04-05", [
            {"topic": "Claude Code launch", "score": 1.5, "source_count": 2,
             "item_count": 3, "sources": ["hn", "rss"], "evidence": "HN; RSS"},
        ])

        # Store a finding that matches the trend
        store_finding(db, "2026-04-05", "news-researcher",
                      "Claude Code becomes the top AI coding tool",
                      "Claude Code overtook GitHub Copilot in usage",
                      importance="high", source_url="https://example.com")

        # Backfill — should find the matching finding
        updated = backfill_trend_results(db, "2026-04-05")
        assert updated >= 1

    def test_backfills_zero_when_no_match(self, db):
        from memory.trends import store_trends, backfill_trend_results

        store_trends(db, "2026-04-05", [
            {"topic": "Quantum computing breakthrough", "score": 1.0,
             "source_count": 1, "item_count": 1, "sources": ["arxiv"],
             "evidence": "arXiv"},
        ])
        # No findings stored — nothing matches
        updated = backfill_trend_results(db, "2026-04-05")
        assert updated >= 0  # should complete without error


class TestGetTrendPerformance:
    """get_trend_performance() returns historical trend effectiveness."""

    def test_returns_topic_stats(self, db):
        from memory.trends import store_trends, backfill_trend_results, get_trend_performance

        # Store trends for multiple days
        for date in ["2026-04-01", "2026-04-02", "2026-04-03"]:
            store_trends(db, date, [
                {"topic": "AI agents", "score": 1.5, "source_count": 2,
                 "item_count": 3, "sources": ["hn", "rss"], "evidence": "HN"},
            ])

        stats = get_trend_performance(db, days=7)
        assert isinstance(stats, list)
        # Should have an entry for "AI agents"
        topics = [s["topic"] for s in stats]
        assert "AI agents" in topics

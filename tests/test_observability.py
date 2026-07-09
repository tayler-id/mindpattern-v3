"""Tests for orchestrator/observability.py — PipelineMonitor."""

import sqlite3

import pytest

from orchestrator.observability import PipelineMonitor


@pytest.fixture()
def monitor():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return PipelineMonitor(conn)


def _insert_quality(monitor, run_date, score):
    monitor.conn.execute(
        """INSERT INTO quality_history
           (run_date, overall_score, coverage, dedup, sources,
            actionability, length_score, topic_balance)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_date, score, score, score, score, score, score, score),
    )
    monitor.conn.commit()


class TestCheckQualityRegression:
    """check_quality_regression() compares today against the latest 7 runs only."""

    def test_regression_detected_despite_old_low_scores(self, monitor):
        """Old low scores must not drag down the 7-run baseline.

        30 ancient runs at 0.3, then 7 recent runs at 0.9. Today scores 0.75:
        a real drop vs the recent 0.9 average that an all-time average
        (~0.41) would mask entirely.
        """
        for day in range(1, 31):
            _insert_quality(monitor, f"2026-05-{day:02d}", 0.3)
        for day in range(1, 8):
            _insert_quality(monitor, f"2026-07-{day:02d}", 0.9)
        _insert_quality(monitor, "2026-07-08", 0.75)

        result = monitor.check_quality_regression("2026-07-08", threshold=0.1)

        assert result is not None, "regression masked by all-time average"
        assert result["today_score"] == 0.75
        assert result["avg_7d"] == pytest.approx(0.9, abs=0.001)
        assert result["delta"] == pytest.approx(-0.15, abs=0.001)

    def test_no_regression_when_stable(self, monitor):
        for day in range(1, 8):
            _insert_quality(monitor, f"2026-07-{day:02d}", 0.85)
        _insert_quality(monitor, "2026-07-08", 0.84)

        assert monitor.check_quality_regression("2026-07-08", threshold=0.1) is None

    def test_no_history_returns_none(self, monitor):
        _insert_quality(monitor, "2026-07-08", 0.5)
        assert monitor.check_quality_regression("2026-07-08") is None

    def test_dimension_regression_uses_recent_window(self, monitor):
        """Per-dimension averages must use the same latest-7 window."""
        for day in range(1, 31):
            _insert_quality(monitor, f"2026-05-{day:02d}", 0.3)
        for day in range(1, 8):
            _insert_quality(monitor, f"2026-07-{day:02d}", 0.9)
        _insert_quality(monitor, "2026-07-08", 0.75)

        result = monitor.check_quality_regression("2026-07-08", threshold=0.1)

        assert result is not None
        # every dimension dropped 0.9 → 0.75, so all should be flagged
        assert len(result["dimensions_regressed"]) == 6

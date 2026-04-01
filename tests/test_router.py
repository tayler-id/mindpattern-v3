"""Tests for adaptive model routing in orchestrator/router.py.

Ticket: 2026-04-01-R014
Feature: Quality-driven cascade model routing for research agents.
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator import router
from orchestrator.traces_db import init_db, log_agent_metrics


def _seed_agent_metrics(conn: sqlite3.Connection, agent_name: str, rows: list[dict]) -> None:
    """Insert mock agent_metrics rows for testing."""
    for row in rows:
        conn.execute(
            "INSERT INTO agent_metrics (agent_name, run_date, findings_count, tokens_used, cost, duration_ms, model_used) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                agent_name,
                row["run_date"],
                row.get("findings_count", 10),
                row.get("tokens_used", 5000),
                row.get("cost", 0.05),
                row.get("duration_ms", 30000),
                row.get("model_used", "sonnet"),
            ),
        )
    conn.commit()


@pytest.fixture
def traces_db():
    """Create a temporary traces.db with schema initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "traces.db"
        conn = init_db(db_path)
        yield conn
        conn.close()


@pytest.fixture(autouse=True)
def _enable_adaptive_routing():
    """Enable adaptive routing for all tests by default."""
    with patch.object(router, "ADAPTIVE_ROUTING_ENABLED", True):
        yield


class TestAdaptiveRoutingPromotesToOpusOnLowQuality:
    """Agents with low quality scores on Sonnet should be promoted to Opus."""

    def test_low_findings_on_sonnet_promotes_to_opus(self, traces_db):
        # 3 consecutive Sonnet runs with low findings (below threshold)
        _seed_agent_metrics(traces_db, "hn-researcher", [
            {"run_date": "2026-03-25", "findings_count": 2, "duration_ms": 60000, "model_used": "sonnet"},
            {"run_date": "2026-03-26", "findings_count": 1, "duration_ms": 55000, "model_used": "sonnet"},
            {"run_date": "2026-03-27", "findings_count": 3, "duration_ms": 65000, "model_used": "sonnet"},
        ])
        model = router.get_adaptive_model(traces_db, "hn-researcher")
        # Low quality on Sonnet → promote to Opus
        assert model == router.MODELS["opus_1m"]


class TestAdaptiveRoutingKeepsSonnetOnHighQuality:
    """Agents with consistently high quality on Sonnet should stay on Sonnet."""

    def test_high_findings_on_sonnet_keeps_sonnet(self, traces_db):
        # 3+ consecutive Sonnet runs with high findings
        _seed_agent_metrics(traces_db, "arxiv-researcher", [
            {"run_date": "2026-03-25", "findings_count": 18, "duration_ms": 30000, "model_used": "sonnet"},
            {"run_date": "2026-03-26", "findings_count": 20, "duration_ms": 28000, "model_used": "sonnet"},
            {"run_date": "2026-03-27", "findings_count": 15, "duration_ms": 32000, "model_used": "sonnet"},
        ])
        model = router.get_adaptive_model(traces_db, "arxiv-researcher")
        assert model == router.MODELS["sonnet"]


class TestAdaptiveRoutingFallbackWithNoHistory:
    """Agents with no or insufficient history should default to Opus (static)."""

    def test_no_history_defaults_to_opus(self, traces_db):
        # No agent_metrics rows at all
        model = router.get_adaptive_model(traces_db, "new-agent")
        assert model == router.MODELS["opus_1m"]

    def test_insufficient_history_defaults_to_opus(self, traces_db):
        # Only 2 runs (below minimum 3)
        _seed_agent_metrics(traces_db, "new-agent", [
            {"run_date": "2026-03-26", "findings_count": 10, "duration_ms": 30000, "model_used": "sonnet"},
            {"run_date": "2026-03-27", "findings_count": 12, "duration_ms": 28000, "model_used": "sonnet"},
        ])
        model = router.get_adaptive_model(traces_db, "new-agent")
        assert model == router.MODELS["opus_1m"]


class TestAdaptiveRoutingDisabledUsesStatic:
    """When ADAPTIVE_ROUTING_ENABLED is false, use static routing."""

    @pytest.fixture(autouse=True)
    def _disable_adaptive_routing(self):
        """Override the module-level autouse fixture to disable routing."""
        with patch.object(router, "ADAPTIVE_ROUTING_ENABLED", False):
            yield

    def test_disabled_returns_static_model(self, traces_db):
        # Even with good history, disabled routing should use static assignment
        _seed_agent_metrics(traces_db, "arxiv-researcher", [
            {"run_date": "2026-03-25", "findings_count": 18, "duration_ms": 30000, "model_used": "sonnet"},
            {"run_date": "2026-03-26", "findings_count": 20, "duration_ms": 28000, "model_used": "sonnet"},
            {"run_date": "2026-03-27", "findings_count": 15, "duration_ms": 32000, "model_used": "sonnet"},
        ])
        model = router.get_adaptive_model(traces_db, "arxiv-researcher")
        # Static routing: research_agent → opus_1m
        assert model == router.MODELS["opus_1m"]


class TestRoutingLogRecorded:
    """Routing decisions should be logged to the model_routing_log table."""

    def test_log_entry_created_on_adaptive_routing(self, traces_db):
        _seed_agent_metrics(traces_db, "hn-researcher", [
            {"run_date": "2026-03-25", "findings_count": 18, "duration_ms": 30000, "model_used": "sonnet"},
            {"run_date": "2026-03-26", "findings_count": 20, "duration_ms": 28000, "model_used": "sonnet"},
            {"run_date": "2026-03-27", "findings_count": 15, "duration_ms": 32000, "model_used": "sonnet"},
        ])
        router.get_adaptive_model(traces_db, "hn-researcher")

        rows = traces_db.execute(
            "SELECT * FROM model_routing_log WHERE agent_name = 'hn-researcher'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["agent_name"] == "hn-researcher"
        assert row["assigned_model"] is not None
        assert row["quality_score"] is not None
        assert row["reason"] is not None

    def test_log_entry_created_on_fallback(self, traces_db):
        """Even fallback decisions should be logged."""
        router.get_adaptive_model(traces_db, "new-agent")

        rows = traces_db.execute(
            "SELECT * FROM model_routing_log WHERE agent_name = 'new-agent'"
        ).fetchall()
        assert len(rows) == 1
        assert "insufficient" in rows[0]["reason"].lower() or "fallback" in rows[0]["reason"].lower()

"""Tests for orchestrator/traces_db.py helper functions.

Uses temporary on-disk SQLite for isolation (init_db requires a Path for mkdir).
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator.traces_db import (
    create_alert,
    create_agent_run,
    create_pipeline_run,
    complete_agent_run,
    get_agent_history,
    get_agent_scorecard,
    init_db,
    log_agent_metrics,
)


@pytest.fixture
def db():
    """Provide a fresh traces.db connection for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = init_db(Path(tmpdir) / "traces.db")
        yield conn
        conn.close()


# ---- Schema ----

def test_schema_creates_all_tables(db):
    """init_db must create exactly the 14 documented tables."""
    cur = db.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [row["name"] for row in cur.fetchall()]
    expected = sorted([
        "agent_metrics", "agent_runs", "alerts", "cost_log", "daily_metrics",
        "events", "evolution_actions", "pipeline_phases", "pipeline_runs",
        "prompt_versions", "proof_packages", "quality_history", "quality_scores",
        "trace_spans",
    ])
    assert tables == expected


# ---- get_agent_history ----

def test_get_agent_history_empty(db):
    """get_agent_history with no data returns zeroed summary."""
    result = get_agent_history(db, "nonexistent-agent")
    assert result["agent_name"] == "nonexistent-agent"
    assert result["runs"] == 0
    assert result["avg_findings"] == 0.0
    assert result["avg_duration_ms"] == 0.0
    assert result["quality_trend"] == []
    assert result["failure_count"] == 0
    assert result["common_issues"] == []


def test_get_agent_history_with_data(db):
    """get_agent_history returns correct aggregates from agent_metrics and agent_runs."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Insert agent_metrics rows
    log_agent_metrics(db, "test-agent", today, 10, 5000, 0.05, 3000, "opus-4")
    log_agent_metrics(db, "test-agent", today, 20, 7000, 0.07, 5000, "opus-4")

    # Insert agent_runs with quality scores and one failure
    run_id = create_pipeline_run(db, "research", "test", run_id="hist-run-1")
    ar1 = create_agent_run(db, run_id, "test-agent")
    complete_agent_run(db, ar1, "completed", input_tokens=100, output_tokens=200)
    db.execute("UPDATE agent_runs SET quality_score = 0.8 WHERE id = ?", (ar1,))
    db.commit()

    # Use a second agent_run via direct SQL (agent_run id must be unique)
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO agent_runs (id, pipeline_run_id, agent_name, status, started_at, quality_score) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("hist-run-1/test-agent-2", run_id, "test-agent", "failed", now, None),
    )
    db.execute(
        "UPDATE agent_runs SET error = 'timeout' WHERE id = 'hist-run-1/test-agent-2'"
    )
    db.commit()

    result = get_agent_history(db, "test-agent")
    assert result["runs"] == 2  # 2 agent_metrics rows
    assert result["avg_findings"] == 15.0  # (10+20)/2
    assert result["avg_duration_ms"] == 4000.0  # (3000+5000)/2
    assert result["quality_trend"] == [0.8]  # only the one non-null score
    assert result["failure_count"] == 1
    assert "timeout" in result["common_issues"]


# ---- get_agent_scorecard ----

def test_get_agent_scorecard(db):
    """get_agent_scorecard returns findings totals and quality trend."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # agent_metrics data
    log_agent_metrics(db, "sc-agent", today, 8, 4000, 0.04, 2000, "sonnet")
    log_agent_metrics(db, "sc-agent", today, 12, 6000, 0.06, 3000, "sonnet")

    # agent_runs with quality scores for trend
    run_id = create_pipeline_run(db, "research", "test", run_id="sc-run-1")
    ar1 = create_agent_run(db, run_id, "sc-agent")
    complete_agent_run(db, ar1, "completed")
    db.execute("UPDATE agent_runs SET quality_score = 0.9 WHERE id = ?", (ar1,))
    db.commit()

    # Add a quality_scores row for high-importance ratio
    db.execute(
        "INSERT INTO quality_scores (agent_run_id, dimension, score) VALUES (?, ?, ?)",
        (ar1, "importance", 0.85),
    )
    db.commit()

    result = get_agent_scorecard(db, "sc-agent")
    assert result["agent_name"] == "sc-agent"
    assert result["total_findings"] == 20  # 8+12
    assert result["avg_findings_per_run"] == 10.0  # (8+12)/2
    assert result["quality_trend"] == [0.9]
    assert result["high_importance_count"] == 1
    assert result["high_importance_ratio"] == 1.0  # 1/1


# ---- log_agent_metrics ----

def test_log_agent_metrics(db):
    """log_agent_metrics inserts a row with all fields correct."""
    log_agent_metrics(db, "insert-agent", "2026-03-30", 15, 9000, 0.10, 6000, "opus-4")
    row = db.execute(
        "SELECT * FROM agent_metrics WHERE agent_name = 'insert-agent'"
    ).fetchone()
    assert row is not None
    assert row["run_date"] == "2026-03-30"
    assert row["findings_count"] == 15
    assert row["tokens_used"] == 9000
    assert row["cost"] == 0.10
    assert row["duration_ms"] == 6000
    assert row["model_used"] == "opus-4"


# ---- create_alert ----

def test_create_alert(db):
    """create_alert inserts with correct severity and default acknowledged=0."""
    create_alert(db, "2026-03-30", "high_cost", "Cost exceeded $1", "critical")
    create_alert(db, "2026-03-30", "low_quality", "Quality below 0.5", "warning")

    rows = db.execute(
        "SELECT * FROM alerts WHERE run_date = '2026-03-30' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2

    assert rows[0]["alert_type"] == "high_cost"
    assert rows[0]["severity"] == "critical"
    assert rows[0]["acknowledged"] == 0

    assert rows[1]["alert_type"] == "low_quality"
    assert rows[1]["severity"] == "warning"
    assert rows[1]["acknowledged"] == 0

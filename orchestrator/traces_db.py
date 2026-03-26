"""traces.db schema initialization and helpers for the mindpattern-v3 orchestrator pipeline.

Ported from daily-research-agent-v2 with additional tables and helpers for
per-phase observability, agent metrics, cost tracking, alerts, and quality
history trends.

Tables (14 total):
  v2 originals (9): pipeline_runs, agent_runs, prompt_versions, proof_packages,
                     events, daily_metrics, trace_spans, quality_scores,
                     evolution_actions
  v3 additions (5): pipeline_phases, agent_metrics, cost_log, alerts,
                     quality_history
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

# ---------------------------------------------------------------------------
# Default database path — resolves relative to the mindpattern-v3 project root
# ---------------------------------------------------------------------------

TRACES_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ramsay" / "traces.db"

MAX_OUTPUT_BYTES = 10_240  # 10 KB truncation limit per architecture


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to traces.db with WAL mode and Row factory."""
    path = db_path or TRACES_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create all tables if they don't exist and return the connection."""
    conn = get_db(db_path)

    conn.executescript("""
        -- ---------------------------------------------------------------
        -- v2 tables (9)
        -- ---------------------------------------------------------------

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            pipeline_type TEXT,
            status TEXT,
            started_at TEXT,
            completed_at TEXT,
            trigger TEXT,
            error TEXT,
            metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            pipeline_run_id TEXT REFERENCES pipeline_runs(id),
            agent_name TEXT,
            status TEXT,
            started_at TEXT,
            completed_at TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            latency_ms INTEGER,
            prompt_version TEXT,
            quality_score REAL,
            error TEXT,
            output TEXT
        );

        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT,
            git_hash TEXT,
            captured_at TEXT,
            file_path TEXT,
            UNIQUE(agent_name, git_hash)
        );

        CREATE TABLE IF NOT EXISTS proof_packages (
            id TEXT PRIMARY KEY,
            pipeline_run_id TEXT REFERENCES pipeline_runs(id),
            topic TEXT,
            status TEXT,
            quality_score REAL,
            creative_brief TEXT,
            post_text TEXT,
            art_path TEXT,
            sources TEXT,
            post_results TEXT,
            reviewer_notes TEXT,
            created_at TEXT,
            reviewed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT,
            event_type TEXT,
            payload TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_metrics (
            date TEXT,
            metric_name TEXT,
            metric_value REAL,
            PRIMARY KEY (date, metric_name)
        );

        CREATE TABLE IF NOT EXISTS trace_spans (
            id TEXT PRIMARY KEY,
            agent_run_id TEXT REFERENCES agent_runs(id),
            parent_span_id TEXT,
            span_type TEXT,
            name TEXT,
            input TEXT,
            output TEXT,
            started_at TEXT,
            duration_ms INTEGER
        );

        CREATE TABLE IF NOT EXISTS quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_run_id TEXT REFERENCES agent_runs(id),
            prompt_version_id INTEGER REFERENCES prompt_versions(id),
            dimension TEXT,
            score REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS evolution_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            agents_affected TEXT NOT NULL,
            reasoning TEXT,
            date TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- ---------------------------------------------------------------
        -- v3 tables (5)
        -- ---------------------------------------------------------------

        CREATE TABLE IF NOT EXISTS pipeline_phases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT NOT NULL REFERENCES pipeline_runs(id),
            phase_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            tokens_used INTEGER,
            cost REAL,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            run_date TEXT NOT NULL,
            findings_count INTEGER,
            tokens_used INTEGER,
            cost REAL,
            duration_ms INTEGER,
            model_used TEXT
        );

        CREATE TABLE IF NOT EXISTS cost_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            phase TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            acknowledged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS quality_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            dimension TEXT NOT NULL,
            score REAL NOT NULL,
            delta_from_avg REAL
        );
    """)

    return conn


@contextmanager
def open_traces_db(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that opens traces.db (with init) and closes on exit."""
    conn = init_db(db_path)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline_runs helpers
# ---------------------------------------------------------------------------


def create_pipeline_run(
    conn: sqlite3.Connection,
    pipeline_type: str,
    trigger: str,
    metadata: str | None = None,
    *,
    run_id: str | None = None,
    status: str = "running",
    commit: bool = True,
) -> str:
    """Insert a new pipeline_runs record and return its id.

    Set commit=False to group with other operations in a caller-managed transaction.
    """
    run_id = run_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO pipeline_runs (id, pipeline_type, status, started_at, trigger, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, pipeline_type, status, now, trigger, metadata),
    )
    if commit:
        conn.commit()
    return run_id


def complete_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str = "completed",
    error: str | None = None,
    *,
    commit: bool = True,
) -> None:
    """Mark a pipeline_runs record as completed (or failed).

    Set commit=False to group with other operations in a caller-managed transaction.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE pipeline_runs SET status = ?, completed_at = ?, error = ? WHERE id = ?",
        (status, now, error, run_id),
    )
    if commit:
        conn.commit()


def get_pipeline_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    """Fetch a single pipeline_runs record by id."""
    cur = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# agent_runs helpers
# ---------------------------------------------------------------------------


def create_agent_run(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    agent_name: str,
    *,
    commit: bool = True,
) -> str:
    """Insert a new agent_runs record and return its id.

    ID format: {pipeline_run_id}/{agent_name}
    """
    agent_run_id = f"{pipeline_run_id}/{agent_name}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO agent_runs (id, pipeline_run_id, agent_name, status, started_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent_run_id, pipeline_run_id, agent_name, "running", now),
    )
    if commit:
        conn.commit()
    return agent_run_id


def complete_agent_run(
    conn: sqlite3.Connection,
    agent_run_id: str,
    status: str = "completed",
    *,
    output: str | None = None,
    error: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    commit: bool = True,
) -> None:
    """Mark an agent_runs record as completed (or failed).

    Output is truncated to 10 KB per architecture retention policy.
    """
    now = datetime.now(timezone.utc).isoformat()
    truncated_output = (
        output[:MAX_OUTPUT_BYTES] if output and len(output) > MAX_OUTPUT_BYTES else output
    )
    conn.execute(
        "UPDATE agent_runs SET status=?, completed_at=?, output=?, error=?, "
        "input_tokens=?, output_tokens=?, latency_ms=? WHERE id=?",
        (status, now, truncated_output, error, input_tokens, output_tokens, latency_ms, agent_run_id),
    )
    if commit:
        conn.commit()


def get_agent_run(conn: sqlite3.Connection, agent_run_id: str) -> sqlite3.Row | None:
    """Fetch a single agent_runs record by id."""
    cur = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (agent_run_id,))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# events helpers
# ---------------------------------------------------------------------------


def log_event(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    event_type: str,
    payload: str,
    *,
    commit: bool = True,
) -> None:
    """Insert an event record into the events table."""
    conn.execute(
        "INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
        (pipeline_run_id, event_type, payload),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# evolution_actions helpers
# ---------------------------------------------------------------------------


def log_evolution_action(
    conn: sqlite3.Connection,
    action_type: str,
    agents_affected: str,
    reasoning: str,
    date: str,
    metadata: str | None = None,
    *,
    commit: bool = True,
) -> int:
    """Log an agent evolution action (spawn, retire, merge) to traces.db.

    Returns the ID of the inserted row.
    """
    cur = conn.execute(
        "INSERT INTO evolution_actions (action_type, agents_affected, reasoning, date, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (action_type, agents_affected, reasoning, date, metadata),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Stale-run cleanup and partial-failure helpers
# ---------------------------------------------------------------------------


def cleanup_stale_runs(
    conn: sqlite3.Connection,
    *,
    commit: bool = True,
) -> int:
    """Mark stale pipeline_runs (any non-terminal status with no completed_at) as failed.

    Called at pipeline startup to clean up after crashes or killed processes.
    Uses NOT IN ('completed', 'failed') to catch all intermediate pipeline states.
    Returns the number of runs cleaned up.
    """
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "UPDATE pipeline_runs SET status = 'failed', completed_at = ?, "
        "error = 'Stale run cleaned up on startup' "
        "WHERE status NOT IN ('completed', 'failed') AND completed_at IS NULL",
        (now,),
    )
    if commit:
        conn.commit()
    return cur.rowcount


def complete_with_warnings(
    conn: sqlite3.Connection,
    run_id: str,
    warnings: list[str],
    *,
    commit: bool = True,
) -> None:
    """Mark a pipeline_run as 'completed' with metadata listing warning steps.

    Used when the pipeline finishes but some non-critical steps failed.
    """
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute("SELECT metadata FROM pipeline_runs WHERE id = ?", (run_id,))
    row = cur.fetchone()
    existing = json.loads(row["metadata"]) if row and row["metadata"] else {}
    existing["warnings"] = warnings
    metadata = json.dumps(existing)
    conn.execute(
        "UPDATE pipeline_runs SET status = 'completed', completed_at = ?, metadata = ? WHERE id = ?",
        (now, metadata, run_id),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# prompt_versions helpers
# ---------------------------------------------------------------------------


def capture_prompt_versions(
    conn: sqlite3.Connection,
    agent_paths: list[Path],
    repo_root: Path | None = None,
    *,
    commit: bool = True,
) -> dict[str, str]:
    """Capture git hash for each agent .md file and upsert into prompt_versions.

    Returns a dict mapping agent_name -> git_hash for use when creating agent_runs.
    Agents whose files have no git history (untracked) are skipped.
    """
    if repo_root is None:
        repo_root = TRACES_DB_PATH.parent

    now = datetime.now(timezone.utc).isoformat()
    result: dict[str, str] = {}

    for path in agent_paths:
        agent_name = path.stem  # e.g. "hn-researcher" from "hn-researcher.md"
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--format=%H", "--", str(path)],
                capture_output=True,
                text=True,
                cwd=str(repo_root),
                timeout=10,
            )
            git_hash = proc.stdout.strip()
            if not git_hash:
                continue  # No git history for this file

            # INSERT OR IGNORE — only inserts if (agent_name, git_hash) combo is new
            conn.execute(
                "INSERT OR IGNORE INTO prompt_versions (agent_name, git_hash, captured_at, file_path) "
                "VALUES (?, ?, ?, ?)",
                (agent_name, git_hash, now, str(path)),
            )
            result[agent_name] = git_hash
        except (subprocess.SubprocessError, OSError):
            continue  # Skip agents where git command fails

    if commit:
        conn.commit()
    return result


def set_prompt_version(
    conn: sqlite3.Connection,
    agent_run_id: str,
    git_hash: str,
    *,
    commit: bool = True,
) -> None:
    """Update an agent_runs record with the prompt_version git hash."""
    conn.execute(
        "UPDATE agent_runs SET prompt_version = ? WHERE id = ?",
        (git_hash, agent_run_id),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# daily_metrics helpers
# ---------------------------------------------------------------------------


def refresh_daily_metrics(
    conn: sqlite3.Connection,
    date_str: str,
    *,
    commit: bool = True,
) -> None:
    """Compute and cache daily aggregate metrics for a given date.

    Computes total_tokens, avg_latency_ms, success_rate, completion_rate
    and INSERT OR REPLACE into the daily_metrics table.
    """
    # total_tokens from agent_runs
    row = conn.execute(
        """
        SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) AS val
        FROM agent_runs WHERE date(started_at) = ?
        """,
        (date_str,),
    ).fetchone()
    total_tokens = row["val"] if row and row["val"] is not None else 0

    # avg_latency_ms from agent_runs
    row = conn.execute(
        """
        SELECT AVG(latency_ms) AS val
        FROM agent_runs WHERE date(started_at) = ? AND latency_ms IS NOT NULL
        """,
        (date_str,),
    ).fetchone()
    avg_latency = row["val"] if row and row["val"] is not None else 0

    # success_rate from agent_runs
    row = conn.execute(
        """
        SELECT
            CAST(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS REAL) / MAX(COUNT(*), 1) AS val
        FROM agent_runs WHERE date(started_at) = ?
        """,
        (date_str,),
    ).fetchone()
    success_rate = row["val"] if row and row["val"] is not None else 0

    # completion_rate from pipeline_runs
    row = conn.execute(
        """
        SELECT
            CAST(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS REAL) / MAX(COUNT(*), 1) AS val
        FROM pipeline_runs WHERE date(started_at) = ?
        """,
        (date_str,),
    ).fetchone()
    completion_rate = row["val"] if row and row["val"] is not None else 0

    for metric_name, metric_value in [
        ("total_tokens", total_tokens),
        ("avg_latency_ms", avg_latency),
        ("success_rate", success_rate),
        ("completion_rate", completion_rate),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO daily_metrics (date, metric_name, metric_value) VALUES (?, ?, ?)",
            (date_str, metric_name, metric_value),
        )

    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# v3: pipeline_phases helpers
# ---------------------------------------------------------------------------


def create_phase(
    conn: sqlite3.Connection,
    pipeline_run_id: str,
    phase_name: str,
    *,
    commit: bool = True,
) -> int:
    """Start a new pipeline phase and return its id."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO pipeline_phases (pipeline_run_id, phase_name, status, started_at) "
        "VALUES (?, ?, 'running', ?)",
        (pipeline_run_id, phase_name, now),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def complete_phase(
    conn: sqlite3.Connection,
    phase_id: int,
    status: str = "completed",
    *,
    tokens_used: int | None = None,
    cost: float | None = None,
    error: str | None = None,
    commit: bool = True,
) -> None:
    """Complete a pipeline phase with final status and optional metrics."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE pipeline_phases SET status=?, completed_at=?, tokens_used=?, cost=?, error=? "
        "WHERE id=?",
        (status, now, tokens_used, cost, error, phase_id),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# v3: agent_metrics helpers
# ---------------------------------------------------------------------------


def log_agent_metrics(
    conn: sqlite3.Connection,
    agent_name: str,
    run_date: str,
    findings_count: int,
    tokens_used: int,
    cost: float,
    duration_ms: int,
    model_used: str,
    *,
    commit: bool = True,
) -> None:
    """Log per-agent observability metrics for a single run."""
    conn.execute(
        "INSERT INTO agent_metrics "
        "(agent_name, run_date, findings_count, tokens_used, cost, duration_ms, model_used) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent_name, run_date, findings_count, tokens_used, cost, duration_ms, model_used),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# v3: cost_log helpers
# ---------------------------------------------------------------------------


def log_cost(
    conn: sqlite3.Connection,
    run_date: str,
    phase: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    *,
    commit: bool = True,
) -> None:
    """Log cost tracking entry by phase and model."""
    conn.execute(
        "INSERT INTO cost_log (run_date, phase, model, input_tokens, output_tokens, cost_usd) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (run_date, phase, model, input_tokens, output_tokens, cost_usd),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# v3: alerts helpers
# ---------------------------------------------------------------------------


def create_alert(
    conn: sqlite3.Connection,
    run_date: str,
    alert_type: str,
    message: str,
    severity: str = "warning",
    *,
    commit: bool = True,
) -> None:
    """Create an observability alert."""
    conn.execute(
        "INSERT INTO alerts (run_date, alert_type, message, severity) "
        "VALUES (?, ?, ?, ?)",
        (run_date, alert_type, message, severity),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# v3: quality_history helpers
# ---------------------------------------------------------------------------


def log_quality_history(
    conn: sqlite3.Connection,
    run_date: str,
    dimension: str,
    score: float,
    delta_from_avg: float | None = None,
    *,
    commit: bool = True,
) -> None:
    """Log a quality score trend entry for a given dimension and date."""
    conn.execute(
        "INSERT INTO quality_history (run_date, dimension, score, delta_from_avg) "
        "VALUES (?, ?, ?, ?)",
        (run_date, dimension, score, delta_from_avg),
    )
    if commit:
        conn.commit()


# ---------------------------------------------------------------------------
# Cross-run learning helpers
# ---------------------------------------------------------------------------


def get_agent_history(
    conn: sqlite3.Connection,
    agent_name: str,
    lookback_days: int = 7,
) -> dict:
    """Query agent_metrics and agent_runs for the last N days.

    Returns a summary dict with run count, avg findings, avg duration,
    quality trend, failure count, and common issues.
    """
    # --- agent_metrics aggregates ---
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS runs,
            COALESCE(AVG(findings_count), 0.0) AS avg_findings,
            COALESCE(AVG(duration_ms), 0.0) AS avg_duration_ms
        FROM agent_metrics
        WHERE agent_name = ?
          AND run_date >= date('now', ? || ' days')
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchone()

    runs = row["runs"] if row else 0
    avg_findings = round(row["avg_findings"], 2) if row else 0.0
    avg_duration_ms = round(row["avg_duration_ms"], 2) if row else 0.0

    # --- quality trend from agent_runs (last N runs, ordered chronologically) ---
    quality_rows = conn.execute(
        """
        SELECT quality_score
        FROM agent_runs
        WHERE agent_name = ?
          AND date(started_at) >= date('now', ? || ' days')
          AND quality_score IS NOT NULL
        ORDER BY started_at ASC
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchall()
    quality_trend = [r["quality_score"] for r in quality_rows]

    # --- failure count from agent_runs ---
    fail_row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM agent_runs
        WHERE agent_name = ?
          AND date(started_at) >= date('now', ? || ' days')
          AND status = 'failed'
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchone()
    failure_count = fail_row["cnt"] if fail_row else 0

    # --- common issues (deduplicated non-null errors) ---
    error_rows = conn.execute(
        """
        SELECT DISTINCT error
        FROM agent_runs
        WHERE agent_name = ?
          AND date(started_at) >= date('now', ? || ' days')
          AND error IS NOT NULL
          AND error != ''
        ORDER BY started_at DESC
        LIMIT 10
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchall()
    common_issues = [r["error"] for r in error_rows]

    return {
        "agent_name": agent_name,
        "runs": runs,
        "avg_findings": avg_findings,
        "avg_duration_ms": avg_duration_ms,
        "quality_trend": quality_trend,
        "failure_count": failure_count,
        "common_issues": common_issues,
    }


def get_agent_scorecard(
    conn: sqlite3.Connection,
    agent_name: str,
    lookback_days: int = 7,
) -> dict:
    """Return a scorecard dict with findings totals, high-importance ratio, and quality trend.

    Queries agent_metrics for findings data and agent_runs for quality scores.
    """
    # --- findings totals from agent_metrics ---
    row = conn.execute(
        """
        SELECT
            COALESCE(SUM(findings_count), 0) AS total_findings,
            COUNT(*) AS run_count,
            COALESCE(AVG(findings_count), 0.0) AS avg_findings_per_run
        FROM agent_metrics
        WHERE agent_name = ?
          AND run_date >= date('now', ? || ' days')
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchone()

    total_findings = row["total_findings"] if row else 0
    run_count = row["run_count"] if row else 0
    avg_findings_per_run = round(row["avg_findings_per_run"], 2) if row else 0.0

    # --- quality trend from agent_runs ---
    quality_rows = conn.execute(
        """
        SELECT quality_score
        FROM agent_runs
        WHERE agent_name = ?
          AND date(started_at) >= date('now', ? || ' days')
          AND quality_score IS NOT NULL
        ORDER BY started_at ASC
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchall()
    quality_trend = [r["quality_score"] for r in quality_rows]

    # --- high-importance count from quality_scores dimension='importance' ---
    # Fall back to counting runs with quality_score >= 0.8 as a proxy
    hi_row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM quality_scores qs
        JOIN agent_runs ar ON qs.agent_run_id = ar.id
        WHERE ar.agent_name = ?
          AND date(ar.started_at) >= date('now', ? || ' days')
          AND qs.dimension = 'importance'
          AND qs.score >= 0.8
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchone()
    high_importance_count = hi_row["cnt"] if hi_row else 0

    # Total importance-scored findings for ratio
    total_importance_row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM quality_scores qs
        JOIN agent_runs ar ON qs.agent_run_id = ar.id
        WHERE ar.agent_name = ?
          AND date(ar.started_at) >= date('now', ? || ' days')
          AND qs.dimension = 'importance'
        """,
        (agent_name, f"-{lookback_days}"),
    ).fetchone()
    total_importance = total_importance_row["cnt"] if total_importance_row else 0

    high_importance_ratio = (
        round(high_importance_count / total_importance, 2)
        if total_importance > 0
        else 0.0
    )

    return {
        "agent_name": agent_name,
        "total_findings": total_findings,
        "high_importance_count": high_importance_count,
        "high_importance_ratio": high_importance_ratio,
        "avg_findings_per_run": avg_findings_per_run,
        "quality_trend": quality_trend,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_traces.db"
        print(f"Initializing test traces.db at {test_db} ...")
        conn = init_db(test_db)

        # Verify all 14 tables exist
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row["name"] for row in cur.fetchall()]
        expected = sorted([
            "agent_metrics", "agent_runs", "alerts", "cost_log", "daily_metrics",
            "events", "evolution_actions", "pipeline_phases", "pipeline_runs",
            "prompt_versions", "proof_packages", "quality_history", "quality_scores",
            "trace_spans",
        ])
        assert tables == expected, f"Expected {expected}, got {tables}"
        print(f"All 14 tables created: {tables}")

        # Round-trip test for pipeline_runs
        run_id = create_pipeline_run(conn, "research", "manual_test", '{"test": true}')
        row = get_pipeline_run(conn, run_id)
        assert row is not None
        assert row["id"] == run_id
        assert row["pipeline_type"] == "research"
        assert row["status"] == "running"
        assert row["trigger"] == "manual_test"
        assert row["metadata"] == '{"test": true}'
        print(f"pipeline_runs round-trip OK: id={run_id}")

        complete_pipeline_run(conn, run_id, "completed")
        row = get_pipeline_run(conn, run_id)
        assert row["status"] == "completed"
        assert row["completed_at"] is not None
        print("pipeline_runs completion OK")

        # Verify WAL mode
        wal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert wal == "wal", f"Expected WAL, got {wal}"
        print("WAL mode confirmed")

        # Clean up test pipeline run
        conn.execute("DELETE FROM pipeline_runs WHERE id = ?", (run_id,))
        conn.commit()

        # --- cleanup_stale_runs ---
        stale1 = create_pipeline_run(conn, "research", "test", run_id="stale-running-001", status="running")
        stale2 = create_pipeline_run(conn, "research", "test", run_id="stale-pending-001", status="pending")
        done1 = create_pipeline_run(conn, "research", "test", run_id="done-001", status="running")
        complete_pipeline_run(conn, done1, "completed")

        cleaned = cleanup_stale_runs(conn)
        assert cleaned == 2, f"Expected 2 stale runs cleaned, got {cleaned}"

        row1 = get_pipeline_run(conn, stale1)
        assert row1["status"] == "failed"
        assert row1["error"] == "Stale run cleaned up on startup"

        row2 = get_pipeline_run(conn, stale2)
        assert row2["status"] == "failed"

        row3 = get_pipeline_run(conn, done1)
        assert row3["status"] == "completed"

        for rid in [stale1, stale2, done1]:
            conn.execute("DELETE FROM pipeline_runs WHERE id = ?", (rid,))
        conn.commit()
        print("cleanup_stale_runs verified")

        # --- complete_with_warnings ---
        warn_id = create_pipeline_run(
            conn, "research", "test",
            '{"user": "ramsay", "vertical": "ai-tech"}',
            run_id="warn-001", status="running",
        )
        complete_with_warnings(conn, warn_id, ["backfill", "sync"])
        row = get_pipeline_run(conn, warn_id)
        assert row["status"] == "completed"
        meta = json.loads(row["metadata"])
        assert meta["warnings"] == ["backfill", "sync"]
        assert meta["user"] == "ramsay"
        conn.execute("DELETE FROM pipeline_runs WHERE id = ?", (warn_id,))
        conn.commit()
        print("complete_with_warnings verified")

        # --- v3: pipeline_phases ---
        pr_id = create_pipeline_run(conn, "research", "test", run_id="phase-test-001")
        phase_id = create_phase(conn, pr_id, "research")
        assert phase_id is not None
        complete_phase(conn, phase_id, "completed", tokens_used=5000, cost=0.03)
        phase_row = conn.execute("SELECT * FROM pipeline_phases WHERE id = ?", (phase_id,)).fetchone()
        assert phase_row["status"] == "completed"
        assert phase_row["tokens_used"] == 5000
        assert phase_row["cost"] == 0.03
        assert phase_row["completed_at"] is not None
        conn.execute("DELETE FROM pipeline_phases WHERE pipeline_run_id = ?", (pr_id,))
        conn.execute("DELETE FROM pipeline_runs WHERE id = ?", (pr_id,))
        conn.commit()
        print("pipeline_phases (create_phase / complete_phase) verified")

        # --- v3: agent_metrics ---
        log_agent_metrics(conn, "hn-researcher", "2026-03-14", 12, 8000, 0.05, 4500, "opus-4")
        am_row = conn.execute("SELECT * FROM agent_metrics WHERE agent_name = 'hn-researcher'").fetchone()
        assert am_row["findings_count"] == 12
        assert am_row["tokens_used"] == 8000
        assert am_row["cost"] == 0.05
        assert am_row["model_used"] == "opus-4"
        conn.execute("DELETE FROM agent_metrics WHERE agent_name = 'hn-researcher'")
        conn.commit()
        print("log_agent_metrics verified")

        # --- v3: cost_log ---
        log_cost(conn, "2026-03-14", "research", "opus-4", 5000, 3000, 0.08)
        cl_row = conn.execute("SELECT * FROM cost_log WHERE run_date = '2026-03-14'").fetchone()
        assert cl_row["phase"] == "research"
        assert cl_row["cost_usd"] == 0.08
        conn.execute("DELETE FROM cost_log WHERE run_date = '2026-03-14'")
        conn.commit()
        print("log_cost verified")

        # --- v3: alerts ---
        create_alert(conn, "2026-03-14", "high_cost", "Daily cost exceeded $1.00", "critical")
        al_row = conn.execute("SELECT * FROM alerts WHERE run_date = '2026-03-14'").fetchone()
        assert al_row["alert_type"] == "high_cost"
        assert al_row["severity"] == "critical"
        assert al_row["acknowledged"] == 0
        conn.execute("DELETE FROM alerts WHERE run_date = '2026-03-14'")
        conn.commit()
        print("create_alert verified")

        # --- v3: quality_history ---
        log_quality_history(conn, "2026-03-14", "relevance", 0.85, 0.05)
        qh_row = conn.execute("SELECT * FROM quality_history WHERE run_date = '2026-03-14'").fetchone()
        assert qh_row["dimension"] == "relevance"
        assert qh_row["score"] == 0.85
        assert qh_row["delta_from_avg"] == 0.05
        conn.execute("DELETE FROM quality_history WHERE run_date = '2026-03-14'")
        conn.commit()
        print("log_quality_history verified")

        # --- context manager ---
        conn.close()
        with open_traces_db(test_db) as ctx_conn:
            assert ctx_conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            tables_check = ctx_conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            assert tables_check == 14
        print("open_traces_db context manager verified")

    print("\nAll checks passed.")

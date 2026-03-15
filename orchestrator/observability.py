"""Pipeline monitoring and metrics collection.

Provides phase-level tracing, per-agent metrics, cost tracking,
quality regression detection, and iMessage-friendly summaries.

Works against the traces.db schema (pipeline_runs, agent_runs, events,
daily_metrics tables).
"""

import json
import time
from datetime import datetime, timezone


class PipelineMonitor:
    """Observability layer for the research pipeline."""

    # Model pricing per 1M tokens (USD)
    MODEL_PRICING = {
        "haiku": {"input": 0.25, "output": 1.25},
        "sonnet": {"input": 3.0, "output": 15.0},
        "opus": {"input": 15.0, "output": 75.0},
    }

    def __init__(self, traces_conn):
        """Takes traces.db connection.

        Args:
            traces_conn: sqlite3.Connection to traces.db with agent_runs,
                         events, daily_metrics tables available.
        """
        self.conn = traces_conn
        self._ensure_tables()

    def _ensure_tables(self):
        """Create monitoring-specific tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS phase_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT DEFAULT 'running',
                tokens_used INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL,
                run_date TEXT NOT NULL,
                findings_count INTEGER DEFAULT 0,
                tokens_used INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                duration_ms INTEGER DEFAULT 0,
                model_used TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(agent_name, run_date)
            );

            CREATE TABLE IF NOT EXISTS cost_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                phase TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS quality_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT UNIQUE NOT NULL,
                overall_score REAL NOT NULL,
                coverage REAL DEFAULT 0.0,
                dedup REAL DEFAULT 0.0,
                sources REAL DEFAULT 0.0,
                actionability REAL DEFAULT 0.0,
                length_score REAL DEFAULT 0.0,
                topic_balance REAL DEFAULT 0.0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_phase_tracking_run ON phase_tracking(pipeline_run_id);
            CREATE INDEX IF NOT EXISTS idx_agent_metrics_date ON agent_metrics(run_date);
            CREATE INDEX IF NOT EXISTS idx_cost_log_date ON cost_log(run_date);
            CREATE INDEX IF NOT EXISTS idx_quality_history_date ON quality_history(run_date);
        """)
        self.conn.commit()

    def start_phase(self, pipeline_run_id: str, phase_name: str) -> int:
        """Record phase start.

        Args:
            pipeline_run_id: The pipeline run this phase belongs to.
            phase_name: Human-readable phase name (e.g. 'research', 'synthesis', 'send').

        Returns:
            phase_id (int) for use with end_phase.
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "INSERT INTO phase_tracking (pipeline_run_id, phase_name, started_at) "
            "VALUES (?, ?, ?)",
            (pipeline_run_id, phase_name, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def end_phase(
        self,
        phase_id: int,
        status: str = "completed",
        *,
        tokens_used: int = 0,
        cost: float = 0.0,
        error: str | None = None,
    ):
        """Record phase completion with metrics.

        Args:
            phase_id: ID returned by start_phase.
            status: 'completed', 'failed', or 'skipped'.
            tokens_used: Total tokens consumed in this phase.
            cost: Cost in USD for this phase.
            error: Error message if status is 'failed'.
        """
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE phase_tracking SET completed_at=?, status=?, tokens_used=?, cost_usd=?, error=? "
            "WHERE id=?",
            (now, status, tokens_used, cost, error, phase_id),
        )
        self.conn.commit()

    def record_agent_metrics(
        self,
        agent_name: str,
        run_date: str,
        *,
        findings_count: int = 0,
        tokens_used: int = 0,
        cost: float = 0.0,
        duration_ms: int = 0,
        model_used: str | None = None,
    ):
        """Record per-agent metrics. Upserts on (agent_name, run_date).

        Args:
            agent_name: Agent identifier (e.g. 'hn-researcher').
            run_date: ISO date string (e.g. '2026-03-14').
            findings_count: Number of findings produced.
            tokens_used: Total tokens consumed.
            cost: Cost in USD.
            duration_ms: Wall-clock duration in milliseconds.
            model_used: Model identifier (e.g. 'opus', 'sonnet').
        """
        self.conn.execute(
            "INSERT INTO agent_metrics (agent_name, run_date, findings_count, tokens_used, "
            "cost_usd, duration_ms, model_used) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(agent_name, run_date) DO UPDATE SET "
            "findings_count=excluded.findings_count, tokens_used=excluded.tokens_used, "
            "cost_usd=excluded.cost_usd, duration_ms=excluded.duration_ms, "
            "model_used=excluded.model_used",
            (agent_name, run_date, findings_count, tokens_used, cost, duration_ms, model_used),
        )
        self.conn.commit()

    def log_cost(
        self,
        run_date: str,
        phase: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ):
        """Log cost entry. Calculate cost_usd based on model pricing.

        Args:
            run_date: ISO date string.
            phase: Pipeline phase (e.g. 'research', 'synthesis', 'social').
            model: Model name key (e.g. 'opus', 'sonnet', 'haiku').
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens consumed.
        """
        pricing = self.MODEL_PRICING.get(model.lower(), {"input": 0.0, "output": 0.0})
        cost_usd = (
            (input_tokens / 1_000_000) * pricing["input"]
            + (output_tokens / 1_000_000) * pricing["output"]
        )

        self.conn.execute(
            "INSERT INTO cost_log (run_date, phase, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_date, phase, model, input_tokens, output_tokens, round(cost_usd, 6)),
        )
        self.conn.commit()

    def record_quality(self, run_date: str, scores: dict):
        """Store quality evaluation scores for a run date.

        Args:
            run_date: ISO date string.
            scores: Dict from NewsletterEvaluator.evaluate() with keys:
                    overall, coverage, dedup, sources, actionability, length, topic_balance.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO quality_history "
            "(run_date, overall_score, coverage, dedup, sources, actionability, length_score, topic_balance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_date,
                scores.get("overall", 0.0),
                scores.get("coverage", 0.0),
                scores.get("dedup", 0.0),
                scores.get("sources", 0.0),
                scores.get("actionability", 0.0),
                scores.get("length", 0.0),
                scores.get("topic_balance", 0.0),
            ),
        )
        self.conn.commit()

    def check_quality_regression(
        self,
        run_date: str,
        threshold: float = 0.1,
    ) -> dict | None:
        """Compare today's quality to 7-day average.

        Returns alert dict if regression detected (score dropped by more than
        threshold below the 7-day average), or None if quality is stable.

        Args:
            run_date: ISO date string for today's run.
            threshold: Minimum drop from average to trigger alert (default 0.1).

        Returns:
            None if no regression, or dict with keys:
                today_score, avg_7d, delta, dimensions_regressed (list of dimension names).
        """
        # Get today's score
        row = self.conn.execute(
            "SELECT * FROM quality_history WHERE run_date = ?", (run_date,)
        ).fetchone()
        if not row:
            return None

        today_score = row["overall_score"]

        # Get 7-day average (excluding today)
        avg_row = self.conn.execute(
            "SELECT AVG(overall_score) AS avg_score, COUNT(*) AS cnt "
            "FROM quality_history WHERE run_date < ? "
            "ORDER BY run_date DESC LIMIT 7",
            (run_date,),
        ).fetchone()

        if not avg_row or avg_row["cnt"] == 0 or avg_row["avg_score"] is None:
            return None  # Not enough history

        avg_7d = avg_row["avg_score"]
        delta = today_score - avg_7d

        if delta >= -threshold:
            return None  # No regression

        # Find which dimensions regressed
        dimensions = ["coverage", "dedup", "sources", "actionability", "length_score", "topic_balance"]
        regressed = []

        for dim in dimensions:
            dim_avg_row = self.conn.execute(
                f"SELECT AVG({dim}) AS avg_val FROM quality_history "
                "WHERE run_date < ? ORDER BY run_date DESC LIMIT 7",
                (run_date,),
            ).fetchone()

            if dim_avg_row and dim_avg_row["avg_val"] is not None:
                dim_today = row[dim]
                dim_avg = dim_avg_row["avg_val"]
                if dim_today < dim_avg - threshold:
                    display_name = dim.replace("_", " ").replace("length score", "length")
                    regressed.append(display_name)

        return {
            "today_score": round(today_score, 3),
            "avg_7d": round(avg_7d, 3),
            "delta": round(delta, 3),
            "dimensions_regressed": regressed,
        }

    def generate_summary(self, run_date: str) -> str:
        """Generate iMessage-ready summary string.

        Format: '87 findings | $1.34 | 18 min | Quality: 0.85 | 2 warnings'

        Args:
            run_date: ISO date string.

        Returns:
            Single-line summary string suitable for iMessage notification.
        """
        # Total findings from agent_metrics
        row = self.conn.execute(
            "SELECT SUM(findings_count) AS total FROM agent_metrics WHERE run_date = ?",
            (run_date,),
        ).fetchone()
        findings = row["total"] if row and row["total"] else 0

        # Total cost from cost_log
        row = self.conn.execute(
            "SELECT SUM(cost_usd) AS total FROM cost_log WHERE run_date = ?",
            (run_date,),
        ).fetchone()
        cost = row["total"] if row and row["total"] else 0.0

        # Total duration from agent_metrics (max since agents run in parallel)
        row = self.conn.execute(
            "SELECT SUM(duration_ms) AS total_ms FROM agent_metrics WHERE run_date = ?",
            (run_date,),
        ).fetchone()
        duration_ms = row["total_ms"] if row and row["total_ms"] else 0
        duration_min = round(duration_ms / 60_000)

        # Quality score
        row = self.conn.execute(
            "SELECT overall_score FROM quality_history WHERE run_date = ?",
            (run_date,),
        ).fetchone()
        quality = row["overall_score"] if row else None

        # Count warnings (failed phases)
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM phase_tracking "
            "WHERE pipeline_run_id LIKE ? AND status = 'failed'",
            (f"%{run_date}%",),
        ).fetchone()
        warnings = row["cnt"] if row else 0

        # Build summary
        parts = [
            f"{findings} findings",
            f"${cost:.2f}",
            f"{duration_min} min",
        ]

        if quality is not None:
            parts.append(f"Quality: {quality:.2f}")

        if warnings > 0:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")

        return " | ".join(parts)

    def get_daily_cost(self, run_date: str) -> dict:
        """Get cost breakdown by model and phase for a given date.

        Returns:
            Dict with keys: total_usd, by_model (dict), by_phase (dict),
            total_input_tokens, total_output_tokens.
        """
        rows = self.conn.execute(
            "SELECT phase, model, input_tokens, output_tokens, cost_usd "
            "FROM cost_log WHERE run_date = ?",
            (run_date,),
        ).fetchall()

        by_model: dict[str, float] = {}
        by_phase: dict[str, float] = {}
        total_input = 0
        total_output = 0
        total_usd = 0.0

        for row in rows:
            model = row["model"]
            phase = row["phase"]
            cost = row["cost_usd"]

            by_model[model] = by_model.get(model, 0.0) + cost
            by_phase[phase] = by_phase.get(phase, 0.0) + cost
            total_input += row["input_tokens"]
            total_output += row["output_tokens"]
            total_usd += cost

        return {
            "total_usd": round(total_usd, 4),
            "by_model": {k: round(v, 4) for k, v in by_model.items()},
            "by_phase": {k: round(v, 4) for k, v in by_phase.items()},
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
        }


if __name__ == "__main__":
    import sqlite3

    # Create in-memory traces DB
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    monitor = PipelineMonitor(conn)
    run_date = "2026-03-14"
    pipeline_run_id = "test-run-001"

    # --- AC #1: Phase tracking ---
    phase_id = monitor.start_phase(pipeline_run_id, "research")
    assert isinstance(phase_id, int) and phase_id > 0
    monitor.end_phase(phase_id, "completed", tokens_used=50000, cost=0.75)

    row = conn.execute("SELECT * FROM phase_tracking WHERE id = ?", (phase_id,)).fetchone()
    assert row["status"] == "completed"
    assert row["tokens_used"] == 50000
    print("AC #1: Phase tracking verified")

    # --- AC #2: Agent metrics ---
    monitor.record_agent_metrics(
        "hn-researcher", run_date,
        findings_count=15, tokens_used=30000, cost=0.45,
        duration_ms=120000, model_used="opus",
    )
    monitor.record_agent_metrics(
        "arxiv-scanner", run_date,
        findings_count=12, tokens_used=25000, cost=0.38,
        duration_ms=90000, model_used="opus",
    )

    row = conn.execute(
        "SELECT * FROM agent_metrics WHERE agent_name = ? AND run_date = ?",
        ("hn-researcher", run_date),
    ).fetchone()
    assert row["findings_count"] == 15
    assert row["model_used"] == "opus"
    print("AC #2: Agent metrics verified")

    # --- AC #2b: Upsert behavior ---
    monitor.record_agent_metrics(
        "hn-researcher", run_date,
        findings_count=18, tokens_used=35000, cost=0.52,
        duration_ms=130000, model_used="opus",
    )
    row = conn.execute(
        "SELECT * FROM agent_metrics WHERE agent_name = ? AND run_date = ?",
        ("hn-researcher", run_date),
    ).fetchone()
    assert row["findings_count"] == 18, "Upsert should update findings_count"
    count = conn.execute(
        "SELECT COUNT(*) FROM agent_metrics WHERE agent_name = ? AND run_date = ?",
        ("hn-researcher", run_date),
    ).fetchone()[0]
    assert count == 1, "Should have exactly 1 row after upsert"
    print("AC #2b: Agent metrics upsert verified")

    # --- AC #3: Cost logging ---
    monitor.log_cost(run_date, "research", "opus", 100000, 20000)
    monitor.log_cost(run_date, "synthesis", "sonnet", 50000, 10000)
    monitor.log_cost(run_date, "social", "haiku", 20000, 5000)

    costs = monitor.get_daily_cost(run_date)
    assert costs["total_usd"] > 0
    assert "opus" in costs["by_model"]
    assert "research" in costs["by_phase"]
    # Verify opus cost: (100000/1M)*15 + (20000/1M)*75 = 1.5 + 1.5 = 3.0
    assert abs(costs["by_model"]["opus"] - 3.0) < 0.01, f"Opus cost: {costs['by_model']['opus']}"
    print(f"AC #3: Cost logging verified (total: ${costs['total_usd']:.2f})")

    # --- AC #4: Quality regression detection ---
    # Store 7 days of history
    for i in range(7):
        day = f"2026-03-{7 + i:02d}"
        monitor.record_quality(day, {
            "overall": 0.85,
            "coverage": 0.9, "dedup": 0.95, "sources": 0.8,
            "actionability": 0.7, "length": 0.85, "topic_balance": 0.8,
        })

    # Store today with a regression
    monitor.record_quality(run_date, {
        "overall": 0.65,
        "coverage": 0.5, "dedup": 0.95, "sources": 0.8,
        "actionability": 0.3, "length": 0.85, "topic_balance": 0.8,
    })

    alert = monitor.check_quality_regression(run_date, threshold=0.1)
    assert alert is not None, "Should detect regression"
    assert alert["today_score"] < alert["avg_7d"]
    assert alert["delta"] < 0
    print(f"AC #4: Quality regression detected (delta: {alert['delta']:.3f})")

    # No regression when score is similar
    monitor.record_quality("2026-03-15", {"overall": 0.84, "coverage": 0.9, "dedup": 0.95,
                                           "sources": 0.8, "actionability": 0.7,
                                           "length": 0.85, "topic_balance": 0.8})
    no_alert = monitor.check_quality_regression("2026-03-15", threshold=0.1)
    assert no_alert is None, "Should not detect regression for stable score"
    print("AC #4b: No false positive regression")

    # --- AC #5: Summary generation ---
    summary = monitor.generate_summary(run_date)
    assert "findings" in summary
    assert "$" in summary
    assert "min" in summary
    assert "Quality" in summary
    print(f"AC #5: Summary: {summary}")

    # --- AC #6: Phase failure tracking ---
    fail_id = monitor.start_phase(pipeline_run_id, "sync")
    monitor.end_phase(fail_id, "failed", error="Connection timeout")
    row = conn.execute("SELECT * FROM phase_tracking WHERE id = ?", (fail_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["error"] == "Connection timeout"
    print("AC #6: Phase failure tracking verified")

    conn.close()
    print("\nAll observability.py checks passed.")

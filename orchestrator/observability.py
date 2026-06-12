"""Pipeline monitoring and metrics collection.

Provides phase-level tracing, per-agent metrics, cost tracking,
quality regression detection, and pipeline summaries.

Works against the traces.db schema (pipeline_runs, agent_runs, events,
daily_metrics tables).
"""

import json
import time
from datetime import datetime, timezone


class PipelineMonitor:
    """Observability layer for the research pipeline."""

    # Model pricing per 1M tokens (USD)
    def __init__(self, traces_conn):
        """Takes traces.db connection.

        Args:
            traces_conn: sqlite3.Connection to traces.db with agent_runs,
                         events, daily_metrics tables available.
        """
        self.conn = traces_conn
        self._ensure_tables()

    def _ensure_tables(self):
        """Create monitoring-specific tables if they don't exist.

        Also migrates tables from older schemas when column mismatches are
        detected (e.g. ``cost`` → ``cost_usd``, row-per-dimension
        ``quality_history`` → row-per-date with individual dimension columns).
        """
        self._migrate_agent_metrics()
        self._migrate_quality_history()

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
            CREATE INDEX IF NOT EXISTS idx_quality_history_date ON quality_history(run_date);
        """)
        self.conn.commit()

    # ── Schema migrations ──────────────────────────────────────────────

    def _migrate_agent_metrics(self):
        """Migrate agent_metrics from v1 schema if needed.

        v1 had ``cost REAL`` instead of ``cost_usd REAL`` and was missing
        ``created_at`` and the UNIQUE(agent_name, run_date) constraint.
        We detect this by checking whether the ``cost_usd`` column exists.
        If the old table is present with the wrong schema, we rename it and
        let _ensure_tables() recreate the correct version, then copy data over.
        """
        columns = self._get_column_names("agent_metrics")
        if columns is None:
            return  # table doesn't exist yet — will be created fresh

        if "cost_usd" in columns:
            return  # already on current schema

        # Old schema detected — migrate
        self.conn.executescript("""
            ALTER TABLE agent_metrics RENAME TO _agent_metrics_v1;
            DROP INDEX IF EXISTS idx_agent_metrics_date;
        """)

        # Create new table
        self.conn.execute("""
            CREATE TABLE agent_metrics (
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
            )
        """)

        # Copy data from old table (mapping cost → cost_usd)
        self.conn.execute("""
            INSERT OR IGNORE INTO agent_metrics
                (agent_name, run_date, findings_count, tokens_used, cost_usd, duration_ms, model_used)
            SELECT agent_name, run_date, findings_count, tokens_used,
                   COALESCE(cost, 0.0), duration_ms, model_used
            FROM _agent_metrics_v1
        """)

        self.conn.execute("DROP TABLE _agent_metrics_v1")
        self.conn.commit()

    def _migrate_quality_history(self):
        """Migrate quality_history from v1 schema if needed.

        v1 stored one row per (run_date, dimension) pair with columns:
            id, run_date, dimension, score, delta_from_avg
        v2 stores one row per run_date with individual dimension columns:
            id, run_date, overall_score, coverage, dedup, sources,
            actionability, length_score, topic_balance, created_at
        We detect v1 by checking for the ``dimension`` column.
        """
        columns = self._get_column_names("quality_history")
        if columns is None:
            return  # table doesn't exist yet — will be created fresh

        if "overall_score" in columns:
            return  # already on current schema

        # Old schema detected — migrate
        self.conn.executescript("""
            ALTER TABLE quality_history RENAME TO _quality_history_v1;
            DROP INDEX IF EXISTS idx_quality_history_date;
        """)

        # Create new table
        self.conn.execute("""
            CREATE TABLE quality_history (
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
            )
        """)

        # Pivot old row-per-dimension data into new row-per-date format.
        # Only migrate dates that have an 'overall' dimension row.
        if "dimension" in columns:
            dates = self.conn.execute(
                "SELECT DISTINCT run_date FROM _quality_history_v1"
            ).fetchall()

            for (run_date,) in dates:
                rows = self.conn.execute(
                    "SELECT dimension, score FROM _quality_history_v1 WHERE run_date = ?",
                    (run_date,),
                ).fetchall()
                dim_map = {r["dimension"]: r["score"] for r in rows} if rows else {}
                # Only insert if there's meaningful data
                if dim_map:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO quality_history "
                        "(run_date, overall_score, coverage, dedup, sources, "
                        "actionability, length_score, topic_balance) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            run_date,
                            dim_map.get("overall", 0.0),
                            dim_map.get("coverage", 0.0),
                            dim_map.get("dedup", 0.0),
                            dim_map.get("sources", 0.0),
                            dim_map.get("actionability", 0.0),
                            dim_map.get("length", 0.0),
                            dim_map.get("topic_balance", 0.0),
                        ),
                    )

        self.conn.execute("DROP TABLE _quality_history_v1")
        self.conn.commit()

    def _get_column_names(self, table_name: str) -> list[str] | None:
        """Return column names for a table, or None if it doesn't exist."""
        try:
            rows = self.conn.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()
            if not rows:
                return None
            # Handle both tuple and Row results
            return [r[1] if isinstance(r, tuple) else r["name"] for r in rows]
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Failed to get column names: {e}")
            return None

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
        """Generate pipeline summary string.

        Format: '87 findings | $1.34 | 18 min | Quality: 0.85 | 2 warnings'

        Args:
            run_date: ISO date string.

        Returns:
            Single-line summary string suitable for Slack notification.
        """
        # Total findings from agent_metrics
        row = self.conn.execute(
            "SELECT SUM(findings_count) AS total FROM agent_metrics WHERE run_date = ?",
            (run_date,),
        ).fetchone()
        findings = row["total"] if row and row["total"] else 0

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
            f"{duration_min} min",
        ]

        if quality is not None:
            parts.append(f"Quality: {quality:.2f}")

        if warnings > 0:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")

        return " | ".join(parts)


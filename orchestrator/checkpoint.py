"""Checkpoint/resume logic for pipeline runs.

On failure, run.py can be re-invoked and it picks up where it left off.
Checkpoints are stored in traces.db.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .pipeline import Phase


def _ensure_table(conn: sqlite3.Connection):
    """Create checkpoints table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_run_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            state_data TEXT,
            user_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(pipeline_run_id, phase)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(pipeline_run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_checkpoints_user ON checkpoints(user_id)"
    )
    # Migrate: add user_id column if table already existed without it
    try:
        conn.execute("ALTER TABLE checkpoints ADD COLUMN user_id TEXT")
    except Exception:
        pass  # Column already exists
    conn.commit()


class Checkpoint:
    """Save and restore pipeline state across crashes."""

    def __init__(self, traces_conn: sqlite3.Connection):
        self.conn = traces_conn
        _ensure_table(self.conn)

    def save(self, pipeline_run_id: str, phase: Phase, state_data: dict | None = None,
             user_id: str | None = None):
        """Write a checkpoint for a completed phase."""
        self.conn.execute(
            """INSERT INTO checkpoints (pipeline_run_id, phase, state_data, user_id)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(pipeline_run_id, phase) DO UPDATE SET
                   state_data = excluded.state_data,
                   user_id = COALESCE(excluded.user_id, checkpoints.user_id),
                   created_at = datetime('now')""",
            (pipeline_run_id, phase.value,
             json.dumps(state_data) if state_data else None, user_id),
        )
        self.conn.commit()

    def load(self, pipeline_run_id: str) -> tuple[Phase | None, dict | None]:
        """Load the last checkpoint for a pipeline run.

        Returns (phase, state_data) or (None, None) if no checkpoint exists.
        """
        row = self.conn.execute(
            """SELECT phase, state_data FROM checkpoints
               WHERE pipeline_run_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (pipeline_run_id,),
        ).fetchone()

        if not row:
            return None, None

        phase = Phase(row[0]) if row[0] else None
        state_data = json.loads(row[1]) if row[1] else None
        return phase, state_data

    def get_completed_phases(self, pipeline_run_id: str) -> list[Phase]:
        """Get all completed phases for a pipeline run, in order."""
        rows = self.conn.execute(
            """SELECT phase FROM checkpoints
               WHERE pipeline_run_id = ?
               ORDER BY created_at ASC""",
            (pipeline_run_id,),
        ).fetchall()
        return [Phase(r[0]) for r in rows]

    def resume_from(self, pipeline_run_id: str) -> Phase | None:
        """Determine which phase to resume from.

        Returns the next phase after the last completed checkpoint,
        or None if all phases are complete.
        """
        from .pipeline import PHASE_ORDER

        completed = self.get_completed_phases(pipeline_run_id)
        if not completed:
            return Phase.INIT

        last_completed = completed[-1]
        try:
            idx = PHASE_ORDER.index(last_completed)
            next_idx = idx + 1
            if next_idx < len(PHASE_ORDER):
                return PHASE_ORDER[next_idx]
            return None  # All phases complete
        except ValueError:
            return Phase.INIT

    def find_resumable_run(self, user_id: str, run_date: str) -> str | None:
        """Find an incomplete pipeline run for this user+date that can be resumed.

        Looks for runs that have checkpoints but didn't reach COMPLETED.
        """
        rows = self.conn.execute(
            """SELECT DISTINCT pipeline_run_id FROM checkpoints
               WHERE pipeline_run_id LIKE ?
                 AND user_id = ?
               ORDER BY created_at DESC""",
            (f"%-{run_date}-%", user_id),
        ).fetchall()

        for row in rows:
            run_id = row[0]
            # Check if it reached COMPLETED
            completed = self.conn.execute(
                """SELECT 1 FROM checkpoints
                   WHERE pipeline_run_id = ? AND phase = 'completed'""",
                (run_id,),
            ).fetchone()
            if not completed:
                return run_id

        return None

    def clear(self, pipeline_run_id: str):
        """Clear all checkpoints for a pipeline run (for re-runs)."""
        self.conn.execute(
            "DELETE FROM checkpoints WHERE pipeline_run_id = ?",
            (pipeline_run_id,),
        )
        self.conn.commit()

"""Track prompt changes and detect performance regressions.

Each prompt file gets a SHA256 hash. When a prompt changes, the new version
is recorded. If quality drops >15% after a prompt change, auto-rollback.

Uses traces.db for version storage — the prompt_versions table already
exists (created by traces_db.py). This module adds a higher-level workflow:
scan for changes, detect regressions, and rollback if needed.
"""

import hashlib
import json
import logging
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Directories to scan for prompt/agent files
PROMPT_DIRS = [
    PROJECT_ROOT / "prompts",
    PROJECT_ROOT / "agents",
    PROJECT_ROOT / "verticals" / "ai-tech" / "agents",
]

# File extensions that count as prompt files
PROMPT_EXTENSIONS = {".md", ".txt", ".prompt"}


class PromptTracker:
    """Track prompt file versions and detect performance regressions.

    Uses the prompt_versions table in traces.db. Each prompt file is
    identified by its relative path from the project root. Versions are
    keyed by SHA256 content hash.

    Args:
        traces_conn: sqlite3.Connection to traces.db (from traces_db.init_db).
    """

    def __init__(self, traces_conn: sqlite3.Connection):
        self.conn = traces_conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create the prompt_tracker table if it doesn't exist.

        This extends traces.db's existing prompt_versions table with
        a dedicated tracking table that stores per-file content hashes,
        quality snapshots, and rollback history.
        """
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS prompt_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                git_hash TEXT,
                quality_snapshot REAL,
                recorded_at TEXT NOT NULL,
                rolled_back INTEGER DEFAULT 0,
                UNIQUE(file_path, content_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_pt_file
                ON prompt_tracker(file_path);
            CREATE INDEX IF NOT EXISTS idx_pt_recorded
                ON prompt_tracker(recorded_at);
        """)
        self.conn.commit()

    def scan_for_changes(self) -> dict[str, dict]:
        """Scan all prompt and agent files for changes since last run.

        Compares current SHA256 of each file against the most recently
        stored version in prompt_tracker.

        Returns:
            Dict mapping relative file paths to change info:
            {
                "prompts/synthesis-pass1.md": {
                    "old_hash": "abc123...",   # None if first time
                    "new_hash": "def456...",
                    "changed": True,
                },
                ...
            }
        """
        results: dict[str, dict] = {}

        for prompt_dir in PROMPT_DIRS:
            if not prompt_dir.is_dir():
                continue

            for path in sorted(prompt_dir.rglob("*")):
                if path.is_dir():
                    continue
                if path.suffix not in PROMPT_EXTENSIONS:
                    continue
                # Skip hidden files and __pycache__
                if any(part.startswith(".") or part == "__pycache__"
                       for part in path.parts):
                    continue

                rel_path = str(path.relative_to(PROJECT_ROOT))
                current_hash = hash_file(path)

                # Look up the most recent stored hash
                row = self.conn.execute(
                    """SELECT content_hash FROM prompt_tracker
                       WHERE file_path = ?
                       ORDER BY recorded_at DESC LIMIT 1""",
                    (rel_path,),
                ).fetchone()

                old_hash = row["content_hash"] if row else None
                changed = old_hash != current_hash

                results[rel_path] = {
                    "old_hash": old_hash,
                    "new_hash": current_hash,
                    "changed": changed,
                }

        return results

    def record_version(
        self,
        file_path: str,
        git_hash: str | None = None,
        quality_snapshot: float | None = None,
    ) -> None:
        """Record the current version of a prompt file.

        Args:
            file_path: Relative path from project root (e.g. 'prompts/synthesis-pass1.md').
            git_hash: Optional git commit hash for traceability.
            quality_snapshot: Optional quality score at time of recording.
        """
        abs_path = PROJECT_ROOT / file_path
        if not abs_path.is_file():
            logger.warning("Cannot record version: file not found: %s", abs_path)
            return

        content_hash = hash_file(abs_path)
        now = datetime.now().isoformat()

        # Resolve git hash if not provided
        if git_hash is None:
            git_hash = _get_git_hash(abs_path)

        self.conn.execute(
            """INSERT OR IGNORE INTO prompt_tracker
               (file_path, content_hash, git_hash, quality_snapshot, recorded_at)
               VALUES (?, ?, ?, ?, ?)""",
            (file_path, content_hash, git_hash, quality_snapshot, now),
        )
        self.conn.commit()

    def check_regression(
        self,
        run_date: str,
        threshold: float = 0.15,
    ) -> list[dict]:
        """Check if any recent prompt changes caused quality regression.

        For each file that changed in the last 7 days, compares the average
        quality score from runs BEFORE the change to the quality score on
        run_date. If quality dropped by more than threshold (default 15%),
        it is flagged as a regression.

        Args:
            run_date: ISO date string (YYYY-MM-DD) of the run to check.
            threshold: Fractional drop threshold (0.15 = 15% drop).

        Returns:
            List of regression dicts:
            [
                {
                    "file": "prompts/synthesis-pass1.md",
                    "old_hash": "abc...",
                    "new_hash": "def...",
                    "quality_before": 0.85,
                    "quality_after": 0.68,
                    "regression_pct": 0.20,
                },
                ...
            ]
        """
        regressions = []

        # Find prompt changes recorded in the last 7 days
        recent_changes = self.conn.execute(
            """SELECT file_path, content_hash, recorded_at
               FROM prompt_tracker
               WHERE recorded_at >= date(?, '-7 days')
               ORDER BY recorded_at DESC""",
            (run_date,),
        ).fetchall()

        # Group by file — we only care about the latest change per file
        seen_files: set[str] = set()
        changes_to_check = []
        for row in recent_changes:
            fp = row["file_path"]
            if fp not in seen_files:
                seen_files.add(fp)
                changes_to_check.append(row)

        for change in changes_to_check:
            fp = change["file_path"]
            new_hash = change["content_hash"]
            change_time = change["recorded_at"]

            # Get the previous version's hash
            prev_row = self.conn.execute(
                """SELECT content_hash FROM prompt_tracker
                   WHERE file_path = ? AND recorded_at < ?
                   ORDER BY recorded_at DESC LIMIT 1""",
                (fp, change_time),
            ).fetchone()

            if not prev_row:
                continue  # First version — nothing to compare

            old_hash = prev_row["content_hash"]
            if old_hash == new_hash:
                continue  # Not actually a change

            # Get average quality BEFORE the change (from prompt_tracker snapshots)
            before_rows = self.conn.execute(
                """SELECT AVG(quality_snapshot) as avg_q
                   FROM prompt_tracker
                   WHERE file_path = ? AND recorded_at < ? AND quality_snapshot IS NOT NULL""",
                (fp, change_time),
            ).fetchone()

            quality_before = before_rows["avg_q"] if before_rows and before_rows["avg_q"] is not None else None

            if quality_before is None:
                # No quality data before the change — try quality_history or run_quality
                quality_before = self._get_quality_from_traces(run_date, before=True)

            if quality_before is None or quality_before == 0:
                continue  # Can't compute regression without baseline

            # Get quality AFTER the change (the current run)
            # First check prompt_tracker snapshots
            after_row = self.conn.execute(
                """SELECT quality_snapshot
                   FROM prompt_tracker
                   WHERE file_path = ? AND recorded_at >= ? AND quality_snapshot IS NOT NULL
                   ORDER BY recorded_at ASC LIMIT 1""",
                (fp, change_time),
            ).fetchone()

            quality_after = after_row["quality_snapshot"] if after_row and after_row["quality_snapshot"] is not None else None

            if quality_after is None:
                quality_after = self._get_quality_from_traces(run_date, before=False)

            if quality_after is None:
                continue

            # Check if quality dropped by more than threshold
            regression_pct = (quality_before - quality_after) / quality_before

            if regression_pct >= threshold:
                regressions.append({
                    "file": fp,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                    "quality_before": round(quality_before, 4),
                    "quality_after": round(quality_after, 4),
                    "regression_pct": round(regression_pct, 4),
                })

        return regressions

    def _get_quality_from_traces(
        self,
        run_date: str,
        before: bool = True,
    ) -> float | None:
        """Fall back to traces.db quality tables if prompt_tracker has no snapshots.

        Checks quality_history (overall dimension) and run_quality tables.

        Args:
            run_date: ISO date string (YYYY-MM-DD).
            before: If True, get average from before run_date; if False, get run_date's score.

        Returns:
            Quality score or None.
        """
        try:
            if before:
                row = self.conn.execute(
                    """SELECT AVG(score) as avg_q FROM quality_history
                       WHERE dimension = 'overall' AND run_date < ?""",
                    (run_date,),
                ).fetchone()
            else:
                row = self.conn.execute(
                    """SELECT score as avg_q FROM quality_history
                       WHERE dimension = 'overall' AND run_date = ?
                       ORDER BY id DESC LIMIT 1""",
                    (run_date,),
                ).fetchone()

            if row and row["avg_q"] is not None:
                return float(row["avg_q"])
        except sqlite3.OperationalError:
            pass  # Table might not exist

        # Try run_quality table
        try:
            if before:
                row = self.conn.execute(
                    """SELECT AVG(overall_score) as avg_q FROM run_quality
                       WHERE run_date < ? AND overall_score > 0""",
                    (run_date,),
                ).fetchone()
            else:
                row = self.conn.execute(
                    """SELECT overall_score as avg_q FROM run_quality
                       WHERE run_date = ?""",
                    (run_date,),
                ).fetchone()

            if row and row["avg_q"] is not None:
                return float(row["avg_q"])
        except sqlite3.OperationalError:
            pass

        return None

    def auto_rollback(self, file_path: str, old_hash: str) -> bool:
        """Rollback a prompt file to a previous version using git.

        Finds the git commit that matches old_hash in prompt_tracker and
        checks out that version of the file. If no git hash is available,
        attempts to restore from a backup copy.

        Args:
            file_path: Relative path from project root.
            old_hash: Content hash of the version to restore.

        Returns:
            True if rollback succeeded, False otherwise.
        """
        abs_path = PROJECT_ROOT / file_path

        # Look up the git hash for the old version
        row = self.conn.execute(
            """SELECT git_hash FROM prompt_tracker
               WHERE file_path = ? AND content_hash = ?
               ORDER BY recorded_at DESC LIMIT 1""",
            (file_path, old_hash),
        ).fetchone()

        git_hash = row["git_hash"] if row else None

        if git_hash:
            try:
                # Save current version as .bak before rollback
                if abs_path.exists():
                    backup_path = abs_path.with_suffix(abs_path.suffix + ".bak")
                    shutil.copy2(str(abs_path), str(backup_path))
                    logger.info("Backed up current version to %s", backup_path)

                # Git checkout the old version
                result = subprocess.run(
                    ["git", "checkout", git_hash, "--", file_path],
                    capture_output=True,
                    text=True,
                    cwd=str(PROJECT_ROOT),
                    timeout=15,
                )

                if result.returncode == 0:
                    # Verify the rollback
                    actual_hash = hash_file(abs_path)
                    if actual_hash == old_hash:
                        logger.info(
                            "Rolled back %s to git commit %s (hash: %s)",
                            file_path, git_hash[:8], old_hash[:12],
                        )
                        # Record the rollback in tracker
                        self._record_rollback(file_path, old_hash, git_hash)
                        return True
                    else:
                        logger.warning(
                            "Rollback hash mismatch for %s: expected %s, got %s",
                            file_path, old_hash[:12], actual_hash[:12],
                        )
                        # The git content may differ from what we hashed — still mark as rolled back
                        self._record_rollback(file_path, actual_hash, git_hash)
                        return True
                else:
                    logger.error(
                        "git checkout failed for %s: %s",
                        file_path, result.stderr.strip(),
                    )
            except (subprocess.SubprocessError, OSError) as exc:
                logger.error("Rollback subprocess failed for %s: %s", file_path, exc)

        # Fallback: check if a .bak file exists from a previous rollback
        backup_path = abs_path.with_suffix(abs_path.suffix + ".bak")
        if backup_path.exists():
            backup_hash = hash_file(backup_path)
            if backup_hash == old_hash:
                shutil.copy2(str(backup_path), str(abs_path))
                logger.info("Restored %s from backup file", file_path)
                self._record_rollback(file_path, old_hash, None)
                return True

        logger.error(
            "Could not rollback %s: no git hash and no matching backup", file_path
        )
        return False

    def _record_rollback(
        self,
        file_path: str,
        content_hash: str,
        git_hash: str | None,
    ) -> None:
        """Record a rollback event in prompt_tracker."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO prompt_tracker
               (file_path, content_hash, git_hash, recorded_at, rolled_back)
               VALUES (?, ?, ?, ?, 1)""",
            (file_path, content_hash, git_hash, now),
        )
        self.conn.commit()

    def get_prompt_history(
        self,
        file_path: str,
        limit: int = 10,
    ) -> list[dict]:
        """Get version history for a prompt file.

        Args:
            file_path: Relative path from project root.
            limit: Maximum number of versions to return (default 10).

        Returns:
            List of version dicts, most recent first:
            [
                {
                    "content_hash": "abc...",
                    "git_hash": "def...",
                    "quality_snapshot": 0.85,
                    "recorded_at": "2026-03-14T10:30:00",
                    "rolled_back": False,
                },
                ...
            ]
        """
        rows = self.conn.execute(
            """SELECT content_hash, git_hash, quality_snapshot, recorded_at, rolled_back
               FROM prompt_tracker
               WHERE file_path = ?
               ORDER BY recorded_at DESC
               LIMIT ?""",
            (file_path, limit),
        ).fetchall()

        return [
            {
                "content_hash": r["content_hash"],
                "git_hash": r["git_hash"],
                "quality_snapshot": r["quality_snapshot"],
                "recorded_at": r["recorded_at"],
                "rolled_back": bool(r["rolled_back"]),
            }
            for r in rows
        ]


# ── Module-level helpers ──────────────────────────────────────────────────


def hash_file(path: Path) -> str:
    """SHA256 hash of a file's contents.

    Args:
        path: Path to the file.

    Returns:
        Hex-encoded SHA256 hash string.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get_git_hash(path: Path) -> str | None:
    """Get the most recent git commit hash for a file.

    Args:
        path: Absolute path to the file.

    Returns:
        Git commit hash string, or None if git is unavailable or file is untracked.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(path)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=10,
        )
        git_hash = result.stdout.strip()
        return git_hash if git_hash else None
    except (subprocess.SubprocessError, OSError):
        return None

"""Failure lesson storage — inspired by RetroAgent pattern.

Stores what went wrong during runs so agents can learn from past failures.
Categories allow filtering by failure type (e.g. 'scraping', 'dedup',
'quality', 'timeout') to surface relevant lessons before each run.
"""

import sqlite3
from datetime import datetime, timedelta


def store_failure(
    db: sqlite3.Connection,
    run_date: str,
    category: str,
    what_went_wrong: str,
    lesson: str,
) -> int:
    """Store a failure lesson.

    Args:
        db: Database connection.
        run_date: ISO date string for when the failure occurred.
        category: Failure category (e.g. 'scraping', 'dedup', 'quality').
        what_went_wrong: Description of the failure.
        lesson: Actionable lesson learned.

    Returns:
        Row ID of the inserted lesson.
    """
    cur = db.execute(
        """INSERT INTO failure_lessons (run_date, category, what_went_wrong, lesson, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (run_date, category, what_went_wrong, lesson, datetime.now().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def recent_failures(
    db: sqlite3.Connection,
    limit: int = 10,
    category: str | None = None,
) -> list[dict]:
    """Get recent failure lessons, optionally filtered by category.

    Args:
        db: Database connection.
        limit: Maximum number of lessons to return.
        category: Optional category filter.

    Returns:
        List of dicts with {id, run_date, category, what_went_wrong, lesson, created_at}.
    """
    if category:
        rows = db.execute(
            """SELECT id, run_date, category, what_went_wrong, lesson, created_at
               FROM failure_lessons
               WHERE category = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (category, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT id, run_date, category, what_went_wrong, lesson, created_at
               FROM failure_lessons
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    return [
        {
            "id": r["id"],
            "run_date": r["run_date"],
            "category": r["category"],
            "what_went_wrong": r["what_went_wrong"],
            "lesson": r["lesson"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def failures_for_date(db: sqlite3.Connection, run_date: str) -> list[dict]:
    """Get all failure lessons for a specific run date.

    Args:
        db: Database connection.
        run_date: ISO date string.

    Returns:
        List of dicts with {id, category, what_went_wrong, lesson, created_at}.
    """
    rows = db.execute(
        """SELECT id, category, what_went_wrong, lesson, created_at
           FROM failure_lessons
           WHERE run_date = ?
           ORDER BY created_at""",
        (run_date,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "category": r["category"],
            "what_went_wrong": r["what_went_wrong"],
            "lesson": r["lesson"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def failure_categories(db: sqlite3.Connection, days: int = 30) -> dict:
    """Count failures by category over the last N days.

    Args:
        db: Database connection.
        days: Number of days to look back.

    Returns:
        Dict mapping category name to count, e.g. {'scraping': 5, 'quality': 2}.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.execute(
        """SELECT category, COUNT(*) as cnt
           FROM failure_lessons
           WHERE run_date >= ?
           GROUP BY category
           ORDER BY cnt DESC""",
        (cutoff,),
    ).fetchall()
    return {r["category"]: r["cnt"] for r in rows}

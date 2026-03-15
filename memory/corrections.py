"""Editorial correction storage — inspired by DPO preference learning.

Stores before/after pairs of content edits so the system can learn
editorial preferences over time. Each correction captures the platform,
original draft, approved version, and the reason for the change.
"""

import sqlite3
from datetime import datetime, timedelta


def store_correction(
    db: sqlite3.Connection,
    platform: str,
    original_text: str,
    approved_text: str,
    reason: str | None = None,
) -> int:
    """Store an editorial correction.

    Args:
        db: Database connection.
        platform: Platform the content targets (e.g. 'twitter', 'linkedin').
        original_text: The original draft text.
        approved_text: The approved/edited text.
        reason: Optional explanation for the edit.

    Returns:
        Row ID of the inserted correction.
    """
    cur = db.execute(
        """INSERT INTO editorial_corrections (platform, original_text, approved_text, reason, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (platform, original_text, approved_text, reason, datetime.now().isoformat()),
    )
    db.commit()
    return cur.lastrowid


def recent_corrections(
    db: sqlite3.Connection,
    platform: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Get recent editorial corrections, optionally filtered by platform.

    Args:
        db: Database connection.
        platform: Optional platform filter.
        limit: Maximum number of corrections to return.

    Returns:
        List of dicts with {id, platform, original_text, approved_text, reason, created_at}.
    """
    if platform:
        rows = db.execute(
            """SELECT id, platform, original_text, approved_text, reason, created_at
               FROM editorial_corrections
               WHERE platform = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (platform, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT id, platform, original_text, approved_text, reason, created_at
               FROM editorial_corrections
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    return [
        {
            "id": r["id"],
            "platform": r["platform"],
            "original_text": r["original_text"],
            "approved_text": r["approved_text"],
            "reason": r["reason"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def correction_stats(db: sqlite3.Connection, days: int = 30) -> dict:
    """Stats on editorial corrections over the last N days.

    Args:
        db: Database connection.
        days: Number of days to look back.

    Returns:
        Dict with:
            - total: total corrections in the window
            - by_platform: {platform: count}
            - by_reason: {reason: count} (top reasons, None excluded)
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Total
    total_row = db.execute(
        "SELECT COUNT(*) as cnt FROM editorial_corrections WHERE created_at >= ?",
        (cutoff,),
    ).fetchone()
    total = total_row["cnt"]

    # By platform
    platform_rows = db.execute(
        """SELECT platform, COUNT(*) as cnt
           FROM editorial_corrections
           WHERE created_at >= ?
           GROUP BY platform
           ORDER BY cnt DESC""",
        (cutoff,),
    ).fetchall()
    by_platform = {r["platform"]: r["cnt"] for r in platform_rows}

    # By reason (exclude NULLs)
    reason_rows = db.execute(
        """SELECT reason, COUNT(*) as cnt
           FROM editorial_corrections
           WHERE created_at >= ? AND reason IS NOT NULL
           GROUP BY reason
           ORDER BY cnt DESC
           LIMIT 20""",
        (cutoff,),
    ).fetchall()
    by_reason = {r["reason"]: r["cnt"] for r in reason_rows}

    return {
        "total": total,
        "by_platform": by_platform,
        "by_reason": by_reason,
    }

"""Cross-agent topic deduplication per run.

Prevents multiple agents from researching the same topic within a single run.
Uses INSERT OR IGNORE on a UNIQUE(run_date, topic_hash) constraint so the
first agent to claim a topic wins atomically.
"""

import sqlite3
from datetime import datetime


def claim_topic(
    db: sqlite3.Connection,
    run_date: str,
    agent: str,
    topic_hash: str,
    url: str | None = None,
) -> bool:
    """Claim a topic for this run.

    Uses INSERT OR IGNORE + check so the first agent to claim wins atomically.

    Args:
        db: Database connection.
        run_date: ISO date string for the run (e.g. '2026-03-14').
        agent: Agent identifier claiming the topic.
        topic_hash: Hash of the topic (caller decides the hashing scheme).
        url: Optional source URL associated with the topic.

    Returns:
        True if this agent successfully claimed the topic,
        False if it was already claimed by another agent.
    """
    cur = db.execute(
        """INSERT OR IGNORE INTO claimed_topics (run_date, agent, topic_hash, url, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (run_date, agent, topic_hash, url, datetime.now().isoformat()),
    )
    db.commit()

    if cur.rowcount == 1:
        return True

    # Row already existed — check if *this* agent owns it
    row = db.execute(
        "SELECT agent FROM claimed_topics WHERE run_date = ? AND topic_hash = ?",
        (run_date, topic_hash),
    ).fetchone()
    return row is not None and row["agent"] == agent


def is_claimed(db: sqlite3.Connection, run_date: str, topic_hash: str) -> dict | None:
    """Check if a topic is claimed for the given run date.

    Args:
        db: Database connection.
        run_date: ISO date string for the run.
        topic_hash: Hash of the topic.

    Returns:
        Dict with {agent, url} if claimed, None otherwise.
    """
    row = db.execute(
        "SELECT agent, url FROM claimed_topics WHERE run_date = ? AND topic_hash = ?",
        (run_date, topic_hash),
    ).fetchone()
    if row is None:
        return None
    return {"agent": row["agent"], "url": row["url"]}


def list_claims(db: sqlite3.Connection, run_date: str) -> list[dict]:
    """List all claimed topics for a run date.

    Args:
        db: Database connection.
        run_date: ISO date string for the run.

    Returns:
        List of dicts with {id, agent, topic_hash, url, created_at}.
    """
    rows = db.execute(
        """SELECT id, agent, topic_hash, url, created_at
           FROM claimed_topics
           WHERE run_date = ?
           ORDER BY created_at""",
        (run_date,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "agent": r["agent"],
            "topic_hash": r["topic_hash"],
            "url": r["url"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def clear_claims(db: sqlite3.Connection, run_date: str):
    """Clear all claims for a run date (useful for re-runs).

    Args:
        db: Database connection.
        run_date: ISO date string for the run.
    """
    db.execute("DELETE FROM claimed_topics WHERE run_date = ?", (run_date,))
    db.commit()

"""Trend history tracking — the learning loop for trend detection.

Stores which trends were detected each run, then backfills how many
findings each trend produced and whether those findings made the
newsletter. Over time, this builds a model of which trend topics
are consistently valuable.

Usage:
    store_trends(db, date, trends)           # after TREND_SCAN
    backfill_trend_results(db, date)         # after LEARN
    stats = get_trend_performance(db, days)  # query historical effectiveness
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta

import numpy as np

from memory.embeddings import embed_text, embed_texts, deserialize_f32

logger = logging.getLogger(__name__)

# Similarity threshold: a finding "matches" a trend if embedding similarity >= this
TREND_MATCH_THRESHOLD = 0.65


def store_trends(
    db: sqlite3.Connection,
    run_date: str,
    trends: list[dict],
) -> int:
    """Store detected trends for a run date.

    Args:
        db: Database connection.
        run_date: ISO date string.
        trends: List of trend dicts from detect_trends().

    Returns:
        Number of trends stored.
    """
    if not trends:
        return 0

    count = 0
    for t in trends:
        topic = t.get("topic", "")
        if not topic:
            continue

        db.execute(
            """INSERT OR REPLACE INTO trend_history
               (run_date, topic, score, source_count, item_count,
                sources_json, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run_date,
                topic,
                t.get("score", 0.0),
                t.get("source_count", 0),
                t.get("item_count", 0),
                json.dumps(t.get("sources", [])),
                t.get("evidence", ""),
            ),
        )
        count += 1

    db.commit()
    logger.info(f"Stored {count} trends for {run_date}")
    return count


def get_trends_for_date(
    db: sqlite3.Connection,
    run_date: str,
) -> list[dict]:
    """Get all stored trends for a specific date."""
    rows = db.execute(
        """SELECT id, run_date, topic, score, source_count, item_count,
                  sources_json, evidence, findings_produced, newsletter_included,
                  created_at
           FROM trend_history WHERE run_date = ?
           ORDER BY score DESC""",
        (run_date,),
    ).fetchall()

    return [
        {
            "id": r["id"],
            "run_date": r["run_date"],
            "topic": r["topic"],
            "score": r["score"],
            "source_count": r["source_count"],
            "item_count": r["item_count"],
            "sources": json.loads(r["sources_json"]) if r["sources_json"] else [],
            "evidence": r["evidence"],
            "findings_produced": r["findings_produced"],
            "newsletter_included": r["newsletter_included"],
        }
        for r in rows
    ]


def backfill_trend_results(
    db: sqlite3.Connection,
    run_date: str,
) -> int:
    """Backfill trend results: how many findings matched each trend.

    For each trend stored for this date, embeds the trend topic and
    compares against all findings from the same date. Counts matches
    above TREND_MATCH_THRESHOLD.

    Call this in the LEARN phase after findings are stored.

    Returns:
        Number of trends updated.
    """
    trends = db.execute(
        "SELECT id, topic FROM trend_history WHERE run_date = ?",
        (run_date,),
    ).fetchall()

    if not trends:
        return 0

    # Get all findings + embeddings for this date
    finding_rows = db.execute(
        """SELECT f.id, f.title, e.embedding
           FROM findings f
           JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.run_date = ?""",
        (run_date,),
    ).fetchall()

    if not finding_rows:
        # No findings, set all to 0
        for t in trends:
            db.execute(
                "UPDATE trend_history SET findings_produced = 0 WHERE id = ?",
                (t["id"],),
            )
        db.commit()
        return len(trends)

    # Build finding embedding matrix
    finding_matrix = np.array(
        [deserialize_f32(r["embedding"]) for r in finding_rows],
        dtype=np.float32,
    )

    # Embed trend topics
    trend_topics = [t["topic"] for t in trends]
    trend_vecs = np.array(embed_texts(trend_topics), dtype=np.float32)

    # Compute similarity matrix: trends × findings
    sim_matrix = trend_vecs @ finding_matrix.T

    updated = 0
    for i, trend_row in enumerate(trends):
        # Count findings that match this trend
        matches = int(np.sum(sim_matrix[i] >= TREND_MATCH_THRESHOLD))

        db.execute(
            "UPDATE trend_history SET findings_produced = ? WHERE id = ?",
            (matches, trend_row["id"]),
        )
        updated += 1

    db.commit()
    logger.info(f"Backfilled {updated} trend results for {run_date}")
    return updated


def get_trend_performance(
    db: sqlite3.Connection,
    days: int = 30,
) -> list[dict]:
    """Get trend performance stats over the last N days.

    Groups by topic, counts how many times it appeared, how many
    findings it produced, and how often it made the newsletter.

    Returns:
        List of dicts sorted by appearance count descending:
        {topic, appearances, avg_score, total_findings, newsletter_count}
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT topic,
                  COUNT(*) as appearances,
                  ROUND(AVG(score), 3) as avg_score,
                  SUM(findings_produced) as total_findings,
                  SUM(newsletter_included) as newsletter_count
           FROM trend_history
           WHERE run_date >= ?
           GROUP BY topic
           ORDER BY appearances DESC""",
        (cutoff,),
    ).fetchall()

    return [
        {
            "topic": r["topic"],
            "appearances": r["appearances"],
            "avg_score": r["avg_score"],
            "total_findings": r["total_findings"] or 0,
            "newsletter_count": r["newsletter_count"] or 0,
        }
        for r in rows
    ]

"""Cross-pipeline signal management.

Signals capture observations from one pipeline (research, social, feedback)
that should influence another. Positive strength = more coverage, negative = less.

All functions take a `db` (sqlite3.Connection) parameter and return data structures.
No argparse, no print, no CLI.
"""

import sqlite3
from datetime import datetime, timedelta


# ── Store ───────────────────────────────────────────────────────────────


def store_signal(
    db: sqlite3.Connection,
    pipeline: str,
    signal_type: str,
    topic: str,
    strength: float,
    evidence: str | None = None,
    run_date: str | None = None,
) -> dict:
    """Store a cross-pipeline signal.

    Args:
        db: Database connection.
        pipeline: Source pipeline name (e.g. 'research', 'social', 'feedback').
        signal_type: Type of signal (e.g. 'trending', 'engagement_boost', 'user_request').
        topic: Topic the signal relates to.
        strength: Signed float -- positive = more coverage, negative = less.
        evidence: Optional evidence text explaining the signal.
        run_date: Date the signal was observed (defaults to today).

    Returns {stored, pipeline, signal_type, topic}.
    """
    now = datetime.now().isoformat()
    date = run_date or datetime.now().strftime("%Y-%m-%d")

    db.execute(
        """INSERT INTO signals (source_pipeline, signal_type, topic, strength,
                                evidence, run_date, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pipeline, signal_type, topic, strength, evidence, date, now),
    )
    db.commit()

    return {
        "stored": True,
        "pipeline": pipeline,
        "signal_type": signal_type,
        "topic": topic,
    }


# ── Context generation ──────────────────────────────────────────────────


def get_signal_context(db: sqlite3.Connection, days: int = 14) -> str:
    """Generate markdown signal context for agent dispatch.

    Returns a markdown string summarizing recent cross-pipeline signals,
    sorted by absolute strength descending.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT source_pipeline, signal_type, topic, strength, evidence, run_date
           FROM signals WHERE run_date >= ?
           ORDER BY ABS(strength) DESC, run_date DESC""",
        (cutoff,),
    ).fetchall()

    if not rows:
        return f"No cross-pipeline signals in the last {days} days."

    lines = [f"## Cross-Pipeline Signals (last {days} days)", ""]
    for r in rows:
        icon = "+" if r["strength"] > 0 else "-"
        lines.append(
            f"- [{r['run_date']}] **{r['topic']}** ({r['signal_type']}, "
            f"{icon}{abs(r['strength']):.1f}) from {r['source_pipeline']}"
        )
        if r["evidence"]:
            lines.append(f"  Evidence: {r['evidence']}")
    lines.append("")
    return "\n".join(lines)


# ── Listing ─────────────────────────────────────────────────────────────


def get_recent_signals(
    db: sqlite3.Connection,
    pipeline: str | None = None,
    signal_type: str | None = None,
    days: int = 7,
) -> list[dict]:
    """List recent signals with optional filters.

    Returns list of {source_pipeline, signal_type, topic, strength, evidence, run_date}.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conditions = ["run_date >= ?"]
    params: list = [cutoff]

    if pipeline:
        conditions.append("source_pipeline = ?")
        params.append(pipeline)
    if signal_type:
        conditions.append("signal_type = ?")
        params.append(signal_type)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"""SELECT source_pipeline, signal_type, topic, strength, evidence, run_date
            FROM signals WHERE {where}
            ORDER BY run_date DESC, ABS(strength) DESC""",
        params,
    ).fetchall()

    return [dict(r) for r in rows]

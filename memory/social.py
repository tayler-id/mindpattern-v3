"""Social media post tracking, deduplication, voice exemplars, and engagement.

All functions take a `db` (sqlite3.Connection) parameter and return data structures.
No argparse, no print, no CLI.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from .embeddings import deserialize_f32, dot_similarity, embed_text, serialize_f32


# ── Social posts ─────────────────────────────────────────────────────────


def store_post(
    db: sqlite3.Connection,
    date: str,
    platform: str,
    content: str,
    post_type: str = "single",
    anchor_text: str | None = None,
    brief_json: str | None = None,
    gate2_action: str | None = None,
    iterations: int = 1,
    posted: bool = False,
    platform_post_id: str | None = None,
) -> int:
    """Store a social media post with its vector embedding. Returns post_id."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur = db.execute(
        """INSERT INTO social_posts
           (date, platform, content, post_type, anchor_text, brief_json,
            gate2_action, iterations, posted, platform_post_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (date, platform, content, post_type, anchor_text, brief_json,
         gate2_action, iterations, 1 if posted else 0, platform_post_id, now),
    )
    post_id = cur.lastrowid

    vec = embed_text(content)
    db.execute(
        "INSERT INTO social_posts_embeddings (post_id, embedding) VALUES (?, ?)",
        (post_id, serialize_f32(vec)),
    )

    db.commit()
    return post_id


def recent_posts(
    db: sqlite3.Connection,
    days: int = 14,
    platform: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List recent posts for dedup context."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conditions = ["date >= ?"]
    params: list = [cutoff]
    if platform:
        conditions.append("platform = ?")
        params.append(platform)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"""SELECT id, date, platform, content, anchor_text, gate2_action, posted
            FROM social_posts WHERE {where}
            ORDER BY date DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    return [dict(r) for r in rows]


def check_duplicate(
    db: sqlite3.Connection,
    anchor_text: str,
    days: int = 14,
    threshold: float = 0.80,
) -> dict:
    """Check if anchor is too similar to recent posts.

    Returns {duplicates, is_duplicate, threshold, posts_checked}.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT p.id, p.date, p.platform, p.content, p.anchor_text, e.embedding
           FROM social_posts p
           JOIN social_posts_embeddings e ON e.post_id = p.id
           WHERE p.date >= ?
           ORDER BY p.date DESC""",
        (cutoff,),
    ).fetchall()

    if not rows:
        return {
            "duplicates": [],
            "is_duplicate": False,
            "threshold": threshold,
            "posts_checked": 0,
        }

    query_vec = embed_text(anchor_text)
    duplicates = []

    for r in rows:
        emb = deserialize_f32(r["embedding"])
        sim = dot_similarity(query_vec, emb)
        if sim >= threshold:
            duplicates.append({
                "id": r["id"],
                "date": r["date"],
                "platform": r["platform"],
                "anchor": r["anchor_text"],
                "content_preview": r["content"][:200],
                "similarity": round(sim, 3),
            })

    duplicates.sort(key=lambda x: -x["similarity"])

    return {
        "duplicates": duplicates,
        "is_duplicate": len(duplicates) > 0,
        "threshold": threshold,
        "posts_checked": len(rows),
    }


def get_exemplars(
    db: sqlite3.Connection,
    platform: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Retrieve approved posts as voice exemplars for writers (RAG)."""
    conditions = ["posted = 1"]
    params: list = []
    if platform:
        conditions.append("platform = ?")
        params.append(platform)

    where = " AND ".join(conditions)
    rows = db.execute(
        f"""SELECT id, date, platform, content, anchor_text, gate2_action
            FROM social_posts WHERE {where}
            ORDER BY date DESC LIMIT ?""",
        params + [limit],
    ).fetchall()

    return [
        {
            "date": r["date"],
            "platform": r["platform"],
            "content": r["content"],
            "anchor": r["anchor_text"],
            "gate2_action": r["gate2_action"],
        }
        for r in rows
    ]


# ── Social feedback ──────────────────────────────────────────────────────


def store_social_feedback(
    db: sqlite3.Connection,
    date: str,
    platform: str,
    action: str,
    original: str | None = None,
    final: str | None = None,
    user_feedback: str | None = None,
) -> dict:
    """Store Gate 2 feedback. Auto-classifies edit_type.

    Returns {stored, platform, action, edit_type}.
    """
    # Classify edit type
    edit_type = "none"
    if action == "skip":
        edit_type = "rejection"
    elif action == "rewrite":
        edit_type = "major_rewrite"
    elif action == "approved" and original and final:
        if original.strip() != final.strip():
            len_diff = abs(len(final) - len(original)) / max(len(original), 1)
            edit_type = "major_rewrite" if len_diff > 0.3 else "minor_tweak"
    elif action == "approved":
        edit_type = "none"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """INSERT INTO social_feedback
           (date, platform, action, original_draft, final_draft,
            user_feedback, edit_type, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (date, platform, action, original, final, user_feedback, edit_type, now),
    )
    db.commit()

    return {
        "stored": True,
        "platform": platform,
        "action": action,
        "edit_type": edit_type,
    }


def get_feedback_patterns(db: sqlite3.Connection, days: int = 30) -> dict:
    """Extract patterns from feedback history.

    Returns {platform_stats, edit_distribution, recent_rewrite_feedback}.
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Aggregate stats per platform
    stats = db.execute(
        """SELECT platform,
                  COUNT(*) as total,
                  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) as approved,
                  SUM(CASE WHEN action = 'rewrite' THEN 1 ELSE 0 END) as rewritten,
                  SUM(CASE WHEN action = 'skip' THEN 1 ELSE 0 END) as skipped
           FROM social_feedback WHERE date >= ?
           GROUP BY platform""",
        (cutoff,),
    ).fetchall()

    # Edit type distribution
    edit_dist = db.execute(
        """SELECT edit_type, COUNT(*) as cnt
           FROM social_feedback WHERE date >= ?
           GROUP BY edit_type ORDER BY cnt DESC""",
        (cutoff,),
    ).fetchall()

    # Recent rewrite feedback (actual user instructions)
    rewrites = db.execute(
        """SELECT date, platform, user_feedback
           FROM social_feedback
           WHERE date >= ? AND action = 'rewrite' AND user_feedback IS NOT NULL
           ORDER BY date DESC LIMIT 10""",
        (cutoff,),
    ).fetchall()

    return {
        "platform_stats": [dict(r) for r in stats],
        "edit_distribution": {r["edit_type"]: r["cnt"] for r in edit_dist},
        "recent_rewrite_feedback": [dict(r) for r in rewrites],
    }


# ── Engagements ──────────────────────────────────────────────────────────


def store_engagement(
    db: sqlite3.Connection,
    user_id: str,
    platform: str,
    engagement_type: str,
    target_post_url: str | None = None,
    target_author: str | None = None,
    target_author_id: str | None = None,
    target_content: str | None = None,
    our_reply: str | None = None,
    status: str = "drafted",
    finding_id: int | None = None,
) -> int:
    """Store an engagement record. Returns engagement id."""
    now = datetime.now().isoformat()

    cur = db.execute(
        """INSERT INTO engagements
           (user_id, platform, engagement_type, target_post_url, target_author,
            target_author_id, target_content, our_reply, status, finding_id,
            created_at, posted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id, platform, engagement_type,
            target_post_url, target_author, target_author_id,
            target_content, our_reply, status, finding_id,
            now,
            now if status == "posted" else None,
        ),
    )
    db.commit()
    return cur.lastrowid


def check_engagement(
    db: sqlite3.Connection,
    target_author_id: str,
    platform: str,
) -> dict:
    """Check if we've engaged with author this week.

    Returns {already_engaged, count}.
    """
    row = db.execute(
        """SELECT COUNT(*) FROM engagements
           WHERE target_author_id = ? AND platform = ?
             AND engagement_type = 'reply'
             AND created_at > datetime('now', '-7 days')""",
        (target_author_id, platform),
    ).fetchone()
    count = row[0] if row else 0
    return {"already_engaged": count > 0, "count": count}


def list_engagements(
    db: sqlite3.Connection,
    user_id: str,
    limit: int = 20,
) -> list[dict]:
    """List recent engagements."""
    rows = db.execute(
        """SELECT platform, engagement_type, target_author,
                  target_post_url, status, created_at
           FROM engagements
           WHERE user_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()

    return [dict(r) for r in rows]


# ── Pending posts (deferred posting window) ──────────────────────────────


def store_pending_post(
    db: sqlite3.Connection,
    platform: str,
    content: str,
    post_after: str,
    image_path: str | None = None,
) -> int:
    """Store a post for deferred publishing. Returns pending post id.

    Args:
        db: Database connection.
        platform: Target platform (e.g., "linkedin", "bluesky").
        content: The approved post content.
        post_after: ISO datetime string -- earliest time to publish.
        image_path: Optional path to image file.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur = db.execute(
        """INSERT INTO pending_posts
           (platform, content, image_path, approved_at, post_after, posted)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (platform, content, image_path, now, post_after),
    )
    db.commit()
    return cur.lastrowid


def get_pending_posts(
    db: sqlite3.Connection,
    platform: str | None = None,
) -> list[dict]:
    """Get all unposted pending posts that are ready to publish (post_after <= now).

    Args:
        db: Database connection.
        platform: Optional platform filter.

    Returns:
        List of pending post dicts with id, platform, content, image_path,
        approved_at, post_after.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conditions = ["posted = 0", "post_after <= ?"]
    params: list = [now]

    if platform:
        conditions.append("platform = ?")
        params.append(platform)

    where = " AND ".join(conditions)

    try:
        rows = db.execute(
            f"""SELECT id, platform, content, image_path, approved_at, post_after
                FROM pending_posts WHERE {where}
                ORDER BY post_after ASC""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Table might not exist yet
        return []


def mark_pending_posted(
    db: sqlite3.Connection,
    pending_id: int,
) -> None:
    """Mark a pending post as posted."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "UPDATE pending_posts SET posted = 1, posted_at = ? WHERE id = ?",
        (now, pending_id),
    )
    db.commit()


def count_posts_today(
    db: sqlite3.Connection,
    platform: str,
) -> int:
    """Count how many posts were actually published today on a platform.

    Checks BOTH the social_posts table (posted=1) and the engagements table
    (engagement_type='post') to be thorough. Returns the higher count to
    prevent any table being out of sync from bypassing the limit.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Check social_posts table
    try:
        row = db.execute(
            """SELECT COUNT(*) FROM social_posts
               WHERE platform = ? AND posted = 1 AND date = ?""",
            (platform, today),
        ).fetchone()
        posts_count = row[0] if row else 0
    except sqlite3.OperationalError:
        posts_count = 0

    # Check engagements table
    try:
        row = db.execute(
            """SELECT COUNT(*) FROM engagements
               WHERE platform = ? AND engagement_type = 'post'
               AND date(created_at) = ?""",
            (platform, today),
        ).fetchone()
        engagements_count = row[0] if row else 0
    except sqlite3.OperationalError:
        engagements_count = 0

    return max(posts_count, engagements_count)

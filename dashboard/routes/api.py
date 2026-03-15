"""API routes for the mindpattern dashboard.

Public routes: read-only, no PII, paginated, date-filtered
Private routes: require bearer token auth
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Depends
from dashboard.auth import require_auth

router = APIRouter()
DATA_DIR = Path(__file__).parent.parent.parent / "data"
USERS_FILE = Path(__file__).parent.parent.parent / "users.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Patterns for stripping PII from text fields
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)


def _valid_date(s: Optional[str]) -> Optional[str]:
    """Return the date string if it matches YYYY-MM-DD, else None."""
    return s if s and _DATE_RE.match(s) else None


def _strip_pii(text: Optional[str]) -> Optional[str]:
    """Remove email addresses and phone numbers from a string."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[redacted]", text)
    text = _PHONE_RE.sub("[redacted]", text)
    return text


def _strip_pii_dict(d: dict, fields: list[str]) -> dict:
    """Strip PII from specified string fields in a dict (returns a copy)."""
    out = dict(d)
    for f in fields:
        if f in out and isinstance(out[f], str):
            out[f] = _strip_pii(out[f])
    return out


def get_memory_db(user_id: str = "ramsay") -> Optional[sqlite3.Connection]:
    """Open memory.db for a user. Fresh connection per request."""
    db_path = DATA_DIR / user_id / "memory.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Public endpoints (no auth) ──────────────────────────────────


@router.get("/api/findings")
async def get_findings(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
    agent: str = Query(None),
    importance: str = Query(None),
):
    """Public: paginated findings with date range filtering. No PII."""
    conn = get_memory_db()
    if conn is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    try:
        where_clauses: list[str] = []
        params: list = []

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("run_date >= ?")
            params.append(since_val)
        if agent:
            where_clauses.append("agent = ?")
            params.append(agent)
        if importance:
            where_clauses.append("importance = ?")
            params.append(importance)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Total count
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM findings WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        # Paginated results
        query = f"""
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [
            _strip_pii_dict(dict(r), ["title", "summary"])
            for r in rows
        ]

        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/api/sources")
async def get_sources(
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
):
    """Public: top sources by quality, paginated."""
    conn = get_memory_db()
    if conn is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    try:
        where_clauses: list[str] = []
        params: list = []

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("last_seen >= ?")
            params.append(since_val)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM sources WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        query = f"""
            SELECT id, url_domain, display_name, hit_count, high_value_count,
                   last_seen, created_at
            FROM sources
            WHERE {where_sql}
            ORDER BY high_value_count DESC, hit_count DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [dict(r) for r in rows]

        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/api/patterns")
async def get_patterns(
    min_count: int = Query(2),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
):
    """Public: recurring patterns, paginated."""
    conn = get_memory_db()
    if conn is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    try:
        where_clauses: list[str] = ["recurrence_count >= ?"]
        params: list = [min_count]

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("last_seen >= ?")
            params.append(since_val)

        where_sql = " AND ".join(where_clauses)

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM patterns WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        query = f"""
            SELECT id, run_date, theme, description, recurrence_count,
                   first_seen, last_seen, created_at
            FROM patterns
            WHERE {where_sql}
            ORDER BY recurrence_count DESC, last_seen DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [
            _strip_pii_dict(dict(r), ["theme", "description"])
            for r in rows
        ]

        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/api/skills")
async def get_skills(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    domain: str = Query(None),
    since: str = Query(None),
):
    """Public: skills by domain, paginated."""
    conn = get_memory_db()
    if conn is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    try:
        where_clauses: list[str] = []
        params: list = []

        if domain:
            where_clauses.append("domain = ?")
            params.append(domain)

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("run_date >= ?")
            params.append(since_val)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM skills WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        query = f"""
            SELECT id, run_date, domain, title, description, steps,
                   difficulty, source_url, source_name, created_at
            FROM skills
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [
            _strip_pii_dict(dict(r), ["title", "description", "steps"])
            for r in rows
        ]

        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/api/stats")
async def get_stats():
    """Public: aggregate statistics across all tables. No PII."""
    conn = get_memory_db()
    if conn is None:
        return {
            "findings": {"total": 0},
            "sources": {"total": 0},
            "patterns": {"total": 0},
            "skills": {"total": 0},
            "social_posts": {"total": 0},
            "run_quality": {},
        }

    try:
        stats: dict = {}

        # Findings summary
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT agent) as unique_agents,
                   COUNT(DISTINCT category) as unique_categories,
                   MIN(run_date) as earliest_date,
                   MAX(run_date) as latest_date,
                   SUM(CASE WHEN importance = 'high' THEN 1 ELSE 0 END) as high_importance
            FROM findings
        """).fetchone()
        stats["findings"] = {
            "total": row["total"],
            "unique_agents": row["unique_agents"],
            "unique_categories": row["unique_categories"],
            "earliest_date": row["earliest_date"] or "",
            "latest_date": row["latest_date"] or "",
            "high_importance": row["high_importance"],
        }

        # Sources summary
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(hit_count) as total_hits,
                   SUM(high_value_count) as total_high_value
            FROM sources
        """).fetchone()
        stats["sources"] = {
            "total": row["total"],
            "total_hits": row["total_hits"] or 0,
            "total_high_value": row["total_high_value"] or 0,
        }

        # Patterns summary
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   AVG(recurrence_count) as avg_recurrence,
                   MAX(recurrence_count) as max_recurrence
            FROM patterns
        """).fetchone()
        stats["patterns"] = {
            "total": row["total"],
            "avg_recurrence": round(row["avg_recurrence"] or 0, 1),
            "max_recurrence": row["max_recurrence"] or 0,
        }

        # Skills summary
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT domain) as unique_domains,
                   MIN(run_date) as earliest_date,
                   MAX(run_date) as latest_date
            FROM skills
        """).fetchone()
        stats["skills"] = {
            "total": row["total"],
            "unique_domains": row["unique_domains"],
            "earliest_date": row["earliest_date"] or "",
            "latest_date": row["latest_date"] or "",
        }

        # Social posts summary
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN posted = 1 THEN 1 ELSE 0 END) as posted,
                   COUNT(DISTINCT platform) as platforms
            FROM social_posts
        """).fetchone()
        stats["social_posts"] = {
            "total": row["total"],
            "posted": row["posted"],
            "platforms": row["platforms"],
        }

        # Latest run quality
        rq_row = conn.execute("""
            SELECT run_date, total_findings, unique_sources, high_value_count,
                   dedup_rate, overall_score
            FROM run_quality
            ORDER BY run_date DESC
            LIMIT 1
        """).fetchone()
        if rq_row:
            stats["run_quality"] = {
                "latest_date": rq_row["run_date"],
                "total_findings": rq_row["total_findings"],
                "unique_sources": rq_row["unique_sources"],
                "high_value_count": rq_row["high_value_count"],
                "dedup_rate": round(rq_row["dedup_rate"] or 0, 3),
                "overall_score": round(rq_row["overall_score"] or 0, 2),
            }
        else:
            stats["run_quality"] = {}

        return stats
    finally:
        conn.close()


@router.get("/healthz")
async def health():
    """Public: health check."""
    db_ok = False
    conn = get_memory_db()
    if conn is not None:
        try:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
        except Exception:
            pass
        finally:
            conn.close()

    return {
        "status": "ok" if db_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if db_ok else "unavailable",
    }


# ── Private endpoints (require auth) ────────────────────────────


@router.get("/api/users", dependencies=[Depends(require_auth)])
async def get_users():
    """Private: user registry (contains email)."""
    if not USERS_FILE.exists():
        return {"users": []}

    try:
        data = json.loads(USERS_FILE.read_text())
        return data
    except (json.JSONDecodeError, Exception):
        return {"users": [], "error": "Failed to parse users.json"}


@router.post("/api/approval/submit", dependencies=[Depends(require_auth)])
async def submit_approval(payload: dict):
    """Private: create approval review for social posts.

    Expected payload:
        {
            "pipeline": "social",
            "stage": "gate2",
            "items": [
                {"platform": "x", "content": "...", "content_type": "post"},
                ...
            ]
        }
    """
    conn = get_memory_db()
    if conn is None:
        return {"error": "Database unavailable"}, 503

    pipeline = payload.get("pipeline", "social")
    stage = payload.get("stage", "gate2")
    items = payload.get("items", [])

    if not items:
        return {"error": "No items provided"}, 400

    import secrets
    token = secrets.token_urlsafe(24)

    try:
        cur = conn.execute(
            "INSERT INTO approval_reviews (pipeline, stage, token) VALUES (?, ?, ?)",
            (pipeline, stage, token),
        )
        review_id = cur.lastrowid

        for item in items:
            conn.execute(
                """INSERT INTO approval_items
                   (review_id, platform, content_type, content, image_url)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    review_id,
                    item.get("platform"),
                    item.get("content_type", "post"),
                    item.get("content", ""),
                    item.get("image_url"),
                ),
            )

        conn.commit()
        return {
            "review_id": review_id,
            "token": token,
            "status": "pending",
            "items_count": len(items),
        }
    finally:
        conn.close()


@router.post("/api/approval/decide/{token}", dependencies=[Depends(require_auth)])
async def decide_approval(token: str, payload: dict):
    """Private: approve/reject social posts.

    Expected payload:
        {
            "action": "approve" | "reject",
            "item_decisions": [
                {"item_id": 1, "status": "approved", "feedback": "..."},
                ...
            ]
        }
    For bulk action on all items, omit item_decisions.
    """
    conn = get_memory_db()
    if conn is None:
        return {"error": "Database unavailable"}, 503

    action = payload.get("action", "approve")
    if action not in ("approve", "reject"):
        return {"error": "action must be 'approve' or 'reject'"}, 400

    try:
        # Look up review by token
        review = conn.execute(
            "SELECT id, status FROM approval_reviews WHERE token = ?",
            (token,),
        ).fetchone()

        if not review:
            return {"error": "Review not found"}, 404

        if review["status"] != "pending":
            return {
                "error": f"Review already decided: {review['status']}",
                "status": review["status"],
            }

        review_id = review["id"]
        review_status = "approved" if action == "approve" else "rejected"
        now = datetime.now().isoformat()

        # Apply per-item decisions if provided
        item_decisions = payload.get("item_decisions")
        if item_decisions:
            for dec in item_decisions:
                item_id = dec.get("item_id")
                item_status = dec.get("status", review_status)
                feedback = dec.get("feedback")
                conn.execute(
                    "UPDATE approval_items SET status = ?, feedback = ? WHERE id = ? AND review_id = ?",
                    (item_status, feedback, item_id, review_id),
                )
        else:
            # Bulk: apply same status to all items
            conn.execute(
                "UPDATE approval_items SET status = ? WHERE review_id = ?",
                (review_status, review_id),
            )

        # Update the review itself
        conn.execute(
            "UPDATE approval_reviews SET status = ?, decided_at = ? WHERE id = ?",
            (review_status, now, review_id),
        )

        conn.commit()

        return {
            "review_id": review_id,
            "status": review_status,
            "decided_at": now,
        }
    finally:
        conn.close()


@router.get("/api/approval/status/{token}", dependencies=[Depends(require_auth)])
async def approval_status(token: str):
    """Private: poll approval state."""
    conn = get_memory_db()
    if conn is None:
        return {"error": "Database unavailable"}, 503

    try:
        review = conn.execute(
            "SELECT id, pipeline, stage, status, created_at, decided_at FROM approval_reviews WHERE token = ?",
            (token,),
        ).fetchone()

        if not review:
            return {"error": "Review not found"}, 404

        review_dict = dict(review)
        review_id = review["id"]

        # Fetch items
        items = conn.execute(
            "SELECT id, platform, content_type, content, image_url, status, feedback FROM approval_items WHERE review_id = ?",
            (review_id,),
        ).fetchall()
        review_dict["items"] = [dict(item) for item in items]

        return review_dict
    finally:
        conn.close()

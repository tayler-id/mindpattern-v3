"""Social History tab -- browse social posts and feedback records from memory.db."""

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from dashboard.memory_db import get_memory_db, MEMORY_DB_PATH

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()

PAGE_SIZE = 20


def _valid_date(s: Optional[str]) -> Optional[str]:
    """Return the date string if it matches YYYY-MM-DD format, else None."""
    return s if s and _DATE_RE.match(s) else None


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _get_summary_stats() -> dict:
    """Return aggregate stats for the summary bar."""
    conn = get_memory_db()
    if conn is None:
        return {
            "total_posts": 0,
            "posted_count": 0,
            "platforms": {},
            "feedback_count": 0,
        }
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM social_posts").fetchone()
        total_posts = row["cnt"] if row else 0

        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM social_posts WHERE posted = 1"
        ).fetchone()
        posted_count = row["cnt"] if row else 0

        cur = conn.execute(
            "SELECT platform, COUNT(*) AS cnt FROM social_posts GROUP BY platform"
        )
        platforms = {r["platform"]: r["cnt"] for r in cur.fetchall()}

        row = conn.execute("SELECT COUNT(*) AS cnt FROM social_feedback").fetchone()
        feedback_count = row["cnt"] if row else 0

        return {
            "total_posts": total_posts,
            "posted_count": posted_count,
            "platforms": platforms,
            "feedback_count": feedback_count,
        }
    finally:
        conn.close()


def _get_post_list(
    platform: Optional[str] = None,
    posted: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
) -> tuple:
    """Query social_posts with filters, return (rows, total_count)."""
    conn = get_memory_db()
    if conn is None:
        return [], 0

    try:
        where_clauses = []
        params = []  # type: list

        if platform:
            where_clauses.append("platform = ?")
            params.append(platform)

        if posted == "posted":
            where_clauses.append("posted = 1")
        elif posted == "draft":
            where_clauses.append("(posted = 0 OR posted IS NULL)")

        date_from = _valid_date(date_from)
        date_to = _valid_date(date_to)
        if date_from:
            where_clauses.append("date >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("date <= ?")
            params.append(date_to)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Total count
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM social_posts" + where_sql, params
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        # Paginated results
        offset = (page - 1) * PAGE_SIZE
        query = (
            "SELECT * FROM social_posts"
            + where_sql
            + " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?"
        )
        cur = conn.execute(query, params + [PAGE_SIZE, offset])
        rows = [dict(r) for r in cur.fetchall()]

        return rows, total
    finally:
        conn.close()


def _get_post_detail(post_id: int) -> tuple:
    """Return a single post and any matching feedback records."""
    conn = get_memory_db()
    if conn is None:
        return None, []

    try:
        cur = conn.execute("SELECT * FROM social_posts WHERE id = ?", (post_id,))
        row = cur.fetchone()
        post = dict(row) if row else None

        feedback = []
        if post:
            # Try to match feedback by date + platform
            cur = conn.execute(
                "SELECT * FROM social_feedback WHERE date = ? AND platform = ? ORDER BY id ASC",
                (post["date"], post["platform"]),
            )
            feedback = [dict(r) for r in cur.fetchall()]

        return post, feedback
    finally:
        conn.close()


def _parse_brief_json(brief_str: Optional[str]) -> Optional[dict]:
    """Safely parse brief_json, returning None on failure."""
    if not brief_str:
        return None
    try:
        return json.loads(brief_str)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Chart data endpoints
# ---------------------------------------------------------------------------


@router.get("/social-history/data/by-platform")
def chart_by_platform():
    """Return Chart.js doughnut data: post counts grouped by platform."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})

    try:
        cur = conn.execute(
            "SELECT platform, COUNT(*) AS cnt FROM social_posts GROUP BY platform ORDER BY cnt DESC"
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    platform_colors = {
        "x": "#1DA1F2",
        "linkedin": "#0A66C2",
        "bluesky": "#0085FF",
    }
    fallback_color = "#64748b"

    labels = [r["platform"] for r in rows]
    data = [r["cnt"] for r in rows]
    colors = [platform_colors.get(lbl, fallback_color) for lbl in labels]

    return JSONResponse({
        "labels": labels,
        "datasets": [{
            "data": data,
            "backgroundColor": colors,
            "borderColor": "#1e293b",
            "borderWidth": 2,
        }],
    })


@router.get("/social-history/data/by-date")
def chart_by_date():
    """Return Chart.js line chart data: post counts grouped by date."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})

    try:
        cur = conn.execute(
            "SELECT date, COUNT(*) AS cnt FROM social_posts GROUP BY date ORDER BY date ASC"
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return JSONResponse({
        "labels": [r["date"] for r in rows],
        "datasets": [{
            "label": "Posts",
            "data": [r["cnt"] for r in rows],
            "borderColor": "#38bdf8",
            "backgroundColor": "rgba(56, 189, 248, 0.1)",
            "fill": True,
        }],
    })


@router.get("/social-history/data/feedback-actions")
def chart_feedback_actions():
    """Return Chart.js doughnut data: feedback counts grouped by action."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})

    try:
        cur = conn.execute(
            "SELECT action, COUNT(*) AS cnt FROM social_feedback GROUP BY action ORDER BY cnt DESC"
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    action_colors = {
        "approve": "#4ade80",
        "reject": "#f87171",
        "rewrite": "#fbbf24",
    }
    fallback_color = "#64748b"

    labels = [r["action"] for r in rows]
    data = [r["cnt"] for r in rows]
    colors = [action_colors.get(lbl, fallback_color) for lbl in labels]

    return JSONResponse({
        "labels": labels,
        "datasets": [{
            "data": data,
            "backgroundColor": colors,
            "borderColor": "#1e293b",
            "borderWidth": 2,
        }],
    })


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@router.get("/social-history/{post_id}", response_class=HTMLResponse)
def social_post_detail(request: Request, post_id: int):
    """Return detail view for a specific social post."""
    post, feedback = _get_post_detail(post_id)
    brief = _parse_brief_json(post.get("brief_json") if post else None)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "post": post,
        "brief": brief,
        "feedback": feedback,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/social_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "social-history",
        "tab_template": "tabs/social_detail.html",
    })


@router.get("/social-history", response_class=HTMLResponse)
def social_history(
    request: Request,
    platform: Optional[str] = None,
    posted: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
):
    """Return social history list with filters and charts."""
    posts, total = _get_post_list(
        platform=platform,
        posted=posted,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )
    stats = _get_summary_stats()
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "posts": posts,
        "stats": stats,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "page_size": PAGE_SIZE,
        "filter_platform": platform or "",
        "filter_posted": posted or "",
        "filter_from": _valid_date(date_from) or "",
        "filter_to": _valid_date(date_to) or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/social_history.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "social-history",
        "tab_template": "tabs/social_history.html",
    })

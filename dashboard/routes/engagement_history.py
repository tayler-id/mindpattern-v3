"""Engagement History tab -- browse historical engagement records from memory.db."""

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

PAGE_SIZE = 30

# -- Color palettes for Chart.js responses --

PLATFORM_COLORS = {
    "x": "#1DA1F2",
    "twitter": "#1DA1F2",
    "linkedin": "#0A66C2",
    "bluesky": "#0085FF",
}
PLATFORM_DEFAULT_COLOR = "#94a3b8"

STATUS_COLORS = {
    "posted": "#4ade80",
    "failed": "#f87171",
    "pending": "#fbbf24",
}
STATUS_DEFAULT_COLOR = "#94a3b8"


def _valid_date(s: Optional[str]) -> Optional[str]:
    """Return the date string if it matches YYYY-MM-DD, else None."""
    return s if s and _DATE_RE.match(s) else None


def _build_where(
    platform: Optional[str],
    engagement_type: Optional[str],
    status: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
):
    """Build a WHERE clause and params list from filter values."""
    clauses = []
    params: list = []
    if platform:
        clauses.append("platform = ?")
        params.append(platform)
    if engagement_type:
        clauses.append("engagement_type = ?")
        params.append(engagement_type)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if date_from:
        clauses.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("created_at <= ?")
        params.append(date_to + "T23:59:59")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _get_summary_stats(
    platform: Optional[str] = None,
    engagement_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """Compute summary stats for the engagement history header."""
    conn = get_memory_db()
    if conn is None:
        return {"total": 0, "by_type": {}, "success_rate": 0.0}
    try:
        where, params = _build_where(platform, engagement_type, status, date_from, date_to)

        cur = conn.execute("SELECT COUNT(*) as cnt FROM engagements" + where, params)
        total = cur.fetchone()["cnt"]

        cur = conn.execute(
            "SELECT engagement_type, COUNT(*) as cnt FROM engagements"
            + where + " GROUP BY engagement_type",
            params,
        )
        by_type = {row["engagement_type"]: row["cnt"] for row in cur.fetchall()}

        # Success rate: posted / (posted + failed) -- ignore pending
        cur = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM engagements"
            + where + " GROUP BY status",
            params,
        )
        status_counts = {row["status"]: row["cnt"] for row in cur.fetchall()}
        posted = status_counts.get("posted", 0)
        failed = status_counts.get("failed", 0)
        denom = posted + failed
        success_rate = round((posted / denom) * 100, 1) if denom > 0 else 0.0

        return {
            "total": total,
            "by_type": by_type,
            "success_rate": success_rate,
        }
    finally:
        conn.close()


def _get_engagement_list(
    platform: Optional[str] = None,
    engagement_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
) -> tuple:
    """Return (engagements, total_count, total_pages) for the given filters + page."""
    conn = get_memory_db()
    if conn is None:
        return [], 0, 0
    try:
        where, params = _build_where(platform, engagement_type, status, date_from, date_to)

        cur = conn.execute("SELECT COUNT(*) as cnt FROM engagements" + where, params)
        total_count = cur.fetchone()["cnt"]

        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * PAGE_SIZE

        query = (
            "SELECT * FROM engagements"
            + where
            + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        cur = conn.execute(query, params + [PAGE_SIZE, offset])
        engagements = [dict(r) for r in cur.fetchall()]
        return engagements, total_count, total_pages
    finally:
        conn.close()


def _get_engagement_detail(engagement_id: int) -> Optional[dict]:
    """Fetch a single engagement record by ID."""
    conn = get_memory_db()
    if conn is None:
        return None
    try:
        cur = conn.execute("SELECT * FROM engagements WHERE id = ?", (engagement_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---- HTML Routes ----


@router.get("/engagement-history", response_class=HTMLResponse)
def engagement_history(
    request: Request,
    platform: Optional[str] = None,
    engagement_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
):
    """List engagements with filters and pagination."""
    date_from = _valid_date(date_from)
    date_to = _valid_date(date_to)

    engagements, total_count, total_pages = _get_engagement_list(
        platform=platform,
        engagement_type=engagement_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
    )
    stats = _get_summary_stats(
        platform=platform,
        engagement_type=engagement_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "engagements": engagements,
        "stats": stats,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "filter_platform": platform or "",
        "filter_type": engagement_type or "",
        "filter_status": status or "",
        "filter_from": date_from or "",
        "filter_to": date_to or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/engagement_history.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "engagement-history",
        "tab_template": "tabs/engagement_history.html",
    })


@router.get("/engagement-history/data/by-platform")
def chart_by_platform():
    """Chart.js data: engagement count grouped by platform (doughnut)."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM engagements GROUP BY platform ORDER BY cnt DESC"
        )
        rows = cur.fetchall()
        labels = [r["platform"] for r in rows]
        values = [r["cnt"] for r in rows]
        colors = [PLATFORM_COLORS.get(lbl.lower(), PLATFORM_DEFAULT_COLOR) for lbl in labels]
        return JSONResponse({
            "labels": labels,
            "datasets": [{
                "data": values,
                "backgroundColor": colors,
                "borderColor": "#0f172a",
                "borderWidth": 2,
            }],
        })
    finally:
        conn.close()


@router.get("/engagement-history/data/by-status")
def chart_by_status():
    """Chart.js data: engagement count grouped by status (bar)."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM engagements GROUP BY status ORDER BY cnt DESC"
        )
        rows = cur.fetchall()
        labels = [r["status"] for r in rows]
        values = [r["cnt"] for r in rows]
        colors = [STATUS_COLORS.get(lbl.lower(), STATUS_DEFAULT_COLOR) for lbl in labels]
        return JSONResponse({
            "labels": labels,
            "datasets": [{
                "label": "Engagements",
                "data": values,
                "backgroundColor": colors,
                "borderColor": colors,
                "borderWidth": 1,
            }],
        })
    finally:
        conn.close()


@router.get("/engagement-history/data/by-date")
def chart_by_date():
    """Chart.js data: engagement count grouped by date (line)."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute(
            "SELECT date(created_at) as day, COUNT(*) as cnt "
            "FROM engagements GROUP BY day ORDER BY day ASC"
        )
        rows = cur.fetchall()
        labels = [r["day"] for r in rows]
        values = [r["cnt"] for r in rows]
        return JSONResponse({
            "labels": labels,
            "datasets": [{
                "label": "Engagements",
                "data": values,
                "borderColor": "#38bdf8",
                "backgroundColor": "rgba(56,189,248,0.1)",
                "fill": True,
                "tension": 0.3,
            }],
        })
    finally:
        conn.close()


@router.get("/engagement-history/{engagement_id}", response_class=HTMLResponse)
def engagement_detail(request: Request, engagement_id: int):
    """Return detail view for a single engagement record."""
    engagement = _get_engagement_detail(engagement_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "engagement": engagement,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/engagement_history_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "engagement-history",
        "tab_template": "tabs/engagement_history_detail.html",
    })

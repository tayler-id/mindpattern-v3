"""Findings Browser tab -- browse research findings stored in memory.db."""

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

PAGE_SIZE = 50

# Color palette for charts
COLORS = ["#38bdf8", "#a78bfa", "#4ade80", "#fbbf24", "#f87171"]


def _valid_date(s: Optional[str]) -> Optional[str]:
    """Return the date string if it matches YYYY-MM-DD format, else None."""
    return s if s and _DATE_RE.match(s) else None


_ALLOWED_COLUMNS = {"agent", "category", "importance", "source_name"}


def _get_distinct_values(column: str) -> list:
    """Return distinct non-null values for a column in the findings table."""
    if column not in _ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column: {column!r}")
    conn = get_memory_db()
    if conn is None:
        return []
    try:
        cur = conn.execute(
            f"SELECT DISTINCT {column} FROM findings WHERE {column} IS NOT NULL AND {column} != '' ORDER BY {column}"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_findings_list(
    agent: Optional[str] = None,
    category: Optional[str] = None,
    importance: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
) -> tuple:
    """Query findings with filters and pagination. Returns (findings, total_count)."""
    conn = get_memory_db()
    if conn is None:
        return [], 0

    date_from = _valid_date(date_from)
    date_to = _valid_date(date_to)

    try:
        where_clauses = []
        params: list = []

        if agent:
            where_clauses.append("agent = ?")
            params.append(agent)
        if category:
            where_clauses.append("category = ?")
            params.append(category)
        if importance:
            where_clauses.append("importance = ?")
            params.append(importance)
        if date_from:
            where_clauses.append("run_date >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("run_date <= ?")
            params.append(date_to)
        if q:
            where_clauses.append("(title LIKE ? OR summary LIKE ?)")
            like_val = f"%{q}%"
            params.append(like_val)
            params.append(like_val)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        count_cur = conn.execute(
            f"SELECT COUNT(*) FROM findings WHERE {where_sql}", params
        )
        total_count = count_cur.fetchone()[0]

        # Get paginated results
        offset = (page - 1) * PAGE_SIZE
        query = f"""
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        cur = conn.execute(query, params + [PAGE_SIZE, offset])
        findings = [dict(r) for r in cur.fetchall()]

        return findings, total_count
    finally:
        conn.close()


def get_finding_detail(finding_id: int) -> Optional[dict]:
    """Query a single finding by id."""
    conn = get_memory_db()
    if conn is None:
        return None
    try:
        cur = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_summary_stats() -> dict:
    """Return summary stats: total findings, unique agents, date range."""
    conn = get_memory_db()
    if conn is None:
        return {"total": 0, "unique_agents": 0, "date_min": "", "date_max": ""}
    try:
        cur = conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT agent) as unique_agents,
                   MIN(run_date) as date_min,
                   MAX(run_date) as date_max
            FROM findings
        """)
        row = cur.fetchone()
        return {
            "total": row["total"],
            "unique_agents": row["unique_agents"],
            "date_min": row["date_min"] or "",
            "date_max": row["date_max"] or "",
        }
    finally:
        conn.close()


# -- Chart.js JSON data endpoints ---------------------------------------------


@router.get("/findings/data/by-agent")
def findings_data_by_agent():
    """Return Chart.js-native data for findings count grouped by agent."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute("""
            SELECT agent, COUNT(*) as cnt
            FROM findings
            WHERE agent IS NOT NULL AND agent != ''
            GROUP BY agent
            ORDER BY cnt DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        bg_colors = [COLORS[i % len(COLORS)] for i in range(len(rows))]
        return JSONResponse({
            "labels": [r["agent"] for r in rows],
            "datasets": [{
                "label": "Findings",
                "data": [r["cnt"] for r in rows],
                "backgroundColor": bg_colors,
            }],
        })
    finally:
        conn.close()


@router.get("/findings/data/by-date")
def findings_data_by_date():
    """Return Chart.js-native data for findings count grouped by run_date."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute("""
            SELECT run_date, COUNT(*) as cnt
            FROM findings
            WHERE run_date IS NOT NULL AND run_date != ''
            GROUP BY run_date
            ORDER BY run_date ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        return JSONResponse({
            "labels": [r["run_date"] for r in rows],
            "datasets": [{
                "label": "Findings",
                "data": [r["cnt"] for r in rows],
                "borderColor": "#38bdf8",
                "backgroundColor": "rgba(56, 189, 248, 0.1)",
                "fill": True,
            }],
        })
    finally:
        conn.close()


# -- Detail route (must be before the list route to avoid path conflict) ------


@router.get("/findings/{finding_id}", response_class=HTMLResponse)
def finding_detail(request: Request, finding_id: int):
    """Return detail view for a single finding."""
    finding = get_finding_detail(finding_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "finding": finding,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/finding_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "findings",
        "tab_template": "tabs/finding_detail.html",
    })


# -- Main list route ----------------------------------------------------------


@router.get("/findings", response_class=HTMLResponse)
def findings_list(
    request: Request,
    agent: Optional[str] = None,
    category: Optional[str] = None,
    importance: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
):
    """Return findings browser with filters, charts, and paginated table."""
    findings, total_count = get_findings_list(
        agent=agent,
        category=category,
        importance=importance,
        date_from=date_from,
        date_to=date_to,
        q=q,
        page=page,
    )
    agents = _get_distinct_values("agent")
    categories = _get_distinct_values("category")
    stats = get_summary_stats()
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1

    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "findings": findings,
        "agents": agents,
        "categories": categories,
        "stats": stats,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "page_size": PAGE_SIZE,
        "filter_agent": agent or "",
        "filter_category": category or "",
        "filter_importance": importance or "",
        "filter_date_from": date_from or "",
        "filter_date_to": date_to or "",
        "filter_q": q or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/findings.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "findings",
        "tab_template": "tabs/findings.html",
    })

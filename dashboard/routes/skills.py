"""Skills Browser tab -- browse skills discovered by research agents in memory.db."""

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

# Color palette for charts
COLORS = [
    "#38bdf8", "#a78bfa", "#4ade80", "#fbbf24", "#f87171",
    "#fb923c", "#e879f9", "#22d3ee", "#a3e635", "#f472b6",
]


def _valid_date(s: Optional[str]) -> Optional[str]:
    """Return the date string if it matches YYYY-MM-DD format, else None."""
    return s if s and _DATE_RE.match(s) else None


def _get_distinct_domains() -> list:
    """Return distinct non-null domain values from the skills table."""
    conn = get_memory_db()
    if conn is None:
        return []
    try:
        cur = conn.execute(
            "SELECT DISTINCT domain FROM skills WHERE domain IS NOT NULL AND domain != '' ORDER BY domain"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_skills_list(
    domain: Optional[str] = None,
    difficulty: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
) -> tuple:
    """Query skills with filters and pagination. Returns (skills, total_count)."""
    conn = get_memory_db()
    if conn is None:
        return [], 0

    date_from = _valid_date(date_from)
    date_to = _valid_date(date_to)

    try:
        where_clauses = []
        params = []  # type: list

        if domain:
            where_clauses.append("domain = ?")
            params.append(domain)
        if difficulty:
            where_clauses.append("difficulty = ?")
            params.append(difficulty)
        if date_from:
            where_clauses.append("run_date >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("run_date <= ?")
            params.append(date_to)
        if q:
            where_clauses.append("(title LIKE ? OR description LIKE ?)")
            like_val = f"%{q}%"
            params.append(like_val)
            params.append(like_val)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        count_cur = conn.execute(
            f"SELECT COUNT(*) FROM skills WHERE {where_sql}", params
        )
        total_count = count_cur.fetchone()[0]

        # Get paginated results
        offset = (page - 1) * PAGE_SIZE
        query = f"""
            SELECT id, run_date, domain, title, description, difficulty,
                   source_url, source_name, created_at
            FROM skills
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        cur = conn.execute(query, params + [PAGE_SIZE, offset])
        skills = [dict(r) for r in cur.fetchall()]

        return skills, total_count
    finally:
        conn.close()


def get_skill_detail(skill_id: int) -> Optional[dict]:
    """Query a single skill by id."""
    conn = get_memory_db()
    if conn is None:
        return None
    try:
        cur = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_summary_stats() -> dict:
    """Return summary stats: total skills, unique domains, date range."""
    conn = get_memory_db()
    if conn is None:
        return {"total": 0, "unique_domains": 0, "date_min": "", "date_max": ""}
    try:
        cur = conn.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT domain) as unique_domains,
                   MIN(run_date) as date_min,
                   MAX(run_date) as date_max
            FROM skills
        """)
        row = cur.fetchone()
        return {
            "total": row["total"],
            "unique_domains": row["unique_domains"],
            "date_min": row["date_min"] or "",
            "date_max": row["date_max"] or "",
        }
    finally:
        conn.close()


# -- Chart.js JSON data endpoints ---------------------------------------------


@router.get("/skills/data/by-domain")
def skills_data_by_domain():
    """Return Chart.js-native data for skills count grouped by domain (horizontal bar)."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute("""
            SELECT domain, COUNT(*) as cnt
            FROM skills
            WHERE domain IS NOT NULL AND domain != ''
            GROUP BY domain
            ORDER BY cnt DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        bg_colors = [COLORS[i % len(COLORS)] for i in range(len(rows))]
        return JSONResponse({
            "labels": [r["domain"] for r in rows],
            "datasets": [{
                "label": "Skills",
                "data": [r["cnt"] for r in rows],
                "backgroundColor": bg_colors,
            }],
        })
    finally:
        conn.close()


@router.get("/skills/data/by-date")
def skills_data_by_date():
    """Return Chart.js-native data for skills count grouped by run_date (line chart)."""
    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"labels": [], "datasets": []})
    try:
        cur = conn.execute("""
            SELECT run_date, COUNT(*) as cnt
            FROM skills
            WHERE run_date IS NOT NULL AND run_date != ''
            GROUP BY run_date
            ORDER BY run_date ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        return JSONResponse({
            "labels": [r["run_date"] for r in rows],
            "datasets": [{
                "label": "Skills",
                "data": [r["cnt"] for r in rows],
                "borderColor": "#38bdf8",
                "backgroundColor": "rgba(56, 189, 248, 0.1)",
                "fill": True,
            }],
        })
    finally:
        conn.close()


# -- Detail route (must be before the list route to avoid path conflict) ------


@router.get("/skills/{skill_id}", response_class=HTMLResponse)
def skill_detail(request: Request, skill_id: int):
    """Return detail view for a single skill."""
    skill = get_skill_detail(skill_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    # Split steps on newlines for numbered list display
    steps_list = []
    if skill and skill.get("steps"):
        steps_list = [s.strip() for s in skill["steps"].split("\n") if s.strip()]

    ctx = {
        "request": request,
        "skill": skill,
        "steps_list": steps_list,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/skill_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "skills",
        "tab_template": "tabs/skill_detail.html",
    })


# -- Main list route ----------------------------------------------------------


@router.get("/skills", response_class=HTMLResponse)
def skills_list(
    request: Request,
    domain: Optional[str] = None,
    difficulty: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
):
    """Return skills browser with filters, charts, and paginated table."""
    skills, total_count = get_skills_list(
        domain=domain,
        difficulty=difficulty,
        date_from=date_from,
        date_to=date_to,
        q=q,
        page=page,
    )
    domains = _get_distinct_domains()
    stats = get_summary_stats()
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE if total_count > 0 else 1

    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "skills": skills,
        "domains": domains,
        "stats": stats,
        "total_count": total_count,
        "page": page,
        "total_pages": total_pages,
        "page_size": PAGE_SIZE,
        "filter_domain": domain or "",
        "filter_difficulty": difficulty or "",
        "filter_date_from": date_from or "",
        "filter_date_to": date_to or "",
        "filter_q": q or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/skills.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "skills",
        "tab_template": "tabs/skills.html",
    })

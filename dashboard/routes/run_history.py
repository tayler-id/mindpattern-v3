"""Run History tab — browse historical pipeline runs and drill into agent detail."""

import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from orchestrator.traces_db import get_db, TRACES_DB_PATH

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(s: str | None) -> str | None:
    """Return the date string if it matches YYYY-MM-DD format, else None."""
    return s if s and _DATE_RE.match(s) else None

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def get_run_list(status: str | None = None, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """Query pipeline_runs for the last 30 days with agent count and duration."""
    date_from = _valid_date(date_from)
    date_to = _valid_date(date_to)

    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        query = """
            SELECT p.*,
                   COUNT(a.id) as agent_count,
                   CASE WHEN p.completed_at IS NOT NULL
                        THEN ROUND((julianday(p.completed_at) - julianday(p.started_at)) * 86400)
                        ELSE NULL END as duration_seconds
            FROM pipeline_runs p
            LEFT JOIN agent_runs a ON a.pipeline_run_id = p.id
            WHERE p.started_at >= date('now', '-30 days')
        """
        params: list = []

        if status == "active":
            query += " AND p.status NOT IN ('completed', 'failed')"
        elif status:
            query += " AND p.status = ?"
            params.append(status)
        if date_from:
            query += " AND p.started_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND p.started_at <= ?"
            params.append(date_to + "T23:59:59")

        query += " GROUP BY p.id ORDER BY p.started_at DESC"

        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_run_detail(run_id: str) -> tuple[dict | None, list[dict]]:
    """Query a specific pipeline run and its agent runs."""
    if not TRACES_DB_PATH.exists():
        return None, []

    conn = get_db()
    try:
        cur = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        pipeline_run = dict(row) if row else None

        agent_runs = []
        if pipeline_run:
            cur = conn.execute(
                "SELECT * FROM agent_runs WHERE pipeline_run_id = ? ORDER BY started_at ASC",
                (run_id,),
            )
            agent_runs = [dict(r) for r in cur.fetchall()]

        return pipeline_run, agent_runs
    finally:
        conn.close()


@router.get("/run-history/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    """Return agent detail view for a specific pipeline run."""
    pipeline_run, agent_runs = get_run_detail(run_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "pipeline_run": pipeline_run,
        "agent_runs": agent_runs,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/run_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "run-history",
        "tab_template": "tabs/run_detail.html",
    })


@router.get("/run-history", response_class=HTMLResponse)
def run_history(
    request: Request,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Return run history list with optional filters."""
    runs = get_run_list(status=status, date_from=date_from, date_to=date_to)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "runs": runs,
        "filter_status": status or "",
        "filter_from": date_from or "",
        "filter_to": date_to or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/run_history.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "run-history",
        "tab_template": "tabs/run_history.html",
    })

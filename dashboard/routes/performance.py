"""Performance tab -- agent quality correlation and prompt drift detection (FR35, FR73-FR74)."""

import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from orchestrator.traces_db import get_db, TRACES_DB_PATH

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PASS_THRESHOLD = 7.0  # Scores >= this are considered "passing"

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _valid_date(s: str | None) -> str | None:
    """Return the date string if it matches YYYY-MM-DD format, else None."""
    return s if s and _DATE_RE.match(s) else None


# -- Cross-DB quality correlation from memory.db (R4-2 E4-F2) ---------------


def get_agent_check_pass_rates(agent_name: str) -> list[dict]:
    """Query agent_checks pass rates from memory.db, grouped by date.

    Returns list of dicts with date, passed, total.
    Uses a separate sqlite3 connection to memory.db (NOT imported from memory.py).
    """
    user = os.environ.get("DASHBOARD_USER", "ramsay")
    mem_db_path = PROJECT_ROOT / "data" / user / "memory.db"

    if not mem_db_path.exists():
        return []

    conn = sqlite3.connect(str(mem_db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT date,
                   SUM(CASE WHEN passed THEN 1 ELSE 0 END) AS passed,
                   COUNT(*) AS total
            FROM agent_checks
            WHERE agent_name = ?
            GROUP BY date
            ORDER BY date ASC
            """,
            (agent_name,),
        )
        return [dict(r) for r in cur.fetchall()]
    except sqlite3.OperationalError:
        # Table may not exist in memory.db
        return []
    finally:
        conn.close()


# -- Quality correlation backend (Task 4) ------------------------------------


def get_agent_list() -> list[str]:
    """Return distinct agent names from agent_runs."""
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute("SELECT DISTINCT agent_name FROM agent_runs ORDER BY agent_name ASC")
        return [row["agent_name"] for row in cur.fetchall()]
    finally:
        conn.close()


def get_quality_over_time(
    agent_name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Quality scores averaged per day for an agent, joined through agent_runs."""
    if not TRACES_DB_PATH.exists():
        return []

    df = _valid_date(date_from)
    dt = _valid_date(date_to)

    conn = get_db()
    try:
        query = """
            SELECT date(ar.started_at) AS date,
                   AVG(qs.score) AS avg_score
            FROM quality_scores qs
            JOIN agent_runs ar ON qs.agent_run_id = ar.id
            WHERE ar.agent_name = ?
        """
        params: list = [agent_name]

        if df:
            query += " AND ar.started_at >= ?"
            params.append(df)
        if dt:
            query += " AND ar.started_at <= ?"
            params.append(dt + "T23:59:59")

        query += " GROUP BY date(ar.started_at) ORDER BY date(ar.started_at) ASC"
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_prompt_change_markers(
    agent_name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Return prompt version change dates and git hashes for an agent."""
    if not TRACES_DB_PATH.exists():
        return []

    df = _valid_date(date_from)
    dt = _valid_date(date_to)

    conn = get_db()
    try:
        query = """
            SELECT pv.git_hash, pv.captured_at, date(pv.captured_at) AS date
            FROM prompt_versions pv
            WHERE pv.agent_name = ?
        """
        params: list = [agent_name]

        if df:
            query += " AND pv.captured_at >= ?"
            params.append(df)
        if dt:
            query += " AND pv.captured_at <= ?"
            params.append(dt + "T23:59:59")

        query += " ORDER BY pv.captured_at ASC"
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_pass_rate_by_version(agent_name: str) -> list[dict]:
    """Compute pass rate (score >= 7.0) per prompt version for an agent.

    Returns list of dicts with id, git_hash, pass_rate, total_scores, passing_scores.
    Ordered by captured_at ASC (oldest first).
    """
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute(
            """
            SELECT pv.id,
                   pv.git_hash,
                   pv.captured_at,
                   COUNT(qs.id) AS total_scores,
                   SUM(CASE WHEN qs.score >= ? THEN 1 ELSE 0 END) AS passing_scores
            FROM prompt_versions pv
            JOIN quality_scores qs ON qs.prompt_version_id = pv.id
            WHERE pv.agent_name = ?
            GROUP BY pv.id
            ORDER BY pv.captured_at ASC
            """,
            (_PASS_THRESHOLD, agent_name),
        )
        results = []
        for row in cur.fetchall():
            total = row["total_scores"]
            passing = row["passing_scores"]
            rate = passing / total if total > 0 else 0.0
            results.append({
                "id": row["id"],
                "git_hash": row["git_hash"],
                "captured_at": row["captured_at"],
                "total_scores": total,
                "passing_scores": passing,
                "pass_rate": round(rate, 3),
            })
        return results
    finally:
        conn.close()


def detect_drift(agent_name: str) -> dict | None:
    """Compare pass rate of current prompt version vs previous.

    Returns dict with warning info if drop >10%, else None.
    """
    versions = get_pass_rate_by_version(agent_name)
    if len(versions) < 2:
        return None

    previous = versions[-2]
    current = versions[-1]

    drop_pct = (previous["pass_rate"] - current["pass_rate"]) * 100

    if drop_pct > 10.0:
        return {
            "agent_name": agent_name,
            "current_hash": current["git_hash"],
            "previous_hash": previous["git_hash"],
            "current_id": current["id"],
            "previous_id": previous["id"],
            "current_rate": current["pass_rate"],
            "previous_rate": previous["pass_rate"],
            "drop_pct": round(drop_pct, 1),
        }

    return None


# -- Chart.js JSON data endpoints (Task 5) -----------------------------------


@router.get("/performance/data/quality")
def performance_data_quality(
    agent: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Return Chart.js-native data for quality scores over time with prompt version annotations."""
    if not agent:
        return JSONResponse({"labels": [], "datasets": [], "annotations": {}})

    scores = get_quality_over_time(agent, date_from, date_to)
    markers = get_prompt_change_markers(agent, date_from, date_to)

    # Build annotation lines for prompt version changes
    annotations = {}
    for i, m in enumerate(markers):
        annotations[f"version_{i}"] = {
            "type": "line",
            "xMin": m["date"],
            "xMax": m["date"],
            "borderColor": "#fbbf24",
            "borderWidth": 2,
            "borderDash": [5, 5],
            "label": {
                "display": True,
                "content": m["git_hash"][:7],
                "position": "start",
            },
        }

    return JSONResponse({
        "labels": [s["date"] for s in scores],
        "datasets": [{
            "label": f"{agent} Quality Score",
            "data": [s["avg_score"] for s in scores],
            "borderColor": "#38bdf8",
            "backgroundColor": "rgba(56, 189, 248, 0.1)",
            "fill": True,
        }],
        "annotations": annotations,
    })


@router.get("/performance/data/drift")
def performance_data_drift():
    """Return list of agents with drift warnings (>10% pass rate drop)."""
    agents = get_agent_list()
    drift_warnings = []
    for agent_name in agents:
        warning = detect_drift(agent_name)
        if warning:
            safe_agent = quote(agent_name, safe="")
            warning["diff_link"] = (
                f"/prompts/{safe_agent}/diff?from={warning['previous_id']}&to={warning['current_id']}"
            )
            drift_warnings.append(warning)
    return JSONResponse(drift_warnings)


# -- Performance tab route (Task 6) ------------------------------------------


@router.get("/performance", response_class=HTMLResponse)
def performance(
    request: Request,
    agent: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Return the Performance tab with quality correlation and drift warnings."""
    agents = get_agent_list()
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "agents": agents,
        "selected_agent": agent or (agents[0] if agents else ""),
        "date_from": _valid_date(date_from) or "",
        "date_to": _valid_date(date_to) or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/performance.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "performance",
        "tab_template": "tabs/performance.html",
    })

"""Metrics tab -- aggregate metrics over configurable date ranges (FR31)."""

import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from orchestrator.traces_db import get_db, TRACES_DB_PATH

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _valid_date(s: str | None) -> str | None:
    """Return the date string if it matches YYYY-MM-DD format, else None."""
    return s if s and _DATE_RE.match(s) else None


def _build_date_filter(
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, str, list]:
    """Build SQL date filter clause fragments and params list.

    Returns (from_expr, to_expr, params) where *_expr is either a "?" placeholder
    (with the value appended to params) or a SQLite date() literal for the default range.
    """
    df = _valid_date(date_from)
    dt = _valid_date(date_to)
    params: list = []

    if df:
        from_expr = "?"
        params.append(df)
    else:
        from_expr = "date('now', '-30 days')"

    if dt:
        to_expr = "?"
        params.append(dt + "T23:59:59")
    else:
        to_expr = "date('now')"

    return from_expr, to_expr, params


# -- daily_metrics cache-first query (R4-2 E4-F3) ----------------------------


def get_daily_metrics(
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Return daily metrics from cache table, falling back to live queries.

    If the daily_metrics table has data for the requested range, use it.
    Otherwise fall back to computing from agent_runs/pipeline_runs.
    """
    if not TRACES_DB_PATH.exists():
        return []

    df = _valid_date(date_from)
    dt = _valid_date(date_to)

    conn = get_db()
    try:
        # Try cache first
        cache_query = "SELECT date, metric_name, metric_value FROM daily_metrics WHERE 1=1"
        params: list = []
        if df:
            cache_query += " AND date >= ?"
            params.append(df)
        if dt:
            cache_query += " AND date <= ?"
            params.append(dt)
        cache_query += " ORDER BY date ASC, metric_name ASC"

        cur = conn.execute(cache_query, params)
        rows = cur.fetchall()

        if rows:
            # Pivot into date-keyed dicts
            result: dict[str, dict] = {}
            for row in rows:
                d = row["date"]
                if d not in result:
                    result[d] = {"date": d}
                result[d][row["metric_name"]] = row["metric_value"]
            return list(result.values())

        # Fallback: compute live from agent_runs/pipeline_runs
        from_expr, to_expr, live_params = _build_date_filter(date_from, date_to)
        cur = conn.execute(
            f"""
            SELECT date(ar.started_at) AS date,
                   SUM(COALESCE(ar.input_tokens, 0) + COALESCE(ar.output_tokens, 0)) AS total_tokens,
                   AVG(ar.latency_ms) AS avg_latency_ms,
                   CAST(SUM(CASE WHEN ar.status = 'completed' THEN 1 ELSE 0 END) AS REAL) / MAX(COUNT(*), 1) AS success_rate
            FROM agent_runs ar
            WHERE ar.started_at >= {from_expr}
              AND ar.started_at <= {to_expr}
            GROUP BY date(ar.started_at)
            ORDER BY date(ar.started_at) ASC
            """,
            live_params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# -- Aggregate backend functions (Task 1) ------------------------------------


def get_tokens_per_day(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """SUM(input_tokens + output_tokens) grouped by date for agent_runs in range."""
    if not TRACES_DB_PATH.exists():
        return []

    from_expr, to_expr, params = _build_date_filter(date_from, date_to)
    conn = get_db()
    try:
        cur = conn.execute(
            f"""
            SELECT date(ar.started_at) AS date,
                   SUM(COALESCE(ar.input_tokens, 0) + COALESCE(ar.output_tokens, 0)) AS total_tokens
            FROM agent_runs ar
            WHERE ar.started_at >= {from_expr}
              AND ar.started_at <= {to_expr}
            GROUP BY date(ar.started_at)
            ORDER BY date(ar.started_at) ASC
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_latency_per_agent(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """AVG(latency_ms) per agent_name for agent_runs in range."""
    if not TRACES_DB_PATH.exists():
        return []

    from_expr, to_expr, params = _build_date_filter(date_from, date_to)
    conn = get_db()
    try:
        cur = conn.execute(
            f"""
            SELECT ar.agent_name,
                   AVG(ar.latency_ms) AS avg_latency_ms
            FROM agent_runs ar
            WHERE ar.started_at >= {from_expr}
              AND ar.started_at <= {to_expr}
              AND ar.latency_ms IS NOT NULL
            GROUP BY ar.agent_name
            ORDER BY ar.agent_name ASC
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_success_failure_rates(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """COUNT of agent_runs by status grouped by date."""
    if not TRACES_DB_PATH.exists():
        return []

    from_expr, to_expr, params = _build_date_filter(date_from, date_to)
    conn = get_db()
    try:
        cur = conn.execute(
            f"""
            SELECT date(ar.started_at) AS date,
                   SUM(CASE WHEN ar.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN ar.status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM agent_runs ar
            WHERE ar.started_at >= {from_expr}
              AND ar.started_at <= {to_expr}
            GROUP BY date(ar.started_at)
            ORDER BY date(ar.started_at) ASC
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_pipeline_completion_rate(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """Completed / total pipeline_runs per date."""
    if not TRACES_DB_PATH.exists():
        return []

    from_expr, to_expr, params = _build_date_filter(date_from, date_to)
    conn = get_db()
    try:
        cur = conn.execute(
            f"""
            SELECT date(p.started_at) AS date,
                   CAST(SUM(CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) AS completion_rate
            FROM pipeline_runs p
            WHERE p.started_at >= {from_expr}
              AND p.started_at <= {to_expr}
            GROUP BY date(p.started_at)
            ORDER BY date(p.started_at) ASC
            """,
            params,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# -- Chart.js JSON data endpoints (Task 2) -----------------------------------


@router.get("/metrics/data/tokens")
def metrics_data_tokens(date_from: str | None = None, date_to: str | None = None):
    """Return Chart.js-native data for tokens per day line chart."""
    rows = get_tokens_per_day(date_from, date_to)
    return JSONResponse({
        "labels": [r["date"] for r in rows],
        "datasets": [{
            "label": "Total Tokens",
            "data": [r["total_tokens"] for r in rows],
            "borderColor": "#38bdf8",
            "backgroundColor": "rgba(56, 189, 248, 0.1)",
            "fill": True,
        }],
    })


@router.get("/metrics/data/latency")
def metrics_data_latency(date_from: str | None = None, date_to: str | None = None):
    """Return Chart.js-native data for avg latency per agent bar chart."""
    rows = get_latency_per_agent(date_from, date_to)
    return JSONResponse({
        "labels": [r["agent_name"] for r in rows],
        "datasets": [{
            "label": "Avg Latency (ms)",
            "data": [r["avg_latency_ms"] for r in rows],
            "backgroundColor": "#a78bfa",
        }],
    })


@router.get("/metrics/data/success-rates")
def metrics_data_success_rates(date_from: str | None = None, date_to: str | None = None):
    """Return Chart.js-native data for stacked success/failure area chart."""
    rows = get_success_failure_rates(date_from, date_to)
    return JSONResponse({
        "labels": [r["date"] for r in rows],
        "datasets": [
            {
                "label": "Completed",
                "data": [r["completed"] for r in rows],
                "borderColor": "#4ade80",
                "backgroundColor": "rgba(74, 222, 128, 0.2)",
                "fill": True,
            },
            {
                "label": "Failed",
                "data": [r["failed"] for r in rows],
                "borderColor": "#f87171",
                "backgroundColor": "rgba(248, 113, 113, 0.2)",
                "fill": True,
            },
        ],
    })


@router.get("/metrics/data/pipeline-completion")
def metrics_data_pipeline_completion(date_from: str | None = None, date_to: str | None = None):
    """Return Chart.js-native data for pipeline completion rate line chart."""
    rows = get_pipeline_completion_rate(date_from, date_to)
    return JSONResponse({
        "labels": [r["date"] for r in rows],
        "datasets": [{
            "label": "Completion Rate",
            "data": [r["completion_rate"] for r in rows],
            "borderColor": "#fbbf24",
            "backgroundColor": "rgba(251, 191, 36, 0.1)",
            "fill": True,
        }],
    })


# -- Metrics tab route (Task 3) ---------------------------------------------


@router.get("/metrics", response_class=HTMLResponse)
def metrics(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Return the Metrics tab with Chart.js visualizations."""
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "date_from": _valid_date(date_from) or "",
        "date_to": _valid_date(date_to) or "",
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/metrics.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "metrics",
        "tab_template": "tabs/metrics.html",
    })

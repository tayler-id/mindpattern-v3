"""Traces tab -- trace tree viewer for pipeline run debugging (FR30)."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from orchestrator.traces_db import get_db, TRACES_DB_PATH

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def get_trace_tree(pipeline_run_id: str) -> list[dict]:
    """Build a nested trace tree from flat trace_spans rows for a pipeline run.

    Returns a list of root span dicts, each with a ``children`` list (recursively nested).
    Orphaned spans (parent_span_id references a nonexistent span) are attached to root level.
    """
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute(
            """
            SELECT ts.*
            FROM trace_spans ts
            JOIN agent_runs ar ON ts.agent_run_id = ar.id
            WHERE ar.pipeline_run_id = ?
            ORDER BY ts.started_at ASC
            """,
            (pipeline_run_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Index all spans by id
    nodes: dict[str, dict] = {}
    for row in rows:
        node = dict(row)
        node["children"] = []
        nodes[node["id"]] = node

    # Build tree: attach children to parents, collect roots
    roots: list[dict] = []
    for node in nodes.values():
        parent_id = node.get("parent_span_id")
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


def get_trace_run_list() -> list[dict]:
    """Return recent pipeline runs (<30 days) that have trace spans.

    Filters out recent runs with zero spans (these are not useful to browse).
    Ordered by started_at DESC.
    """
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute(
            """
            SELECT
                p.id,
                p.pipeline_type,
                p.status,
                p.started_at,
                p.completed_at,
                COUNT(DISTINCT ar.id) AS agent_count,
                COUNT(ts.id) AS span_count
            FROM pipeline_runs p
            LEFT JOIN agent_runs ar ON ar.pipeline_run_id = p.id
            LEFT JOIN trace_spans ts ON ts.agent_run_id = ar.id
            WHERE p.started_at >= date('now', '-30 days')
            GROUP BY p.id
            HAVING agent_count > 0
            ORDER BY p.started_at DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_older_trace_runs() -> list[dict]:
    """Return pipeline runs older than 30 days with a pruned indicator.

    Does NOT filter by span_count -- pruned runs have 0 spans by definition.
    """
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute(
            """
            SELECT
                p.id,
                p.pipeline_type,
                p.status,
                p.started_at,
                p.completed_at,
                COUNT(ts.id) AS span_count
            FROM pipeline_runs p
            LEFT JOIN agent_runs ar ON ar.pipeline_run_id = p.id
            LEFT JOIN trace_spans ts ON ts.agent_run_id = ar.id
            WHERE p.started_at < date('now', '-30 days')
            GROUP BY p.id
            ORDER BY p.started_at DESC
            """
        )
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["spans_pruned"] = d["span_count"] == 0
            results.append(d)
        return results
    finally:
        conn.close()


def check_spans_pruned(pipeline_run_id: str) -> bool:
    """Check if a pipeline run's trace spans have been pruned (old run with no spans).

    Returns True if the run is older than 30 days AND has zero trace spans.
    Returns False if the run has spans or is recent.
    """
    if not TRACES_DB_PATH.exists():
        return False

    conn = get_db()
    try:
        # Check if the run is older than 30 days
        cur = conn.execute(
            """
            SELECT
                p.started_at,
                (p.started_at < date('now', '-30 days')) AS is_old,
                COUNT(ts.id) AS span_count
            FROM pipeline_runs p
            LEFT JOIN agent_runs ar ON ar.pipeline_run_id = p.id
            LEFT JOIN trace_spans ts ON ts.agent_run_id = ar.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (pipeline_run_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        return bool(row["is_old"]) and row["span_count"] == 0
    finally:
        conn.close()


def _get_run_with_tree(run_id: str) -> tuple[dict | None, list[dict], bool]:
    """Fetch pipeline run metadata, trace tree, and pruned status in a single connection.

    Returns (pipeline_run_dict | None, tree_roots, spans_pruned_bool).
    """
    if not TRACES_DB_PATH.exists():
        return None, [], False

    conn = get_db()
    try:
        # Pipeline run metadata
        cur = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        pipeline_run = dict(row) if row else None

        # Trace spans
        cur = conn.execute(
            """
            SELECT ts.*
            FROM trace_spans ts
            JOIN agent_runs ar ON ts.agent_run_id = ar.id
            WHERE ar.pipeline_run_id = ?
            ORDER BY ts.started_at ASC
            """,
            (run_id,),
        )
        span_rows = cur.fetchall()

        # Build tree
        tree: list[dict] = []
        if span_rows:
            nodes: dict[str, dict] = {}
            for r in span_rows:
                node = dict(r)
                node["children"] = []
                nodes[node["id"]] = node
            for node in nodes.values():
                pid = node.get("parent_span_id")
                if pid and pid in nodes:
                    nodes[pid]["children"].append(node)
                else:
                    tree.append(node)

        # If no trace spans, build tree from agent_runs instead
        if not span_rows:
            cur = conn.execute(
                """
                SELECT id, agent_name, status, started_at, completed_at,
                       latency_ms, error, output
                FROM agent_runs
                WHERE pipeline_run_id = ?
                ORDER BY started_at ASC
                """,
                (run_id,),
            )
            agent_rows = cur.fetchall()
            for r in agent_rows:
                node = dict(r)
                node["children"] = []
                node["span_type"] = "agent"
                node["name"] = node.get("agent_name", "unknown")
                tree.append(node)

        # Pruned check
        spans_pruned = False
        if pipeline_run and not span_rows and not tree:
            is_old = conn.execute(
                "SELECT (started_at < date('now', '-30 days')) AS is_old FROM pipeline_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if is_old and is_old["is_old"]:
                spans_pruned = True

        return pipeline_run, tree, spans_pruned
    finally:
        conn.close()


@router.get("/traces/{run_id}", response_class=HTMLResponse)
def trace_detail(request: Request, run_id: str):
    """Return the trace tree view for a specific pipeline run."""
    pipeline_run, tree, spans_pruned = _get_run_with_tree(run_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "pipeline_run": pipeline_run,
        "tree": tree,
        "spans_pruned": spans_pruned,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/trace_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "traces",
        "tab_template": "tabs/trace_detail.html",
    })


@router.get("/traces", response_class=HTMLResponse)
def traces(request: Request):
    """Return the Traces tab -- list pipeline runs with span counts."""
    runs = get_trace_run_list()
    older_runs = get_older_trace_runs()
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "runs": runs,
        "older_runs": older_runs,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/traces.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "traces",
        "tab_template": "tabs/traces.html",
    })

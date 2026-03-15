"""Pipeline Status tab — real-time view of current or most recent pipeline run."""

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from dashboard.platform_health import check_linkedin_token_health
from orchestrator.traces_db import get_db, TRACES_DB_PATH

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
# On Fly.io the reports live on the volume at /data/reports/ (symlinked via /app/data)
DATA_DIR = SCRIPT_DIR / "data"

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def get_pipeline_context() -> dict:
    """Query traces.db for current running or most recent pipeline run + agent runs + events."""
    pipeline_run = None
    agent_runs = []
    recent_events = []

    if not TRACES_DB_PATH.exists():
        return {"pipeline_run": None, "agent_runs": [], "recent_events": []}

    conn = get_db()
    try:
        # First try to find a currently active pipeline (any non-terminal state)
        cur = conn.execute(
            "SELECT * FROM pipeline_runs WHERE status NOT IN ('completed', 'failed') "
            "ORDER BY started_at DESC LIMIT 1"
        )
        pipeline_run = cur.fetchone()

        # If nothing running, get the most recent completed/failed run
        if not pipeline_run:
            cur = conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
            )
            pipeline_run = cur.fetchone()

        if pipeline_run:
            cur = conn.execute(
                "SELECT * FROM agent_runs WHERE pipeline_run_id = ? ORDER BY started_at ASC",
                (pipeline_run["id"],),
            )
            agent_runs = cur.fetchall()

            # Get recent events for this run
            cur = conn.execute(
                "SELECT * FROM events WHERE pipeline_run_id = ? ORDER BY id DESC LIMIT 50",
                (pipeline_run["id"],),
            )
            recent_events = cur.fetchall()
    finally:
        conn.close()

    # Parse event payloads
    parsed_events = []
    for evt in reversed(recent_events):  # chronological order
        e = dict(evt)
        try:
            e["parsed_payload"] = json.loads(e.get("payload", "{}"))
        except (json.JSONDecodeError, TypeError):
            e["parsed_payload"] = {}
        parsed_events.append(e)

    return {
        "pipeline_run": dict(pipeline_run) if pipeline_run else None,
        "agent_runs": [dict(r) for r in agent_runs],
        "recent_events": parsed_events,
    }


def _first_existing(*paths: Path) -> Path | None:
    """Return the first path that exists, or None."""
    for p in paths:
        if p.exists():
            return p
    return None


@router.get("/api/pipeline-log", response_class=HTMLResponse)
def pipeline_log(request: Request, lines: int = 50):
    """Return the tail of today's debug log + orchestrator JSONL as HTML lines."""
    today = date.today().isoformat()
    output_lines = []

    # Debug log (phases, watchdog, findings)
    # Check both local (/app/reports) and volume (/app/data/reports) paths
    debug_log = _first_existing(
        SCRIPT_DIR / "reports" / "ramsay" / f"{today}.debug.log",
        DATA_DIR / "reports" / "ramsay" / f"{today}.debug.log",
    )
    if debug_log:
        try:
            all_lines = debug_log.read_text().strip().split("\n")
            output_lines.extend(all_lines[-lines:])
        except Exception:
            pass

    # Orchestrator JSONL (pipeline stages with timestamps)
    jsonl_log = _first_existing(
        SCRIPT_DIR / "reports" / f"orchestrator-{today}.jsonl",
        DATA_DIR / "reports" / f"orchestrator-{today}.jsonl",
    )
    if jsonl_log:
        try:
            for raw in jsonl_log.read_text().strip().split("\n"):
                if not raw.strip():
                    continue
                try:
                    entry = json.loads(raw)
                    ts = entry.get("ts", "")[:19]
                    stage = entry.get("stage", "")
                    msg = entry.get("msg", "")
                    output_lines.append(f"{ts} [{stage}] {msg}")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    # Social JSONL
    social_log = _first_existing(
        SCRIPT_DIR / "reports" / f"social-{today}.jsonl",
        DATA_DIR / "reports" / f"social-{today}.jsonl",
    )
    if social_log:
        try:
            for raw in social_log.read_text().strip().split("\n"):
                if not raw.strip():
                    continue
                try:
                    entry = json.loads(raw)
                    ts = entry.get("ts", "")[:19]
                    stage = entry.get("stage", "")
                    msg = entry.get("msg", "")
                    output_lines.append(f"{ts} [social:{stage}] {msg}")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    # Engagement JSONL
    eng_log = _first_existing(
        SCRIPT_DIR / "reports" / f"engagement-{today}.jsonl",
        DATA_DIR / "reports" / f"engagement-{today}.jsonl",
    )
    if eng_log:
        try:
            for raw in eng_log.read_text().strip().split("\n"):
                if not raw.strip():
                    continue
                try:
                    entry = json.loads(raw)
                    ts = entry.get("ts", "")[:19]
                    stage = entry.get("stage", "")
                    msg = entry.get("msg", "")
                    output_lines.append(f"{ts} [engagement:{stage}] {msg}")
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    # Sort all lines by timestamp
    output_lines.sort()
    tail = output_lines[-lines:] if output_lines else ["No logs for today."]

    # Return as escaped HTML lines
    import html
    escaped = "\n".join(html.escape(line) for line in tail)
    return escaped


@router.get("/pipeline-status", response_class=HTMLResponse)
def pipeline_status(request: Request):
    """Return pipeline status tab content.

    htmx requests get the tab fragment; direct requests get the full page.
    """
    ctx = get_pipeline_context()
    linkedin_health = check_linkedin_token_health()
    is_htmx = request.headers.get("HX-Request") == "true"

    if is_htmx:
        return templates.TemplateResponse("tabs/pipeline_status.html", {
            "request": request,
            "linkedin_health": linkedin_health,
            **ctx,
        })

    return templates.TemplateResponse("base.html", {
        "request": request,
        "active_tab": "pipeline-status",
        "linkedin_health": linkedin_health,
        **ctx,
    })

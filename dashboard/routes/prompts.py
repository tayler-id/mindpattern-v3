"""Prompts tab — version history, detail, diff, and rollback for agent prompt files."""

import html as _html
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from orchestrator.traces_db import get_db, TRACES_DB_PATH

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def get_agent_list() -> list[dict]:
    """Return all agents with their latest prompt version info and total version count."""
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute("""
            SELECT
                pv.agent_name,
                pv.git_hash AS latest_hash,
                pv.captured_at AS latest_captured_at,
                pv.file_path,
                (SELECT COUNT(*) FROM prompt_versions pv2
                 WHERE pv2.agent_name = pv.agent_name) AS version_count,
                (SELECT COUNT(*) FROM agent_runs ar
                 WHERE ar.agent_name = pv.agent_name
                   AND ar.prompt_version IS NOT NULL) AS total_runs
            FROM prompt_versions pv
            INNER JOIN (
                SELECT agent_name, MAX(id) AS max_id
                FROM prompt_versions
                GROUP BY agent_name
            ) latest ON pv.id = latest.max_id
            ORDER BY pv.agent_name
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_version_history(agent_name: str) -> list[dict]:
    """Return chronological version history for an agent: hash, date, run count."""
    if not TRACES_DB_PATH.exists():
        return []

    conn = get_db()
    try:
        cur = conn.execute("""
            SELECT
                pv.id,
                pv.git_hash,
                pv.captured_at,
                pv.file_path,
                COUNT(ar.id) AS run_count
            FROM prompt_versions pv
            LEFT JOIN agent_runs ar
                ON ar.agent_name = pv.agent_name
                AND ar.prompt_version = pv.git_hash
            WHERE pv.agent_name = ?
            GROUP BY pv.id
            ORDER BY pv.captured_at DESC
        """, (agent_name,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_version_detail(agent_name: str, version_id: int) -> dict | None:
    """Return full version detail: hash, path, first/last run dates, total runs, avg quality."""
    if not TRACES_DB_PATH.exists():
        return None

    conn = get_db()
    try:
        cur = conn.execute(
            "SELECT * FROM prompt_versions WHERE id = ? AND agent_name = ?",
            (version_id, agent_name),
        )
        pv_row = cur.fetchone()
        if not pv_row:
            return None

        pv = dict(pv_row)

        # Get run statistics for this version
        cur = conn.execute("""
            SELECT
                COUNT(*) AS total_runs,
                MIN(ar.started_at) AS first_run_at,
                MAX(ar.started_at) AS last_run_at,
                AVG(ar.quality_score) AS avg_quality_score
            FROM agent_runs ar
            WHERE ar.agent_name = ?
              AND ar.prompt_version = ?
        """, (agent_name, pv["git_hash"]))
        stats = dict(cur.fetchone())

        return {**pv, **stats}
    finally:
        conn.close()


def get_prompt_diff(
    agent_name: str,
    version_id_from: int,
    version_id_to: int,
) -> str | None:
    """Return the unified diff between two prompt versions for an agent.

    Returns:
        - The raw unified diff string if both versions are found.
        - Empty string if both versions point to the same git hash.
        - None if either version ID is not found, doesn't belong to the agent, or git fails.
    """
    if not TRACES_DB_PATH.exists():
        return None

    conn = get_db()
    try:
        # Look up both versions
        cur = conn.execute(
            "SELECT id, git_hash, file_path FROM prompt_versions "
            "WHERE id = ? AND agent_name = ?",
            (version_id_from, agent_name),
        )
        row_from = cur.fetchone()
        if not row_from:
            return None

        cur = conn.execute(
            "SELECT id, git_hash, file_path FROM prompt_versions "
            "WHERE id = ? AND agent_name = ?",
            (version_id_to, agent_name),
        )
        row_to = cur.fetchone()
        if not row_to:
            return None
    finally:
        conn.close()

    hash_from = row_from["git_hash"]
    hash_to = row_to["git_hash"]
    file_path = row_from["file_path"]

    # Same hash means no diff
    if hash_from == hash_to:
        return ""

    repo_root = TRACES_DB_PATH.parent
    try:
        proc = subprocess.run(
            ["git", "diff", hash_from, hash_to, "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        # Return stdout (the diff); stderr is non-empty for bad objects etc.
        # but git diff still returns rc=0 for valid comparisons.
        if proc.returncode != 0:
            return None
        return proc.stdout
    except (subprocess.SubprocessError, OSError):
        return None


def revert_prompt_version(
    agent_name: str,
    version_id: int,
) -> dict | None:
    """Revert an agent's prompt file to a previous version via git checkout + commit.

    Returns:
        - A dict with success=True, reverted_to_hash, new_hash on success.
        - None if version_id is not found or doesn't belong to agent_name.

    Raises no exceptions — git failures return None.
    """
    if not TRACES_DB_PATH.exists():
        return None

    conn = get_db()
    try:
        cur = conn.execute(
            "SELECT id, git_hash, file_path FROM prompt_versions "
            "WHERE id = ? AND agent_name = ?",
            (version_id, agent_name),
        )
        row = cur.fetchone()
        if not row:
            return None
    finally:
        conn.close()

    target_hash = row["git_hash"]
    file_path = row["file_path"]
    short_hash = target_hash[:8]
    repo_root = TRACES_DB_PATH.parent

    try:
        # 1. Restore the file content from the target hash
        proc = subprocess.run(
            ["git", "checkout", target_hash, "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        if proc.returncode != 0:
            return None

        # 2. Stage the reverted file
        proc = subprocess.run(
            ["git", "add", file_path],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        if proc.returncode != 0:
            # Restore working tree to HEAD state on failure
            subprocess.run(
                ["git", "checkout", "HEAD", "--", file_path],
                capture_output=True, text=True, cwd=str(repo_root), timeout=10,
            )
            return None

        # 3. Commit the revert (scoped to the prompt file only)
        commit_msg = f"Revert {agent_name} to {short_hash} via dashboard"
        proc = subprocess.run(
            ["git", "commit", "-m", commit_msg, "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        if proc.returncode != 0:
            # Restore working tree to HEAD state on failure (e.g. nothing to commit)
            subprocess.run(
                ["git", "checkout", "HEAD", "--", file_path],
                capture_output=True, text=True, cwd=str(repo_root), timeout=10,
            )
            return None

        # 4. Capture the new hash after commit
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", file_path],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=10,
        )
        new_hash = proc.stdout.strip()
        if not new_hash:
            return None

        # 5. Insert new prompt_versions row for the reverted state
        now = datetime.now(timezone.utc).isoformat()
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO prompt_versions "
                "(agent_name, git_hash, captured_at, file_path) VALUES (?, ?, ?, ?)",
                (agent_name, new_hash, now, file_path),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "success": True,
            "reverted_to_hash": short_hash,
            "new_hash": new_hash[:8],
        }

    except (subprocess.SubprocessError, OSError):
        return None


@router.post("/prompts/{agent_name}/revert", response_class=HTMLResponse)
def prompt_revert(
    request: Request,
    agent_name: str,
    version_id: int = Form(...),
):
    """Revert an agent's prompt file to a previous version.

    On success, redirects to the prompt history view.
    On failure, returns an error HTML fragment.
    """
    result = revert_prompt_version(agent_name, version_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    if result and result.get("success"):
        if is_htmx:
            response = HTMLResponse(content="", status_code=200)
            response.headers["HX-Redirect"] = f"/prompts/{agent_name}"
            return response
        return RedirectResponse(url=f"/prompts/{agent_name}", status_code=303)

    # Error case — escape agent_name to prevent XSS
    safe_name = _html.escape(agent_name)
    error_html = (
        '<div class="card" style="border-color:#f87171;">'
        '<p class="error-text">Failed to revert prompt version. '
        'The version may not exist or a git error occurred.</p>'
        f'<a hx-get="/prompts/{safe_name}" hx-target="#main-content" '
        f'hx-swap="innerHTML" style="color:#38bdf8;cursor:pointer;">'
        '&larr; Back to history</a></div>'
    )

    if is_htmx:
        return HTMLResponse(content=error_html, status_code=422)
    # Non-htmx: return full-page redirect to history view
    return RedirectResponse(url=f"/prompts/{agent_name}", status_code=303)


@router.get("/prompts/{agent_name}/diff", response_class=HTMLResponse)
def prompt_diff(
    request: Request,
    agent_name: str,
    from_version: int = Query(..., alias="from"),
    to_version: int = Query(..., alias="to"),
):
    """Return rendered diff between two prompt versions as an HTML fragment."""
    diff_text = get_prompt_diff(agent_name, from_version, to_version)
    is_htmx = request.headers.get("HX-Request") == "true"

    # Look up short hashes for display
    conn = get_db()
    try:
        from_row = conn.execute(
            "SELECT git_hash FROM prompt_versions WHERE id = ?", (from_version,)
        ).fetchone()
        to_row = conn.execute(
            "SELECT git_hash FROM prompt_versions WHERE id = ?", (to_version,)
        ).fetchone()
    finally:
        conn.close()

    from_hash = from_row["git_hash"][:8] if from_row else "unknown"
    to_hash = to_row["git_hash"][:8] if to_row else "unknown"

    ctx = {
        "request": request,
        "agent_name": agent_name,
        "diff_text": diff_text or "",
        "from_hash": from_hash,
        "to_hash": to_hash,
        "from_version": from_version,
        "to_version": to_version,
        "no_diff": diff_text is not None and diff_text == "",
        "error": diff_text is None,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/prompt_diff.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "prompts",
        "tab_template": "tabs/prompt_diff.html",
    })


@router.get("/prompts/{agent_name}/{version_id}", response_class=HTMLResponse)
def prompt_detail(request: Request, agent_name: str, version_id: int):
    """Return version detail fragment for a specific prompt version."""
    detail = get_version_detail(agent_name, version_id)
    is_htmx = request.headers.get("HX-Request") == "true"

    # Determine if this is the latest version (revert button hidden for latest)
    is_latest = False
    if detail:
        versions = get_version_history(agent_name)
        if versions and versions[0]["id"] == version_id:
            is_latest = True

    ctx = {
        "request": request,
        "agent_name": agent_name,
        "detail": detail,
        "is_latest": is_latest,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/prompt_detail.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "prompts",
        "tab_template": "tabs/prompt_detail.html",
    })


@router.get("/prompts/{agent_name}", response_class=HTMLResponse)
def prompt_history(request: Request, agent_name: str):
    """Return version history for a specific agent."""
    versions = get_version_history(agent_name)
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "agent_name": agent_name,
        "versions": versions,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/prompt_history.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "prompts",
        "tab_template": "tabs/prompt_history.html",
    })


@router.get("/prompts", response_class=HTMLResponse)
def prompts(request: Request):
    """Return the Prompts tab — agent list with latest version info."""
    agents = get_agent_list()
    is_htmx = request.headers.get("HX-Request") == "true"

    ctx = {
        "request": request,
        "agents": agents,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/prompts.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "prompts",
        "tab_template": "tabs/prompts.html",
    })

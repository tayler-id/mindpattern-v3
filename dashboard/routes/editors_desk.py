"""Editor's Desk tab — approval queue for proof packages, engagement gate, and posting."""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from dashboard.platform_health import check_linkedin_token_health
from orchestrator.traces_db import get_db, TRACES_DB_PATH

# v3: engagement moved to social module
try:
    from social.engagement import EngagementPipeline
    def post_engagement_replies(*args, **kwargs):
        pass  # Handled via EngagementPipeline now
except ImportError:
    def post_engagement_replies(*args, **kwargs):
        pass

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Path to social-post.py for subprocess calls
SOCIAL_POST_SCRIPT = Path(__file__).resolve().parent.parent.parent / "social-post.py"

# Paths for memory.py integration (social post/feedback storage)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_SCRIPT = PROJECT_ROOT / "memory.py"
USER_ID = os.environ.get("DASHBOARD_USER", "ramsay")
MEMORY_DB = PROJECT_ROOT / "data" / USER_ID / "memory.db"

# Engagement pipeline paths
ENGAGEMENT_CANDIDATES_FILE = PROJECT_ROOT / "data" / "engagement-drafts" / "engagement-candidates.json"
ENGAGEMENT_APPROVED_FILE = PROJECT_ROOT / "data" / "engagement-drafts" / "engagement-approved.json"

router = APIRouter()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_pending_packages(db_path: Path | None = None) -> list[dict]:
    """Return all proof_packages with status pending_review, newest first."""
    path = db_path or TRACES_DB_PATH
    if not path.exists():
        return []

    conn = get_db(path)
    try:
        cur = conn.execute(
            "SELECT pp.*, pr.pipeline_type "
            "FROM proof_packages pp "
            "LEFT JOIN pipeline_runs pr ON pr.id = pp.pipeline_run_id "
            "WHERE pp.status = 'pending_review' "
            "ORDER BY pp.created_at DESC"
        )
        rows = cur.fetchall()
        return [_parse_package_fields(row) for row in rows]
    finally:
        conn.close()


def get_package_detail(package_id: str, db_path: Path | None = None) -> dict | None:
    """Return a single proof_package by id with parsed JSON fields."""
    path = db_path or TRACES_DB_PATH
    if not path.exists():
        return None

    conn = get_db(path)
    try:
        cur = conn.execute(
            "SELECT pp.*, pr.pipeline_type "
            "FROM proof_packages pp "
            "LEFT JOIN pipeline_runs pr ON pr.id = pp.pipeline_run_id "
            "WHERE pp.id = ?",
            (package_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return _parse_package_fields(row)
    finally:
        conn.close()


def update_package_status(
    package_id: str,
    status: str,
    *,
    notes: str | None = None,
    post_results: dict | None = None,
    db_path: Path | None = None,
) -> None:
    """Update a proof_package's status, reviewer_notes, post_results, and reviewed_at."""
    path = db_path or TRACES_DB_PATH
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db(path)
    try:
        post_results_json = json.dumps(post_results) if post_results else None
        conn.execute(
            "UPDATE proof_packages SET status = ?, "
            "reviewer_notes = COALESCE(?, reviewer_notes), "
            "post_results = COALESCE(?, post_results), reviewed_at = ? "
            "WHERE id = ?",
            (status, notes, post_results_json, now, package_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_eic_kill(db_path: Path | None = None, date_str: str | None = None) -> str | None:
    """Return the EIC kill explanation for the given date, or None.

    Queries the events table for the most recent 'eic_kill_all' event
    on the given date (or today if not specified).
    """
    path = db_path or TRACES_DB_PATH
    if not path.exists():
        return None

    if date_str is None:
        date_str = date.today().isoformat()

    conn = get_db(path)
    try:
        cur = conn.execute(
            "SELECT payload FROM events "
            "WHERE event_type = 'eic_kill_all' "
            "AND created_at LIKE ? "
            "ORDER BY id DESC LIMIT 1",
            (f"{date_str}%",),
        )
        row = cur.fetchone()
        if not row:
            return None
        payload = json.loads(row["payload"])
        return payload.get("kill_explanation")
    except (json.JSONDecodeError, TypeError):
        return None
    finally:
        conn.close()


def get_reviewed_packages(db_path: Path | None = None, date_str: str | None = None) -> list[dict]:
    """Return all proof_packages for the given date that have been reviewed.

    Includes packages with status approved, rejected, revision, posted,
    partially_posted, or failed.
    """
    path = db_path or TRACES_DB_PATH
    if not path.exists():
        return []

    if date_str is None:
        date_str = date.today().isoformat()

    conn = get_db(path)
    try:
        cur = conn.execute(
            "SELECT pp.*, pr.pipeline_type "
            "FROM proof_packages pp "
            "LEFT JOIN pipeline_runs pr ON pr.id = pp.pipeline_run_id "
            "WHERE pp.status IN ('approved', 'rejected', 'revision', 'posted', 'partially_posted', 'failed') "
            "AND pp.reviewed_at LIKE ? "
            "ORDER BY pp.reviewed_at DESC",
            (f"{date_str}%",),
        )
        rows = cur.fetchall()
        return [_parse_package_fields(row) for row in rows]
    finally:
        conn.close()


def get_review_summary(db_path: Path | None = None, date_str: str | None = None) -> dict:
    """Return counts of today's reviewed packages by status.

    Returns: {"approved": N, "rejected": N, "revised": N}
    """
    path = db_path or TRACES_DB_PATH
    if not path.exists():
        return {"approved": 0, "rejected": 0, "revised": 0}

    if date_str is None:
        date_str = date.today().isoformat()

    conn = get_db(path)
    try:
        cur = conn.execute(
            "SELECT status, COUNT(*) as cnt "
            "FROM proof_packages "
            "WHERE status IN ('approved', 'rejected', 'revision', 'posted', 'partially_posted', 'failed') "
            "AND reviewed_at LIKE ? "
            "GROUP BY status",
            (f"{date_str}%",),
        )
        counts = {"approved": 0, "rejected": 0, "revised": 0}
        for row in cur.fetchall():
            status = row["status"]
            if status == "revision":
                counts["revised"] = row["cnt"]
            elif status in ("approved", "posted", "partially_posted"):
                counts["approved"] = counts["approved"] + row["cnt"]
            elif status == "failed":
                counts["rejected"] = counts["rejected"] + row["cnt"]
            else:
                counts[status] = row["cnt"]
        return counts
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Posting helpers
# ---------------------------------------------------------------------------


def determine_post_status(results: dict) -> str:
    """Determine overall posting status from per-platform results.

    Returns:
        "posted" -- all platforms succeeded or were skipped (at least one success)
        "partially_posted" -- some succeeded and some failed
        "failed" -- all platforms failed or no platforms attempted
    """
    successes = 0
    failures = 0

    for platform, result in results.items():
        if result.get("status") == "skipped":
            continue  # Skipped platforms don't count as success or failure
        if result.get("success"):
            successes += 1
        else:
            failures += 1

    if successes == 0:
        return "failed"
    if failures == 0:
        return "posted"
    return "partially_posted"


def post_to_platforms(post_text: dict, art_path: str | None) -> dict:
    """Call social-post.py post per platform and return results dict.

    post_text: {"x": "...", "linkedin": "...", "bluesky": "..."}
    Returns: {"x": {"success": True, ...}, "linkedin": {...}, "bluesky": {...}}
    """
    results = {}
    python_path = sys.executable

    for platform, content in post_text.items():
        if not content:
            results[platform] = {"success": False, "error": "No content for platform"}
            continue

        cmd = [
            python_path, str(SOCIAL_POST_SCRIPT),
            "post",
            "--platform", platform,
            "--content", content,
        ]
        if art_path:
            cmd.extend(["--image", art_path])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            try:
                result = json.loads(proc.stdout)
            except (json.JSONDecodeError, TypeError):
                result = {
                    "success": proc.returncode == 0,
                    "error": proc.stderr[:500] if proc.stderr else "Unknown error",
                }
            results[platform] = result
        except subprocess.TimeoutExpired:
            results[platform] = {"success": False, "error": "Posting timed out (60s)"}
        except Exception as exc:
            results[platform] = {"success": False, "error": str(exc)}

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_json_parse(value: str | None):
    """Parse a JSON string, returning None on failure."""
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_package_fields(row: dict) -> dict:
    """Parse JSON fields and compute art_url for a proof_packages row dict."""
    pkg = dict(row)
    post_text_parsed = _safe_json_parse(pkg.get("post_text"))
    # Normalize array format [{platform, content}, ...] to dict {platform: content}
    if isinstance(post_text_parsed, list):
        post_text_parsed = {
            item.get("platform", ""): item.get("content", "")
            for item in post_text_parsed
            if isinstance(item, dict)
        }
    pkg["post_text_parsed"] = post_text_parsed
    pkg["sources_parsed"] = _safe_json_parse(pkg.get("sources")) or []
    pkg["creative_brief_parsed"] = _safe_json_parse(pkg.get("creative_brief"))
    pkg["post_results_parsed"] = _safe_json_parse(pkg.get("post_results"))
    pkg["art_url"] = _art_url(pkg.get("art_path"))
    return pkg


def _art_url(art_path: str | None) -> str | None:
    """Convert a filesystem art_path to a /data/ URL for the browser.

    Strips the leading path up to and including 'data/' so the StaticFiles mount
    can serve it. Returns None if the path is empty or doesn't look valid.
    """
    if not art_path:
        return None
    # art_path values look like "data/social-drafts/linkedin-art.png"
    # or "/Users/.../data/social-drafts/linkedin-art.png"
    if "data/" in art_path:
        relative = art_path.split("data/", 1)[-1]
        return f"/data/{relative}"
    return None


# ---------------------------------------------------------------------------
# Social memory helpers (Story 3.2)
# ---------------------------------------------------------------------------

def store_social_memory(
    package: dict,
    *,
    post_results: dict | None = None,
    gate2_action: str = "approved",
) -> None:
    """Store approved social posts to memory.db for dedup and voice training.

    Calls `memory.py --db {db} social store` via subprocess for each platform
    with content. Best-effort: failures are logged but never raise.
    """
    post_text = package.get("post_text_parsed") or {}
    brief = package.get("creative_brief_parsed") or {}
    anchor = brief.get("anchor", "") if isinstance(brief, dict) else ""
    results = post_results or {}
    today = date.today().isoformat()
    python_path = sys.executable

    for platform, content in post_text.items():
        if not content:
            continue

        cmd = [
            python_path, str(MEMORY_SCRIPT),
            "--db", str(MEMORY_DB),
            "social", "store",
            "--date", today,
            "--platform", platform,
            "--content", content,
            "--gate2-action", gate2_action,
        ]
        if anchor:
            cmd.extend(["--anchor", anchor])

        # Add --posted flag if this platform was successfully posted
        plat_result = results.get(platform, {})
        if plat_result.get("success"):
            cmd.append("--posted")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                logger.warning(
                    "memory.py social store returned %d for %s: %s",
                    proc.returncode, platform, proc.stderr[:200],
                )
        except Exception as exc:
            logger.warning("Failed to store social post for %s: %s", platform, exc)


def store_social_feedback(
    package: dict,
    action: str,
    *,
    user_feedback: str | None = None,
) -> None:
    """Store Gate 2 feedback to memory.db for voice pattern extraction.

    Calls `memory.py --db {db} social feedback store` via subprocess for each
    platform with content. Best-effort: failures are logged but never raise.
    """
    post_text = package.get("post_text_parsed") or {}
    today = date.today().isoformat()
    python_path = sys.executable

    for platform, content in post_text.items():
        if not content:
            continue

        cmd = [
            python_path, str(MEMORY_SCRIPT),
            "--db", str(MEMORY_DB),
            "social", "feedback", "store",
            "--date", today,
            "--platform", platform,
            "--action", action,
            "--original", content,
        ]
        if user_feedback:
            cmd.extend(["--user-feedback", user_feedback])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                logger.warning(
                    "memory.py social feedback store returned %d for %s: %s",
                    proc.returncode, platform, proc.stderr[:200],
                )
        except Exception as exc:
            logger.warning("Failed to store social feedback for %s: %s", platform, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/editors-desk", response_class=HTMLResponse)
def editors_desk(request: Request):
    """Return Editor's Desk tab content.

    htmx requests get the tab fragment; direct requests get the full page.
    Includes EIC kill explanation and reviewed packages summary.
    """
    today_str = date.today().isoformat()
    packages = get_pending_packages()
    eic_kill_reason = get_latest_eic_kill(date_str=today_str)
    reviewed_packages = get_reviewed_packages(date_str=today_str)
    review_summary = get_review_summary(date_str=today_str)
    is_htmx = request.headers.get("HX-Request") == "true"

    # Engagement candidates count for the engagement section
    engagement_candidates = _load_engagement_candidates()
    engagement_count = len(engagement_candidates)

    # LinkedIn token health check
    linkedin_health = check_linkedin_token_health()

    ctx = {
        "request": request,
        "packages": packages,
        "eic_kill_reason": eic_kill_reason,
        "reviewed_packages": reviewed_packages,
        "review_summary": review_summary,
        "today_date": today_str,
        "engagement_count": engagement_count,
        "linkedin_health": linkedin_health,
    }

    if is_htmx:
        return templates.TemplateResponse("tabs/editors_desk.html", ctx)

    return templates.TemplateResponse("base.html", {
        **ctx,
        "active_tab": "editors-desk",
        "tab_template": "tabs/editors_desk.html",
    })


@router.post("/api/editors-desk/{package_id}/approve", response_class=HTMLResponse)
def approve_package(request: Request, package_id: str):
    """Approve a proof package and trigger posting to all platforms."""
    pkg = get_package_detail(package_id)
    if not pkg:
        return HTMLResponse("<div class='card error-text'>Package not found.</div>", status_code=404)

    # Trigger posting
    post_text = pkg.get("post_text_parsed") or {}
    art_path = pkg.get("art_path")
    results = post_to_platforms(post_text, art_path)

    # Determine status based on posting results
    status = determine_post_status(results)
    update_package_status(package_id, status, post_results=results)

    # Store to memory.db for dedup and voice training (best-effort)
    try:
        store_social_memory(pkg, post_results=results, gate2_action="approved")
    except Exception as exc:
        logger.warning("store_social_memory failed: %s", exc)

    try:
        store_social_feedback(pkg, action="approved")
    except Exception as exc:
        logger.warning("store_social_feedback failed: %s", exc)

    # Re-fetch the updated package for the partial
    updated = get_package_detail(package_id)
    return templates.TemplateResponse("partials/proof_card.html", {
        "request": request,
        "pkg": updated,
    })


@router.post("/api/editors-desk/{package_id}/retry", response_class=HTMLResponse)
def retry_failed_platforms(request: Request, package_id: str):
    """Retry posting to failed platforms only."""
    pkg = get_package_detail(package_id)
    if not pkg:
        return HTMLResponse("<div class='card error-text'>Package not found.</div>", status_code=404)

    existing_results = pkg.get("post_results_parsed") or {}
    post_text = pkg.get("post_text_parsed") or {}
    art_path = pkg.get("art_path")

    # Build subset of only failed platforms
    failed_text = {}
    for platform, result in existing_results.items():
        if not result.get("success") and result.get("status") != "skipped":
            if platform in post_text:
                failed_text[platform] = post_text[platform]

    if not failed_text:
        # Nothing to retry -- return current card
        return templates.TemplateResponse("partials/proof_card.html", {
            "request": request,
            "pkg": pkg,
        })

    # Re-post only failed platforms
    retry_results = post_to_platforms(failed_text, art_path)

    # Merge retry results into existing results
    merged = {**existing_results, **retry_results}

    # Recalculate status
    new_status = determine_post_status(merged)
    update_package_status(package_id, new_status, post_results=merged)

    updated = get_package_detail(package_id)
    return templates.TemplateResponse("partials/proof_card.html", {
        "request": request,
        "pkg": updated,
    })


@router.post("/api/editors-desk/{package_id}/reject", response_class=HTMLResponse)
def reject_package(request: Request, package_id: str, notes: str = Form(default="")):
    """Reject a proof package with optional reviewer notes."""
    pkg = get_package_detail(package_id)
    if not pkg:
        return HTMLResponse("<div class='card error-text'>Package not found.</div>", status_code=404)

    update_package_status(package_id, "rejected", notes=notes or None)

    # Store rejection feedback to memory.db (best-effort)
    try:
        store_social_feedback(pkg, action="skip")
    except Exception as exc:
        logger.warning("store_social_feedback failed on reject: %s", exc)

    updated = get_package_detail(package_id)
    return templates.TemplateResponse("partials/proof_card.html", {
        "request": request,
        "pkg": updated,
    })


@router.post("/api/editors-desk/{package_id}/revise", response_class=HTMLResponse)
def revise_package(request: Request, package_id: str, notes: str = Form(default="")):
    """Send a proof package back for revision with feedback notes."""
    pkg = get_package_detail(package_id)
    if not pkg:
        return HTMLResponse("<div class='card error-text'>Package not found.</div>", status_code=404)

    update_package_status(package_id, "revision", notes=notes or None)

    # Store revision feedback to memory.db (best-effort)
    try:
        store_social_feedback(pkg, action="rewrite", user_feedback=notes or None)
    except Exception as exc:
        logger.warning("store_social_feedback failed on revise: %s", exc)

    updated = get_package_detail(package_id)
    return templates.TemplateResponse("partials/proof_card.html", {
        "request": request,
        "pkg": updated,
    })


# ---------------------------------------------------------------------------
# Engagement gate helpers
# ---------------------------------------------------------------------------

def _load_engagement_candidates(
    candidates_path: Optional[Path] = None,
) -> list[dict]:
    """Load engagement candidates from JSON file."""
    path = candidates_path or ENGAGEMENT_CANDIDATES_FILE
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, Exception):
        return []


def _check_engagement_dedup(
    target_post_url: Optional[str],
    db_path: Optional[Path] = None,
    user_id: Optional[str] = None,
) -> bool:
    """Check if we already replied to this post URL. Returns True if already replied."""
    if not target_post_url:
        return False

    path = db_path or MEMORY_DB
    if not path.exists():
        return False

    uid = user_id or USER_ID

    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id FROM engagements WHERE target_post_url = ? AND user_id = ? AND engagement_type = 'reply' LIMIT 1",
                (target_post_url, uid),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def _filter_candidates_dedup(
    candidates: list[dict],
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Filter out candidates we've already replied to."""
    return [
        c for c in candidates
        if not _check_engagement_dedup(
            c.get("target_url") or c.get("target_post_url"),
            db_path=db_path,
        )
    ]


# ---------------------------------------------------------------------------
# Engagement gate routes
# ---------------------------------------------------------------------------

@router.get("/engagement-gate", response_class=HTMLResponse)
def engagement_gate(request: Request):
    """Show engagement candidates for approval."""
    candidates = _load_engagement_candidates()
    filtered = _filter_candidates_dedup(candidates)

    ctx = {
        "request": request,
        "candidates": filtered,
        "total_count": len(candidates),
        "filtered_count": len(filtered),
        "deduped_count": len(candidates) - len(filtered),
    }

    return templates.TemplateResponse("tabs/engagement_gate.html", ctx)


@router.post("/api/engagement/approve", response_class=HTMLResponse)
def approve_engagement(request: Request, body: dict = Body(...)):
    """Approve selected engagement candidates by indices."""
    approved_indices = body.get("approved_indices", [])
    candidates = _load_engagement_candidates()

    approved = [candidates[i] for i in approved_indices if i < len(candidates)]

    # Write approved candidates
    approved_path = ENGAGEMENT_APPROVED_FILE
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(json.dumps(approved, indent=2))

    return HTMLResponse(
        f'<div class="card" style="padding:1rem;background:#14532d;color:#4ade80;">'
        f'Approved {len(approved)} engagement replies. Ready for posting.</div>'
    )


@router.post("/api/engagement/approve-all", response_class=HTMLResponse)
def approve_all_engagement(request: Request):
    """Approve all engagement candidates."""
    candidates = _load_engagement_candidates()
    filtered = _filter_candidates_dedup(candidates)

    approved_path = ENGAGEMENT_APPROVED_FILE
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(json.dumps(filtered, indent=2))

    return HTMLResponse(
        f'<div class="card" style="padding:1rem;background:#14532d;color:#4ade80;">'
        f'Approved all {len(filtered)} engagement replies. Ready for posting.</div>'
    )


@router.post("/api/engagement/skip-all", response_class=HTMLResponse)
def skip_all_engagement(request: Request):
    """Skip all engagement candidates."""
    approved_path = ENGAGEMENT_APPROVED_FILE
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(json.dumps([], indent=2))

    return HTMLResponse(
        '<div class="card" style="padding:1rem;background:#78350f;color:#fbbf24;">'
        'Skipped all engagement candidates.</div>'
    )


@router.post("/api/engagement/approve-single", response_class=HTMLResponse)
def approve_single_engagement(request: Request, target_url: str = Form(...)):
    """Approve a single engagement candidate by target_url."""
    candidates = _load_engagement_candidates()

    # Look up candidate by target_url
    candidate = None
    for c in candidates:
        c_url = c.get("target_url") or c.get("target_post_url", "")
        if c_url == target_url:
            candidate = c
            break

    if candidate is None:
        return HTMLResponse(
            '<div class="card error-text">Candidate not found for the given URL.</div>',
            status_code=404,
        )

    # Load existing approved or start fresh
    approved_path = ENGAGEMENT_APPROVED_FILE
    existing = []
    if approved_path.exists():
        try:
            existing = json.loads(approved_path.read_text())
        except (json.JSONDecodeError, Exception):
            existing = []

    existing.append(candidate)
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(json.dumps(existing, indent=2))

    return HTMLResponse(
        f'<div class="card" style="padding:0.5rem;background:#14532d;color:#4ade80;">'
        f'Approved reply to @{candidate.get("target_author", "unknown")} on {candidate.get("platform", "")}.</div>'
    )


# ---------------------------------------------------------------------------
# Engagement posting routes (Story 3.4)
# ---------------------------------------------------------------------------

@router.post("/api/engagement/post", response_class=HTMLResponse)
def post_approved_engagement(request: Request):
    """Post all approved engagement replies with rate limiting.

    Reads engagement-approved.json, posts via social-post.py reply per platform
    with 30s spacing and threading, auto-follows authors, stores to memory.db.
    """
    approved_path = ENGAGEMENT_APPROVED_FILE
    if not approved_path.exists():
        return HTMLResponse(
            '<div class="card" style="padding:1rem;background:#78350f;color:#fbbf24;">'
            'No approved engagement replies found. Approve candidates first.</div>'
        )

    try:
        approved = json.loads(approved_path.read_text())
    except (json.JSONDecodeError, Exception):
        return HTMLResponse(
            '<div class="card error-text">Failed to read approved candidates file.</div>',
            status_code=500,
        )

    if not approved:
        return HTMLResponse(
            '<div class="card" style="padding:1rem;background:#78350f;color:#fbbf24;">'
            'No approved engagement replies to post.</div>'
        )

    result = post_engagement_replies(
        approved_candidates=approved,
        user_id=USER_ID,
        project_root=PROJECT_ROOT,
    )

    posted = result.get("posted", 0)
    failed = result.get("failed", 0)
    skipped = result.get("skipped", 0)
    error = result.get("error")

    if error:
        return HTMLResponse(
            f'<div class="card" style="padding:1rem;background:#7f1d1d;color:#f87171;">'
            f'Posting blocked: {error}</div>'
        )

    # Build result summary
    parts = []
    if posted > 0:
        parts.append(f'<span style="color:#4ade80;">{posted} posted</span>')
    if failed > 0:
        parts.append(f'<span style="color:#f87171;">{failed} failed</span>')
    if skipped > 0:
        parts.append(f'<span style="color:#fbbf24;">{skipped} skipped</span>')

    summary = ", ".join(parts) if parts else "No results"

    # Retain only failed candidates in the approved file (so they can be retried)
    try:
        results_list = result.get("results", [])
        failed_candidates = [
            r["candidate"] for r in results_list
            if isinstance(r, dict) and not r.get("reply", {}).get("success", False)
        ]
        approved_path.write_text(json.dumps(failed_candidates, indent=2))
    except Exception:
        pass

    bg_color = "#14532d" if posted > 0 and failed == 0 else "#1c1917"
    border_color = "#166534" if posted > 0 and failed == 0 else "#92400e"

    return HTMLResponse(
        f'<div class="card" style="padding:1rem;background:{bg_color};border:1px solid {border_color};">'
        f'<h3 style="color:#f8fafc;margin:0 0 0.5rem 0;">Engagement Posting Complete</h3>'
        f'<p style="font-size:0.875rem;">{summary}</p>'
        f'</div>'
    )

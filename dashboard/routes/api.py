"""API routes for the mindpattern dashboard.

Public routes: read-only, no PII, paginated, date-filtered
Private routes: require bearer token auth
"""

import json
import re
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, Query, Depends
from dashboard.auth import require_auth

router = APIRouter()
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
# Reports may be in project_root/reports/ (local) or /data/reports/ (Fly.io)
_reports_candidates = [PROJECT_ROOT / "reports", DATA_DIR / ".." / "reports", Path("/data/reports")]
REPORTS_DIR = next((p for p in _reports_candidates if p.exists()), PROJECT_ROOT / "reports")
USERS_FILE = PROJECT_ROOT / "users.json"


def _deserialize_f32(blob: bytes) -> list[float]:
    """Deserialize bytes back to a float vector."""
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _embed_text(text: str) -> list[float]:
    """Generate a 384-dim embedding. Lazy-loads the model."""
    global _embed_model
    if "_embed_model" not in globals() or _embed_model is None:
        from fastembed import TextEmbedding
        globals()["_embed_model"] = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return list(_embed_model.embed([text]))[0].tolist()

_embed_model = None

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Patterns for stripping PII from text fields
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)


def _valid_date(s: Optional[str]) -> Optional[str]:
    """Return the date string if it matches YYYY-MM-DD, else None."""
    return s if s and _DATE_RE.match(s) else None


def _strip_pii(text: Optional[str]) -> Optional[str]:
    """Remove email addresses and phone numbers from a string."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[redacted]", text)
    text = _PHONE_RE.sub("[redacted]", text)
    return text


def _strip_pii_dict(d: dict, fields: list[str]) -> dict:
    """Strip PII from specified string fields in a dict (returns a copy)."""
    out = dict(d)
    for f in fields:
        if f in out and isinstance(out[f], str):
            out[f] = _strip_pii(out[f])
    return out


def get_memory_db(user_id: str = "ramsay") -> Optional[sqlite3.Connection]:
    """Open memory.db for a user. Fresh connection per request."""
    db_path = DATA_DIR / user_id / "memory.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Public endpoints (no auth) ──────────────────────────────────


@router.get("/api/findings")
async def get_findings(
    limit: int = Query(200, le=2000),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
    date: str = Query(None),
    agent: str = Query(None),
    importance: str = Query(None),
    user: str = Query("ramsay"),
):
    """Public: paginated findings with date filtering. No PII.
    Use `date` for exact match, `since` for range (>= date)."""
    conn = get_memory_db(user)
    if conn is None:
        return []

    try:
        where_clauses: list[str] = []
        params: list = []

        # Exact date match takes priority over since (range)
        date_val = _valid_date(date)
        since_val = _valid_date(since)
        if date_val:
            where_clauses.append("run_date = ?")
            params.append(date_val)
        elif since_val:
            where_clauses.append("run_date >= ?")
            params.append(since_val)
        if agent:
            where_clauses.append("agent = ?")
            params.append(agent)
        if importance:
            where_clauses.append("importance = ?")
            params.append(importance)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Total count
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM findings WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        # Paginated results
        query = f"""
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [
            _strip_pii_dict(dict(r), ["title", "summary"])
            for r in rows
        ]

        return items
    finally:
        conn.close()


@router.get("/api/sources")
async def get_sources(
    limit: int = Query(30, le=500),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
    user: str = Query("ramsay"),
):
    """Public: top sources by quality, paginated."""
    conn = get_memory_db(user)
    if conn is None:
        return []

    try:
        where_clauses: list[str] = []
        params: list = []

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("last_seen >= ?")
            params.append(since_val)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM sources WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        query = f"""
            SELECT id, url_domain, display_name, hit_count, high_value_count,
                   last_seen, created_at
            FROM sources
            WHERE {where_sql}
            ORDER BY high_value_count DESC, hit_count DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [dict(r) for r in rows]

        return items
    finally:
        conn.close()


@router.get("/api/patterns")
async def get_patterns(
    min_count: int = Query(1),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
    user: str = Query("ramsay"),
):
    """Public: recurring patterns, paginated."""
    conn = get_memory_db(user)
    if conn is None:
        return []

    try:
        where_clauses: list[str] = ["recurrence_count >= ?"]
        params: list = [min_count]

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("last_seen >= ?")
            params.append(since_val)

        where_sql = " AND ".join(where_clauses)

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM patterns WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        query = f"""
            SELECT id, run_date, theme, description, recurrence_count,
                   first_seen, last_seen, created_at
            FROM patterns
            WHERE {where_sql}
            ORDER BY recurrence_count DESC, last_seen DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [
            _strip_pii_dict(dict(r), ["theme", "description"])
            for r in rows
        ]

        return items
    finally:
        conn.close()


@router.get("/api/skills")
async def get_skills(
    limit: int = Query(100, le=200),
    offset: int = Query(0, ge=0),
    domain: str = Query(None),
    since: str = Query(None),
    user: str = Query("ramsay"),
):
    """Public: skills by domain, paginated."""
    conn = get_memory_db(user)
    if conn is None:
        return []

    try:
        where_clauses: list[str] = []
        params: list = []

        if domain:
            where_clauses.append("domain = ?")
            params.append(domain)

        since_val = _valid_date(since)
        if since_val:
            where_clauses.append("run_date >= ?")
            params.append(since_val)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = conn.execute(
            f"SELECT COUNT(*) FROM skills WHERE {where_sql}", params
        ).fetchone()
        total = count_row[0]

        query = f"""
            SELECT id, run_date, domain, title, description, steps,
                   difficulty, source_url, source_name, created_at
            FROM skills
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [limit, offset]).fetchall()
        items = [
            _strip_pii_dict(dict(r), ["title", "description", "steps"])
            for r in rows
        ]

        return items
    finally:
        conn.close()


@router.get("/api/stats")
async def get_stats(user: str = Query("ramsay")):
    """Public: aggregate statistics. Returns v2-compatible flat format
    (findings/sources/patterns/skills as integers, by_agent, by_date)
    so the Vercel frontend can render charts."""
    conn = get_memory_db(user)
    if conn is None:
        return {
            "findings": 0, "sources": 0, "patterns": 0, "skills": 0,
            "by_agent": {}, "by_date": {},
        }

    try:
        # Counts
        findings_total = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        sources_total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        patterns_total = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        skills_total = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]

        # by_agent breakdown
        by_agent_rows = conn.execute(
            "SELECT agent, COUNT(*) as c FROM findings GROUP BY agent ORDER BY c DESC"
        ).fetchall()
        by_agent = {r["agent"]: r["c"] for r in by_agent_rows}

        # by_date breakdown
        by_date_rows = conn.execute(
            "SELECT run_date, COUNT(*) as c FROM findings GROUP BY run_date ORDER BY run_date DESC"
        ).fetchall()
        by_date = {r["run_date"]: r["c"] for r in by_date_rows}

        return {
            "findings": findings_total,
            "sources": sources_total,
            "patterns": patterns_total,
            "skills": skills_total,
            "by_agent": by_agent,
            "by_date": by_date,
        }
    finally:
        conn.close()


@router.get("/api/search")
async def search_findings(
    q: str = Query(""),
    limit: int = Query(20, le=100),
    user: str = Query("ramsay"),
):
    """Public: semantic search over findings using embeddings."""
    if not q:
        return []

    conn = get_memory_db(user)
    if conn is None:
        return []

    try:
        rows = conn.execute(
            """SELECT f.id, f.run_date, f.agent, f.title, f.summary, f.importance,
                      f.source_url, f.source_name, e.embedding
               FROM findings f JOIN findings_embeddings e ON e.finding_id = f.id"""
        ).fetchall()

        if not rows:
            return []

        query_vec = np.array(_embed_text(q), dtype=np.float32)
        results = []
        for r in rows:
            emb = np.array(_deserialize_f32(r["embedding"]), dtype=np.float32)
            sim = float(np.dot(query_vec, emb))
            results.append({
                "id": r["id"], "run_date": r["run_date"], "agent": r["agent"],
                "title": r["title"], "summary": r["summary"],
                "importance": r["importance"], "source_url": r["source_url"],
                "source_name": r["source_name"], "similarity": round(max(0, sim), 3),
            })

        results.sort(key=lambda x: -x["similarity"])
        return results[:limit]
    finally:
        conn.close()


@router.get("/api/skills/search")
async def search_skills(
    q: str = Query(""),
    limit: int = Query(20, le=100),
    user: str = Query("ramsay"),
):
    """Public: semantic search over skills using embeddings."""
    if not q:
        return []

    conn = get_memory_db(user)
    if conn is None:
        return []

    try:
        rows = conn.execute(
            """SELECT s.id, s.run_date, s.domain, s.title, s.description, s.steps,
                      s.difficulty, s.source_url, s.source_name, e.embedding
               FROM skills s JOIN skills_embeddings e ON e.skill_id = s.id"""
        ).fetchall()

        if not rows:
            return []

        query_vec = np.array(_embed_text(q), dtype=np.float32)
        results = []
        for r in rows:
            emb = np.array(_deserialize_f32(r["embedding"]), dtype=np.float32)
            sim = float(np.dot(query_vec, emb))
            results.append({
                "id": r["id"], "run_date": r["run_date"], "domain": r["domain"],
                "title": r["title"], "description": r["description"],
                "steps": r["steps"], "difficulty": r["difficulty"],
                "source_url": r["source_url"], "source_name": r["source_name"],
                "similarity": round(max(0, sim), 3),
            })

        results.sort(key=lambda x: -x["similarity"])
        return results[:limit]
    finally:
        conn.close()


@router.get("/api/health")
async def get_health(user: str = Query("ramsay")):
    """Public: pipeline and agent health data."""
    conn = get_memory_db(user)
    result = {
        "pipeline_runs": [],
        "agent_stats": [],
        "recent_errors": [],
        "approval_summary": {"pending": 0, "decided": 0},
    }
    if conn is None:
        return result

    try:
        try:
            rows = conn.execute(
                """SELECT run_date, total_findings, unique_sources, high_value_count,
                          agent_utilization, overall_score
                   FROM run_quality ORDER BY run_date DESC LIMIT 30"""
            ).fetchall()
            result["pipeline_runs"] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass

        try:
            rows = conn.execute(
                """SELECT agent, note_type, COUNT(*) as count
                   FROM agent_notes GROUP BY agent, note_type
                   ORDER BY agent, count DESC"""
            ).fetchall()
            result["agent_stats"] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass

        try:
            rows = conn.execute(
                """SELECT run_date, agent, note_type, content, created_at
                   FROM agent_notes
                   WHERE note_type IN ('error', 'warning', 'skip_list')
                   ORDER BY created_at DESC LIMIT 20"""
            ).fetchall()
            result["recent_errors"] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass

        try:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM approval_reviews WHERE status = 'pending'"
            ).fetchone()
            result["approval_summary"]["pending"] = row["c"] if row else 0
            row = conn.execute(
                "SELECT COUNT(*) as c FROM approval_reviews WHERE status != 'pending'"
            ).fetchone()
            result["approval_summary"]["decided"] = row["c"] if row else 0
        except sqlite3.OperationalError:
            pass

        return result
    finally:
        conn.close()


@router.get("/api/reports")
async def list_reports(user: str = Query("ramsay")):
    """Public: list available newsletter reports."""
    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return []

    reports = []
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        name = f.stem
        # Extract date from filename (YYYY-MM-DD or YYYY-MM-DD-HHMMSS)
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if not date_match:
            continue
        date_str = date_match.group(1)

        # Read first few lines for title/summary
        text = f.read_text(errors="replace")
        lines = text.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else name
        subtitle = ""
        for line in lines[1:5]:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                subtitle = line.lstrip("## ").strip()
                break

        reports.append({
            "date": date_str,
            "filename": f.name,
            "title": title,
            "subtitle": subtitle,
            "size": f.stat().st_size,
        })

    return reports


@router.get("/api/reports/search")
async def search_reports(
    q: str = Query(""),
    user: str = Query("ramsay"),
    limit: int = Query(10, le=50),
):
    """Public: search newsletter reports by text content."""
    if not q:
        return []

    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return []

    query_lower = q.lower()
    results = []
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", f.stem)
        if not date_match:
            continue

        text = f.read_text(errors="replace")
        if query_lower not in text.lower():
            continue

        lines = text.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else f.stem

        # Find a matching snippet
        snippet = ""
        for line in lines:
            if query_lower in line.lower():
                snippet = line.strip()[:200]
                break

        results.append({
            "date": date_match.group(1),
            "filename": f.name,
            "title": title,
            "excerpt": snippet,
        })

        if len(results) >= limit:
            break

    return results


@router.get("/api/reports/{date}")
async def get_report(date: str, user: str = Query("ramsay")):
    """Public: get a single newsletter report by date."""
    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return None

    # Find file matching date prefix
    matches = list(reports_dir.glob(f"{date}*.md"))
    if not matches:
        return None

    # Use the first match (or the one without debug/stderr suffix)
    target = matches[0]
    for m in matches:
        if "debug" not in m.name and "stderr" not in m.name:
            target = m
            break

    text = target.read_text(errors="replace")
    lines = text.strip().split("\n")
    title = lines[0].lstrip("# ").strip() if lines else target.stem

    return {
        "date": date,
        "filename": target.name,
        "title": title,
        "content": text,
    }


@router.get("/api/skill-domains")
async def get_skill_domains(user: str = Query("ramsay")):
    """Public: list distinct skill domains."""
    conn = get_memory_db(user)
    if conn is None:
        return []
    try:
        rows = conn.execute("SELECT DISTINCT domain FROM skills ORDER BY domain").fetchall()
        return [r["domain"] for r in rows]
    finally:
        conn.close()


@router.get("/healthz")
async def health():
    """Public: health check."""
    db_ok = False
    conn = get_memory_db()
    if conn is not None:
        try:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
        except Exception:
            pass
        finally:
            conn.close()

    return {
        "status": "ok" if db_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if db_ok else "unavailable",
    }


# ── Private endpoints (require auth) ────────────────────────────


@router.get("/api/users", dependencies=[Depends(require_auth)])
async def get_users():
    """Private: user registry (contains email)."""
    if not USERS_FILE.exists():
        return {"users": []}

    try:
        data = json.loads(USERS_FILE.read_text())
        return data
    except (json.JSONDecodeError, Exception):
        return {"users": [], "error": "Failed to parse users.json"}


@router.post("/api/approval/submit", dependencies=[Depends(require_auth)])
async def submit_approval(payload: dict):
    """Private: create approval review for social posts.

    Expected payload:
        {
            "pipeline": "social",
            "stage": "gate2",
            "items": [
                {"platform": "x", "content": "...", "content_type": "post"},
                ...
            ]
        }
    """
    conn = get_memory_db()
    if conn is None:
        return {"error": "Database unavailable"}, 503

    pipeline = payload.get("pipeline", "social")
    stage = payload.get("stage", "gate2")
    items = payload.get("items", [])

    if not items:
        return {"error": "No items provided"}, 400

    import secrets
    token = secrets.token_urlsafe(24)

    try:
        cur = conn.execute(
            "INSERT INTO approval_reviews (pipeline, stage, token) VALUES (?, ?, ?)",
            (pipeline, stage, token),
        )
        review_id = cur.lastrowid

        for item in items:
            conn.execute(
                """INSERT INTO approval_items
                   (review_id, platform, content_type, content, image_url)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    review_id,
                    item.get("platform"),
                    item.get("content_type", "post"),
                    item.get("content", ""),
                    item.get("image_url"),
                ),
            )

        conn.commit()
        return {
            "review_id": review_id,
            "token": token,
            "status": "pending",
            "items_count": len(items),
        }
    finally:
        conn.close()


@router.post("/api/approval/decide/{token}", dependencies=[Depends(require_auth)])
async def decide_approval(token: str, payload: dict):
    """Private: approve/reject social posts.

    Expected payload:
        {
            "action": "approve" | "reject",
            "item_decisions": [
                {"item_id": 1, "status": "approved", "feedback": "..."},
                ...
            ]
        }
    For bulk action on all items, omit item_decisions.
    """
    conn = get_memory_db()
    if conn is None:
        return {"error": "Database unavailable"}, 503

    action = payload.get("action", "approve")
    if action not in ("approve", "reject"):
        return {"error": "action must be 'approve' or 'reject'"}, 400

    try:
        # Look up review by token
        review = conn.execute(
            "SELECT id, status FROM approval_reviews WHERE token = ?",
            (token,),
        ).fetchone()

        if not review:
            return {"error": "Review not found"}, 404

        if review["status"] != "pending":
            return {
                "error": f"Review already decided: {review['status']}",
                "status": review["status"],
            }

        review_id = review["id"]
        review_status = "approved" if action == "approve" else "rejected"
        now = datetime.now().isoformat()

        # Apply per-item decisions if provided
        item_decisions = payload.get("item_decisions")
        if item_decisions:
            for dec in item_decisions:
                item_id = dec.get("item_id")
                item_status = dec.get("status", review_status)
                feedback = dec.get("feedback")
                conn.execute(
                    "UPDATE approval_items SET status = ?, feedback = ? WHERE id = ? AND review_id = ?",
                    (item_status, feedback, item_id, review_id),
                )
        else:
            # Bulk: apply same status to all items
            conn.execute(
                "UPDATE approval_items SET status = ? WHERE review_id = ?",
                (review_status, review_id),
            )

        # Update the review itself
        conn.execute(
            "UPDATE approval_reviews SET status = ?, decided_at = ? WHERE id = ?",
            (review_status, now, review_id),
        )

        conn.commit()

        return {
            "review_id": review_id,
            "status": review_status,
            "decided_at": now,
        }
    finally:
        conn.close()


@router.get("/api/approval/status/{token}", dependencies=[Depends(require_auth)])
async def approval_status(token: str):
    """Private: poll approval state."""
    conn = get_memory_db()
    if conn is None:
        return {"error": "Database unavailable"}, 503

    try:
        review = conn.execute(
            "SELECT id, pipeline, stage, status, created_at, decided_at FROM approval_reviews WHERE token = ?",
            (token,),
        ).fetchone()

        if not review:
            return {"error": "Review not found"}, 404

        review_dict = dict(review)
        review_id = review["id"]

        # Fetch items
        items = conn.execute(
            "SELECT id, platform, content_type, content, image_url, status, feedback FROM approval_items WHERE review_id = ?",
            (review_id,),
        ).fetchall()
        review_dict["items"] = [dict(item) for item in items]

        return review_dict
    finally:
        conn.close()


# ── Pipeline-facing approval endpoints (no auth) ─────────────
#
# These endpoints match the URLs that social/approval.py calls:
#   POST /api/approvals       — submit a new approval request
#   GET  /api/approvals/{token} — poll for a decision
#
# The pipeline runs locally and cannot provide bearer tokens, so these
# are unauthenticated.  The dashboard UI uses the auth-protected
# /api/approval/* routes above for human reviewers.


@router.post("/api/approvals")
async def pipeline_submit_approval(payload: dict):
    """Pipeline-facing: create approval review from the social pipeline.

    Expected payload (from social/approval.py):
        {
            "gate_type": "topic" | "draft" | "engagement",
            "token": "<client-generated token>",
            "items": [...],
            "created_at": "..."
        }
    """
    from fastapi.responses import JSONResponse

    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503)

    gate_type = payload.get("gate_type", "draft")
    token = payload.get("token", "")
    items = payload.get("items", [])

    if not token:
        return JSONResponse({"error": "No token provided"}, status_code=400)
    if not items:
        return JSONResponse({"error": "No items provided"}, status_code=400)

    # Map gate_type to pipeline/stage for the approval_reviews table
    stage_map = {"topic": "gate1", "draft": "gate2", "engagement": "engagement"}
    stage = stage_map.get(gate_type, gate_type)

    try:
        # Ensure approval_reviews table exists (may not on first deploy)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approval_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline TEXT DEFAULT 'social',
                stage TEXT,
                token TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                decided_at TEXT,
                selected_index INTEGER,
                feedback TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS approval_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER REFERENCES approval_reviews(id),
                platform TEXT,
                content_type TEXT DEFAULT 'post',
                content TEXT,
                image_url TEXT,
                status TEXT DEFAULT 'pending',
                feedback TEXT
            )
        """)

        cur = conn.execute(
            "INSERT INTO approval_reviews (pipeline, stage, token, created_at) VALUES (?, ?, ?, ?)",
            ("social", stage, token, payload.get("created_at", datetime.now().isoformat())),
        )
        review_id = cur.lastrowid

        for item in items:
            conn.execute(
                """INSERT INTO approval_items
                   (review_id, platform, content_type, content, image_url)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    review_id,
                    item.get("platform", ""),
                    item.get("content_type", "post"),
                    json.dumps(item) if not isinstance(item.get("content"), str) else item.get("content", ""),
                    item.get("image_url"),
                ),
            )

        conn.commit()
        return JSONResponse({
            "review_id": review_id,
            "token": token,
            "status": "pending",
            "items_count": len(items),
        }, status_code=201)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        conn.close()


@router.get("/api/approvals/{token}")
async def pipeline_poll_approval(token: str):
    """Pipeline-facing: poll approval state (called by social/approval.py).

    Returns the review status and items. The pipeline checks for
    status != 'pending' to know when a decision has been made.
    """
    from fastapi.responses import JSONResponse

    conn = get_memory_db()
    if conn is None:
        return JSONResponse({"error": "Database unavailable"}, status_code=503)

    try:
        review = conn.execute(
            "SELECT id, pipeline, stage, status, created_at, decided_at, selected_index, feedback "
            "FROM approval_reviews WHERE token = ?",
            (token,),
        ).fetchone()

        if not review:
            return JSONResponse({"error": "Review not found"}, status_code=404)

        review_dict = dict(review)
        review_id = review["id"]

        # Fetch items
        items = conn.execute(
            "SELECT id, platform, content_type, content, image_url, status, feedback "
            "FROM approval_items WHERE review_id = ?",
            (review_id,),
        ).fetchall()
        review_dict["items"] = [dict(item) for item in items]

        return review_dict
    finally:
        conn.close()

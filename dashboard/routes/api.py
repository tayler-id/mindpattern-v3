"""API routes for the mindpattern dashboard.

Public routes: read-only, no PII, paginated, date-filtered
Private routes: require bearer token auth
"""

import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import numpy as np
from fastapi import APIRouter, Query, Depends
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from dashboard.auth import require_auth
from orchestrator.audio_briefing import audio_artifact_paths
from orchestrator.site_content import (
    build_public_story,
    build_structured_issue,
    is_publishable_site_story,
    normalize_slug,
    sanitize_site_artifact,
    site_artifact_path,
)
from orchestrator.site_graph import CorpusGraphReadModel
from memory.embeddings import deserialize_f32 as _deserialize_f32
from memory.embeddings import embed_text as _embed_text
from orchestrator.arcs import load_narrative_arcs
from orchestrator.media_contracts import redact_sensitive_text, validate_run_date
from slack_bot.heartbeat import is_stale as bot_heartbeat_stale

router = APIRouter()
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
# Reports may be in project_root/reports/ (local) or /data/reports/ (Fly.io)
_reports_candidates = [PROJECT_ROOT / "reports", DATA_DIR / ".." / "reports", Path("/data/reports")]
REPORTS_DIR = next((p for p in _reports_candidates if p.exists()), PROJECT_ROOT / "reports")
USERS_FILE = PROJECT_ROOT / "users.json"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Patterns for stripping PII from text fields
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)
_REPORT_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")
_REPORT_BAD_LINE_RE = re.compile(
    r"^(?:"
    r"now\b.*(?:write|newsletter|report|final output)|"
    r"let me\b.*(?:write|newsletter|report)|"
    r"prompt is too long|"
    r"dry-run report|"
    r"this is a dry-run placeholder"
    r")\.?$",
    re.IGNORECASE,
)
_MIN_PUBLIC_REPORT_BYTES = 1_000
_MIN_STRUCTURED_REPORT_BYTES = 80


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


_USER_RE = re.compile(r"^[a-z0-9_-]+$")
_ARC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_PUBLIC_ENTITY_SLUG_BLOCKLIST = {
    "and",
    "because",
    "but",
    "for",
    "from",
    "into",
    "not",
    "source",
    "story",
    "that",
    "the",
    "this",
    "with",
}


def _safe_user(user: str) -> Optional[str]:
    """Reject user ids that could traverse paths (user becomes a path part)."""
    return user if _USER_RE.fullmatch(user or "") else None


def _safe_arc_id(arc_id: str) -> Optional[str]:
    """Reject path-like or malformed public narrative arc IDs."""
    return arc_id if _ARC_ID_RE.fullmatch(arc_id or "") else None


def _valid_run_date(s: Optional[str]) -> Optional[str]:
    """Return a real YYYY-MM-DD date string, else None."""
    if not s:
        return None
    try:
        return validate_run_date(s)
    except ValueError:
        return None


def _strip_inline_markdown(text: str) -> str:
    """Remove common inline markdown markers from public report metadata."""
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = re.sub(r"[*_`]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_bad_report_line(line: str) -> bool:
    return bool(_REPORT_BAD_LINE_RE.match(_strip_inline_markdown(line).strip()))


def _clean_report_markdown(text: str) -> str:
    """Drop assistant preamble before the canonical newsletter heading."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    lines = normalized.split("\n")
    first_nonempty = next((i for i, line in enumerate(lines) if line.strip()), 0)
    heading_index = None
    for i, line in enumerate(lines[:25]):
        match = _REPORT_HEADING_RE.match(line.strip())
        if match and not _is_bad_report_line(match.group(1)):
            heading_index = i
            break

    if heading_index is not None and heading_index > first_nonempty:
        leading = [line.strip() for line in lines[first_nonempty:heading_index] if line.strip()]
        if leading and all(_is_bad_report_line(line) or line == "---" for line in leading):
            return "\n".join(lines[heading_index:]).strip()

    while lines and lines[0].strip() and _is_bad_report_line(lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).strip()


def _report_title_from_content(*, content: str, date: str, fallback_name: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _REPORT_HEADING_RE.match(stripped)
        title = match.group(1).strip() if match else stripped
        title = _strip_inline_markdown(title)
        if title and not _is_bad_report_line(title):
            return title

    try:
        formatted = datetime.strptime(date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        formatted = date
    except TypeError:
        formatted = fallback_name
    return f"Ramsay Research Agent — {formatted}"


def _report_subtitle_from_content(*, content: str, title: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped in {"---", "***"}:
            continue
        if stripped.startswith("#"):
            continue
        candidate = _strip_inline_markdown(stripped)
        if not candidate or candidate == title or _is_bad_report_line(candidate):
            continue
        if candidate.lower().startswith(("top 5 stories", "breaking news", "security")):
            continue
        return candidate
    return ""


def _is_public_report_content(content: str, *, min_bytes: int = _MIN_PUBLIC_REPORT_BYTES) -> bool:
    if len(content.encode("utf-8")) < min_bytes:
        return False
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    if first_line and _is_bad_report_line(first_line):
        return False
    return True


def _report_file_rank(path: Path, date: str) -> tuple[int, int, int, str]:
    name = path.name.lower()
    exact = 0 if path.name == f"{date}.md" else 1
    generated = 1 if any(token in name for token in ("dry-run", "debug", "stderr")) else 0
    size_rank = -path.stat().st_size
    return (exact, generated, size_rank, path.name)


def _report_metadata(path: Path, date: str) -> dict | None:
    text = path.read_text(errors="replace")
    content = _clean_report_markdown(text)
    if not _is_public_report_content(content):
        return None
    title = _report_title_from_content(content=content, date=date, fallback_name=path.stem)
    return {
        "date": date,
        "filename": path.name,
        "title": title,
        "subtitle": _report_subtitle_from_content(content=content, title=title),
        "size": path.stat().st_size,
        "word_count": len(content.split()),
        "content_status": "cleaned" if content != text.strip() else "full",
    }


def _public_narrative_arc(arc: dict) -> dict:
    """Whitelist and redact fields exposed by the public narrative arc API."""
    scores = arc.get("scores") if isinstance(arc.get("scores"), dict) else {}
    evidence = []
    for item in arc.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        source_url = redact_sensitive_text(item.get("source_url", ""))
        if not source_url.startswith(("http://", "https://")):
            source_url = ""
        evidence.append({
            "finding_id": item.get("finding_id"),
            "run_date": _valid_run_date(str(item.get("run_date", ""))) or "",
            "agent": redact_sensitive_text(item.get("agent", "")),
            "title": redact_sensitive_text(item.get("title", "")),
            "summary": redact_sensitive_text(item.get("summary", "")),
            "source_url": source_url,
            "source_name": redact_sensitive_text(item.get("source_name", "")),
        })

    return {
        "id": redact_sensitive_text(arc.get("id", "")),
        "title": redact_sensitive_text(arc.get("title", "")),
        "summary": redact_sensitive_text(arc.get("summary", "")),
        "status": redact_sensitive_text(arc.get("status", "")),
        "first_seen": _valid_run_date(str(arc.get("first_seen", ""))) or "",
        "last_seen": _valid_run_date(str(arc.get("last_seen", ""))) or "",
        "evidence_count": int(arc.get("evidence_count") or 0),
        "date_count": int(arc.get("date_count") or 0),
        "source_domain_count": int(arc.get("source_domain_count") or 0),
        "agent_count": int(arc.get("agent_count") or 0),
        "scores": {
            key: float(scores.get(key) or 0.0)
            for key in (
                "recurrence",
                "velocity",
                "source_diversity",
                "freshness",
                "confidence",
            )
        },
        "evidence": evidence,
    }


def _audio_not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Audio briefing not found"})


def _safe_audio_paths(date: str, user: str) -> dict[str, Path] | None:
    date_val = _valid_run_date(date)
    user_val = _safe_user(user)
    if date_val is None or user_val is None:
        return None
    try:
        return audio_artifact_paths(
            date=date_val,
            user=user_val,
            reports_root=REPORTS_DIR,
        )
    except ValueError:
        return None


def _load_audio_metadata(date: str, user: str) -> tuple[dict | None, dict[str, Path] | None]:
    paths = _safe_audio_paths(date, user)
    if paths is None or not paths["metadata"].exists():
        return None, paths
    try:
        metadata = json.loads(paths["metadata"].read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None, paths

    date_val = _valid_run_date(str(metadata.get("date", "")))
    if date_val != date:
        return None, paths
    metadata["date"] = date
    metadata["user"] = user
    return metadata, paths


def _public_audio_metadata(
    metadata: dict,
    *,
    user: str,
    paths: dict[str, Path],
) -> dict:
    date = _valid_run_date(str(metadata.get("date", ""))) or ""
    has_audio_file = bool(metadata.get("has_audio_file")) and paths["audio"].exists()
    notes = []
    for note in metadata.get("show_notes") or []:
        if not isinstance(note, dict):
            continue
        url = redact_sensitive_text(note.get("url", ""))
        if not url.startswith(("http://", "https://")):
            continue
        notes.append({
            "label": redact_sensitive_text(note.get("label", "Source")),
            "url": url,
        })

    return {
        "id": redact_sensitive_text(metadata.get("id", f"{date}-audio-morning-briefing")),
        "type": "audio_briefing",
        "date": date,
        "user": user,
        "status": redact_sensitive_text(metadata.get("status", "")),
        "generated_at": redact_sensitive_text(metadata.get("generated_at", "")),
        "provider": redact_sensitive_text(metadata.get("provider", "")),
        "model": redact_sensitive_text(metadata.get("model", "")),
        "voice": redact_sensitive_text(metadata.get("voice", "")),
        "source_count": int(metadata.get("source_count") or 0),
        "duration_seconds": float(metadata.get("duration_seconds") or 0),
        "has_audio_file": has_audio_file,
        "audio_placeholder": bool(metadata.get("audio_placeholder")),
        "source_report_hash": redact_sensitive_text(metadata.get("source_report_hash", "")),
        "script_hash": redact_sensitive_text(metadata.get("script_hash", "")),
        "audio_hash": redact_sensitive_text(metadata.get("audio_hash", "")),
        "labels": [redact_sensitive_text(label) for label in metadata.get("labels") or []],
        "show_notes": notes,
        "public_url": f"/api/audio-briefings/{date}/file?user={user}" if has_audio_file else "",
        "transcript_url": f"/api/audio-briefings/{date}/transcript?user={user}",
    }


def get_memory_db(user_id: str = "ramsay") -> Optional[sqlite3.Connection]:
    """Open memory.db for a user. Fresh connection per request."""
    if _safe_user(user_id) is None:
        return None
    db_path = DATA_DIR / user_id / "memory.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _open_graph_model(user: str) -> tuple[sqlite3.Connection, CorpusGraphReadModel] | None:
    conn = get_memory_db(user)
    if conn is None:
        return None
    return conn, CorpusGraphReadModel(conn)


def _public_finding(row: sqlite3.Row | dict, *, kind: str = "finding") -> dict:
    """Whitelist fields for public finding-shaped API responses."""
    item = dict(row)
    public = {
        "kind": kind,
        "id": int(item.get("id") or 0),
        "run_date": _valid_date(item.get("run_date")) or "",
        "agent": item.get("agent") or "",
        "title": item.get("title") or "",
        "summary": item.get("summary") or "",
        "importance": item.get("importance") or "",
        "category": item.get("category") or "",
        "source_url": item.get("source_url") or "",
        "source_name": item.get("source_name") or "",
        "created_at": item.get("created_at") or "",
    }
    return _strip_pii_dict(public, ["title", "summary"])


def _finding_not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Finding not found"})


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _source_ref_from_finding(item: dict) -> dict | None:
    source_url = redact_sensitive_text(item.get("source_url") or "")
    if not source_url.startswith(("http://", "https://")):
        return None
    parsed = urlparse(source_url)
    domain = re.sub(r"^www\.", "", parsed.netloc.lower())
    if not domain:
        return None
    return {
        "url": source_url,
        "domain": domain,
        "title": redact_sensitive_text(item.get("source_name") or domain),
    }


def _entity_slug_expr(column: str) -> str:
    return f"lower(replace(replace({column}, ' ', '-'), '_', '-'))"


def _entity_search_pattern(entity_slug: str) -> str:
    tokens = [token for token in entity_slug.split("-") if token]
    return "%" + "%".join(tokens) + "%"


def _safe_entity_slug(name: str) -> str:
    try:
        return normalize_slug(name)
    except ValueError:
        return "unknown"


def _public_corpus_entity(user: str, entity_slug: str, *, limit: int) -> dict:
    conn = get_memory_db(user)
    if conn is None:
        return {
            "name": entity_slug.replace("-", " ").title(),
            "relationships": [],
            "findings": [],
            "source_trail": [],
            "kg_entities": [],
            "graph_sources": [],
        }

    try:
        entity_name = entity_slug.replace("-", " ").title()
        graph_sources: set[str] = set()
        relationships: list[dict] = []
        finding_ids: set[int] = set()
        kg_entities: list[dict] = []

        if _table_exists(conn, "kg_entities") and _table_exists(conn, "kg_entity_aliases"):
            kg_rows = conn.execute(
                f"""
                SELECT DISTINCT e.id, e.canonical_name, e.entity_type, e.description,
                       e.mention_count, e.importance, e.first_seen, e.last_seen
                FROM kg_entities e
                LEFT JOIN kg_entity_aliases a ON a.entity_id = e.id
                WHERE {_entity_slug_expr("e.canonical_name")} = ?
                   OR {_entity_slug_expr("a.alias")} = ?
                ORDER BY e.importance DESC, e.mention_count DESC
                LIMIT 5
                """,
                (entity_slug, entity_slug),
            ).fetchall()
            for row in kg_rows:
                graph_sources.add("kg_entities")
                kg_entity = {
                    "id": int(row["id"]),
                    "name": redact_sensitive_text(row["canonical_name"]),
                    "kind": redact_sensitive_text(row["entity_type"] or "Other"),
                    "description": redact_sensitive_text(row["description"] or ""),
                    "mention_count": int(row["mention_count"] or 0),
                    "importance": float(row["importance"] or 0.0),
                    "first_seen": _valid_date(row["first_seen"]) or "",
                    "last_seen": _valid_date(row["last_seen"]) or "",
                }
                kg_entities.append(kg_entity)
                entity_name = kg_entity["name"] or entity_name

                if _table_exists(conn, "kg_edges"):
                    edge_rows = conn.execute(
                        """
                        SELECT edge.id, edge.predicate, edge.fact_text, edge.fact_type,
                               edge.confidence, edge.finding_id,
                               subject.canonical_name AS subject_name,
                               object.canonical_name AS object_name,
                               subject.entity_type AS subject_type,
                               object.entity_type AS object_type
                        FROM kg_edges edge
                        JOIN kg_entities subject ON subject.id = edge.subject_id
                        JOIN kg_entities object ON object.id = edge.object_id
                        WHERE edge.invalid_at IS NULL
                          AND (edge.subject_id = ? OR edge.object_id = ?)
                        ORDER BY edge.confidence DESC, edge.id DESC
                        LIMIT 40
                        """,
                        (kg_entity["id"], kg_entity["id"]),
                    ).fetchall()
                    for edge in edge_rows:
                        graph_sources.add("kg_edges")
                        finding_id = edge["finding_id"]
                        if finding_id is not None:
                            finding_ids.add(int(finding_id))
                        relationships.append({
                            "source": "kg_edges",
                            "relationship": redact_sensitive_text(edge["predicate"]),
                            "entity_a": redact_sensitive_text(edge["subject_name"]),
                            "entity_a_type": redact_sensitive_text(edge["subject_type"] or ""),
                            "entity_b": redact_sensitive_text(edge["object_name"]),
                            "entity_b_type": redact_sensitive_text(edge["object_type"] or ""),
                            "fact_text": redact_sensitive_text(edge["fact_text"] or ""),
                            "fact_type": redact_sensitive_text(edge["fact_type"] or "Fact"),
                            "confidence": float(edge["confidence"] or 0.0),
                            "finding_id": int(finding_id) if finding_id is not None else None,
                            "target_url": f"/f/{finding_id}" if finding_id is not None else "",
                        })

        if _table_exists(conn, "entity_graph"):
            rows = conn.execute(
                f"""
                SELECT entity_a, entity_a_type, relationship, entity_b, entity_b_type,
                       finding_id, created_at
                FROM entity_graph
                WHERE {_entity_slug_expr("entity_a")} = ?
                   OR {_entity_slug_expr("entity_b")} = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                (entity_slug, entity_slug),
            ).fetchall()
            for row in rows:
                graph_sources.add("entity_graph")
                a_slug = _safe_entity_slug(row["entity_a"])
                matched_a = a_slug == entity_slug
                entity_name = redact_sensitive_text(row["entity_a"] if matched_a else row["entity_b"])
                related_name = redact_sensitive_text(row["entity_b"] if matched_a else row["entity_a"])
                related_type = redact_sensitive_text(row["entity_b_type"] if matched_a else row["entity_a_type"] or "")
                finding_id = row["finding_id"]
                if finding_id is not None:
                    finding_ids.add(int(finding_id))
                relationships.append({
                    "source": "entity_graph",
                    "relationship": redact_sensitive_text(row["relationship"]),
                    "related_entity": related_name,
                    "related_entity_slug": _safe_entity_slug(related_name),
                    "related_entity_type": related_type,
                    "finding_id": int(finding_id) if finding_id is not None else None,
                    "target_url": f"/f/{finding_id}" if finding_id is not None else "",
                    "created_at": redact_sensitive_text(row["created_at"] or ""),
                })

        findings_by_id: dict[int, dict] = {}
        if finding_ids:
            placeholders = ",".join("?" for _ in finding_ids)
            rows = conn.execute(
                f"""
                SELECT id, run_date, agent, title, summary, importance, category,
                       source_url, source_name, created_at
                FROM findings
                WHERE id IN ({placeholders})
                ORDER BY run_date DESC, created_at DESC
                LIMIT ?
                """,
                [*finding_ids, limit],
            ).fetchall()
            for row in rows:
                public = _public_finding(row)
                public["target_url"] = f"/f/{public['id']}"
                public["relationship"] = "entity_graph_provenance"
                findings_by_id[public["id"]] = public

        if len(findings_by_id) < limit and _table_exists(conn, "findings"):
            pattern = _entity_search_pattern(entity_slug)
            rows = conn.execute(
                """
                SELECT id, run_date, agent, title, summary, importance, category,
                       source_url, source_name, created_at
                FROM findings
                WHERE lower(title || ' ' || COALESCE(summary, '')) LIKE ?
                ORDER BY run_date DESC, created_at DESC
                LIMIT ?
                """,
                (pattern, limit),
            ).fetchall()
            for row in rows:
                graph_sources.add("findings_text")
                public = _public_finding(row)
                public["target_url"] = f"/f/{public['id']}"
                public["relationship"] = "entity_text_match"
                findings_by_id.setdefault(public["id"], public)
                if len(findings_by_id) >= limit:
                    break

        source_by_url: dict[str, dict] = {}
        for finding in findings_by_id.values():
            source = _source_ref_from_finding(finding)
            if source is not None:
                source_by_url.setdefault(source["url"], source)

        return {
            "name": entity_name,
            "relationships": relationships[:limit],
            "findings": list(findings_by_id.values())[:limit],
            "source_trail": list(source_by_url.values())[:limit],
            "kg_entities": kg_entities,
            "graph_sources": sorted(graph_sources),
        }
    finally:
        conn.close()


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


@router.get("/api/finding/{finding_id}")
async def get_finding(
    finding_id: int,
    user: str = Query("ramsay"),
):
    """Public: one finding by ID with whitelisted fields only."""
    opened = _open_graph_model(user)
    if opened is None:
        return _finding_not_found()
    conn, model = opened
    try:
        graph_finding = model.get_finding(finding_id)
        if graph_finding is not None:
            related = model.get_related_paths_for_finding(finding_id, limit=5)
            graph_finding["related_paths"] = related["items"] if related else []
            return graph_finding

        row = conn.execute(
            """
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE id = ?
            """,
            (finding_id,),
        ).fetchone()
        if row is None:
            return _finding_not_found()
        return _public_finding(row)
    finally:
        conn.close()


@router.get("/api/findings/{finding_id}")
async def get_finding_detail(
    finding_id: int,
    user: str = Query("ramsay"),
):
    """Public: first-class finding page data with graph links."""
    return await get_finding(finding_id=finding_id, user=user)


@router.get("/api/related/{finding_id}")
async def get_related_findings(
    finding_id: int,
    mode: str = Query("semantic"),
    limit: int = Query(10, ge=0, le=50),
    user: str = Query("ramsay"),
):
    """Public: source finding's related findings over stored embeddings."""
    if mode not in {"semantic", "blended"}:
        return JSONResponse(status_code=400, content={"error": "Unsupported related mode"})

    opened = _open_graph_model(user)
    if opened is None:
        return _finding_not_found()

    conn, model = opened
    try:
        if mode == "blended":
            blended = model.get_related_paths_for_finding(finding_id, limit=limit)
            if blended is None:
                return _finding_not_found()
            return blended

        source = conn.execute(
            """
            SELECT f.id, f.title, e.embedding
            FROM findings f
            LEFT JOIN findings_embeddings e ON e.finding_id = f.id
            WHERE f.id = ?
            """,
            (finding_id,),
        ).fetchone()
        if source is None:
            return _finding_not_found()
        if source["embedding"] is None or limit == 0:
            return {
                "kind": "related",
                "finding_id": finding_id,
                "mode": "semantic",
                "items": [],
                "total": 0,
            }

        source_vec = np.array(_deserialize_f32(source["embedding"]), dtype=np.float32)
        rows = conn.execute(
            """
            SELECT f.id, f.run_date, f.agent, f.title, f.summary, f.importance,
                   f.category, f.source_url, f.source_name, f.created_at, e.embedding
            FROM findings f
            JOIN findings_embeddings e ON e.finding_id = f.id
            WHERE f.id != ?
            """,
            (finding_id,),
        ).fetchall()

        scored = []
        for row in rows:
            emb = np.array(_deserialize_f32(row["embedding"]), dtype=np.float32)
            score = float(np.dot(source_vec, emb))
            public = _public_finding(row)
            public.update({
                "score": round(max(0.0, score), 4),
                "similarity": round(max(0.0, score), 4),
                "mode": "semantic",
                "relationship": "semantic_similarity",
                "reason": "Embedding similarity over stored MindPattern findings.",
                "target_url": f"/f/{public['id']}",
            })
            scored.append(public)

        scored.sort(key=lambda item: (-item["score"], item["id"]))
        items = scored[:limit]
        return {
            "kind": "related",
            "finding_id": finding_id,
            "mode": "semantic",
            "items": items,
            "total": len(items),
        }
    finally:
        conn.close()


@router.get("/api/entities")
async def list_entities(
    q: str = Query(""),
    limit: int = Query(50, ge=0, le=200),
    offset: int = Query(0, ge=0),
    user: str = Query("ramsay"),
):
    """Public: paginated corpus entity index for dynamic entity pages."""
    opened = _open_graph_model(user)
    if opened is None:
        return {
            "kind": "entities",
            "status": "missing",
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "graph_sources": [],
            "degraded_reasons": ["missing memory database"],
        }
    conn, model = opened
    try:
        return model.list_entities(q=q, limit=limit, offset=offset)
    finally:
        conn.close()


@router.get("/api/feed")
async def get_feed(
    limit: int = Query(50, ge=0, le=200),
    offset: int = Query(0, ge=0),
    since: str = Query(None),
    date: str = Query(None),
    user: str = Query("ramsay"),
):
    """Public: forward-compatible Wire feed wrapper over public findings."""
    conn = get_memory_db(user)
    if conn is None:
        return {
            "kind": "feed",
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }

    try:
        where_clauses: list[str] = []
        params: list = []
        date_val = _valid_date(date)
        since_val = _valid_date(since)
        if date_val:
            where_clauses.append("run_date = ?")
            params.append(date_val)
        elif since_val:
            where_clauses.append("run_date >= ?")
            params.append(since_val)
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        total = conn.execute(
            f"SELECT COUNT(*) FROM findings WHERE {where_sql}",
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE {where_sql}
            ORDER BY run_date DESC, created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()
        items = []
        for idx, row in enumerate(rows, start=offset + 1):
            item = _public_finding(row)
            item.update({
                "rank": idx,
                "target_type": "finding",
                "target_id": str(item["id"]),
                "target_url": f"/f/{item['id']}",
                "confidence": "source-backed",
            })
            items.append(item)
        return {
            "kind": "feed",
            "items": items,
            "total": int(total),
            "limit": limit,
            "offset": offset,
        }
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


@router.get("/api/sources/{domain}")
async def get_source_detail(
    domain: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: str = Query("ramsay"),
):
    """Public: one source-domain page with linked findings and entities."""
    opened = _open_graph_model(user)
    if opened is None:
        return JSONResponse(status_code=404, content={"error": "Source not found"})
    conn, model = opened
    try:
        source = model.get_source(domain, limit=limit, offset=offset)
        if source.get("status") == "missing":
            return JSONResponse(status_code=404, content={"error": "Source not found"})
        return source
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


@router.get("/api/narrative-arcs")
async def get_narrative_arcs(
    date: str = Query(None),
    user: str = Query("ramsay"),
    limit: int = Query(20, ge=0, le=100),
):
    """Public: source-backed narrative arcs for a run date. No raw PII."""
    date_val = _valid_run_date(date)
    user_val = _safe_user(user)
    if date_val is None or user_val is None:
        return []

    try:
        arcs = load_narrative_arcs(
            date=date_val,
            user=user_val,
            reports_root=REPORTS_DIR,
            limit=limit,
        )
    except (ValueError, OSError, json.JSONDecodeError):
        return []

    return [_public_narrative_arc(arc) for arc in arcs]


@router.get("/api/narrative-arcs/{arc_id}")
async def get_narrative_arc(
    arc_id: str,
    date: str = Query(None),
    user: str = Query("ramsay"),
):
    """Public: one source-backed narrative arc by ID. No raw PII."""
    arc_id_val = _safe_arc_id(arc_id)
    date_val = _valid_run_date(date)
    user_val = _safe_user(user)
    if arc_id_val is None or date_val is None or user_val is None:
        return None

    try:
        arcs = load_narrative_arcs(
            date=date_val,
            user=user_val,
            reports_root=REPORTS_DIR,
        )
    except (ValueError, OSError, json.JSONDecodeError):
        return None

    for arc in arcs:
        if arc.get("id") == arc_id_val:
            return _public_narrative_arc(arc)
    return None


@router.get("/api/audio-briefings")
async def list_audio_briefings(
    user: str = Query("ramsay"),
    limit: int = Query(30, ge=0, le=100),
):
    """Public: list generated audio briefings. No private paths or raw files."""
    user_val = _safe_user(user)
    if user_val is None:
        return []
    audio_dir = (REPORTS_DIR / user_val / "audio").resolve()
    try:
        audio_dir.relative_to(REPORTS_DIR.resolve())
    except ValueError:
        return []
    if not audio_dir.exists():
        return []

    items = []
    for metadata_file in sorted(audio_dir.glob("*.json"), reverse=True):
        if metadata_file.name.endswith(".provenance.json"):
            continue
        date_val = _valid_run_date(metadata_file.stem)
        if date_val is None:
            continue
        metadata, paths = _load_audio_metadata(date_val, user_val)
        if metadata is None or paths is None:
            continue
        items.append(_public_audio_metadata(metadata, user=user_val, paths=paths))
        if len(items) >= limit:
            break
    return items


@router.get("/api/audio-briefings/{date}")
async def get_audio_briefing(date: str, user: str = Query("ramsay")):
    """Public: get one audio briefing metadata record by date."""
    metadata, paths = _load_audio_metadata(date, user)
    if metadata is None or paths is None:
        return _audio_not_found()
    return _public_audio_metadata(metadata, user=user, paths=paths)


@router.get("/api/audio-briefings/{date}/file")
async def get_audio_briefing_file(date: str, user: str = Query("ramsay")):
    """Public: stream a known MP3 artifact for a valid date/user only."""
    metadata, paths = _load_audio_metadata(date, user)
    if metadata is None or paths is None:
        return _audio_not_found()
    public = _public_audio_metadata(metadata, user=user, paths=paths)
    if not public["has_audio_file"] or not paths["audio"].exists():
        return _audio_not_found()
    return FileResponse(
        paths["audio"],
        media_type="audio/mpeg",
        filename=paths["audio"].name,
    )


@router.get("/api/audio-briefings/{date}/transcript")
async def get_audio_briefing_transcript(date: str, user: str = Query("ramsay")):
    """Public: return a known audio transcript for a valid date/user only."""
    metadata, paths = _load_audio_metadata(date, user)
    if metadata is None or paths is None or not paths["transcript"].exists():
        return _audio_not_found()
    return PlainTextResponse(
        paths["transcript"].read_text(errors="replace"),
        media_type="text/plain",
    )


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
    if _safe_user(user) is None:
        return []
    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return []

    by_date: dict[str, Path] = {}
    for f in sorted(reports_dir.glob("*.md"), reverse=True):
        name = f.stem
        # Extract date from filename (YYYY-MM-DD or YYYY-MM-DD-HHMMSS)
        date_match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
        if not date_match:
            continue
        date_str = date_match.group(1)
        if any(token in f.name.lower() for token in ("debug", "stderr")):
            continue
        current = by_date.get(date_str)
        if current is None or _report_file_rank(f, date_str) < _report_file_rank(current, date_str):
            by_date[date_str] = f

    reports = []
    for date_str, path in sorted(by_date.items(), reverse=True):
        report = _report_metadata(path, date_str)
        if report is not None:
            reports.append(report)

    return reports


@router.get("/api/reports/search")
async def search_reports(
    q: str = Query(""),
    user: str = Query("ramsay"),
    limit: int = Query(10, le=50),
):
    """Public: search newsletter reports by text content."""
    if not q or _safe_user(user) is None:
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


def _report_file_for_date(*, date: str, user: str) -> Path | None:
    if _valid_run_date(date) is None or _safe_user(user) is None:
        return None
    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return None
    matches = [
        path
        for path in reports_dir.glob(f"{date}*.md")
        if not any(token in path.name.lower() for token in ("debug", "stderr"))
    ]
    if not matches:
        return None
    matches.sort(key=lambda path: _report_file_rank(path, date))
    target = matches[0]
    try:
        target.resolve().relative_to(reports_dir.resolve())
    except ValueError:
        return None
    return target


def _structured_issue_dates(*, user: str) -> list[str]:
    if _safe_user(user) is None:
        return []
    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return []
    dates: set[str] = set()
    for path in reports_dir.glob("*.md"):
        if any(token in path.name.lower() for token in ("debug", "stderr")):
            continue
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.stem)
        if match and _valid_run_date(match.group(1)):
            dates.add(match.group(1))
    return sorted(dates, reverse=True)


def _structured_issue_from_report_file(*, date: str, user: str) -> dict | None:
    target = _report_file_for_date(date=date, user=user)
    if target is None:
        return None

    text = _clean_report_markdown(target.read_text(errors="replace"))
    if not _is_public_report_content(text, min_bytes=_MIN_STRUCTURED_REPORT_BYTES):
        return None
    title = _report_title_from_content(content=text, date=date, fallback_name=target.stem)
    try:
        return build_structured_issue(
            date=validate_run_date(date),
            user=user,
            title=title,
            content=text,
        )
    except ValueError:
        return None


def _published_story_refs_for_issue(*, date: str, user: str) -> list[dict]:
    refs: list[dict] = []
    seen_story_units: set[str] = set()
    for path in _public_story_files(user):
        story = _load_public_story_file(path)
        if story is None or story.get("issue_date") != date:
            continue
        story_unit_id = str(
            story.get("story_unit_id")
            or story.get("provenance", {}).get("source_story_unit_id")
            or ""
        ).strip()
        if not story_unit_id or story_unit_id in seen_story_units:
            continue
        seen_story_units.add(story_unit_id)
        refs.append(
            {
                "story_unit_id": story_unit_id,
                "slug": story["slug"],
                "title": story["title"],
                "target_url": story["target_url"],
                "confidence": story["confidence"],
                "source_domains": story.get("graph_connectors", {}).get("source_domains", []),
                "entity_ids": story.get("graph_connectors", {}).get("entity_ids", []),
            }
        )
    return sorted(refs, key=lambda item: item["story_unit_id"])


def _enrich_issue_with_published_stories(*, issue: dict, user: str) -> dict:
    refs = _published_story_refs_for_issue(date=issue["date"], user=user)
    refs_by_story_unit = {ref["story_unit_id"]: ref for ref in refs}
    enriched = dict(issue)
    enriched["published_story_refs"] = refs
    enriched["story_units"] = [
        {
            **story,
            **(
                {"published_story": refs_by_story_unit[story["id"]]}
                if story.get("id") in refs_by_story_unit
                else {}
            ),
        }
        for story in issue.get("story_units", [])
    ]
    return enriched


@router.get("/api/issues")
async def list_structured_issues(user: str = Query("ramsay")):
    """Public: list newsletter issues with structured API links."""
    if _safe_user(user) is None:
        return []
    reports = await list_reports(user=user)
    return [
        {
            "date": report["date"],
            "filename": report["filename"],
            "title": report["title"],
            "subtitle": report.get("subtitle", ""),
            "structured_url": f"/api/issues/{report['date']}/structured?user={user}",
        }
        for report in reports
    ]


@router.get("/api/issues/{date}/structured")
async def get_structured_issue(date: str, user: str = Query("ramsay")):
    """Public: deterministic issue -> sections/story units/source graph."""
    issue = _structured_issue_from_report_file(date=date, user=user)
    if issue is None:
        return JSONResponse(status_code=404, content={"error": "Issue not found"})
    return _enrich_issue_with_published_stories(issue=issue, user=user)


def _story_date_from_slug(slug: str) -> str | None:
    candidate = slug[:10] if len(slug) >= 10 else ""
    return _valid_run_date(candidate)


async def _iter_structured_issues(user: str):
    for date in _structured_issue_dates(user=user):
        issue = _structured_issue_from_report_file(date=date, user=user)
        if issue is not None:
            yield issue


def _story_from_issue(issue: dict, story_slug: str) -> dict | None:
    for story_unit in issue.get("story_units", []):
        try:
            if normalize_slug(str(story_unit.get("id"))) != story_slug:
                continue
        except ValueError:
            continue
        return build_public_story(issue=issue, story_unit=story_unit)
    return None


def _story_from_structured_issue_slug(*, story_slug: str, user: str) -> dict | None:
    date = _story_date_from_slug(story_slug)
    if date is None:
        return None
    issue = _structured_issue_from_report_file(date=date, user=user)
    if issue is None:
        return None
    return _story_from_issue(issue, story_slug)


def _public_story_files(user: str) -> list[Path]:
    base = (REPORTS_DIR / user / "site-stories").resolve()
    try:
        base.relative_to(REPORTS_DIR.resolve())
    except ValueError:
        return []
    if not base.exists():
        return []
    files = [path for path in base.rglob("*.json") if path.is_file()]
    return sorted(files, key=lambda path: path.as_posix(), reverse=True)


def _public_story_source_refs(items: list[dict]) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        source_url = redact_sensitive_text(str(item.get("url", "")))
        if not source_url.startswith(("http://", "https://")) or source_url in seen:
            continue
        parsed = urlparse(source_url)
        domain = redact_sensitive_text(str(item.get("domain") or parsed.netloc.lower().removeprefix("www.")))
        if not domain:
            continue
        seen.add(source_url)
        refs.append({
            "url": source_url,
            "domain": domain,
            "title": redact_sensitive_text(str(item.get("title") or domain)),
        })
    return refs


def _public_story_entity_refs(items: list[dict]) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_slug = str(item.get("slug") or item.get("id") or "")
        try:
            slug = normalize_slug(raw_slug)
        except ValueError:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        refs.append({
            "id": slug,
            "slug": slug,
            "name": redact_sensitive_text(str(item.get("name") or slug.replace("-", " ").title())),
            "kind": redact_sensitive_text(str(item.get("kind") or "unknown")),
        })
    return refs


def _public_story_edges(items: list[dict]) -> list[dict]:
    edges: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target_url = redact_sensitive_text(str(item.get("target_url") or ""))
        if target_url and not target_url.startswith(("/", "http://", "https://")):
            target_url = ""
        edges.append({
            "kind": redact_sensitive_text(str(item.get("kind") or "")),
            "relationship": redact_sensitive_text(str(item.get("relationship") or "")),
            "id": redact_sensitive_text(str(item.get("id") or "")),
            "label": redact_sensitive_text(str(item.get("label") or "")),
            "target_url": target_url,
            "evidence": redact_sensitive_text(str(item.get("evidence") or "")),
        })
    return edges


def _public_story_claim_evidence(items: list[dict]) -> list[dict]:
    evidence: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source_url = redact_sensitive_text(str(item.get("source_url") or ""))
        if source_url and not source_url.startswith(("http://", "https://")):
            source_url = ""
        finding_id = item.get("finding_id")
        evidence.append({
            "claim": redact_sensitive_text(str(item.get("claim") or "")),
            "source_url": source_url,
            "finding_id": int(finding_id) if str(finding_id).isdigit() else None,
        })
    return [item for item in evidence if item["claim"] or item["source_url"] or item["finding_id"] is not None]


def _public_story_provenance(item: dict) -> dict:
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    input_artifacts = []
    for artifact in provenance.get("input_artifacts") or []:
        artifact_text = redact_sensitive_text(str(artifact))
        if artifact_text.startswith("reports/"):
            input_artifacts.append(artifact_text)
    source_finding_ids = [
        int(finding_id)
        for finding_id in provenance.get("source_finding_ids") or []
        if str(finding_id).isdigit()
    ]
    source_issue_dates = [
        date
        for date in (str(value) for value in provenance.get("source_issue_dates") or [])
        if _valid_run_date(date)
    ]
    source_story_unit_id = redact_sensitive_text(str(provenance.get("source_story_unit_id") or ""))
    return {
        "generated_by": redact_sensitive_text(str(provenance.get("generated_by") or "")),
        "generated_at": redact_sensitive_text(str(provenance.get("generated_at") or "")),
        "input_artifacts": input_artifacts,
        "source_finding_ids": source_finding_ids,
        "source_issue_dates": source_issue_dates,
        "source_story_unit_id": source_story_unit_id,
        "redaction_status": redact_sensitive_text(str(provenance.get("redaction_status") or "passed")),
        "ai_generated": bool(provenance.get("ai_generated")),
        "human_approved": bool(provenance.get("human_approved")),
    }


def _public_story_artifact(item: dict, *, fallback_slug: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    if item.get("status") != "published" or item.get("confidence") != "high":
        return None
    gate_item = dict(item)
    if gate_item.get("kind") == "story":
        gate_item["kind"] = "site_story"
    if not gate_item.get("source_refs") and item.get("source_trail"):
        gate_item["source_refs"] = item.get("source_trail")
    if not is_publishable_site_story(gate_item):
        return None
    try:
        slug = normalize_slug(str(item.get("slug") or fallback_slug))
    except ValueError:
        return None

    source_refs = _public_story_source_refs(item.get("source_refs") or item.get("source_trail") or [])
    claim_evidence = _public_story_claim_evidence(item.get("claim_evidence") or [])
    if not source_refs or not claim_evidence:
        return None

    issue_date = _valid_run_date(str(item.get("issue_date") or item.get("date") or "")) or ""
    title = redact_sensitive_text(str(item.get("title") or "")).strip()
    if not title:
        return None
    raw_provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    story_unit_id = redact_sensitive_text(
        str(item.get("story_unit_id") or raw_provenance.get("source_story_unit_id") or "")
    )

    finding_ids = [
        int(finding_id)
        for finding_id in item.get("finding_ids") or item.get("primary_finding_ids") or []
        if str(finding_id).isdigit()
    ]
    graph_connectors = item.get("graph_connectors") if isinstance(item.get("graph_connectors"), dict) else {}
    graph_connectors = {
        "issue_date": issue_date,
        "source_urls": [source["url"] for source in source_refs],
        "source_domains": sorted({source["domain"] for source in source_refs}),
        "entity_ids": [
            entity["id"]
            for entity in _public_story_entity_refs(item.get("entity_refs") or item.get("entities") or [])
        ],
        "topic_terms": [
            redact_sensitive_text(str(term))
            for term in graph_connectors.get("topic_terms", [])
            if str(term)
        ][:16],
        "finding_ids": finding_ids,
        "arc_ids": [redact_sensitive_text(str(arc_id)) for arc_id in item.get("arc_ids", []) if str(arc_id)],
    }

    body_markdown = redact_sensitive_text(str(item.get("body_markdown") or item.get("body") or item.get("take") or ""))
    summary = redact_sensitive_text(str(item.get("summary") or item.get("dek") or item.get("take") or ""))

    return {
        "kind": "story",
        "id": slug,
        "slug": slug,
        "story_unit_id": story_unit_id,
        "status": "published",
        "issue_date": issue_date,
        "date": issue_date,
        "title": title,
        "dek": redact_sensitive_text(str(item.get("dek") or "")),
        "summary": summary,
        "take": redact_sensitive_text(str(item.get("take") or "")),
        "why_now": redact_sensitive_text(str(item.get("why_now") or "")),
        "body_excerpt": summary,
        "body_markdown": body_markdown or summary,
        "source_refs": source_refs,
        "source_trail": source_refs,
        "entity_refs": _public_story_entity_refs(item.get("entity_refs") or item.get("entities") or []),
        "finding_ids": finding_ids,
        "primary_finding_ids": finding_ids,
        "supporting_finding_ids": [
            int(finding_id)
            for finding_id in item.get("supporting_finding_ids", [])
            if str(finding_id).isdigit()
        ],
        "arc_ids": graph_connectors["arc_ids"],
        "graph_connectors": graph_connectors,
        "graph_edges": _public_story_edges(item.get("graph_edges") or []),
        "related_paths": [
            related
            for related in item.get("related_paths", [])
            if isinstance(related, dict) and str(related.get("target_url", "")).startswith(("/", "http://", "https://"))
        ],
        "target_url": f"/s/{slug}",
        "confidence": "high",
        "labels": [redact_sensitive_text(str(label)) for label in item.get("labels", []) if str(label)],
        "json_ld_ready": bool(item.get("json_ld_ready", True)),
        "claim_evidence": claim_evidence,
        "provenance": _public_story_provenance(item),
    }


def _load_public_story_file(path: Path) -> dict | None:
    try:
        path.resolve().relative_to((REPORTS_DIR).resolve())
    except ValueError:
        return None
    try:
        item = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return _public_story_artifact(item, fallback_slug=path.stem)


async def _all_public_stories(user: str) -> list[dict]:
    stories: list[dict] = []
    covered_story_units: set[str] = set()
    seen_slugs: set[str] = set()
    for path in _public_story_files(user):
        story = _load_public_story_file(path)
        if story is None:
            continue
        seen_slugs.add(str(story.get("slug") or ""))
        if story.get("story_unit_id"):
            covered_story_units.add(str(story["story_unit_id"]))
        stories.append(story)

    for date in _structured_issue_dates(user=user):
        issue = _structured_issue_from_report_file(date=date, user=user)
        if issue is None:
            continue
        for story_unit in issue.get("story_units", []):
            story_unit_id = str(story_unit.get("id") or "")
            if story_unit_id in covered_story_units:
                continue
            story = build_public_story(issue=issue, story_unit=story_unit)
            if story is None:
                continue
            slug = str(story.get("slug") or "")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            stories.append(story)

    stories.sort(key=lambda story: (story.get("issue_date", ""), story.get("slug", "")), reverse=True)
    return stories


def _story_connector_set(story: dict, key: str) -> set:
    values = story.get("graph_connectors", {}).get(key, [])
    return {str(value) for value in values if str(value)}


def _story_entity_labels(story: dict) -> dict[str, str]:
    return {
        str(entity["id"]): str(entity["name"])
        for entity in story.get("entity_refs", [])
        if entity.get("id") and entity.get("name")
    }


def _source_ref_by_url(story: dict) -> dict[str, dict]:
    return {
        str(source["url"]): source
        for source in story.get("source_refs", [])
        if source.get("url")
    }


def _related_path_from_graph(source: dict, candidate: dict) -> dict | None:
    source_urls = _story_connector_set(source, "source_urls")
    candidate_urls = _story_connector_set(candidate, "source_urls")
    source_domains = _story_connector_set(source, "source_domains")
    candidate_domains = _story_connector_set(candidate, "source_domains")
    source_entities = _story_connector_set(source, "entity_ids")
    candidate_entities = _story_connector_set(candidate, "entity_ids")
    source_topics = _story_connector_set(source, "topic_terms")
    candidate_topics = _story_connector_set(candidate, "topic_terms")
    source_findings = _story_connector_set(source, "finding_ids")
    candidate_findings = _story_connector_set(candidate, "finding_ids")
    source_arcs = _story_connector_set(source, "arc_ids")
    candidate_arcs = _story_connector_set(candidate, "arc_ids")

    shared_urls = sorted(source_urls & candidate_urls)
    shared_domains = sorted(source_domains & candidate_domains)
    shared_entities = sorted(source_entities & candidate_entities)
    shared_topics = sorted(source_topics & candidate_topics)
    shared_findings = sorted(source_findings & candidate_findings)
    shared_arcs = sorted(source_arcs & candidate_arcs)

    if len(shared_topics) < 2:
        shared_topics = []

    if not any([shared_urls, shared_domains, shared_entities, shared_topics, shared_findings, shared_arcs]):
        return None

    evidence_edges: list[dict] = []
    relationships: list[str] = []
    reason_parts: list[str] = []
    score = 0.0
    source_refs = _source_ref_by_url(source)
    entity_labels = _story_entity_labels(source) | _story_entity_labels(candidate)

    if shared_urls:
        relationships.append("shared_source_url")
        score += 6 * len(shared_urls)
        labels: list[str] = []
        for url in shared_urls[:3]:
            ref = source_refs.get(url, {})
            label = ref.get("title") or ref.get("domain") or url
            labels.append(label)
            evidence_edges.append({
                "kind": "source_url",
                "relationship": "shared_source_url",
                "id": url,
                "label": label,
                "target_url": url,
            })
        reason_parts.append(f"same source URL: {', '.join(labels)}")

    if shared_domains:
        relationships.append("shared_source_domain")
        score += 3 * len(shared_domains)
        for domain in shared_domains[:3]:
            evidence_edges.append({
                "kind": "source_domain",
                "relationship": "shared_source_domain",
                "id": domain,
                "label": domain,
                "target_url": f"/source/{domain}",
            })
        reason_parts.append(f"same source domain: {', '.join(shared_domains[:3])}")

    if shared_entities:
        relationships.append("shared_entity")
        score += 4 * len(shared_entities)
        labels = [entity_labels.get(entity_id, entity_id) for entity_id in shared_entities[:4]]
        for entity_id, label in zip(shared_entities[:4], labels):
            evidence_edges.append({
                "kind": "entity",
                "relationship": "shared_entity",
                "id": entity_id,
                "label": label,
                "target_url": f"/e/{entity_id}",
            })
        reason_parts.append(f"same entities: {', '.join(labels)}")

    if shared_topics:
        relationships.append("shared_topic")
        score += 1.5 * len(shared_topics)
        for topic in shared_topics[:5]:
            evidence_edges.append({
                "kind": "topic",
                "relationship": "shared_topic",
                "id": topic,
                "label": topic,
                "target_url": "",
            })
        reason_parts.append(f"same topic terms: {', '.join(shared_topics[:5])}")

    if shared_findings:
        relationships.append("shared_finding")
        score += 5 * len(shared_findings)
        for finding_id in shared_findings[:3]:
            evidence_edges.append({
                "kind": "finding",
                "relationship": "shared_finding",
                "id": finding_id,
                "label": f"Finding {finding_id}",
                "target_url": f"/f/{finding_id}",
            })
        reason_parts.append(f"same findings: {', '.join(shared_findings[:3])}")

    if shared_arcs:
        relationships.append("shared_arc")
        score += 5 * len(shared_arcs)
        for arc_id in shared_arcs[:3]:
            evidence_edges.append({
                "kind": "arc",
                "relationship": "shared_arc",
                "id": arc_id,
                "label": arc_id,
                "target_url": "",
            })
        reason_parts.append(f"same narrative arcs: {', '.join(shared_arcs[:3])}")

    return {
        "kind": "story",
        "id": candidate["id"],
        "slug": candidate["slug"],
        "title": candidate["title"],
        "summary": candidate.get("summary", ""),
        "issue_date": candidate["issue_date"],
        "target_url": candidate["target_url"],
        "relationship": "+".join(relationships),
        "reason": "Graph match: " + "; ".join(reason_parts),
        "score": round(score, 2),
        "evidence_edges": evidence_edges[:10],
    }


def _story_with_graph_related(story: dict, stories: list[dict], *, limit: int = 8) -> dict:
    related_paths = []
    for candidate in stories:
        if candidate.get("slug") == story.get("slug"):
            continue
        related = _related_path_from_graph(story, candidate)
        if related is not None:
            related_paths.append(related)

    related_paths.sort(
        key=lambda item: (item["score"], item.get("issue_date", "")),
        reverse=True,
    )
    enriched = dict(story)
    enriched["related_paths"] = related_paths[:limit]
    return enriched


def _load_site_artifact_response(
    *,
    kind: str,
    date: str,
    user: str,
) -> dict | JSONResponse:
    safe_user = _safe_user(user)
    if safe_user is None:
        return JSONResponse(status_code=404, content={"error": "Artifact not found"})
    try:
        path = site_artifact_path(
            kind=kind,
            user=safe_user,
            date=date,
            reports_root=REPORTS_DIR,
        )
        safe_date = validate_run_date(date)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "Artifact not found"})

    if not path.exists():
        return {
            "kind": kind,
            "date": safe_date,
            "status": "missing",
            "provenance": {
                "generated_by": "mindpattern.site_content.api",
                "redaction_status": "passed",
            },
        }

    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return JSONResponse(status_code=404, content={"error": "Artifact not found"})
    public_payload = sanitize_site_artifact(payload)
    public_payload.setdefault("kind", kind)
    public_payload.setdefault("date", safe_date)
    public_payload.setdefault("status", "unknown")
    return public_payload


@router.get("/api/site/runs/{date}")
async def get_site_run_artifact(date: str, user: str = Query("ramsay")):
    """Public: content-machine run ledger for one date."""
    return _load_site_artifact_response(kind="site_run", date=date, user=user)


@router.get("/api/site/corpus/{date}")
async def get_site_corpus_artifact(date: str, user: str = Query("ramsay")):
    """Public: content-machine corpus inventory for one date."""
    return _load_site_artifact_response(kind="site_corpus", date=date, user=user)


@router.get("/api/stories")
async def list_public_stories(
    user: str = Query("ramsay"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """Public: published Rabbit Hole stories with full pagination metadata."""
    if _safe_user(user) is None:
        return {
            "kind": "stories",
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "has_more": False,
        }

    stories = await _all_public_stories(user)
    total = len(stories)

    return {
        "kind": "stories",
        "items": stories[offset: offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }


@router.get("/api/stories/{slug}")
async def get_public_story(slug: str, user: str = Query("ramsay")):
    """Public: one published Rabbit Hole story by slug.

    AI-written site-story artifacts win when present. Source-backed structured
    newsletter story units are the dynamic fallback, so the public site can
    read the full archive without requiring hand-built JSON for every story.
    """
    if _safe_user(user) is None:
        return JSONResponse(status_code=404, content={"error": "Story not found"})
    try:
        story_slug = normalize_slug(slug)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "Story not found"})

    for path in _public_story_files(user):
        if path.stem != story_slug:
            continue
        story = _load_public_story_file(path)
        if story is not None:
            return story
    story = _story_from_structured_issue_slug(story_slug=story_slug, user=user)
    if story is not None:
        return story
    return JSONResponse(status_code=404, content={"error": "Story not found"})


@router.get("/api/entities/{slug}/neighbors")
async def get_entity_neighbors(
    slug: str,
    user: str = Query("ramsay"),
    limit: int = Query(20, ge=1, le=100),
):
    """Public: neighboring entities with evidence edges."""
    if _safe_user(user) is None:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})
    try:
        entity_slug = normalize_slug(slug)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})
    if entity_slug in _PUBLIC_ENTITY_SLUG_BLOCKLIST or len(entity_slug) < 4:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})

    opened = _open_graph_model(user)
    if opened is None:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})
    conn, model = opened
    try:
        neighbors = model.get_entity_neighbors(entity_slug, limit=limit)
        if not neighbors.get("items"):
            return JSONResponse(status_code=404, content={"error": "Entity not found"})
        return neighbors
    finally:
        conn.close()


@router.get("/api/entities/{slug}")
async def get_entity(slug: str, user: str = Query("ramsay"), limit: int = Query(20, ge=1, le=50)):
    """Public: dynamic entity page data from newsletters plus existing corpus graph."""
    if _safe_user(user) is None:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})
    try:
        entity_slug = normalize_slug(slug)
    except ValueError:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})
    if entity_slug in _PUBLIC_ENTITY_SLUG_BLOCKLIST or len(entity_slug) < 4:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})

    graph_detail: dict | None = None
    opened = _open_graph_model(user)
    if opened is not None:
        conn, model = opened
        try:
            graph_detail = model.get_entity(entity_slug, limit=limit, offset=0)
        finally:
            conn.close()

    corpus = _public_corpus_entity(user, entity_slug, limit=limit)
    story_units: list[dict] = []
    source_by_url: dict[str, dict] = {}
    issue_dates: list[str] = []
    entity_name = ""
    seen_story_ids: set[str] = set()

    for date in _structured_issue_dates(user=user):
        if date in issue_dates:
            continue
        issue = _structured_issue_from_report_file(date=date, user=user)
        if issue is None:
            continue

        entity = next(
            (item for item in issue["entities"] if item.get("slug") == entity_slug),
            None,
        )
        if entity is None:
            continue
        entity_name = entity_name or entity.get("name", "")
        issue_dates.append(date)

        for story in issue["story_units"]:
            if entity_slug not in story.get("entity_ids", []):
                continue
            if story["id"] in seen_story_ids:
                continue
            seen_story_ids.add(story["id"])
            public_story = {
                "id": story["id"],
                "slug": story["slug"],
                "issue_date": story["issue_date"],
                "issue_title": issue["title"],
                "section_id": story["section_id"],
                "title": story["title"],
                "summary": story["summary"],
                "source_refs": story["source_refs"],
                "arc_ids": story.get("arc_ids", []),
                "finding_ids": story.get("finding_ids", []),
                "target_url": f"/briefings/{story['issue_date']}",
            }
            story_units.append(public_story)
            for source in story["source_refs"]:
                source_by_url.setdefault(source["url"], source)
            if len(story_units) >= limit:
                break
        if len(story_units) >= limit:
            break

    if graph_detail:
        for source in graph_detail.get("source_trail", []):
            source_by_url.setdefault(source["url"], source)
    for source in corpus["source_trail"]:
        source_by_url.setdefault(source["url"], source)

    graph_findings = graph_detail.get("findings", []) if graph_detail else []
    graph_relationships = graph_detail.get("relationships", []) if graph_detail else []
    graph_counts = graph_detail.get("counts", {}) if graph_detail else {}
    graph_pagination = graph_detail.get("pagination", {}) if graph_detail else {}
    graph_sources_from_model = graph_detail.get("graph_sources", []) if graph_detail else []

    findings_by_id: dict[int, dict] = {}
    for finding in graph_findings + corpus["findings"]:
        finding_id = finding.get("id")
        if finding_id is None:
            continue
        findings_by_id.setdefault(int(finding_id), finding)
    merged_findings = list(findings_by_id.values())[:limit]

    relationship_keys: set[tuple] = set()
    merged_relationships: list[dict] = []
    for relationship in graph_relationships + corpus["relationships"]:
        key = (
            relationship.get("source"),
            relationship.get("relationship"),
            relationship.get("finding_id"),
            relationship.get("related_entity")
            or relationship.get("entity_b")
            or relationship.get("entity_a"),
        )
        if key in relationship_keys:
            continue
        relationship_keys.add(key)
        merged_relationships.append(relationship)

    if not story_units and not merged_findings and not merged_relationships and not corpus["kg_entities"]:
        return JSONResponse(status_code=404, content={"error": "Entity not found"})

    graph_sources = sorted({"newsletter_issues"} if story_units else set())
    graph_sources = sorted(set(graph_sources) | set(corpus["graph_sources"]) | set(graph_sources_from_model))
    source_trail = list(source_by_url.values())
    counts = {
        "story_units": len(story_units),
        "findings": max(len(merged_findings), int(graph_counts.get("findings") or 0)),
        "relationships": max(len(merged_relationships), int(graph_counts.get("relationships") or 0)),
        "sources": max(len(source_trail), int(graph_counts.get("sources") or 0)),
    }

    return {
        "kind": "entity",
        "slug": entity_slug,
        "name": entity_name
        or (graph_detail or {}).get("name")
        or corpus["name"]
        or entity_slug.replace("-", " ").title(),
        "user": user,
        "status": "ready",
        "confidence": "source-backed" if story_units or source_trail else "corpus-backed",
        "counts": counts,
        "pagination": {
            "limit": int(graph_pagination.get("limit") or limit),
            "offset": int(graph_pagination.get("offset") or 0),
            "has_more": bool(graph_pagination.get("has_more")),
        },
        "story_units": story_units,
        "findings": merged_findings,
        "relationships": merged_relationships,
        "kg_entities": corpus["kg_entities"],
        "source_trail": source_trail,
        "issue_dates": issue_dates,
        "graph_sources": graph_sources,
        "total": len(story_units) + len(merged_findings) + len(merged_relationships),
        "limit": limit,
        "provenance": {
            "generated_by": "mindpattern.site_content.entity_reader+corpus_graph",
            "source_issue_dates": issue_dates,
            "graph_sources": graph_sources,
            "redaction_status": "passed",
            "ai_generated": False,
        },
    }


@router.get("/api/reports/{date}")
async def get_report(date: str, user: str = Query("ramsay")):
    """Public: get a single newsletter report by date."""
    # date becomes a glob and user a path part — validate both (audit:
    # path traversal via date=../../..)
    if _valid_date(date) is None or _safe_user(user) is None:
        return None
    reports_dir = REPORTS_DIR / user
    if not reports_dir.exists():
        return None

    target = _report_file_for_date(date=date, user=user)
    if target is None:
        return None

    text = _clean_report_markdown(target.read_text(errors="replace"))
    if not _is_public_report_content(text):
        return None
    title = _report_title_from_content(content=text, date=date, fallback_name=target.stem)

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
    """Public: health check.

    On Fly (FLY_APP_NAME set) a stale bot heartbeat returns 503 so the
    failing health check restarts the machine — a dead Socket Mode
    connection must not look healthy (M0 task 12).
    """
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

    bot_stale = bot_heartbeat_stale()
    body = {
        "status": "ok" if db_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "database": "connected" if db_ok else "unavailable",
        "bot": "stale" if bot_stale else "alive",
    }

    if bot_stale and os.environ.get("FLY_APP_NAME"):
        body["status"] = "bot-dead"
        return JSONResponse(status_code=503, content=body)

    return body


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

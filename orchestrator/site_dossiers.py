"""Entity and source dossier artifacts for the Rabbit Hole public site.

Evidence-only builders over the corpus read model: a dossier is a curated,
public-safe snapshot (profile, timeline, sources, relationships) written as a
``site-dossiers/...`` artifact. An optional agent-written "take" can be layered
on later; the evidence core is deterministic so dossiers never fabricate graph
data. Fails open — dossier problems must never block the newsletter pipeline.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from orchestrator.media_contracts import redact_sensitive_text, validate_run_date
from orchestrator.site_content import _is_entity_candidate, normalize_slug, write_site_artifact
from orchestrator.site_graph import CorpusGraphReadModel

DEFAULT_ENTITY_DOSSIER_LIMIT = 25
DEFAULT_SOURCE_DOSSIER_LIMIT = 15


def build_entity_dossier(
    model: CorpusGraphReadModel,
    slug: str,
    *,
    date: str,
    user: str,
) -> dict[str, Any] | None:
    """Build one public entity dossier from corpus evidence. None if empty."""
    entity_slug = normalize_slug(slug)
    entity = model.get_entity(entity_slug, limit=40)
    findings = list(entity.get("findings") or [])
    if not findings:
        return None

    timeline: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        run_date = str(finding.get("run_date") or "")
        if not run_date:
            continue
        timeline.setdefault(run_date, []).append({
            "finding_id": finding.get("id"),
            "title": finding.get("title", ""),
            "source_url": finding.get("source_url", ""),
            "source_name": finding.get("source_name", ""),
            "target_url": finding.get("target_url") or f"/f/{finding.get('id')}",
        })
    timeline_entries = [
        {"date": run_date, "items": items[:5]}
        for run_date, items in sorted(timeline.items(), reverse=True)
    ][:30]

    source_counts: dict[str, int] = {}
    for finding in findings:
        domain = str(finding.get("source_url") or "")
        domain = domain.split("/")[2] if domain.startswith("http") and len(domain.split("/")) > 2 else ""
        if domain:
            source_counts[domain] = source_counts.get(domain, 0) + 1
    top_sources = [
        {"domain": domain, "finding_count": count, "target_url": f"/source/{domain}"}
        for domain, count in sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    ]

    return {
        "kind": "entity_dossier",
        "slug": entity_slug,
        "name": entity.get("name") or entity_slug.replace("-", " ").title(),
        "entity_kind": entity.get("entity_kind") or entity.get("kind") or "unknown",
        "date": date,
        "status": "published",
        "confidence": "source-backed",
        "summary": redact_sensitive_text(str(entity.get("summary") or "")),
        "take": "",
        "counts": {
            "findings": int(entity.get("total") or len(findings)),
            "relationships": len(entity.get("relationships") or []),
            "sources": len(top_sources),
        },
        "timeline": timeline_entries,
        "top_sources": top_sources,
        "relationships": (entity.get("relationships") or [])[:20],
        "target_url": f"/e/{entity_slug}",
        "json_ld_ready": True,
        "provenance": {
            "generated_by": "mindpattern.site_dossiers.entity_builder",
            "provider": "deterministic",
            "graph_sources": sorted(entity.get("graph_sources") or []),
            "redaction_status": "passed",
        },
    }


def build_source_dossier(
    model: CorpusGraphReadModel,
    domain: str,
    *,
    date: str,
    user: str,
) -> dict[str, Any] | None:
    """Build one public source dossier from corpus evidence. None if empty."""
    source = model.get_source(domain, limit=40)
    findings = list(source.get("findings") or [])
    if not findings:
        return None

    return {
        "kind": "source_dossier",
        "slug": normalize_slug(domain.replace(".", "-")),
        "domain": domain,
        "name": source.get("display_name") or domain,
        "date": date,
        "status": "published",
        "confidence": "source-backed",
        "take": "",
        "counts": dict(source.get("counts") or {}),
        "recent_findings": [
            {
                "finding_id": finding.get("id"),
                "run_date": finding.get("run_date", ""),
                "title": finding.get("title", ""),
                "target_url": finding.get("target_url") or f"/f/{finding.get('id')}",
            }
            for finding in findings[:20]
        ],
        "entities": (source.get("entities") or [])[:20],
        "target_url": f"/source/{domain}",
        "json_ld_ready": True,
        "provenance": {
            "generated_by": "mindpattern.site_dossiers.source_builder",
            "provider": "deterministic",
            "redaction_status": "passed",
        },
    }


def _is_dossier_entity(slug: str, name: str) -> bool:
    """Only real named entities get dossiers — never slugified sentences."""
    if not slug or len(slug) > 48 or slug == "unknown":
        return False
    if len(slug.split("-")) > 5:
        return False
    return _is_entity_candidate(name or slug.replace("-", " ").title())


def _top_entity_slugs(conn: sqlite3.Connection, model: CorpusGraphReadModel, *, limit: int) -> list[str]:
    listing = model.list_entities(limit=limit * 3)
    slugs = []
    for item in listing.get("items") or []:
        slug = str(item.get("slug") or "")
        if _is_dossier_entity(slug, str(item.get("name") or "")):
            slugs.append(slug)
        if len(slugs) >= limit:
            break
    return slugs


def _top_source_domains(conn: sqlite3.Connection, *, limit: int) -> list[str]:
    try:
        rows = conn.execute(
            """
            SELECT url_domain FROM sources
            WHERE COALESCE(url_domain, '') != ''
            ORDER BY hit_count DESC, url_domain ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row["url_domain"]) for row in rows]


def run_dossier_generation(
    conn: sqlite3.Connection,
    *,
    date: str,
    user: str,
    reports_root: Path,
    entity_limit: int = DEFAULT_ENTITY_DOSSIER_LIMIT,
    source_limit: int = DEFAULT_SOURCE_DOSSIER_LIMIT,
) -> dict[str, Any]:
    """Write dossier artifacts for the highest-signal entities and sources."""
    run_date = validate_run_date(date)
    model = CorpusGraphReadModel(conn)
    written: list[str] = []
    skipped = 0

    for slug in _top_entity_slugs(conn, model, limit=entity_limit):
        try:
            dossier = build_entity_dossier(model, slug, date=run_date, user=user)
        except ValueError:
            skipped += 1
            continue
        if dossier is None:
            skipped += 1
            continue
        path = write_site_artifact(
            kind="entity_dossier",
            user=user,
            reports_root=reports_root,
            slug=dossier["slug"],
            artifact=dossier,
        )
        written.append(str(path))

    for domain in _top_source_domains(conn, limit=source_limit):
        try:
            dossier = build_source_dossier(model, domain, date=run_date, user=user)
        except ValueError:
            skipped += 1
            continue
        if dossier is None:
            skipped += 1
            continue
        path = write_site_artifact(
            kind="source_dossier",
            user=user,
            reports_root=reports_root,
            slug=dossier["slug"],
            artifact=dossier,
        )
        written.append(str(path))

    return {
        "kind": "dossier_run",
        "date": run_date,
        "user": user,
        "written": len(written),
        "skipped": skipped,
        "artifacts": written,
    }

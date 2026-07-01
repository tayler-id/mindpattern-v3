"""Public-safe corpus graph read model for Rabbit Hole.

This module centralizes read-only access to the existing MindPattern corpus so
API routes and content-machine graph packs do not duplicate ad hoc SQL.
"""

from __future__ import annotations

import re
import sqlite3
import struct
from typing import Any
from urllib.parse import urlparse

from orchestrator.media_contracts import redact_sensitive_text, validate_run_date
from orchestrator.site_content import normalize_slug

_RELATED_STOPWORDS = {
    "about",
    "after",
    "again",
    "agent",
    "agents",
    "also",
    "and",
    "are",
    "because",
    "briefing",
    "but",
    "can",
    "from",
    "into",
    "its",
    "new",
    "newsletter",
    "not",
    "now",
    "section",
    "source",
    "stories",
    "story",
    "that",
    "the",
    "this",
    "today",
    "top",
    "using",
    "with",
    "your",
}
_URL_RE = re.compile(r"https?://\S+")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#._-]{2,}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _safe_slug(value: Any) -> str:
    try:
        return normalize_slug(str(value or ""))
    except ValueError:
        return "unknown"


def _source_domain(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.netloc.lower().removeprefix("www.")


def _source_ref_from_finding(finding: dict[str, Any]) -> dict[str, str] | None:
    url = redact_sensitive_text(str(finding.get("source_url") or ""))
    domain = _source_domain(url)
    if not url.startswith(("http://", "https://")) or not domain:
        return None
    return {
        "url": url,
        "domain": domain,
        "title": redact_sensitive_text(str(finding.get("source_name") or domain)),
    }


def _public_finding(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    finding_id = int(data["id"])
    run_date = str(data.get("run_date") or "")
    try:
        run_date = validate_run_date(run_date)
    except ValueError:
        run_date = ""
    public = {
        "kind": "finding",
        "id": finding_id,
        "run_date": run_date,
        "agent": redact_sensitive_text(data.get("agent") or ""),
        "title": redact_sensitive_text(data.get("title") or ""),
        "summary": redact_sensitive_text(data.get("summary") or ""),
        "importance": redact_sensitive_text(data.get("importance") or ""),
        "category": redact_sensitive_text(data.get("category") or ""),
        "source_url": redact_sensitive_text(data.get("source_url") or ""),
        "source_name": redact_sensitive_text(data.get("source_name") or ""),
        "created_at": redact_sensitive_text(data.get("created_at") or ""),
        "target_url": f"/f/{finding_id}",
    }
    source_ref = _source_ref_from_finding(public)
    public["source_refs"] = [source_ref] if source_ref else []
    return public


def _entity_ref(name: str, kind: str = "unknown", **extra: Any) -> dict[str, Any]:
    slug = _safe_slug(name)
    ref = {
        "id": slug,
        "slug": slug,
        "name": redact_sensitive_text(name),
        "kind": redact_sensitive_text(kind or "unknown"),
        "target_url": f"/e/{slug}",
    }
    for key, value in extra.items():
        if value not in (None, ""):
            ref[key] = value
    return ref


def _signal_tokens(text: str) -> set[str]:
    """Return reader-meaningful topic tokens, excluding URLs and generic labels."""
    cleaned = _URL_RE.sub(" ", text.lower())
    tokens = set()
    for token in _TOKEN_RE.findall(cleaned):
        token = token.strip("._-")
        if not token or token in _RELATED_STOPWORDS:
            continue
        if "." in token:
            continue
        tokens.add(token)
    return tokens


def _deserialize_embedding(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _dot_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _connector_label(kind: str) -> str:
    labels = {
        "shared_entity": "Shared entity",
        "same_source_domain": "Same source domain",
        "same_source_url": "Same source URL",
        "semantic_neighbor": "Semantic neighbor",
        "same_arc": "Same arc",
        "shared_topic": "Shared topic",
        "same_research_window": "Same research window",
        "policy_dependency": "Policy dependency",
        "stack_layer": "Stack layer",
        "threat_pattern": "Threat pattern",
        "actor_role": "Actor role",
        "contrast": "Contrast",
        "update": "Update thread",
        "recurring_source_cluster": "Recurring source cluster",
        "followup_thread": "Follow-up thread",
        "newsletter_context": "Newsletter context",
    }
    return labels.get(kind, kind.replace("_", " ").title())


def _connector(kind: str, *, detail: str, weight: float, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": _connector_label(kind),
        "detail": redact_sensitive_text(detail),
        "weight": round(weight, 4),
        "evidence": evidence,
    }


class CorpusGraphReadModel:
    """Read-only public graph projection over a MindPattern memory DB."""

    def __init__(self, conn: sqlite3.Connection, *, arc_memberships: dict[int, set[str]] | None = None):
        self.conn = conn
        self.arc_memberships = arc_memberships or {}

    def list_entities(self, *, q: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
        graph_sources: set[str] = set()
        degraded_reasons: list[str] = []
        entities: dict[str, dict[str, Any]] = {}
        query_slug = _safe_slug(q) if q else ""
        query_like = f"%{q.lower()}%" if q else "%"

        if _table_exists(self.conn, "kg_entities"):
            graph_sources.add("kg_entities")
            rows = self.conn.execute(
                """
                SELECT canonical_name, entity_type, mention_count, importance,
                       first_seen, last_seen
                FROM kg_entities
                WHERE lower(canonical_name) LIKE ?
                ORDER BY importance DESC, mention_count DESC, canonical_name ASC
                """,
                (query_like,),
            ).fetchall()
            for row in rows:
                slug = _safe_slug(row["canonical_name"])
                if query_slug and query_slug not in slug:
                    continue
                entities[slug] = _entity_ref(
                    row["canonical_name"],
                    row["entity_type"] or "unknown",
                    mention_count=int(row["mention_count"] or 0),
                    importance=float(row["importance"] or 0.0),
                    first_seen=redact_sensitive_text(row["first_seen"] or ""),
                    last_seen=redact_sensitive_text(row["last_seen"] or ""),
                    graph_sources=["kg_entities"],
                )
        else:
            degraded_reasons.append("missing table: kg_entities")

        if _table_exists(self.conn, "entity_graph"):
            graph_sources.add("entity_graph")
            rows = self.conn.execute(
                """
                SELECT entity_a, entity_a_type, entity_b, entity_b_type, COUNT(*) AS mention_count
                FROM (
                    SELECT entity_a, entity_a_type, entity_b, entity_b_type FROM entity_graph
                    UNION ALL
                    SELECT entity_b AS entity_a, entity_b_type AS entity_a_type,
                           entity_a AS entity_b, entity_a_type AS entity_b_type FROM entity_graph
                )
                WHERE lower(entity_a) LIKE ?
                GROUP BY entity_a, entity_a_type, entity_b, entity_b_type
                """,
                (query_like,),
            ).fetchall()
            for row in rows:
                slug = _safe_slug(row["entity_a"])
                if query_slug and query_slug not in slug:
                    continue
                existing = entities.get(slug)
                if existing:
                    existing["mention_count"] = max(
                        int(existing.get("mention_count") or 0),
                        int(row["mention_count"] or 0),
                    )
                    existing["graph_sources"] = sorted(set(existing.get("graph_sources", [])) | {"entity_graph"})
                    continue
                entities[slug] = _entity_ref(
                    row["entity_a"],
                    row["entity_a_type"] or "unknown",
                    mention_count=int(row["mention_count"] or 0),
                    importance=0.0,
                    graph_sources=["entity_graph"],
                )
        else:
            degraded_reasons.append("missing table: entity_graph")

        items = sorted(
            entities.values(),
            key=lambda item: (
                -float(item.get("importance") or 0.0),
                -int(item.get("mention_count") or 0),
                item["name"].lower(),
            ),
        )
        total = len(items)
        page = items[offset: offset + limit]
        return {
            "kind": "entities",
            "status": "ready" if graph_sources else "degraded",
            "items": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
            "graph_sources": sorted(graph_sources),
            "degraded_reasons": degraded_reasons,
        }

    def get_entity(self, slug: str, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        entity_slug = normalize_slug(slug)
        graph_sources: set[str] = set()
        entity_name = entity_slug.replace("-", " ").title()
        relationships: list[dict[str, Any]] = []
        finding_ids: set[int] = set()
        kg_entity_ids: set[int] = set()

        if _table_exists(self.conn, "kg_entities"):
            graph_sources.add("kg_entities")
            rows = self.conn.execute(
                """
                SELECT id, canonical_name, entity_type, mention_count, importance,
                       first_seen, last_seen
                FROM kg_entities
                WHERE lower(replace(canonical_name, ' ', '-')) = ?
                """,
                (entity_slug,),
            ).fetchall()
            for row in rows:
                kg_entity_ids.add(int(row["id"]))
                entity_name = redact_sensitive_text(row["canonical_name"] or entity_name)

        if kg_entity_ids and _table_exists(self.conn, "kg_edges"):
            graph_sources.add("kg_edges")
            for entity_id in kg_entity_ids:
                rows = self.conn.execute(
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
                    LIMIT 100
                    """,
                    (entity_id, entity_id),
                ).fetchall()
                for row in rows:
                    finding_id = row["finding_id"]
                    if finding_id is not None:
                        finding_ids.add(int(finding_id))
                    relationships.append({
                        "source": "kg_edges",
                        "relationship": redact_sensitive_text(row["predicate"] or ""),
                        "entity_a": redact_sensitive_text(row["subject_name"] or ""),
                        "entity_a_type": redact_sensitive_text(row["subject_type"] or ""),
                        "entity_b": redact_sensitive_text(row["object_name"] or ""),
                        "entity_b_type": redact_sensitive_text(row["object_type"] or ""),
                        "fact_text": redact_sensitive_text(row["fact_text"] or ""),
                        "fact_type": redact_sensitive_text(row["fact_type"] or "Fact"),
                        "confidence": float(row["confidence"] or 0.0),
                        "finding_id": int(finding_id) if finding_id is not None else None,
                        "target_url": f"/f/{finding_id}" if finding_id is not None else "",
                        "evidence_edges": [{
                            "kind": "kg_edge",
                            "relationship": redact_sensitive_text(row["predicate"] or ""),
                            "id": str(row["id"]),
                            "target_url": f"/f/{finding_id}" if finding_id is not None else "",
                        }],
                    })

        if _table_exists(self.conn, "entity_graph"):
            graph_sources.add("entity_graph")
            rows = self.conn.execute(
                """
                SELECT id, entity_a, entity_a_type, relationship, entity_b, entity_b_type,
                       finding_id, created_at
                FROM entity_graph
                WHERE lower(replace(entity_a, ' ', '-')) = ?
                   OR lower(replace(entity_b, ' ', '-')) = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 100
                """,
                (entity_slug, entity_slug),
            ).fetchall()
            for row in rows:
                matched_a = _safe_slug(row["entity_a"]) == entity_slug
                entity_name = redact_sensitive_text(row["entity_a"] if matched_a else row["entity_b"])
                related_name = redact_sensitive_text(row["entity_b"] if matched_a else row["entity_a"])
                finding_id = row["finding_id"]
                if finding_id is not None:
                    finding_ids.add(int(finding_id))
                relationships.append({
                    "source": "entity_graph",
                    "relationship": redact_sensitive_text(row["relationship"] or ""),
                    "related_entity": related_name,
                    "related_entity_slug": _safe_slug(related_name),
                    "related_entity_type": redact_sensitive_text(
                        row["entity_b_type"] if matched_a else row["entity_a_type"] or ""
                    ),
                    "finding_id": int(finding_id) if finding_id is not None else None,
                    "target_url": f"/f/{finding_id}" if finding_id is not None else "",
                    "created_at": redact_sensitive_text(row["created_at"] or ""),
                    "evidence_edges": [{
                        "kind": "entity_graph",
                        "relationship": redact_sensitive_text(row["relationship"] or ""),
                        "id": str(row["id"]),
                        "target_url": f"/f/{finding_id}" if finding_id is not None else "",
                    }],
                })

        findings = self._findings_for_entity(entity_slug, finding_ids=finding_ids, limit=limit, offset=offset)
        source_by_url: dict[str, dict[str, str]] = {}
        for finding in findings:
            for source in finding.get("source_refs", []):
                source_by_url[source["url"]] = source
        return {
            "kind": "entity",
            "slug": entity_slug,
            "name": entity_name,
            "status": "ready" if graph_sources or findings else "missing",
            "counts": {
                "findings": len(findings),
                "relationships": len(relationships),
                "sources": len(source_by_url),
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": len(findings) == limit,
            },
            "findings": findings,
            "relationships": relationships,
            "source_trail": list(source_by_url.values()),
            "graph_sources": sorted(graph_sources | ({"findings_text"} if findings else set())),
            "provenance": {
                "generated_by": "mindpattern.site_graph.read_model",
                "redaction_status": "passed",
            },
        }

    def get_entity_neighbors(self, slug: str, *, limit: int = 20) -> dict[str, Any]:
        detail = self.get_entity(slug, limit=limit, offset=0)
        neighbors: dict[str, dict[str, Any]] = {}
        for relationship in detail["relationships"]:
            name = relationship.get("related_entity") or relationship.get("entity_b")
            if not name:
                continue
            ref = _entity_ref(str(name), str(relationship.get("related_entity_type") or "unknown"))
            ref["relationship"] = relationship.get("relationship", "")
            ref["evidence_edges"] = relationship.get("evidence_edges", [])
            neighbors[ref["slug"]] = ref
        items = list(neighbors.values())[:limit]
        return {
            "kind": "entity_neighbors",
            "entity_slug": normalize_slug(slug),
            "items": items,
            "total": len(items),
            "limit": limit,
        }

    def get_source(self, domain: str, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        safe_domain = domain.lower().removeprefix("www.")
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", safe_domain):
            return {"kind": "source", "status": "missing", "domain": safe_domain, "findings": [], "entities": []}

        source = {
            "kind": "source",
            "domain": safe_domain,
            "display_name": safe_domain,
            "status": "ready",
            "counts": {"findings": 0, "entities": 0},
            "findings": [],
            "entities": [],
            "pagination": {"limit": limit, "offset": offset, "has_more": False},
            "provenance": {"generated_by": "mindpattern.site_graph.read_model", "redaction_status": "passed"},
        }
        if _table_exists(self.conn, "sources"):
            row = self.conn.execute(
                """
                SELECT url_domain, display_name, hit_count, high_value_count, last_seen, created_at
                FROM sources
                WHERE lower(replace(url_domain, 'www.', '')) = ?
                """,
                (safe_domain,),
            ).fetchone()
            if row is not None:
                source.update({
                    "display_name": redact_sensitive_text(row["display_name"] or safe_domain),
                    "hit_count": int(row["hit_count"] or 0),
                    "high_value_count": int(row["high_value_count"] or 0),
                    "last_seen": redact_sensitive_text(row["last_seen"] or ""),
                    "created_at": redact_sensitive_text(row["created_at"] or ""),
                })
        if _table_exists(self.conn, "findings"):
            rows = self.conn.execute(
                """
                SELECT id, run_date, agent, title, summary, importance, category,
                       source_url, source_name, created_at
                FROM findings
                WHERE lower(source_url) LIKE ?
                ORDER BY run_date DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                (f"%{safe_domain}%", limit, offset),
            ).fetchall()
            findings = [_public_finding(row) for row in rows]
            source["findings"] = findings
            source["counts"]["findings"] = len(findings)
            source["pagination"]["has_more"] = len(findings) == limit
            entity_refs: dict[str, dict[str, Any]] = {}
            for finding in findings:
                for entity in self._entities_for_finding(finding["id"]):
                    entity_refs[entity["slug"]] = entity
            source["entities"] = list(entity_refs.values())
            source["counts"]["entities"] = len(entity_refs)
        return source

    def get_finding(self, finding_id: int) -> dict[str, Any] | None:
        if not _table_exists(self.conn, "findings"):
            return None
        row = self.conn.execute(
            """
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE id = ?
            """,
            (finding_id,),
        ).fetchone()
        if row is None:
            return None
        finding = _public_finding(row)
        finding["entities"] = self._entities_for_finding(finding_id)
        finding["provenance"] = {
            "generated_by": "mindpattern.site_graph.read_model",
            "redaction_status": "passed",
        }
        return finding

    def get_related_paths_for_finding(self, finding_id: int, *, limit: int = 10) -> dict[str, Any] | None:
        """Return evidence-backed related findings with reader-facing connectors."""
        source = self.get_finding(finding_id)
        if source is None:
            return None

        source_entities = {entity["slug"]: entity for entity in source.get("entities", [])}
        source_urls = {ref["url"] for ref in source.get("source_refs", []) if ref.get("url")}
        source_domains = {ref["domain"] for ref in source.get("source_refs", []) if ref.get("domain")}
        source_arcs = self.arc_memberships.get(finding_id, set())
        source_tokens = _signal_tokens(
            " ".join(
                [
                    source.get("title", ""),
                    source.get("summary", ""),
                    source.get("category", ""),
                ]
            )
        )
        source_embedding = self._embedding_for_finding(finding_id)

        if not _table_exists(self.conn, "findings"):
            return {
                "kind": "related",
                "finding_id": finding_id,
                "mode": "blended",
                "items": [],
                "total": 0,
            }

        rows = self.conn.execute(
            """
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE id != ?
            ORDER BY run_date DESC, created_at DESC
            LIMIT 300
            """,
            (finding_id,),
        ).fetchall()

        related: list[dict[str, Any]] = []
        for row in rows:
            target = _public_finding(row)
            target_entities = {entity["slug"]: entity for entity in self._entities_for_finding(target["id"])}
            target_urls = {ref["url"] for ref in target.get("source_refs", []) if ref.get("url")}
            target_domains = {ref["domain"] for ref in target.get("source_refs", []) if ref.get("domain")}
            target_arcs = self.arc_memberships.get(target["id"], set())
            target_tokens = _signal_tokens(
                " ".join([target.get("title", ""), target.get("summary", ""), target.get("category", "")])
            )
            connectors: list[dict[str, Any]] = []

            shared_entities = sorted(set(source_entities) & set(target_entities))
            if shared_entities:
                names = [
                    target_entities[slug].get("name") or source_entities[slug].get("name") or slug
                    for slug in shared_entities[:3]
                ]
                connectors.append(
                    _connector(
                        "shared_entity",
                        detail=", ".join(names),
                        weight=0.32,
                        evidence=[
                            {
                                "kind": "entity",
                                "id": slug,
                                "target_url": f"/e/{slug}",
                            }
                            for slug in shared_entities[:3]
                        ],
                    )
                )

            shared_urls = sorted(source_urls & target_urls)
            if shared_urls:
                connectors.append(
                    _connector(
                        "same_source_url",
                        detail=shared_urls[0],
                        weight=0.2,
                        evidence=[
                            {
                                "kind": "source_url",
                                "url": shared_urls[0],
                            }
                        ],
                    )
                )

            shared_domains = sorted(source_domains & target_domains)
            if shared_domains:
                connectors.append(
                    _connector(
                        "same_source_domain",
                        detail=", ".join(shared_domains[:2]),
                        weight=0.18,
                        evidence=[
                            {
                                "kind": "source_domain",
                                "domain": domain,
                                "target_url": f"/source/{domain}",
                            }
                            for domain in shared_domains[:2]
                        ],
                    )
                )

            shared_arcs = sorted(source_arcs & target_arcs)
            if shared_arcs:
                connectors.append(
                    _connector(
                        "same_arc",
                        detail=", ".join(shared_arcs[:2]),
                        weight=0.22,
                        evidence=[
                            {
                                "kind": "narrative_arc",
                                "id": arc_id,
                                "target_url": f"/arcs/{arc_id}",
                            }
                            for arc_id in shared_arcs[:2]
                        ],
                    )
                )

            target_embedding = self._embedding_for_finding(target["id"])
            similarity = _dot_similarity(source_embedding, target_embedding)
            if similarity >= 0.45:
                connectors.append(
                    _connector(
                        "semantic_neighbor",
                        detail=f"stored embedding similarity {similarity:.2f}",
                        weight=min(0.25, max(0.0, similarity) * 0.25),
                        evidence=[
                            {
                                "kind": "embedding",
                                "similarity": round(similarity, 4),
                            }
                        ],
                    )
                )

            shared_tokens = sorted(source_tokens & target_tokens)
            if len(shared_tokens) >= 2:
                connectors.append(
                    _connector(
                        "shared_topic",
                        detail=", ".join(shared_tokens[:4]),
                        weight=0.14,
                        evidence=[
                            {
                                "kind": "topic_term",
                                "term": term,
                            }
                            for term in shared_tokens[:4]
                        ],
                    )
                )

            if source.get("run_date") and source.get("run_date") == target.get("run_date"):
                connectors.append(
                    _connector(
                        "newsletter_context",
                        detail=source["run_date"],
                        weight=0.05,
                        evidence=[{"kind": "run_date", "date": source["run_date"]}],
                    )
                )
            elif source.get("run_date") and target.get("run_date"):
                connectors.append(
                    _connector(
                        "same_research_window",
                        detail=f"{target['run_date']} near {source['run_date']}",
                        weight=0.03,
                        evidence=[{"kind": "run_date", "date": target["run_date"]}],
                    )
                )

            connector_text = " ".join(sorted(source_tokens | target_tokens))
            if {"policy", "commerce", "regulation", "export", "dependency"} & set(connector_text.split()):
                connectors.append(
                    _connector(
                        "policy_dependency",
                        detail="policy or regulatory dependency appears in the evidence",
                        weight=0.08,
                        evidence=[{"kind": "text_signal", "signal": "policy"}],
                    )
                )
            if {"runtime", "stack", "infrastructure", "model", "code"} & set(connector_text.split()):
                connectors.append(
                    _connector(
                        "stack_layer",
                        detail="both findings touch the same technical stack layer",
                        weight=0.08,
                        evidence=[{"kind": "text_signal", "signal": "stack_layer"}],
                    )
                )
            if {"cve", "ransomware", "leak", "security", "threat"} & set(connector_text.split()):
                connectors.append(
                    _connector(
                        "threat_pattern",
                        detail="both findings carry security or threat language",
                        weight=0.08,
                        evidence=[{"kind": "text_signal", "signal": "threat"}],
                    )
                )
            if shared_entities and {"released", "pushed", "shipped", "positioned", "made"} & set(
                connector_text.split()
            ):
                connectors.append(
                    _connector(
                        "actor_role",
                        detail="named actors appear in comparable roles",
                        weight=0.06,
                        evidence=[{"kind": "entity_role", "entities": shared_entities[:3]}],
                    )
                )
            if {"versus", "against", "contrast", "competes"} & set(connector_text.split()):
                connectors.append(
                    _connector(
                        "contrast",
                        detail="comparison or competitive framing appears in the evidence",
                        weight=0.05,
                        evidence=[{"kind": "text_signal", "signal": "contrast"}],
                    )
                )
            if {"update", "released", "ship", "shipped", "widens", "changes"} & set(connector_text.split()):
                connectors.append(
                    _connector(
                        "update",
                        detail="both findings read as part of an update thread",
                        weight=0.05,
                        evidence=[{"kind": "text_signal", "signal": "update"}],
                    )
                )
            if len(shared_domains) > 0 and len(shared_entities) > 0:
                connectors.append(
                    _connector(
                        "recurring_source_cluster",
                        detail="same source cluster reinforces an entity connection",
                        weight=0.05,
                        evidence=[{"kind": "source_domain", "domain": shared_domains[0]}],
                    )
                )
            if {"follow", "followup", "deeper", "research"} & set(connector_text.split()):
                connectors.append(
                    _connector(
                        "followup_thread",
                        detail="follow-up research language appears in the evidence",
                        weight=0.04,
                        evidence=[{"kind": "text_signal", "signal": "followup"}],
                    )
                )

            if not connectors:
                continue

            score = round(sum(connector["weight"] for connector in connectors), 4)
            target.update(
                {
                    "score": score,
                    "similarity": round(max(0.0, similarity), 4),
                    "mode": "blended",
                    "relationship": "multi_connector",
                    "connectors": connectors,
                    "connector_labels": [connector["label"] for connector in connectors],
                    "reason": self._related_reason(connectors),
                    "entities": list(target_entities.values()),
                }
            )
            related.append(target)

        related.sort(key=lambda item: (-item["score"], -item.get("similarity", 0.0), item["id"]))
        items = related[:limit]
        return {
            "kind": "related",
            "finding_id": finding_id,
            "mode": "blended",
            "items": items,
            "total": len(items),
        }

    def _embedding_for_finding(self, finding_id: int) -> list[float]:
        if not _table_exists(self.conn, "findings_embeddings"):
            return []
        row = self.conn.execute(
            "SELECT embedding FROM findings_embeddings WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        if row is None:
            return []
        return _deserialize_embedding(row["embedding"])

    @staticmethod
    def _related_reason(connectors: list[dict[str, Any]]) -> str:
        labels = [connector["label"] for connector in connectors[:3]]
        if not labels:
            return "Related by corpus graph evidence."
        if len(labels) == 1:
            return f"Related by {labels[0].lower()}."
        return "Related by " + ", ".join(label.lower() for label in labels[:-1]) + f", and {labels[-1].lower()}."

    def _findings_for_entity(
        self,
        entity_slug: str,
        *,
        finding_ids: set[int],
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        if not _table_exists(self.conn, "findings"):
            return []
        findings_by_id: dict[int, dict[str, Any]] = {}
        if finding_ids:
            placeholders = ",".join("?" for _ in finding_ids)
            rows = self.conn.execute(
                f"""
                SELECT id, run_date, agent, title, summary, importance, category,
                       source_url, source_name, created_at
                FROM findings
                WHERE id IN ({placeholders})
                ORDER BY run_date DESC, created_at DESC
                """,
                tuple(finding_ids),
            ).fetchall()
            for row in rows:
                findings_by_id[int(row["id"])] = _public_finding(row)

        pattern = "%" + "%".join(entity_slug.split("-")) + "%"
        rows = self.conn.execute(
            """
            SELECT id, run_date, agent, title, summary, importance, category,
                   source_url, source_name, created_at
            FROM findings
            WHERE lower(title || ' ' || COALESCE(summary, '')) LIKE ?
            ORDER BY run_date DESC, created_at DESC
            LIMIT ?
            """,
            (pattern, offset + limit),
        ).fetchall()
        for row in rows:
            findings_by_id.setdefault(int(row["id"]), _public_finding(row))

        ordered = sorted(
            findings_by_id.values(),
            key=lambda item: (item.get("run_date", ""), item.get("created_at", ""), item["id"]),
            reverse=True,
        )
        return ordered[offset: offset + limit]

    def _entities_for_finding(self, finding_id: int) -> list[dict[str, Any]]:
        entities: dict[str, dict[str, Any]] = {}
        if _table_exists(self.conn, "entity_graph"):
            rows = self.conn.execute(
                """
                SELECT entity_a, entity_a_type, entity_b, entity_b_type
                FROM entity_graph
                WHERE finding_id = ?
                """,
                (finding_id,),
            ).fetchall()
            for row in rows:
                for name_key, type_key in (("entity_a", "entity_a_type"), ("entity_b", "entity_b_type")):
                    ref = _entity_ref(row[name_key], row[type_key] or "unknown")
                    entities[ref["slug"]] = ref
        if _table_exists(self.conn, "kg_edges") and _table_exists(self.conn, "kg_entities"):
            rows = self.conn.execute(
                """
                SELECT subject.canonical_name AS subject_name, subject.entity_type AS subject_type,
                       object.canonical_name AS object_name, object.entity_type AS object_type
                FROM kg_edges edge
                JOIN kg_entities subject ON subject.id = edge.subject_id
                JOIN kg_entities object ON object.id = edge.object_id
                WHERE edge.finding_id = ?
                """,
                (finding_id,),
            ).fetchall()
            for row in rows:
                for name_key, type_key in (("subject_name", "subject_type"), ("object_name", "object_type")):
                    ref = _entity_ref(row[name_key], row[type_key] or "unknown")
                    entities[ref["slug"]] = ref
        return list(entities.values())

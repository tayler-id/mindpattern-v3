"""Reader-facing related paths between public stories.

Pure module (no DB / network / model deps) mirroring the finding-level
connector conventions in ``orchestrator/site_graph.py``. Every connector is
derived from shared graph connectors (entities, sources, topics, findings,
arcs) or from explicit text signals layered on top of a shared substrate —
related paths are never fabricated for unconnected stories.
"""

from __future__ import annotations

import re
from typing import Any, Callable

# Text signals only ever fire on top of a shared substrate (entity/topic/
# source/finding/arc); on their own they never connect two stories.
_CONTRAST_SIGNALS = {
    "against",
    "but",
    "competes",
    "contradicts",
    "denies",
    "disputes",
    "however",
    "pushback",
    "pushes back",
    "skeptical",
    "slows",
    "tension",
    "versus",
    "vs",
}
_IMPLICATION_SIGNALS = {
    "downstream",
    "implication",
    "implications",
    "means for",
    "now that",
    "opens the door",
    "ripple",
    "sets up",
    "what it means",
    "which means",
}

_CONNECTOR_LABELS = {
    "shared_entity": "Shared entity",
    "same_source_url": "Same source",
    "same_source_domain": "Same source domain",
    "shared_topic": "Shared topic",
    "shared_finding": "Same underlying finding",
    "same_arc": "Same narrative arc",
    "semantic_neighbor": "Semantically similar",
    "temporal_continuation": "What happened next",
    "temporal_precursor": "Earlier coverage",
    "contrast": "Tension",
    "downstream_implication": "Downstream implication",
}

SEMANTIC_NEIGHBOR_THRESHOLD = 0.45


def _connector(
    kind: str,
    *,
    label: str | None = None,
    detail: str,
    weight: float,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label or _CONNECTOR_LABELS.get(kind, kind.replace("_", " ").title()),
        "detail": detail,
        "weight": round(weight, 4),
        "evidence": evidence,
    }


def _connector_set(story: dict, key: str) -> set[str]:
    values = story.get("graph_connectors", {}).get(key, [])
    return {str(value) for value in values if str(value)}


def _entity_labels(story: dict) -> dict[str, str]:
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


def _story_text(story: dict) -> str:
    return " ".join(
        str(story.get(key) or "") for key in ("title", "summary")
    ).lower()


def _matched_signals(text: str, signals: set[str]) -> list[str]:
    matched = []
    for signal in sorted(signals):
        if " " in signal:
            if signal in text:
                matched.append(signal)
        elif re.search(rf"\b{re.escape(signal)}\b", text):
            matched.append(signal)
    return matched


def _readable_reason(connectors: list[dict[str, Any]]) -> str:
    details = [connector["detail"] for connector in connectors[:3] if connector.get("detail")]
    if not details:
        return "Connected in the public knowledge graph."
    sentence = "; ".join(details)
    return sentence[0].upper() + sentence[1:] + "."


def related_path_between_stories(
    source: dict,
    candidate: dict,
    *,
    similarity: float | None = None,
) -> dict | None:
    """Build one reader-facing related path from ``source`` to ``candidate``.

    Returns ``None`` when the two stories share no graph evidence.
    ``similarity`` is an optional precomputed cosine similarity between the
    stories' embeddings (the caller owns embedding access to keep this pure).
    """
    shared_urls = sorted(_connector_set(source, "source_urls") & _connector_set(candidate, "source_urls"))
    shared_domains = sorted(
        _connector_set(source, "source_domains") & _connector_set(candidate, "source_domains")
    )
    shared_entities = sorted(_connector_set(source, "entity_ids") & _connector_set(candidate, "entity_ids"))
    shared_topics = sorted(_connector_set(source, "topic_terms") & _connector_set(candidate, "topic_terms"))
    shared_findings = sorted(_connector_set(source, "finding_ids") & _connector_set(candidate, "finding_ids"))
    shared_arcs = sorted(_connector_set(source, "arc_ids") & _connector_set(candidate, "arc_ids"))

    if len(shared_topics) < 2:
        shared_topics = []

    semantic = similarity is not None and similarity >= SEMANTIC_NEIGHBOR_THRESHOLD
    has_substrate = any(
        [shared_urls, shared_domains, shared_entities, shared_topics, shared_findings, shared_arcs]
    )
    if not has_substrate and not semantic:
        return None

    connectors: list[dict[str, Any]] = []
    evidence_edges: list[dict[str, Any]] = []
    entity_labels = _entity_labels(source) | _entity_labels(candidate)
    source_refs = _source_ref_by_url(source)

    if shared_findings:
        labels = [f"finding {finding_id}" for finding_id in shared_findings[:3]]
        connectors.append(
            _connector(
                "shared_finding",
                detail=f"built on the same source evidence ({', '.join(labels)})",
                weight=5 * len(shared_findings),
                evidence=[{"kind": "finding", "id": fid} for fid in shared_findings[:3]],
            )
        )
        for finding_id in shared_findings[:3]:
            evidence_edges.append({
                "kind": "finding",
                "relationship": "shared_finding",
                "id": finding_id,
                "label": f"Finding {finding_id}",
                "target_url": f"/f/{finding_id}",
            })

    if shared_arcs:
        connectors.append(
            _connector(
                "same_arc",
                detail=f"part of the same narrative arc ({', '.join(shared_arcs[:2])})",
                weight=5 * len(shared_arcs),
                evidence=[{"kind": "arc", "id": arc_id} for arc_id in shared_arcs[:3]],
            )
        )
        for arc_id in shared_arcs[:3]:
            evidence_edges.append({
                "kind": "arc",
                "relationship": "same_arc",
                "id": arc_id,
                "label": arc_id,
                "target_url": "",
            })

    if shared_entities:
        names = [entity_labels.get(entity_id, entity_id) for entity_id in shared_entities[:4]]
        connectors.append(
            _connector(
                "shared_entity",
                label=f"Shared entity: {names[0]}" if len(names) == 1 else "Shared entities",
                detail=f"both cover {', '.join(names)}",
                weight=4 * len(shared_entities),
                evidence=[
                    {"kind": "entity", "id": entity_id, "label": entity_labels.get(entity_id, entity_id)}
                    for entity_id in shared_entities[:4]
                ],
            )
        )
        for entity_id, name in zip(shared_entities[:4], names):
            evidence_edges.append({
                "kind": "entity",
                "relationship": "shared_entity",
                "id": entity_id,
                "label": name,
                "target_url": f"/e/{entity_id}",
            })

    if shared_urls:
        labels = []
        for url in shared_urls[:3]:
            ref = source_refs.get(url, {})
            labels.append(str(ref.get("title") or ref.get("domain") or url))
        connectors.append(
            _connector(
                "same_source_url",
                detail=f"cite the same source ({', '.join(labels)})",
                weight=6 * len(shared_urls),
                evidence=[{"kind": "source_url", "id": url} for url in shared_urls[:3]],
            )
        )
        for url, label in zip(shared_urls[:3], labels):
            evidence_edges.append({
                "kind": "source_url",
                "relationship": "same_source_url",
                "id": url,
                "label": label,
                "target_url": url,
            })
    elif shared_domains:
        connectors.append(
            _connector(
                "same_source_domain",
                detail=f"reported by the same outlet ({', '.join(shared_domains[:3])})",
                weight=3 * len(shared_domains),
                evidence=[{"kind": "source_domain", "id": domain} for domain in shared_domains[:3]],
            )
        )
        for domain in shared_domains[:3]:
            evidence_edges.append({
                "kind": "source_domain",
                "relationship": "same_source_domain",
                "id": domain,
                "label": domain,
                "target_url": f"/source/{domain}",
            })

    if shared_topics:
        connectors.append(
            _connector(
                "shared_topic",
                detail=f"overlapping topics ({', '.join(shared_topics[:5])})",
                weight=1.5 * len(shared_topics),
                evidence=[{"kind": "topic", "id": topic} for topic in shared_topics[:5]],
            )
        )
        for topic in shared_topics[:5]:
            evidence_edges.append({
                "kind": "topic",
                "relationship": "shared_topic",
                "id": topic,
                "label": topic,
                "target_url": "",
            })

    if semantic:
        connectors.append(
            _connector(
                "semantic_neighbor",
                detail=f"covers closely related ground (similarity {similarity:.2f})",
                weight=4 * float(similarity or 0.0),
                evidence=[{"kind": "embedding", "similarity": round(float(similarity or 0.0), 4)}],
            )
        )

    # Text-signal connectors: only on top of shared entities or topics, so the
    # relationship always has graph evidence behind it.
    source_date = str(source.get("issue_date") or "")
    candidate_date = str(candidate.get("issue_date") or "")
    if shared_entities and source_date and candidate_date and source_date != candidate_date:
        anchor = entity_labels.get(shared_entities[0], shared_entities[0])
        if candidate_date > source_date:
            connectors.append(
                _connector(
                    "temporal_continuation",
                    detail=f"picks up the {anchor} thread on {candidate_date}",
                    weight=2.0,
                    evidence=[{"kind": "issue_date", "from": source_date, "to": candidate_date}],
                )
            )
        else:
            connectors.append(
                _connector(
                    "temporal_precursor",
                    detail=f"earlier {anchor} coverage from {candidate_date}",
                    weight=1.5,
                    evidence=[{"kind": "issue_date", "from": source_date, "to": candidate_date}],
                )
            )

    if shared_entities or shared_topics:
        pair_text = _story_text(candidate)
        contrast_hits = _matched_signals(pair_text, _CONTRAST_SIGNALS)
        if contrast_hits:
            connectors.append(
                _connector(
                    "contrast",
                    detail=f"pushes against this story ({contrast_hits[0]})",
                    weight=2.0,
                    evidence=[{"kind": "text_signal", "signal": signal} for signal in contrast_hits[:2]],
                )
            )
        implication_hits = _matched_signals(pair_text, _IMPLICATION_SIGNALS)
        if implication_hits:
            connectors.append(
                _connector(
                    "downstream_implication",
                    detail=f"traces where this leads ({implication_hits[0]})",
                    weight=2.0,
                    evidence=[{"kind": "text_signal", "signal": signal} for signal in implication_hits[:2]],
                )
            )

    if not connectors:
        return None

    score = round(sum(connector["weight"] for connector in connectors), 2)
    return {
        "kind": "story",
        "id": candidate.get("id"),
        "slug": candidate.get("slug"),
        "title": candidate.get("title"),
        "summary": candidate.get("summary", ""),
        "issue_date": candidate_date,
        "target_url": candidate.get("target_url"),
        "relationship": "multi_connector",
        "connectors": connectors,
        "connector_labels": [connector["label"] for connector in connectors],
        "reason": _readable_reason(connectors),
        "score": score,
        "evidence_edges": evidence_edges[:10],
    }


def related_paths_for_story(
    story: dict,
    stories: list[dict],
    *,
    limit: int = 8,
    similarity_for: Callable[[dict], float | None] | None = None,
) -> list[dict]:
    """Rank reader-facing related paths from ``story`` into ``stories``."""
    paths: list[dict] = []
    for candidate in stories:
        if candidate.get("slug") == story.get("slug"):
            continue
        similarity = similarity_for(candidate) if similarity_for is not None else None
        path = related_path_between_stories(story, candidate, similarity=similarity)
        if path is not None:
            paths.append(path)

    paths.sort(key=lambda item: (item["score"], item.get("issue_date", "")), reverse=True)
    return paths[:limit]

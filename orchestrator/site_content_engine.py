"""Deterministic Rabbit Hole public content machine.

This module is the backend writer for site-native public intelligence
artifacts. It deliberately starts with fixture/dry-run providers only: no live
models, network, Slack, email, social APIs, Fly, Vercel, or full daily pipeline.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orchestrator.arcs import narrative_arcs_artifact_path
from orchestrator.media_contracts import redact_sensitive_text, validate_run_date
from orchestrator.site_content import (
    build_public_story,
    is_publishable_site_story,
    normalize_slug,
    sanitize_site_artifact,
    site_artifact_path,
    write_site_artifact,
)
from orchestrator.site_experts import run_site_expert_loop
from orchestrator.site_graph import CorpusGraphReadModel

_GENERIC_PUBLIC_TITLES = {
    "top 5 stories today",
    "top stories",
    "security",
    "source",
    "sources",
}
_IMPORTANCE_SCORE = {"high": 3.0, "medium": 2.0, "low": 1.0}
_PUBLIC_STORY_TYPES = {"finding_story"}


def load_fixture_cases(path: Path | str) -> dict[str, Any]:
    """Load public-safe content-machine fixture cases."""
    payload = json.loads(Path(path).read_text())
    cases = list(payload.get("cases") or [])
    for case in cases:
        if case.get("status") == "weak":
            case["type"] = "weak_input"
    payload["cases"] = cases
    return sanitize_site_artifact(payload)


def select_content_candidates(cases: list[dict[str, Any]], *, date: str) -> dict[str, Any]:
    """Select useful public candidates without mutating newsletter selection."""
    validate_run_date(date)
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for case in cases:
        candidate = _candidate_record(case, date=date)
        reasons = _candidate_rejection_reasons(case)
        if reasons:
            rejected.append({
                "id": candidate["id"],
                "candidate_type": candidate["candidate_type"],
                "reason": "no_public_candidate",
                "reasons": reasons,
            })
            continue
        selected.append(candidate)

    selected.sort(
        key=lambda item: (
            -float(item["score"]),
            item["candidate_type"],
            item["id"],
        )
    )
    return {
        "kind": "site_candidate_selection",
        "date": date,
        "selected": selected,
        "rejected": rejected,
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.selector",
            "provider": "deterministic",
            "newsletter_mutated": False,
        },
    }


def build_graph_pack(case: dict[str, Any], *, date: str, user: str) -> dict[str, Any]:
    """Build a bounded, public-safe graph pack from a candidate case."""
    run_date = validate_run_date(date)
    candidate_id = normalize_slug(str(case.get("id") or case.get("title") or "candidate"))
    primary = _public_finding(case.get("primary_finding") or {})
    source_refs = _source_refs(case)
    entity_refs = _entity_refs(case)
    graph_edges = _graph_edges(case)
    related_paths = _related_paths(case)
    degraded_reasons = _candidate_rejection_reasons(case)

    if primary:
        primary_evidence = [primary]
    else:
        primary_evidence = []
        if "missing_primary_evidence" not in degraded_reasons:
            degraded_reasons.append("missing_primary_evidence")

    return sanitize_site_artifact(
        {
            "kind": "site_graph_pack",
            "id": candidate_id,
            "candidate_id": candidate_id,
            "candidate_type": case.get("type") or "finding_story",
            "date": run_date,
            "user": user,
            "status": "degraded" if degraded_reasons else "ready",
            "degraded_reasons": degraded_reasons,
            "why_now": redact_sensitive_text(str(case.get("why_now") or "")),
            "primary_evidence": primary_evidence,
            "source_refs": source_refs,
            "entity_refs": entity_refs,
            "graph_edges": graph_edges,
            "semantic_neighbors": related_paths,
            "narrative_arcs": [
                {
                    "id": normalize_slug(str(arc_id)),
                    "target_url": f"/arcs/{normalize_slug(str(arc_id))}",
                }
                for arc_id in case.get("arc_ids") or []
            ],
            "historical_occurrences": [],
            "related_public_stories": [],
            "contrasts": _contrast_refs(case),
            "related_paths": related_paths,
            "claim_evidence_candidates": _claim_evidence_candidates(primary, source_refs),
            "redaction_report": {"status": "passed"},
            "provenance": {
                "generated_by": "mindpattern.site_content_engine.graph_pack_builder",
                "provider": "deterministic",
                "source_case_id": candidate_id,
                "redaction_status": "passed",
            },
        }
    )


def evaluate_site_story_confidence(
    story: dict[str, Any],
    *,
    skeptic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate whether a site story meets the public publishing floor."""
    reasons: list[str] = []
    title = str(story.get("title") or "").strip()
    public_text = "\n".join(
        str(story.get(key) or "")
        for key in ("title", "dek", "take", "why_now")
    )
    skeptic_result = skeptic or story.get("skeptic") or {}

    if story.get("kind") != "site_story":
        reasons.append("wrong_kind")
    if not title or _is_generic_title(title):
        reasons.append("generic_section_title")
    if not str(story.get("why_now") or "").strip():
        reasons.append("missing_why_now")
    if not story.get("source_refs"):
        reasons.append("missing_source_evidence")
    if not story.get("claim_evidence"):
        reasons.append("missing_claim_evidence")
    if not story.get("graph_edges"):
        reasons.append("missing_graph_evidence")
    if story.get("provenance", {}).get("redaction_status") != "passed":
        reasons.append("redaction_not_passed")
    if "**" in public_text or re.search(r"\[[^\]]+\]\([^)]+\)", public_text):
        reasons.append("raw_markdown_in_public_fields")
    if story.get("stale_repeat") and not str(story.get("why_now") or "").strip():
        reasons.append("stale_repeat_without_update")
    if skeptic_result.get("kill_switch"):
        reasons.append("skeptic_kill_switch")

    publishable = not reasons and is_publishable_site_story(story)
    return {
        "publishable": publishable,
        "confidence": "high" if publishable else "degraded",
        "reasons": reasons,
    }


def generate_site_story(
    graph_pack: dict[str, Any],
    *,
    expert_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate deterministic site-native story copy from one graph pack."""
    candidate_id = normalize_slug(str(graph_pack.get("candidate_id") or "story"))
    primary = (graph_pack.get("primary_evidence") or [{}])[0]
    title = _site_title(graph_pack, primary)
    source_refs = list(graph_pack.get("source_refs") or [])
    entity_refs = list(graph_pack.get("entity_refs") or [])
    graph_edges = list(graph_pack.get("graph_edges") or [])
    related_paths = list(graph_pack.get("related_paths") or [])
    claim_evidence = list(graph_pack.get("claim_evidence_candidates") or [])

    if graph_pack.get("status") == "degraded":
        story = {
            "kind": "site_story",
            "id": candidate_id,
            "slug": candidate_id,
            "status": "degraded",
            "confidence": "degraded",
            "issue_date": graph_pack.get("date", ""),
            "title": title,
            "dek": "This candidate did not meet the public publishing floor.",
            "take": "",
            "why_now": graph_pack.get("why_now", ""),
            "body_markdown": "",
            "source_refs": source_refs,
            "entity_refs": entity_refs,
            "primary_finding_ids": _finding_ids(graph_pack.get("primary_evidence") or []),
            "supporting_finding_ids": [],
            "arc_ids": [arc.get("id") for arc in graph_pack.get("narrative_arcs") or []],
            "graph_edges": graph_edges,
            "related_paths": related_paths,
            "claim_evidence": claim_evidence,
            "provenance": _story_provenance(graph_pack, expert_results or []),
            "json_ld_ready": False,
        }
        gate = evaluate_site_story_confidence(story)
        story["rejection_reasons"] = sorted(set(graph_pack.get("degraded_reasons") or []) | set(gate["reasons"]))
        return sanitize_site_artifact(story)

    why_now = str(graph_pack.get("why_now") or "The graph pack connected fresh source evidence today.")
    entity_names = [entity.get("name", "") for entity in entity_refs if entity.get("name")]
    source_domains = [source.get("domain", "") for source in source_refs if source.get("domain")]
    lead_entity = entity_names[0] if entity_names else "This signal"
    lead_source = source_domains[0] if source_domains else "the source trail"
    summary = redact_sensitive_text(str(primary.get("summary") or primary.get("title") or ""))
    body = (
        f"{summary}\n\n"
        f"Why it matters: {lead_entity} is now connected to a public graph trail "
        f"through {lead_source}, related findings, and explicit claim evidence.\n\n"
        "Follow the thread through the source trail and related graph paths rather "
        "than treating this as an isolated headline."
    ).strip()
    story = {
        "kind": "site_story",
        "id": candidate_id,
        "slug": candidate_id,
        "status": "published",
        "confidence": "high",
        "issue_date": graph_pack.get("date", ""),
        "title": title,
        "dek": "A source-backed Rabbit Hole intelligence artifact.",
        "take": f"{lead_entity} is moving from a single finding into connected public intelligence.",
        "why_now": why_now,
        "body_markdown": body,
        "source_refs": source_refs,
        "entity_refs": entity_refs,
        "primary_finding_ids": _finding_ids(graph_pack.get("primary_evidence") or []),
        "supporting_finding_ids": [
            int(item["id"])
            for item in related_paths
            if str(item.get("id", "")).isdigit()
        ][:10],
        "arc_ids": [arc.get("id") for arc in graph_pack.get("narrative_arcs") or []],
        "graph_edges": graph_edges,
        "related_paths": related_paths,
        "claim_evidence": claim_evidence,
        "provenance": _story_provenance(graph_pack, expert_results or []),
        "json_ld_ready": True,
    }
    gate = evaluate_site_story_confidence(story)
    if not gate["publishable"]:
        story["status"] = "degraded"
        story["confidence"] = "degraded"
        story["json_ld_ready"] = False
        story["rejection_reasons"] = gate["reasons"]
    return sanitize_site_artifact(story)


def run_site_content_dry_run(
    *,
    date: str,
    user: str,
    reports_root: Path,
    fixture_path: Path | str,
) -> dict[str, Any]:
    """Run the fixture-backed content machine and write public-safe artifacts."""
    run_date = validate_run_date(date)
    payload = load_fixture_cases(fixture_path)
    cases = list(payload.get("cases") or [])
    selection = select_content_candidates(cases, date=run_date)
    artifacts_written: list[str] = []
    rejections = list(selection["rejected"])
    published_count = 0
    degraded_count = 0
    graph_pack_count = 0

    for case in cases:
        candidate_id = normalize_slug(str(case.get("id") or "candidate"))
        candidate_record = _candidate_record(case, date=run_date)
        candidate_path = write_site_artifact(
            kind="site_candidate",
            user=user,
            reports_root=reports_root,
            date=run_date,
            slug=candidate_id,
            artifact=candidate_record,
        )
        artifacts_written.append(_artifact_ref(candidate_path, reports_root))

        should_write_story = case.get("type") in _PUBLIC_STORY_TYPES or case.get("type") == "weak_input"
        should_build_pack = should_write_story or case.get("id") in {item["id"] for item in selection["selected"]}
        if not should_build_pack:
            continue

        graph_pack = build_graph_pack(case, date=run_date, user=user)
        pack_path = write_site_artifact(
            kind="site_graph_pack",
            user=user,
            reports_root=reports_root,
            date=run_date,
            slug=candidate_id,
            artifact=graph_pack,
        )
        artifacts_written.append(_artifact_ref(pack_path, reports_root))
        graph_pack_count += 1

        if not should_write_story:
            continue
        expert_results = run_site_expert_loop(graph_pack, context={"date": run_date, "user": user})
        story = generate_site_story(graph_pack, expert_results=expert_results)
        story_path = write_site_artifact(
            kind="site_story",
            user=user,
            reports_root=reports_root,
            date=run_date,
            slug=candidate_id,
            artifact=story,
        )
        artifacts_written.append(_artifact_ref(story_path, reports_root))
        if story.get("status") == "published":
            published_count += 1
        else:
            degraded_count += 1

    corpus = {
        "kind": "site_corpus",
        "date": run_date,
        "user": user,
        "status": "ready",
        "counts": {
            "candidate_cases": len(cases),
            "selected_candidates": len(selection["selected"]),
            "rejected_candidates": len(selection["rejected"]),
            "graph_packs": graph_pack_count,
            "published_stories": published_count,
            "degraded_stories": degraded_count,
        },
        "coverage": {
            "source": "fixture",
            "has_embeddings": False,
            "has_arcs": any(case.get("arc_ids") for case in cases),
        },
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.dry_run",
            "redaction_status": "passed",
        },
    }
    corpus_path = write_site_artifact(
        kind="site_corpus",
        user=user,
        reports_root=reports_root,
        date=run_date,
        artifact=corpus,
    )
    artifacts_written.append(_artifact_ref(corpus_path, reports_root))

    arc_payload = _fixture_arc_payload(cases, date=run_date, user=user)
    if arc_payload["arcs"]:
        arc_path = narrative_arcs_artifact_path(date=run_date, user=user, reports_root=reports_root)
        arc_path.parent.mkdir(parents=True, exist_ok=True)
        arc_path.write_text(json.dumps(sanitize_site_artifact(arc_payload), indent=2, sort_keys=True) + "\n")
        artifacts_written.append(_artifact_ref(arc_path, reports_root))

    ledger = {
        "kind": "site_run",
        "date": run_date,
        "user": user,
        "status": "completed",
        "mode": "fixture_dry_run",
        "inputs_scanned": {
            "fixture_cases": len(cases),
            "fixture_path": Path(fixture_path).name,
        },
        "candidates_considered": len(cases),
        "selected_candidates": [item["id"] for item in selection["selected"]],
        "graph_packs_built": graph_pack_count,
        "generated_story_count": published_count,
        "degraded_story_count": degraded_count,
        "rejections": rejections,
        "artifacts_written": artifacts_written,
        "redaction_status": "passed",
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.dry_run",
            "provider": "deterministic",
            "newsletter_mutated": False,
        },
    }
    run_path = write_site_artifact(
        kind="site_run",
        user=user,
        reports_root=reports_root,
        date=run_date,
        artifact=ledger,
    )
    artifacts_written.append(_artifact_ref(run_path, reports_root))
    ledger["artifacts_written"] = artifacts_written
    run_path.write_text(json.dumps(sanitize_site_artifact(ledger), indent=2, sort_keys=True) + "\n")
    return ledger


def run_site_content_for_date(
    *,
    date: str,
    user: str,
    reports_root: Path,
    conn: sqlite3.Connection,
    max_stories: int = 5,
) -> dict[str, Any]:
    """Run the deterministic content machine against a public-safe corpus read model."""
    run_date = validate_run_date(date)
    graph = CorpusGraphReadModel(conn)
    cases = _candidate_cases_from_corpus(conn, graph, date=run_date, limit=max(10, max_stories * 3))
    selection = select_content_candidates(cases, date=run_date)
    selected = selection["selected"][:max_stories]
    selected_ids = {item["id"] for item in selected}
    artifacts_written: list[str] = []
    published_count = 0
    degraded_count = 0
    graph_pack_count = 0

    for case in cases:
        candidate_id = normalize_slug(str(case.get("id") or "candidate"))
        if candidate_id not in selected_ids:
            continue

        candidate_record = _candidate_record(case, date=run_date)
        candidate_path = write_site_artifact(
            kind="site_candidate",
            user=user,
            reports_root=reports_root,
            date=run_date,
            slug=candidate_id,
            artifact=candidate_record,
        )
        artifacts_written.append(_artifact_ref(candidate_path, reports_root))

        graph_pack = build_graph_pack(case, date=run_date, user=user)
        pack_path = write_site_artifact(
            kind="site_graph_pack",
            user=user,
            reports_root=reports_root,
            date=run_date,
            slug=candidate_id,
            artifact=graph_pack,
        )
        artifacts_written.append(_artifact_ref(pack_path, reports_root))
        graph_pack_count += 1

        expert_results = run_site_expert_loop(graph_pack, context={"date": run_date, "user": user})
        story = generate_site_story(graph_pack, expert_results=expert_results)
        story_path = write_site_artifact(
            kind="site_story",
            user=user,
            reports_root=reports_root,
            date=run_date,
            slug=candidate_id,
            artifact=story,
        )
        artifacts_written.append(_artifact_ref(story_path, reports_root))
        if story.get("status") == "published":
            published_count += 1
        else:
            degraded_count += 1

    corpus = {
        "kind": "site_corpus",
        "date": run_date,
        "user": user,
        "status": "ready" if cases else "degraded",
        "counts": {
            "findings": len(cases),
            "selected_candidates": len(selected),
            "rejected_candidates": len(selection["rejected"]),
            "graph_packs": graph_pack_count,
            "published_stories": published_count,
            "degraded_stories": degraded_count,
        },
        "coverage": {
            "source": "corpus",
            "has_embeddings": _table_has_rows(conn, "findings_embeddings"),
            "has_arcs": False,
        },
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.corpus_run",
            "redaction_status": "passed",
        },
    }
    corpus_path = write_site_artifact(
        kind="site_corpus",
        user=user,
        reports_root=reports_root,
        date=run_date,
        artifact=corpus,
    )
    artifacts_written.append(_artifact_ref(corpus_path, reports_root))

    ledger = {
        "kind": "site_run",
        "date": run_date,
        "user": user,
        "status": "completed" if cases else "degraded",
        "mode": "corpus_deterministic",
        "inputs_scanned": {
            "findings": len(cases),
            "max_stories": max_stories,
        },
        "candidates_considered": len(cases),
        "selected_candidates": [item["id"] for item in selected],
        "graph_packs_built": graph_pack_count,
        "generated_story_count": published_count,
        "degraded_story_count": degraded_count,
        "rejections": selection["rejected"],
        "artifacts_written": artifacts_written,
        "redaction_status": "passed",
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.corpus_run",
            "provider": "deterministic",
            "newsletter_mutated": False,
        },
    }
    run_path = write_site_artifact(
        kind="site_run",
        user=user,
        reports_root=reports_root,
        date=run_date,
        artifact=ledger,
    )
    artifacts_written.append(_artifact_ref(run_path, reports_root))
    ledger["artifacts_written"] = artifacts_written
    run_path.write_text(json.dumps(sanitize_site_artifact(ledger), indent=2, sort_keys=True) + "\n")
    return sanitize_site_artifact(ledger)


def run_historical_site_seed_generation(
    *,
    date: str,
    user: str,
    reports_root: Path,
    source_dates: list[str] | None = None,
    max_stories: int = 5,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Generate a small public historical seed from audited site issues."""
    run_date = validate_run_date(date)
    if max_stories < 1:
        raise ValueError("max_stories must be positive")
    generated = generated_at or f"{run_date}T00:00:00+00:00"
    requested_dates = {validate_run_date(item) for item in source_dates or []}
    audit_path = site_artifact_path(
        kind="site_issue_backfill",
        date=run_date,
        user=user,
        reports_root=reports_root,
    )
    if not audit_path.exists():
        ledger = _historical_seed_ledger(
            run_date=run_date,
            user=user,
            generated_at=generated,
            status="degraded",
            degraded_reasons=["missing_backfill_audit"],
            decisions=[],
            artifacts_written=[],
            issues_scanned=0,
        )
        write_site_artifact(
            kind="site_historical_seed",
            user=user,
            reports_root=reports_root,
            date=run_date,
            artifact=ledger,
        )
        return sanitize_site_artifact(ledger)

    audit = json.loads(audit_path.read_text())
    parsed_records = [
        record
        for record in audit.get("parsed") or []
        if not requested_dates or record.get("date") in requested_dates
    ]
    decisions: list[dict[str, Any]] = []
    artifacts_written: list[str] = []
    published_count = 0
    graph_pack_count = 0
    issues_scanned = 0

    for record in parsed_records:
        issue_date = validate_run_date(str(record.get("date") or ""))
        issue_path = site_artifact_path(
            kind="site_issue",
            date=issue_date,
            user=user,
            reports_root=reports_root,
        )
        if not issue_path.exists():
            decisions.append(
                {
                    "id": issue_date,
                    "issue_date": issue_date,
                    "action": "skipped",
                    "reasons": ["missing_structured_issue_artifact"],
                }
            )
            continue
        issue = json.loads(issue_path.read_text())
        issues_scanned += 1

        for story_unit in issue.get("story_units") or []:
            candidate_id = normalize_slug(str(story_unit.get("id") or story_unit.get("title") or "story"))
            graph_pack = _historical_graph_pack(
                issue=issue,
                story_unit=story_unit,
                user=user,
                generated_at=generated,
            )
            pack_path = write_site_artifact(
                kind="site_graph_pack",
                user=user,
                reports_root=reports_root,
                date=issue_date,
                slug=candidate_id,
                artifact=graph_pack,
            )
            artifacts_written.append(_artifact_ref(pack_path, reports_root))
            graph_pack_count += 1

            story = _historical_site_story_from_graph_pack(graph_pack, generated_at=generated)
            if story.get("status") == "published" and published_count < max_stories:
                story_path = write_site_artifact(
                    kind="site_story",
                    user=user,
                    reports_root=reports_root,
                    date=issue_date,
                    slug=candidate_id,
                    artifact=story,
                )
                artifacts_written.append(_artifact_ref(story_path, reports_root))
                published_count += 1
                decisions.append(
                    {
                        "id": candidate_id,
                        "issue_date": issue_date,
                        "story_unit_id": story_unit.get("id"),
                        "action": "published",
                        "reasons": [],
                        "graph_pack_artifact": _artifact_ref(pack_path, reports_root),
                        "story_artifact": _artifact_ref(story_path, reports_root),
                    }
                )
                continue

            if story.get("status") == "published":
                decisions.append(
                    {
                        "id": candidate_id,
                        "issue_date": issue_date,
                        "story_unit_id": story_unit.get("id"),
                        "action": "skipped",
                        "reasons": ["max_stories_reached"],
                        "graph_pack_artifact": _artifact_ref(pack_path, reports_root),
                    }
                )
                continue

            decisions.append(
                {
                    "id": candidate_id,
                    "issue_date": issue_date,
                    "story_unit_id": story_unit.get("id"),
                    "action": "degraded",
                    "reasons": story.get("rejection_reasons") or graph_pack.get("degraded_reasons") or [],
                    "graph_pack_artifact": _artifact_ref(pack_path, reports_root),
                }
            )

    ledger = _historical_seed_ledger(
        run_date=run_date,
        user=user,
        generated_at=generated,
        status="completed" if issues_scanned else "degraded",
        degraded_reasons=[] if issues_scanned else ["no_audited_issues"],
        decisions=decisions,
        artifacts_written=artifacts_written,
        issues_scanned=issues_scanned,
        graph_pack_count=graph_pack_count,
    )
    seed_path = write_site_artifact(
        kind="site_historical_seed",
        user=user,
        reports_root=reports_root,
        date=run_date,
        artifact=ledger,
    )
    artifacts_written.append(_artifact_ref(seed_path, reports_root))
    ledger["artifacts_written"] = artifacts_written
    seed_path.write_text(json.dumps(sanitize_site_artifact(ledger), indent=2, sort_keys=True) + "\n")
    return sanitize_site_artifact(ledger)


def _historical_graph_pack(
    *,
    issue: dict[str, Any],
    story_unit: dict[str, Any],
    user: str,
    generated_at: str,
) -> dict[str, Any]:
    issue_date = validate_run_date(str(issue.get("date") or story_unit.get("issue_date") or ""))
    candidate_id = normalize_slug(str(story_unit.get("id") or story_unit.get("title") or "story"))
    public_story = build_public_story(issue=issue, story_unit=story_unit)
    degraded_reasons: list[str] = []
    if public_story is None:
        degraded_reasons.append("missing_source_evidence")
        source_refs: list[dict[str, Any]] = []
        entity_refs: list[dict[str, Any]] = []
        graph_edges: list[dict[str, Any]] = []
    else:
        source_refs = list(public_story.get("source_refs") or [])
        entity_refs = list(public_story.get("entity_refs") or [])
        graph_edges = list(public_story.get("graph_edges") or [])

    if issue.get("provenance", {}).get("redaction_status") != "passed":
        degraded_reasons.append("redaction_not_passed")
    if _is_generic_title(str(story_unit.get("title") or "")):
        degraded_reasons.append("generic_section_title")

    summary = redact_sensitive_text(str(story_unit.get("summary") or story_unit.get("title") or ""))
    claim_evidence = []
    if summary and source_refs:
        claim_evidence.append(
            {
                "claim": summary,
                "source_url": source_refs[0]["url"],
                "finding_id": None,
                "issue_story_unit_id": story_unit.get("id"),
            }
        )

    return sanitize_site_artifact(
        {
            "kind": "site_graph_pack",
            "id": candidate_id,
            "candidate_id": candidate_id,
            "candidate_type": "historical_issue_story",
            "date": issue_date,
            "user": user,
            "status": "degraded" if degraded_reasons else "ready",
            "degraded_reasons": sorted(set(degraded_reasons)),
            "why_now": (
                "This canonical newsletter story is being backfilled into Rabbit Hole "
                "so the public archive has source-backed graph paths."
            ),
            "primary_evidence": [
                {
                    "kind": "issue_story_unit",
                    "id": story_unit.get("id"),
                    "issue_date": issue_date,
                    "title": story_unit.get("title"),
                    "summary": summary,
                    "target_url": f"/briefings/{issue_date}",
                }
            ],
            "source_refs": source_refs,
            "entity_refs": entity_refs,
            "graph_edges": graph_edges,
            "semantic_neighbors": [],
            "narrative_arcs": [],
            "historical_occurrences": [],
            "related_public_stories": [],
            "contrasts": [],
            "related_paths": [],
            "claim_evidence_candidates": claim_evidence,
            "story_body_markdown": story_unit.get("body_markdown", ""),
            "provenance": {
                "generated_by": "mindpattern.site_content_engine.historical_graph_pack",
                "generated_at": generated_at,
                "provider": "deterministic",
                "input_artifacts": [f"reports/{user}/site-issues/{issue_date}.json"],
                "source_issue_dates": [issue_date],
                "source_story_unit_id": story_unit.get("id"),
                "redaction_status": issue.get("provenance", {}).get("redaction_status", "passed"),
            },
        }
    )


def _historical_site_story_from_graph_pack(
    graph_pack: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    candidate_id = normalize_slug(str(graph_pack.get("candidate_id") or "historical-story"))
    issue_date = validate_run_date(str(graph_pack.get("date") or ""))
    evidence = (graph_pack.get("primary_evidence") or [{}])[0]
    title = redact_sensitive_text(str(evidence.get("title") or candidate_id.replace("-", " ").title()))
    summary = redact_sensitive_text(str(evidence.get("summary") or title))
    story = {
        "kind": "site_story",
        "id": candidate_id,
        "slug": candidate_id,
        "status": "published",
        "confidence": "high",
        "issue_date": issue_date,
        "title": title,
        "dek": "A source-backed story from the canonical MindPattern archive.",
        "take": summary,
        "why_now": str(graph_pack.get("why_now") or ""),
        "body_markdown": redact_sensitive_text(str(graph_pack.get("story_body_markdown") or summary)),
        "source_refs": list(graph_pack.get("source_refs") or []),
        "entity_refs": list(graph_pack.get("entity_refs") or []),
        "primary_finding_ids": [],
        "supporting_finding_ids": [],
        "arc_ids": [],
        "graph_edges": list(graph_pack.get("graph_edges") or []),
        "related_paths": list(graph_pack.get("related_paths") or []),
        "claim_evidence": list(graph_pack.get("claim_evidence_candidates") or []),
        "provenance": {
            "generated_by": "mindpattern.site_content_engine.historical_seed",
            "generated_at": generated_at,
            "input_artifacts": graph_pack.get("provenance", {}).get("input_artifacts", []),
            "source_finding_ids": [],
            "source_issue_dates": [issue_date],
            "redaction_status": graph_pack.get("provenance", {}).get("redaction_status", "passed"),
            "ai_generated": False,
            "human_approved": False,
        },
        "json_ld_ready": True,
    }
    gate = evaluate_site_story_confidence(story)
    if graph_pack.get("status") == "degraded" or not gate["publishable"]:
        story["status"] = "degraded"
        story["confidence"] = "degraded"
        story["json_ld_ready"] = False
        story["rejection_reasons"] = sorted(set(graph_pack.get("degraded_reasons") or []) | set(gate["reasons"]))
    return sanitize_site_artifact(story)


def _historical_seed_ledger(
    *,
    run_date: str,
    user: str,
    generated_at: str,
    status: str,
    degraded_reasons: list[str],
    decisions: list[dict[str, Any]],
    artifacts_written: list[str],
    issues_scanned: int,
    graph_pack_count: int = 0,
) -> dict[str, Any]:
    counts = {
        "issues_scanned": issues_scanned,
        "candidates_considered": len([item for item in decisions if item.get("story_unit_id")]),
        "published": len([item for item in decisions if item.get("action") == "published"]),
        "drafted": len([item for item in decisions if item.get("action") == "drafted"]),
        "degraded": len([item for item in decisions if item.get("action") == "degraded"]),
        "skipped": len([item for item in decisions if item.get("action") == "skipped"]),
        "graph_packs": graph_pack_count,
    }
    return sanitize_site_artifact(
        {
            "kind": "site_historical_seed",
            "date": run_date,
            "user": user,
            "status": status,
            "degraded_reasons": degraded_reasons,
            "counts": counts,
            "decisions": decisions,
            "artifacts_written": artifacts_written,
            "provenance": {
                "generated_by": "mindpattern.site_content_engine.historical_seed",
                "generated_at": generated_at,
                "provider": "deterministic",
                "newsletter_mutated": False,
                "selection_policy": "publish_only_high_confidence_source_backed_candidates",
            },
        }
    )


def _candidate_cases_from_corpus(
    conn: sqlite3.Connection,
    graph: CorpusGraphReadModel,
    *,
    date: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not _table_has_rows(conn, "findings"):
        return []
    rows = conn.execute(
        """
        SELECT id, run_date, agent, title, summary, importance, category,
               source_url, source_name, created_at
        FROM findings
        WHERE run_date = ?
          AND COALESCE(source_url, '') LIKE 'http%'
          AND COALESCE(title, '') != ''
          AND COALESCE(summary, '') != ''
        ORDER BY
          CASE lower(COALESCE(importance, ''))
            WHEN 'critical' THEN 0
            WHEN 'high' THEN 1
            WHEN 'medium' THEN 2
            ELSE 3
          END,
          created_at DESC,
          id DESC
        LIMIT ?
        """,
        (date, limit),
    ).fetchall()
    cases: list[dict[str, Any]] = []
    for row in rows:
        finding = _public_finding(dict(row))
        if _is_generic_title(str(finding.get("title") or "")):
            continue
        detail = graph.get_finding(int(finding["id"])) or finding
        related = graph.get_related_paths_for_finding(int(finding["id"]), limit=5) or {}
        source_refs = list(finding.get("source_refs") or [])
        entity_refs = list(detail.get("entities") or [])
        graph_edges = _graph_edges_for_corpus_case(
            primary=finding,
            source_refs=source_refs,
            entity_refs=entity_refs,
        )
        cases.append(
            sanitize_site_artifact(
                {
                    "id": normalize_slug(str(finding["title"])),
                    "type": "finding_story",
                    "importance": finding.get("importance") or "medium",
                    "why_now": _why_now_for_finding(finding),
                    "primary_finding": finding,
                    "source_refs": source_refs,
                    "entities": entity_refs,
                    "graph_edges": graph_edges,
                    "related_paths": list(related.get("items") or []),
                    "arc_ids": [],
                }
            )
        )
    return cases


def _graph_edges_for_corpus_case(
    *,
    primary: dict[str, Any],
    source_refs: list[dict[str, str]],
    entity_refs: list[dict[str, Any]],
) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    finding_id = str(primary.get("id") or "")
    evidence = redact_sensitive_text(str(primary.get("summary") or primary.get("title") or ""))[:240]
    for source in source_refs[:2]:
        domain = str(source.get("domain") or "")
        if not domain:
            continue
        edges.append(
            {
                "kind": "source_evidence",
                "relationship": "reported_by",
                "id": domain,
                "label": source.get("title") or domain,
                "target_url": f"/source/{domain}",
                "evidence": evidence,
            }
        )
    for entity in entity_refs[:4]:
        slug = str(entity.get("slug") or entity.get("id") or "")
        if not slug:
            continue
        edges.append(
            {
                "kind": "entity_evidence",
                "relationship": "mentions",
                "id": slug,
                "label": str(entity.get("name") or slug),
                "target_url": f"/e/{slug}",
                "evidence": f"Finding {finding_id} mentions {entity.get('name') or slug}.",
            }
        )
    return edges


def _why_now_for_finding(finding: dict[str, Any]) -> str:
    source = finding.get("source_name") or (finding.get("source_refs") or [{}])[0].get("domain") or "the source trail"
    return (
        f"This entered the {finding.get('run_date')} research corpus from {source} "
        "and has enough source evidence to become a public Rabbit Hole story."
    )


def _table_has_rows(conn: sqlite3.Connection, table_name: str) -> bool:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        return False
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table_name,),
    ).fetchone()
    if row is None:
        return False
    count = conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()
    return count is not None


def _candidate_record(case: dict[str, Any], *, date: str) -> dict[str, Any]:
    candidate_id = normalize_slug(str(case.get("id") or "candidate"))
    importance = str(case.get("importance") or "low").lower()
    source_count = len(_source_refs(case))
    edge_count = len(_graph_edges(case))
    why_now = str(case.get("why_now") or "").strip()
    score = _IMPORTANCE_SCORE.get(importance, 0.5) + min(source_count, 3) * 0.4 + min(edge_count, 3) * 0.3
    if why_now:
        score += 0.4
    return sanitize_site_artifact(
        {
            "kind": "site_candidate",
            "id": candidate_id,
            "candidate_type": case.get("type") or "finding_story",
            "date": validate_run_date(date),
            "status": "ready" if not _candidate_rejection_reasons(case) else "degraded",
            "importance": importance,
            "score": round(score, 4),
            "why_now": redact_sensitive_text(why_now),
            "primary_finding_id": (case.get("primary_finding") or {}).get("id"),
            "source_count": source_count,
            "graph_edge_count": edge_count,
            "provenance": {
                "generated_by": "mindpattern.site_content_engine.selector",
                "provider": "deterministic",
            },
        }
    )


def _candidate_rejection_reasons(case: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if case.get("type") == "weak_input" or case.get("status") == "weak":
        reasons.append("weak_input")
    if not str(case.get("why_now") or "").strip():
        reasons.append("missing_why_now")
    primary = case.get("primary_finding") or {}
    title = str(primary.get("title") or case.get("title") or "")
    if _is_generic_title(title):
        reasons.append("generic_section_title")
    if case.get("type") in {"finding_story", "weak_input"} and not _source_refs(case):
        reasons.append("missing_source_evidence")
    if case.get("type") in {"finding_story", "weak_input"} and not _graph_edges(case):
        reasons.append("missing_graph_evidence")
    return sorted(set(reasons))


def _public_finding(finding: dict[str, Any]) -> dict[str, Any]:
    if not finding:
        return {}
    source_url = redact_sensitive_text(str(finding.get("source_url") or ""))
    source_refs = list(finding.get("source_refs") or [])
    if not source_refs and source_url.startswith(("http://", "https://")):
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower().removeprefix("www.")
        source_refs = [
            {
                "url": source_url,
                "domain": domain,
                "title": redact_sensitive_text(str(finding.get("source_name") or domain)),
            }
        ]
    return sanitize_site_artifact(
        {
            "kind": "finding",
            "id": int(finding.get("id") or 0),
            "run_date": validate_run_date(str(finding.get("run_date") or "2026-01-01")),
            "agent": finding.get("agent") or "",
            "title": finding.get("title") or "",
            "summary": finding.get("summary") or "",
            "importance": finding.get("importance") or "",
            "category": finding.get("category") or "",
            "source_url": source_url,
            "source_name": finding.get("source_name") or "",
            "target_url": finding.get("target_url") or f"/f/{int(finding.get('id') or 0)}",
            "source_refs": source_refs,
        }
    )


def _source_refs(case: dict[str, Any]) -> list[dict[str, str]]:
    refs = []
    seen = set()
    for source in case.get("source_refs") or (case.get("primary_finding") or {}).get("source_refs") or []:
        if not isinstance(source, dict):
            continue
        url = redact_sensitive_text(str(source.get("url") or ""))
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        parsed = urlparse(url)
        domain = redact_sensitive_text(str(source.get("domain") or parsed.netloc.lower().removeprefix("www.")))
        refs.append({
            "url": url,
            "domain": domain,
            "title": redact_sensitive_text(str(source.get("title") or domain)),
        })
        seen.add(url)
    return refs


def _entity_refs(case: dict[str, Any]) -> list[dict[str, str]]:
    refs = []
    seen = set()
    for entity in case.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        slug = normalize_slug(str(entity.get("slug") or entity.get("id") or entity.get("name") or "entity"))
        if slug in seen:
            continue
        seen.add(slug)
        refs.append({
            "id": slug,
            "slug": slug,
            "name": redact_sensitive_text(str(entity.get("name") or slug.replace("-", " ").title())),
            "kind": redact_sensitive_text(str(entity.get("kind") or "unknown")),
            "target_url": f"/e/{slug}",
        })
    return refs


def _graph_edges(case: dict[str, Any]) -> list[dict[str, str]]:
    edges = []
    for edge in case.get("graph_edges") or []:
        if not isinstance(edge, dict):
            continue
        target_url = redact_sensitive_text(str(edge.get("target_url") or ""))
        if target_url and not target_url.startswith(("/", "http://", "https://")):
            target_url = ""
        edges.append({
            "kind": redact_sensitive_text(str(edge.get("kind") or "")),
            "relationship": redact_sensitive_text(str(edge.get("relationship") or "")),
            "id": redact_sensitive_text(str(edge.get("id") or "")),
            "label": redact_sensitive_text(str(edge.get("label") or "")),
            "target_url": target_url,
            "evidence": redact_sensitive_text(str(edge.get("evidence") or "")),
        })
    return edges


def _related_paths(case: dict[str, Any]) -> list[dict[str, Any]]:
    paths = []
    for item in case.get("related_paths") or []:
        if not isinstance(item, dict):
            continue
        paths.append(sanitize_site_artifact(item))
    return paths


def _contrast_refs(case: dict[str, Any]) -> list[dict[str, str]]:
    if case.get("type") != "contrast_pair":
        return []
    return [{"kind": "contrast_pair", "id": normalize_slug(str(case.get("id") or "contrast"))}]


def _claim_evidence_candidates(primary: dict[str, Any], source_refs: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not primary or not source_refs:
        return []
    claim = redact_sensitive_text(str(primary.get("summary") or primary.get("title") or ""))
    if not claim:
        return []
    return [
        {
            "claim": claim,
            "source_url": source_refs[0]["url"],
            "finding_id": int(primary.get("id") or 0),
        }
    ]


def _site_title(graph_pack: dict[str, Any], primary: dict[str, Any]) -> str:
    if graph_pack.get("status") == "degraded":
        return redact_sensitive_text(str(primary.get("title") or graph_pack.get("candidate_id") or "Degraded candidate"))
    entity_refs = graph_pack.get("entity_refs") or []
    lead_entity = entity_refs[0].get("name") if entity_refs else ""
    source_title = str(primary.get("title") or "")
    if lead_entity and "runtime" in source_title.lower():
        return f"{lead_entity} agent runtime reliability becomes public infrastructure"
    if source_title and not _is_generic_title(source_title):
        return f"{source_title} becomes a connected public signal"
    return f"{graph_pack.get('candidate_id', 'signal').replace('-', ' ').title()} becomes a connected public signal"


def _story_provenance(graph_pack: dict[str, Any], expert_results: list[dict[str, Any]]) -> dict[str, Any]:
    finding_ids = _finding_ids(graph_pack.get("primary_evidence") or [])
    return {
        "generated_by": "mindpattern.site_content_engine.story_generator",
        "generated_at": f"{graph_pack.get('date', '2026-01-01')}T00:00:00+00:00",
        "input_artifacts": [
            f"reports/{graph_pack.get('user', 'ramsay')}/site-graph-packs/{graph_pack.get('date')}/{graph_pack.get('candidate_id')}.json"
        ],
        "source_finding_ids": finding_ids,
        "source_issue_dates": [graph_pack.get("date", "")],
        "expert_roles": [result.get("role", "") for result in expert_results],
        "redaction_status": "passed",
        "ai_generated": True,
        "human_approved": False,
    }


def _finding_ids(items: list[dict[str, Any]]) -> list[int]:
    ids = []
    for item in items:
        value = item.get("id")
        if str(value).isdigit():
            ids.append(int(value))
    return ids


def _is_generic_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    return normalized in _GENERIC_PUBLIC_TITLES


def _artifact_ref(path: Path, reports_root: Path) -> str:
    try:
        return f"reports/{path.resolve().relative_to(reports_root.resolve()).as_posix()}"
    except ValueError:
        return path.name


def _fixture_arc_payload(cases: list[dict[str, Any]], *, date: str, user: str) -> dict[str, Any]:
    arcs: dict[str, dict[str, Any]] = {}
    for case in cases:
        primary = _public_finding(case.get("primary_finding") or {})
        evidence = []
        if primary and primary.get("source_url"):
            evidence.append(
                {
                    "finding_id": primary.get("id"),
                    "run_date": primary.get("run_date") or date,
                    "agent": primary.get("agent") or "",
                    "title": primary.get("title") or "",
                    "summary": primary.get("summary") or "",
                    "source_url": primary.get("source_url") or "",
                    "source_name": primary.get("source_name") or "",
                }
            )
        for arc_id_raw in case.get("arc_ids") or []:
            arc_id = normalize_slug(str(arc_id_raw))
            arc = arcs.setdefault(
                arc_id,
                {
                    "id": arc_id,
                    "title": arc_id.replace("-", " ").title(),
                    "summary": redact_sensitive_text(str(case.get("why_now") or "")),
                    "status": "active",
                    "first_seen": date,
                    "last_seen": date,
                    "evidence": [],
                    "scores": {
                        "recurrence": 0.5,
                        "velocity": 0.5,
                        "source_diversity": 0.5,
                        "freshness": 1.0,
                        "confidence": 0.8,
                    },
                },
            )
            arc["evidence"].extend(evidence)

    public_arcs = []
    for arc in arcs.values():
        evidence = arc["evidence"]
        domains = {
            urlparse(str(item.get("source_url") or "")).netloc.lower().removeprefix("www.")
            for item in evidence
            if item.get("source_url")
        }
        agents = {str(item.get("agent") or "") for item in evidence if item.get("agent")}
        dates = {str(item.get("run_date") or "") for item in evidence if item.get("run_date")}
        arc.update(
            {
                "evidence_count": len(evidence),
                "date_count": max(1, len(dates)),
                "source_domain_count": len(domains),
                "agent_count": len(agents),
            }
        )
        public_arcs.append(arc)

    return {
        "date": date,
        "user": user,
        "arcs": sorted(public_arcs, key=lambda item: item["id"]),
        "rejected": [],
        "summary": {
            "accepted_count": len(public_arcs),
            "rejected_count": 0,
            "input_count": len(cases),
            "candidate_count": len(public_arcs),
        },
    }

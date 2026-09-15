"""Synthetic files for isolated dashboard verification."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

FIXTURE_DATE = "2026-07-01"
FIXTURE_USER = "ramsay"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def create_fixture(source_root: Path, scratch_root: Path) -> dict[str, str]:
    reports_root = scratch_root / "reports"
    story_root = reports_root / FIXTURE_USER / "site-stories" / FIXTURE_DATE
    run_root = reports_root / FIXTURE_USER / "site-runs"
    corpus_root = reports_root / FIXTURE_USER / "site-corpus"
    data_root = source_root / "data"
    db_path = data_root / FIXTURE_USER / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("SELECT 1").fetchone()

    story = {
        "kind": "site_story",
        "id": "verification-story",
        "slug": "verification-story",
        "status": "published",
        "confidence": "high",
        "issue_date": FIXTURE_DATE,
        "title": "Verification story exercises the public route",
        "dek": "A deterministic story used only by the verification toolkit.",
        "summary": "Verification confirms the published story contract.",
        "take": "The actual dashboard route decides whether this fixture is public.",
        "why_now": "The verifier needs a stable source-backed artifact.",
        "body_markdown": "Verification confirms the published story contract.",
        "source_refs": [{
            "url": "https://example.test/verification-story",
            "domain": "example.test",
            "title": "Verification source",
        }],
        "entity_refs": [{"id": "verification", "slug": "verification", "name": "Verification", "kind": "topic"}],
        "primary_finding_ids": [101],
        "supporting_finding_ids": [],
        "arc_ids": [],
        "graph_edges": [{
            "kind": "entity",
            "relationship": "same_entity",
            "id": "verification",
            "label": "Verification",
            "target_url": "/e/verification",
            "evidence": "finding:101",
        }],
        "related_paths": [],
        "claim_evidence": [{
            "claim": "The verification story passes the public content gate.",
            "source_url": "https://example.test/verification-story",
            "finding_id": 101,
        }],
        "provenance": {
            "generated_by": "mindpattern.verification.fixture",
            "generated_at": "2026-07-01T12:00:00+00:00",
            "input_artifacts": ["reports/ramsay/site-graph-packs/2026-07-01/verification-story.json"],
            "source_finding_ids": [101],
            "source_issue_dates": [FIXTURE_DATE],
            "redaction_status": "passed",
            "ai_generated": True,
            "human_approved": False,
        },
        "json_ld_ready": True,
    }
    _write_json(story_root / "verification-story.json", story)
    _write_json(story_root / "verification-draft.json", {
        **story,
        "id": "verification-draft",
        "slug": "verification-draft",
        "status": "draft",
        "title": "Verification draft must stay private",
    })
    _write_json(story_root / "verification-invalid.json", {
        **story,
        "id": "verification-invalid",
        "slug": "verification-invalid",
        "title": "Top 5 Stories Today",
    })
    _write_json(run_root / f"{FIXTURE_DATE}.json", {
        "kind": "site_run",
        "date": FIXTURE_DATE,
        "status": "completed",
        "generated_story_count": 1,
        "raw_slack_body": "fixture raw content must not leak",
        "summary": "Contact owner@verification.invalid token=fixture-token-must-not-leak",
    })
    _write_json(corpus_root / f"{FIXTURE_DATE}.json", {
        "kind": "site_corpus",
        "date": FIXTURE_DATE,
        "status": "ready",
        "counts": {"findings": 300, "entities": 14000, "edges": 42000},
        "coverage": {"has_embeddings": True},
        "subscriber_email": "reader@verification.invalid",
    })
    _write_json(source_root / "users.json", {
        "users": [{"id": FIXTURE_USER, "name": "Verification User", "email": "fixture-user@verification.invalid"}]
    })
    (reports_root / FIXTURE_USER).mkdir(parents=True, exist_ok=True)
    (source_root / "reports" / FIXTURE_USER).mkdir(parents=True, exist_ok=True)
    return {
        "date": FIXTURE_DATE,
        "user": FIXTURE_USER,
        "reports_root": str(reports_root),
        "data_root": str(data_root),
        "database": str(db_path),
    }

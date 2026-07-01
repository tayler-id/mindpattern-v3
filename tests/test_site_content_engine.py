import json
import sqlite3
from pathlib import Path

from orchestrator.site_content import is_publishable_site_story, site_artifact_path
from orchestrator.site_content_engine import (
    build_graph_pack,
    load_fixture_cases,
    run_site_content_dry_run,
    run_site_content_for_date,
    select_content_candidates,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "site_content" / "graph_pack_cases.json"


def test_fixture_cases_cover_public_content_machine_shapes():
    payload = load_fixture_cases(FIXTURE_PATH)
    case_types = {case["type"] for case in payload["cases"]}

    assert {
        "finding_story",
        "arc_update",
        "entity_dossier",
        "source_watch",
        "contrast_pair",
        "weak_input",
        "followup_update",
    } <= case_types
    serialized = json.dumps(payload).lower()
    assert "raw_slack_body" not in serialized
    assert "subscriber_email" not in serialized
    assert "xoxb-" not in serialized
    assert "sk-" not in serialized


def test_selector_ranks_public_usefulness_and_records_weak_inputs():
    payload = load_fixture_cases(FIXTURE_PATH)
    selection = select_content_candidates(payload["cases"], date="2026-07-01")

    assert selection["selected"][0]["id"] == "openai-agent-runtime-reliability"
    assert selection["selected"][0]["candidate_type"] == "finding_story"
    rejected = {item["id"]: item for item in selection["rejected"]}
    assert rejected["weak-parser-chunk"]["reason"] == "no_public_candidate"
    assert "missing_source_evidence" in rejected["weak-parser-chunk"]["reasons"]


def test_graph_pack_builder_bounds_evidence_without_model_calls():
    payload = load_fixture_cases(FIXTURE_PATH)
    candidate = next(case for case in payload["cases"] if case["id"] == "openai-agent-runtime-reliability")
    graph_pack = build_graph_pack(candidate, date="2026-07-01", user="ramsay")

    assert graph_pack["kind"] == "site_graph_pack"
    assert graph_pack["candidate_id"] == "openai-agent-runtime-reliability"
    assert graph_pack["primary_evidence"][0]["id"] == 101
    assert graph_pack["source_refs"][0]["domain"] == "openai.com"
    assert graph_pack["entity_refs"][0]["slug"] == "openai"
    assert graph_pack["related_paths"][0]["connector_labels"]
    assert graph_pack["claim_evidence_candidates"][0]["finding_id"] == 101
    assert graph_pack["provenance"]["provider"] == "deterministic"


def test_dry_run_writes_ledger_corpus_pack_candidate_and_story(tmp_path):
    reports_root = tmp_path / "reports"
    result = run_site_content_dry_run(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
        fixture_path=FIXTURE_PATH,
    )

    assert result["status"] == "completed"
    assert result["generated_story_count"] == 1
    assert result["degraded_story_count"] == 1

    run_path = site_artifact_path(kind="site_run", date="2026-07-01", user="ramsay", reports_root=reports_root)
    corpus_path = site_artifact_path(kind="site_corpus", date="2026-07-01", user="ramsay", reports_root=reports_root)
    candidate_path = site_artifact_path(
        kind="site_candidate",
        date="2026-07-01",
        slug="openai-agent-runtime-reliability",
        user="ramsay",
        reports_root=reports_root,
    )
    pack_path = site_artifact_path(
        kind="site_graph_pack",
        date="2026-07-01",
        slug="openai-agent-runtime-reliability",
        user="ramsay",
        reports_root=reports_root,
    )
    story_path = site_artifact_path(
        kind="site_story",
        date="2026-07-01",
        slug="openai-agent-runtime-reliability",
        user="ramsay",
        reports_root=reports_root,
    )
    weak_story_path = site_artifact_path(
        kind="site_story",
        date="2026-07-01",
        slug="weak-parser-chunk",
        user="ramsay",
        reports_root=reports_root,
    )
    arc_path = reports_root / "ramsay" / "arcs" / "2026-07-01.json"

    for path in (run_path, corpus_path, candidate_path, pack_path, story_path, weak_story_path):
        assert path.exists(), path
    assert arc_path.exists()

    story = json.loads(story_path.read_text())
    assert story["kind"] == "site_story"
    assert story["status"] == "published"
    assert story["confidence"] == "high"
    assert story["title"] != "Top 5 Stories Today"
    assert "**" not in story["title"] + story["dek"] + story["take"] + story["why_now"]
    assert is_publishable_site_story(story)

    weak_story = json.loads(weak_story_path.read_text())
    assert weak_story["status"] == "degraded"
    assert weak_story["confidence"] == "degraded"
    assert is_publishable_site_story(weak_story) is False
    assert "generic_section_title" in weak_story["rejection_reasons"]

    ledger = json.loads(run_path.read_text())
    assert ledger["kind"] == "site_run"
    assert ledger["inputs_scanned"]["fixture_cases"] >= 7
    assert ledger["artifacts_written"]
    assert ledger["rejections"][0]["reason"] == "no_public_candidate"

    corpus = json.loads(corpus_path.read_text())
    assert corpus["kind"] == "site_corpus"
    assert corpus["counts"]["candidate_cases"] >= 7
    assert corpus["counts"]["published_stories"] == 1

    arcs = json.loads(arc_path.read_text())
    assert arcs["arcs"][0]["id"] == "agent-runtime-control-plane"
    assert arcs["arcs"][0]["evidence"][0]["finding_id"] == 101


def test_corpus_run_writes_site_story_from_public_findings(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            agent TEXT,
            title TEXT,
            summary TEXT,
            importance TEXT,
            category TEXT,
            source_url TEXT,
            source_name TEXT,
            created_at TEXT
        );
        CREATE TABLE entity_graph (
            entity_a TEXT,
            entity_a_type TEXT,
            entity_b TEXT,
            entity_b_type TEXT,
            relationship TEXT,
            strength REAL,
            evidence TEXT,
            finding_id INTEGER,
            run_date TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO findings (
            id, run_date, agent, title, summary, importance, category,
            source_url, source_name, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                501,
                "2026-07-01",
                "agents-researcher",
                "OpenAI runtime control plane outage changes agent deployment risk",
                "OpenAI published runtime controls after an outage exposed reliability dependencies for agent builders.",
                "high",
                "agents",
                "https://openai.com/news/agent-runtime",
                "OpenAI",
                "2026-07-01T08:00:00",
            ),
            (
                502,
                "2026-07-01",
                "infra-researcher",
                "Agent runtime observability becomes required for production deployments",
                "Teams are adding tracing, retries, and fallback controls around long-running agent jobs.",
                "medium",
                "infrastructure",
                "https://example.com/agent-observability",
                "Example Research",
                "2026-07-01T09:00:00",
            ),
        ],
    )
    conn.execute(
        """
        INSERT INTO entity_graph (
            entity_a, entity_a_type, entity_b, entity_b_type, relationship,
            strength, evidence, finding_id, run_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "OpenAI",
            "company",
            "Agent runtime",
            "topic",
            "operates",
            0.9,
            "Source-backed finding links OpenAI to agent runtime controls.",
            501,
            "2026-07-01",
        ),
    )
    conn.commit()

    reports_root = tmp_path / "reports"
    result = run_site_content_for_date(
        date="2026-07-01",
        user="ramsay",
        reports_root=reports_root,
        conn=conn,
        max_stories=2,
    )

    assert result["status"] == "completed"
    assert result["mode"] == "corpus_deterministic"
    assert result["inputs_scanned"]["findings"] == 2
    assert result["generated_story_count"] >= 1
    assert result["degraded_story_count"] == 0
    assert result["provenance"]["newsletter_mutated"] is False

    story_path = site_artifact_path(
        kind="site_story",
        date="2026-07-01",
        slug="openai-runtime-control-plane-outage-changes-agent-deployment-risk",
        user="ramsay",
        reports_root=reports_root,
    )
    pack_path = site_artifact_path(
        kind="site_graph_pack",
        date="2026-07-01",
        slug="openai-runtime-control-plane-outage-changes-agent-deployment-risk",
        user="ramsay",
        reports_root=reports_root,
    )
    assert story_path.exists()
    assert pack_path.exists()

    story = json.loads(story_path.read_text())
    assert story["status"] == "published"
    assert story["confidence"] == "high"
    assert story["primary_finding_ids"] == [501]
    assert story["source_refs"][0]["domain"] == "openai.com"
    assert story["entity_refs"]
    assert story["graph_edges"]
    assert story["claim_evidence"]
    assert is_publishable_site_story(story)

import json
from pathlib import Path

from orchestrator.runner import _balance_story_candidates


def _finding(
    finding_id,
    run_date,
    title,
    summary,
    *,
    agent="agent-a",
    source_name="Example",
    source_url=None,
    importance="high",
):
    return {
        "id": finding_id,
        "run_date": run_date,
        "agent": agent,
        "title": title,
        "summary": summary,
        "importance": importance,
        "source_name": source_name,
        "source_url": source_url or f"https://{source_name.lower()}.example/{finding_id}",
    }


def _arc_fixture_findings():
    return [
        _finding(
            1,
            "2026-06-26",
            "AI IDEs shift from autocomplete to background agents",
            "Cursor and Claude Code are moving IDE work toward agent workflows.",
            agent="vibe-coding-researcher",
            source_name="GitHub",
        ),
        _finding(
            2,
            "2026-06-27",
            "Agent IDE workflows become the new coding surface",
            "Developer tools are consolidating around background coding agents.",
            agent="saas-disruption-researcher",
            source_name="Hacker News",
        ),
        _finding(
            3,
            "2026-06-28",
            "Coding agents move from sidecars into the IDE",
            "The IDE is becoming the control plane for autonomous agent work.",
            agent="vibe-coding-researcher",
            source_name="RSS",
        ),
        _finding(
            4,
            "2026-06-28",
            "Duplicate: AI IDEs shift from autocomplete to background agents",
            "Same-day duplicate coverage of IDE agent workflows.",
            agent="duplicate-agent",
            source_name="RSS",
        ),
        _finding(
            5,
            "2026-06-28",
            "Unrelated GPU pricing update",
            "Cloud GPU spot prices changed for training workloads.",
            agent="infra-researcher",
            source_name="Vendor Blog",
        ),
    ]


def test_build_narrative_arcs_returns_stable_source_backed_arcs(tmp_path):
    from orchestrator.arcs import build_narrative_arcs

    result_a = build_narrative_arcs(
        _arc_fixture_findings(),
        date="2026-06-28",
        artifact_root=tmp_path,
        user="ramsay",
        write_artifact=False,
    )
    result_b = build_narrative_arcs(
        list(reversed(_arc_fixture_findings())),
        date="2026-06-28",
        artifact_root=tmp_path,
        user="ramsay",
        write_artifact=False,
    )

    assert result_a["summary"]["accepted_count"] == 1
    assert result_a["summary"]["rejected_count"] >= 1
    arc = result_a["arcs"][0]

    assert arc["id"] == result_b["arcs"][0]["id"]
    assert arc["status"] == "active"
    assert arc["evidence_count"] >= 3
    assert arc["date_count"] >= 2
    assert arc["source_domain_count"] >= 2
    assert arc["scores"]["source_diversity"] > 0
    assert arc["scores"]["freshness"] > 0
    assert {item["finding_id"] for item in arc["evidence"]} >= {1, 2, 3}
    assert "raw_slack_body" not in json.dumps(arc)


def test_single_day_duplicates_do_not_become_arcs(tmp_path):
    from orchestrator.arcs import build_narrative_arcs

    duplicate_findings = [
        _finding(
            10 + idx,
            "2026-06-28",
            "MCP security prompt injection disclosure",
            "Multiple writeups describe MCP security prompt injection controls.",
            agent=f"agent-{idx}",
            source_name=f"Source {idx}",
        )
        for idx in range(4)
    ]

    result = build_narrative_arcs(
        duplicate_findings,
        date="2026-06-28",
        artifact_root=tmp_path,
        user="ramsay",
        write_artifact=False,
    )

    assert result["arcs"] == []
    assert any(
        rejected["reason"] == "single_day_only"
        for rejected in result["rejected"]
    )


def test_stale_arc_is_marked_stale_not_active(tmp_path):
    from orchestrator.arcs import build_narrative_arcs

    stale_findings = [
        _finding(
            20,
            "2026-06-01",
            "Agent governance becomes a product category",
            "Multiple vendors packaged agent governance controls.",
            agent="governance-agent",
            source_name="Analyst",
        ),
        _finding(
            21,
            "2026-06-03",
            "Agent governance tooling consolidates",
            "Security vendors are bundling policy controls for agents.",
            agent="security-agent",
            source_name="Security Blog",
        ),
        _finding(
            22,
            "2026-06-05",
            "Agent governance product category gets funding",
            "A funding round validates governance as a new agent category.",
            agent="market-agent",
            source_name="Tech Press",
        ),
    ]

    result = build_narrative_arcs(
        stale_findings,
        date="2026-06-28",
        artifact_root=tmp_path,
        user="ramsay",
        write_artifact=False,
    )

    assert len(result["arcs"]) == 1
    assert result["arcs"][0]["status"] == "stale"
    assert result["arcs"][0]["scores"]["freshness"] == 0


def test_write_narrative_arcs_artifact_under_reports_path(tmp_path):
    from orchestrator.arcs import build_narrative_arcs

    result = build_narrative_arcs(
        _arc_fixture_findings(),
        date="2026-06-28",
        artifact_root=tmp_path,
        user="ramsay",
        write_artifact=True,
    )

    artifact = tmp_path / "ramsay" / "arcs" / "2026-06-28.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text())

    assert payload["date"] == "2026-06-28"
    assert payload["arcs"][0]["id"] == result["arcs"][0]["id"]
    assert payload["summary"]["accepted_count"] == 1


def test_story_candidate_balance_is_identical_with_arc_artifacts(tmp_path):
    from orchestrator.arcs import build_narrative_arcs

    findings = _arc_fixture_findings()
    without_arcs, _ = _balance_story_candidates(
        findings,
        {"source_health_summary": {"responsive_source_count": 3}},
    )

    build_narrative_arcs(
        findings,
        date="2026-06-28",
        artifact_root=tmp_path,
        user="ramsay",
        write_artifact=True,
    )

    with_arcs, _ = _balance_story_candidates(
        findings,
        {"source_health_summary": {"responsive_source_count": 3}},
    )

    assert [finding["id"] for finding in with_arcs] == [
        finding["id"] for finding in without_arcs
    ]

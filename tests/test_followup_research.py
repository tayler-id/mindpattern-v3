"""Tests for Slack-triggered follow-up research.

The feature must stay separate from the daily runner: tests here use dry-run
and injected agent boundaries so they never call Claude, Slack, network, social
posting, email, Fly, or private local databases.
"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from orchestrator.traces_db import init_db


def test_parse_followup_request_accepts_supported_prefixes():
    from orchestrator.followup import parse_followup_request

    cases = [
        "follow up: compare agent-reach and opencli for social search",
        "follow-up: compare agent-reach and opencli for social search",
        "research this: compare agent-reach and opencli for social search",
    ]

    for text in cases:
        request = parse_followup_request(text, channel_type="briefing")

        assert request is not None
        assert request["error"] is None
        assert request["query"] == "compare agent-reach and opencli for social search"
        assert request["source"] == "slack"
        assert request["channel_type"] == "briefing"
        assert request["query_hash"].startswith("sha256:")
        assert len(request["query_preview"]) <= 120


def test_parse_followup_request_rejects_vague_or_non_commands():
    from orchestrator.followup import parse_followup_request

    assert parse_followup_request("what about this?") is None

    request = parse_followup_request("follow up: more")

    assert request is not None
    assert request["query"] == ""
    assert "specific" in request["error"].lower()


def test_parse_followup_request_redacts_sensitive_preview_text():
    from orchestrator.followup import parse_followup_request

    request = parse_followup_request(
        "follow up: investigate token xoxb-123-secret and api key sk-test-secret"
    )

    assert request is not None
    assert "xoxb-123-secret" not in request["query_preview"]
    assert "sk-test-secret" not in request["query_preview"]
    assert "[redacted]" in request["query_preview"]


def test_dry_run_followup_returns_findings_without_agent_calls(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    request = parse_followup_request(
        "follow up: compare agent-reach and opencli for social search"
    )
    agent_runner = MagicMock()

    result = run_followup_research(
        request,
        dry_run=True,
        agent_runner=agent_runner,
        artifact_dir=tmp_path / "followups",
    )

    agent_runner.assert_not_called()
    assert result["status"] == "completed"
    assert result["mode"] == "dry_run"
    assert 3 <= len(result["findings"]) <= 7
    assert result["why_this_matters"]
    assert result["next_action"]
    assert result["artifact"]
    assert Path(result["artifact"]).exists()


def test_disable_outbound_forces_dry_run_without_default_agent(tmp_path, monkeypatch):
    from orchestrator.followup import parse_followup_request, run_followup_research

    monkeypatch.setenv("MP_DISABLE_OUTBOUND", "1")
    request = parse_followup_request(
        "follow up: compare agent-reach and opencli for social search"
    )

    with patch("orchestrator.followup._default_agent_runner") as default_runner:
        result = run_followup_research(
            request,
            dry_run=None,
            artifact_dir=tmp_path / "followups",
        )

    default_runner.assert_not_called()
    assert result["mode"] == "dry_run"
    assert result["status"] == "completed"


def test_followup_service_has_no_runner_delivery_social_or_fly_imports():
    source = Path("orchestrator/followup.py").read_text()
    tree = ast.parse(source)
    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)

    forbidden_imports = {
        "run",
        "orchestrator.runner",
        "orchestrator.newsletter",
        "social.pipeline",
        "social.posting",
        "social.approval",
    }
    forbidden_tokens = {
        "run.py",
        "send_newsletter",
        "send_email",
        "sync_to_fly",
        "sync_data_to_fly",
        "flyctl",
        "BlueskyClient",
        "LinkedInClient",
        "post_to_platforms",
    }

    assert imports.isdisjoint(forbidden_imports)
    for token in forbidden_tokens:
        assert token not in source


def test_followup_logs_safe_trace_and_artifact(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    traces_conn = init_db(tmp_path / "traces.db")
    request = parse_followup_request(
        "follow up: investigate token xoxb-123-secret in Slack thread"
    )

    result = run_followup_research(
        request,
        dry_run=True,
        traces_conn=traces_conn,
        artifact_dir=tmp_path / "followups",
    )

    row = traces_conn.execute(
        "SELECT event_type, payload FROM events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    traces_conn.close()

    assert row is not None
    assert row["event_type"] == "followup_research_complete"
    payload = json.loads(row["payload"])
    payload_json = json.dumps(payload)
    artifact_text = Path(result["artifact"]).read_text()

    assert payload["query_hash"].startswith("sha256:")
    assert "xoxb-123-secret" not in payload_json
    assert "xoxb-123-secret" not in artifact_text
    assert "Slack thread" in artifact_text


def test_live_agent_failure_returns_visible_degraded_result(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    request = parse_followup_request(
        "follow up: compare agent-reach and opencli for social search"
    )

    def failing_agent_runner(*_args, **_kwargs):
        raise RuntimeError("simulated agent outage")

    result = run_followup_research(
        request,
        dry_run=False,
        agent_runner=failing_agent_runner,
        artifact_dir=tmp_path / "followups",
    )

    assert result["status"] == "failed"
    assert result["degraded"] is True
    assert result["findings"] == []
    assert "failed" in result["why_this_matters"].lower()
    assert result["artifact"]
    assert Path(result["artifact"]).exists()


def test_live_followup_fans_out_to_multiple_research_agents(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    request = parse_followup_request(
        "follow up: why agent-reach matters for social search reliability"
    )
    calls = []

    def fake_agent_runner(agent_name, prompt, **_kwargs):
        calls.append((agent_name, prompt))
        return {
            "findings": [
                {
                    "title": f"Finding from {agent_name}",
                    "summary": f"{agent_name} found fresh context beyond current stored findings.",
                    "source_name": agent_name,
                }
            ],
            "next_action": "Compare the agent outputs.",
        }

    result = run_followup_research(
        request,
        dry_run=False,
        agent_runner=fake_agent_runner,
        artifact_dir=tmp_path / "followups",
    )

    called_agents = {name for name, _prompt in calls}
    assert called_agents == {
        "followup-web-researcher",
        "followup-social-researcher",
        "followup-technical-researcher",
        "followup-skeptic-researcher",
    }
    assert all("Do not summarize only existing MindPattern findings" in prompt for _name, prompt in calls)
    assert result["status"] == "completed"
    assert result["mode"] == "live"
    assert result["agent_count"] == 4
    assert result["successful_agent_count"] == 4
    assert len(result["findings"]) == 4
    assert {finding["agent"] for finding in result["findings"]} == called_agents


def test_live_followup_degrades_when_one_agent_fails_but_uses_others(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    request = parse_followup_request(
        "follow up: why agent-reach matters for social search reliability"
    )

    def mixed_agent_runner(agent_name, *_args, **_kwargs):
        if agent_name == "followup-social-researcher":
            raise RuntimeError("reddit backend unavailable")
        return {
            "findings": [
                {
                    "title": f"Finding from {agent_name}",
                    "summary": "Usable research survived a partial backend failure.",
                    "source_name": agent_name,
                }
            ]
        }

    result = run_followup_research(
        request,
        dry_run=False,
        agent_runner=mixed_agent_runner,
        artifact_dir=tmp_path / "followups",
    )

    assert result["status"] == "completed"
    assert result["degraded"] is True
    assert result["agent_count"] == 4
    assert result["successful_agent_count"] == 3
    assert result["failed_agent_count"] == 1
    assert len(result["findings"]) == 3
    assert "followup-social-researcher" in result["errors"][0]


def test_live_agent_result_parses_raw_json_output(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    request = parse_followup_request(
        "follow up: why agent-reach matters for social search reliability"
    )
    raw_output = json.dumps({
        "findings": [
            {
                "title": "Agent Reach keeps source access modular",
                "summary": "It routes social search through available backends instead of hard-coding one fragile provider.",
                "source_name": "Agent Reach",
                "source_url": None,
            }
        ],
        "next_action": "Turn this into a short social reliability note.",
    })

    result = run_followup_research(
        request,
        dry_run=False,
        agent_runner=lambda *_args, **_kwargs: SimpleNamespace(
            findings=[],
            raw_output=f"Here is the result:\n{raw_output}\n",
        ),
        artifact_dir=tmp_path / "followups",
    )

    assert result["status"] == "completed"
    assert result["findings"][0]["title"] == "Agent Reach keeps source access modular"
    assert result["next_action"] == "Turn this into a short social reliability note."


def test_live_agent_result_falls_back_to_raw_text_finding(tmp_path):
    from orchestrator.followup import parse_followup_request, run_followup_research

    request = parse_followup_request(
        "follow up: why agent-reach matters for social search reliability"
    )

    result = run_followup_research(
        request,
        dry_run=False,
        agent_runner=lambda *_args, **_kwargs: SimpleNamespace(
            findings=[],
            raw_output="Agent Reach matters because it lets the system swap search backends when one source degrades.",
        ),
        artifact_dir=tmp_path / "followups",
    )

    assert result["status"] == "completed"
    assert result["findings"][0]["title"] == "Follow-up response"
    assert "swap search backends" in result["findings"][0]["summary"]


def test_parse_followup_action_maps_owner_workflow_commands():
    from orchestrator.followup import parse_followup_action

    assert parse_followup_action("cover") == "cover"
    assert parse_followup_action("cover tomorrow") == "cover"
    assert parse_followup_action("draft") == "draft"
    assert parse_followup_action("social draft") == "draft"
    assert parse_followup_action("archive") == "archive"
    assert parse_followup_action("save") == "archive"
    assert parse_followup_action("ignore") == "ignore"
    assert parse_followup_action("skip") is None
    assert parse_followup_action("maybe later") is None


def test_cover_action_saves_next_day_candidate_findings_and_graph_links(tmp_path):
    import memory
    from orchestrator.followup import apply_followup_action

    db = memory.get_db(tmp_path / "memory.db")
    result = {
        "query_hash": "sha256:test",
        "query_preview": "agent reach social reliability",
        "artifact": "reports/ramsay/followups/example.md",
        "findings": [
            {
                "agent": "followup-web-researcher",
                "title": "Agent Reach routes social search",
                "summary": "It lets the system swap backends when one source fails.",
                "source_name": "Agent Reach",
                "source_url": "https://example.com/agent-reach",
            }
        ],
    }

    with patch("memory.findings.embed_text", return_value=[0.0] * 384):
        action_result = apply_followup_action(
            result,
            "cover",
            db=db,
            today="2026-06-26",
        )

    assert action_result["status"] == "completed"
    assert action_result["action"] == "cover"
    assert action_result["run_date"] == "2026-06-27"
    assert action_result["finding_count"] == 1
    assert action_result["relationship_count"] == 3

    row = db.execute(
        "SELECT run_date, agent, title, importance, category, summary FROM findings"
    ).fetchone()
    assert row["run_date"] == "2026-06-27"
    assert row["agent"] == "followup-cover-candidate"
    assert row["importance"] == "high"
    assert row["category"] == "followup_cover_candidate"
    assert "Follow-up query: agent reach social reliability" in row["summary"]

    graph_count = db.execute(
        "SELECT COUNT(*) AS c FROM entity_graph WHERE finding_id = ?",
        (action_result["finding_ids"][0],),
    ).fetchone()["c"]
    db.close()
    assert graph_count == 3


def test_archive_action_saves_followup_to_memory_and_working_entity_graph(tmp_path):
    import memory
    from orchestrator.followup import apply_followup_action

    db = memory.get_db(tmp_path / "memory.db")
    result = {
        "query_hash": "sha256:test",
        "query_preview": "agent reach social reliability",
        "artifact": "reports/ramsay/followups/example.md",
        "findings": [
            {
                "agent": "followup-social-researcher",
                "title": "Reddit auth restores social signal",
                "summary": "Authenticated Reddit access helps avoid zero-source research.",
                "source_name": "Reddit",
            }
        ],
    }

    with patch("memory.findings.embed_text", return_value=[0.0] * 384):
        action_result = apply_followup_action(
            result,
            "archive",
            db=db,
            today="2026-06-26",
        )

    assert action_result["status"] == "completed"
    assert action_result["action"] == "archive"
    assert action_result["run_date"] == "2026-06-26"
    assert action_result["finding_count"] == 1

    finding = db.execute(
        "SELECT agent, category, importance FROM findings"
    ).fetchone()
    assert finding["agent"] == "followup-social-researcher"
    assert finding["category"] == "followup_archive"
    assert finding["importance"] == "medium"

    relationships = db.execute(
        "SELECT entity_a, relationship, entity_b FROM entity_graph ORDER BY id"
    ).fetchall()
    db.close()
    assert any(r["entity_a"] == "Follow-Up Research" for r in relationships)
    assert any(r["entity_a"] == "Reddit" for r in relationships)

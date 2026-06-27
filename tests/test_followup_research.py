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

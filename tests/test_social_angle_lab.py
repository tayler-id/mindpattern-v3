import ast
import json
from pathlib import Path


def test_parse_social_angle_request_accepts_supported_commands():
    from orchestrator.social_angles import parse_social_angle_request

    topic = parse_social_angle_request(
        "angles: why agent-reach matters for social search reliability",
        channel_type="posts",
    )
    url = parse_social_angle_request("angle lab: https://example.com/story")
    finding = parse_social_angle_request("angles finding 123")
    arc = parse_social_angle_request("angles arc ai-ides-consolidate-abc12345")

    assert topic["error"] is None
    assert topic["source_type"] == "topic"
    assert topic["query"] == "why agent-reach matters for social search reliability"
    assert topic["channel_type"] == "posts"
    assert topic["request_hash"].startswith("sha256:")

    assert url["source_type"] == "url"
    assert url["url"] == "https://example.com/story"
    assert finding["source_type"] == "finding"
    assert finding["finding_id"] == 123
    assert arc["source_type"] == "arc"
    assert arc["arc_id"] == "ai-ides-consolidate-abc12345"


def test_parse_social_angle_request_rejects_unclear_and_newsletter_control_text():
    from orchestrator.social_angles import parse_social_angle_request

    assert parse_social_angle_request("what should we post?") is None

    empty = parse_social_angle_request("angles:")
    vague = parse_social_angle_request("angles: more")
    bad_finding = parse_social_angle_request("angles finding tomorrow")
    bad_arc = parse_social_angle_request("angles arc ../../users")
    newsletter = parse_social_angle_request("angles: send newsletter today")

    assert "specific" in empty["error"].lower()
    assert "specific" in vague["error"].lower()
    assert "finding" in bad_finding["error"].lower()
    assert "arc" in bad_arc["error"].lower()
    assert "newsletter" in newsletter["error"].lower()
    assert newsletter["query"] == ""


def test_parse_social_angle_request_redacts_sensitive_text():
    from orchestrator.social_angles import parse_social_angle_request

    slack_marker = "".join(["xo", "xb", "-123", "-fixture"])
    openai_marker = "".join(["s", "k", "-test", "-fixture"])
    request = parse_social_angle_request(
        f"angles: investigate credential {slack_marker} and key {openai_marker}"
    )

    assert request["error"] is None
    assert slack_marker not in json.dumps(request)
    assert openai_marker not in json.dumps(request)
    assert "[redacted]" in request["query"]
    assert "[redacted]" in request["query_preview"]


def test_social_angle_artifact_path_is_reports_only(tmp_path):
    from orchestrator.social_angles import social_angles_artifact_path

    path = social_angles_artifact_path(
        date="2026-06-28",
        user="ramsay",
        reports_root=tmp_path,
    )

    assert path == tmp_path / "ramsay" / "social-angles" / "2026-06-28.json"
    assert "data/social-angles" not in str(path)

    for kwargs in (
        {"date": "../../users", "user": "ramsay"},
        {"date": "2026-06-28", "user": "../ramsay"},
    ):
        try:
            social_angles_artifact_path(reports_root=tmp_path, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe social angle artifact path was accepted")


def test_social_angle_candidate_public_contract_is_stable_and_safe():
    from orchestrator.social_angles import SocialAngleCandidate

    angle = SocialAngleCandidate(
        angle_id="angle_1",
        angle_type="builder_lesson",
        platform="linkedin",
        hook="Agent Reach exposes why source reliability matters.",
        thesis="The real story is not search volume; it is trustworthy coverage.",
        source_urls=["https://example.com/source", "file:///private/db"],
        confidence=1.5,
        risk_note="Email tayler@example.com before posting.",
        verdict="keep",
    )

    public = angle.to_public_dict()

    assert public == {
        "angle_id": "angle_1",
        "angle_type": "builder_lesson",
        "platform": "linkedin",
        "hook": "Agent Reach exposes why source reliability matters.",
        "thesis": "The real story is not search volume; it is trustworthy coverage.",
        "source_urls": ["https://example.com/source"],
        "confidence": 1.0,
        "risk_note": "Email [redacted] before posting.",
        "verdict": "keep",
    }


def test_social_prompt_files_share_approved_builder_detail_boundary():
    from social.writers import _build_writer_agent_prompt

    prompt = _build_writer_agent_prompt(
        "linkedin",
        {
            "anchor": "Example source-backed story",
            "reaction": "A practical workflow changed.",
            "confidence": "HIGH",
            "do_not_include": [],
        },
    )
    prompt_files = {
        "agents/expeditor.md": Path("agents/expeditor.md").read_text(),
        "agents/linkedin-writer.md": Path("agents/linkedin-writer.md").read_text(),
        "agents/bluesky-writer.md": Path("agents/bluesky-writer.md").read_text(),
        "agents/eic.md": Path("agents/eic.md").read_text(),
        "agents/linkedin-critic.md": Path("agents/linkedin-critic.md").read_text(),
        "agents/bluesky-critic.md": Path("agents/bluesky-critic.md").read_text(),
    }

    for text in [prompt, *prompt_files.values()]:
        assert "Approved builder-detail boundary" in text
        assert "in my own research workflow" in text
        assert "agent counts, cron/pipeline flexing" in text
        assert "I run 12 agents" not in text
        assert "my pipeline flagged" not in text
        assert "my morning cron" not in text
        assert "builder transparency is ENCOURAGED" not in text
        assert "Missing builder detail" not in text


def test_generate_social_angles_dry_run_writes_ranked_artifact(tmp_path):
    from orchestrator.social_angles import (
        generate_social_angles,
        parse_social_angle_request,
    )

    request = parse_social_angle_request(
        "angles: https://example.com/agent-reach-social-search"
    )

    result = generate_social_angles(
        request,
        date="2026-06-28",
        user="ramsay",
        reports_root=tmp_path,
        dry_run=True,
        source_context={
            "title": "Agent Reach restores social search reliability",
            "summary": "X, Reddit, YouTube, and Exa coverage make research less brittle.",
            "source_urls": ["https://example.com/agent-reach-social-search"],
        },
    )

    assert result["status"] == "completed"
    assert result["mode"] == "dry_run"
    assert result["summary"]["generated_count"] == 6
    assert result["summary"]["shown_count"] >= 3
    assert all(angle["verdict"] in {"keep", "revise"} for angle in result["shown_angles"])
    assert result["shown_angles"] == sorted(
        result["shown_angles"], key=lambda item: item["score"], reverse=True
    )
    assert result["artifact"]
    artifact = Path(result["artifact"])
    assert artifact == tmp_path / "ramsay" / "social-angles" / "2026-06-28.json"
    payload = json.loads(artifact.read_text())
    assert payload["summary"]["generated_count"] == 6
    assert any(angle["verdict"] == "reject" for angle in payload["angles"])
    assert "data/social-angles" not in str(artifact)


def test_angle_critic_rejects_product_pitch_and_unsupported_claims():
    from orchestrator.social_angles import SocialAngleCandidate, critique_social_angle

    angle = SocialAngleCandidate(
        angle_id="angle_99",
        angle_type="market_take",
        platform="linkedin",
        hook="Powered by MindPattern, AI is changing everything.",
        thesis="Try MindPattern because every team needs this now.",
        source_urls=[],
        confidence=0.9,
        risk_note="Unsupported product demo.",
    )

    critique = critique_social_angle(angle)

    assert critique["verdict"] == "reject"
    assert "product_pitch_framing" in critique["kill_switches"]
    assert "no_source_backed_evidence" in critique["kill_switches"]
    assert "generic_ai_framing" in critique["kill_switches"]


def test_angle_generation_provider_boundary_is_injectable_and_fails_to_dry_run(tmp_path):
    from unittest.mock import MagicMock

    from orchestrator.social_angles import generate_social_angles, parse_social_angle_request

    request = parse_social_angle_request("angles: https://example.com/story")
    provider = MagicMock(
        return_value=[
            {
                "angle_id": "provider_1",
                "angle_type": "builder_lesson",
                "platform": "linkedin",
                "hook": "A source-backed builder lesson from the story.",
                "thesis": "The useful lesson is to check source reliability before drafting.",
                "source_urls": ["https://example.com/story"],
                "confidence": 0.8,
                "risk_note": "Needs careful source framing.",
            }
        ]
    )

    live_result = generate_social_angles(
        request,
        date="2026-06-28",
        user="ramsay",
        reports_root=tmp_path,
        dry_run=False,
        angle_provider=provider,
        write_artifact=False,
    )
    fallback_result = generate_social_angles(
        request,
        date="2026-06-28",
        user="ramsay",
        reports_root=tmp_path,
        dry_run=False,
        angle_provider=None,
        write_artifact=False,
    )

    provider.assert_called_once()
    assert live_result["mode"] == "provider"
    assert live_result["summary"]["generated_count"] == 1
    assert fallback_result["mode"] == "dry_run"
    assert fallback_result["summary"]["generated_count"] == 6


def test_social_angle_contract_module_has_no_live_side_effect_imports():
    source = Path("orchestrator/social_angles.py").read_text()
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
        "slack_bot",
        "social.pipeline",
        "social.posting",
        "social.approval",
    }
    forbidden_call_markers = {
        "run.py",
        "send_newsletter",
        "send_email",
        "sync_to_fly",
        "flyctl",
        "chat.postMessage",
        "BlueskyClient",
        "LinkedInClient",
        "post_to_platforms",
    }

    assert imports.isdisjoint(forbidden_imports)
    for marker in forbidden_call_markers:
        assert marker not in source

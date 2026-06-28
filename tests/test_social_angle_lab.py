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

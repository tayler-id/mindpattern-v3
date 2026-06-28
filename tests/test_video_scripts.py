import ast
import json
from pathlib import Path


def test_parse_video_script_request_accepts_supported_commands():
    from orchestrator.video_scripts import parse_video_script_request

    topic = parse_video_script_request(
        "video script: why agent-reach matters for social search reliability",
        channel_type="posts",
    )
    url = parse_video_script_request("video script: https://example.com/story")
    finding = parse_video_script_request("video finding 123")
    arc = parse_video_script_request("video arc ai-ides-consolidate-abc12345")
    angle = parse_video_script_request("video angle 2")

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
    assert angle["source_type"] == "angle"
    assert angle["angle_index"] == 2


def test_parse_video_script_request_rejects_unclear_and_live_post_text():
    from orchestrator.video_scripts import parse_video_script_request

    assert parse_video_script_request("make a video") is None

    empty = parse_video_script_request("video script:")
    vague = parse_video_script_request("video script: more")
    bad_finding = parse_video_script_request("video finding tomorrow")
    bad_arc = parse_video_script_request("video arc ../../users")
    bad_angle = parse_video_script_request("video angle 0")
    live_post = parse_video_script_request("video script: post this live to TikTok")
    newsletter = parse_video_script_request("video script: send the newsletter story")

    assert "specific" in empty["error"].lower()
    assert "specific" in vague["error"].lower()
    assert "finding" in bad_finding["error"].lower()
    assert "arc" in bad_arc["error"].lower()
    assert "angle" in bad_angle["error"].lower()
    assert "manual publish" in live_post["error"].lower()
    assert "newsletter" in newsletter["error"].lower()
    assert live_post["query"] == ""


def test_parse_video_script_request_redacts_sensitive_text():
    from orchestrator.video_scripts import parse_video_script_request

    slack_marker = "".join(["xo", "xb", "-123", "-fixture"])
    openai_marker = "".join(["s", "k", "-test", "-fixture"])
    request = parse_video_script_request(
        f"video script: explain credential {slack_marker} and key {openai_marker}"
    )

    request_json = json.dumps(request)
    assert request["error"] is None
    assert slack_marker not in request_json
    assert openai_marker not in request_json
    assert "[redacted]" in request["query"]
    assert "[redacted]" in request["query_preview"]


def test_video_script_package_public_contract_is_stable_and_safe():
    from orchestrator.video_scripts import VideoScriptPackage

    package = VideoScriptPackage(
        package_id="pkg_1",
        date="2026-06-28",
        source_type="finding",
        source_ref="finding:123",
        duration_seconds=45,
        hook="Agent Reach changed the source reliability story.",
        spoken_script="Email tayler@example.com before posting.",
        shot_list=["Show the workflow", "Show source checks"],
        captions=["Source reliability beats reach."],
        source_urls=["https://example.com/source", "file:///private/db"],
        labels=["AI-assisted script", "manual publish only"],
        risk_labels=["manual review"],
    )

    public = package.to_public_dict()

    assert public == {
        "package_id": "pkg_1",
        "date": "2026-06-28",
        "source_type": "finding",
        "source_ref": "finding:123",
        "duration_seconds": 45,
        "status": "ready",
        "hook": "Agent Reach changed the source reliability story.",
        "spoken_script": "Email [redacted] before posting.",
        "shot_list": ["Show the workflow", "Show source checks"],
        "captions": ["Source reliability beats reach."],
        "source_urls": ["https://example.com/source"],
        "labels": ["AI-assisted script", "manual publish only"],
        "risk_labels": ["manual review"],
    }


def test_video_scripts_module_has_no_provider_slack_runner_or_posting_imports():
    source = Path("orchestrator/video_scripts.py").read_text()
    tree = ast.parse(source)
    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)

    forbidden_imports = {
        "requests",
        "openai",
        "slack_bot",
        "orchestrator.runner",
        "orchestrator.newsletter",
        "social.posting",
    }
    forbidden_call_markers = {
        "send_newsletter",
        "chat.postMessage",
        "post_to_platforms",
        "generate_video",
        "flyctl",
    }

    assert imports.isdisjoint(forbidden_imports)
    for marker in forbidden_call_markers:
        assert marker not in source

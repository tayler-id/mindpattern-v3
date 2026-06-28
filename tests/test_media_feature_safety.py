"""Cross-feature safety regressions for media, angle, and Slack dry paths."""

import ast
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# slack_sdk is not installed in the focused test environment.
if "slack_sdk" not in sys.modules:
    slack_sdk_stub = MagicMock()
    sys.modules["slack_sdk"] = slack_sdk_stub
    sys.modules["slack_sdk.errors"] = MagicMock()


FEATURE_MODULES = [
    Path("orchestrator/arcs.py"),
    Path("orchestrator/social_angles.py"),
    Path("orchestrator/audio_briefing.py"),
    Path("orchestrator/video_scripts.py"),
]


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
            imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def test_media_feature_modules_have_no_outbound_or_deploy_side_effect_markers():
    forbidden_imports = {
        "requests",
        "httpx",
        "urllib.request",
        "slack_bot",
        "orchestrator.runner",
        "orchestrator.newsletter",
        "social.posting",
        "social.clients",
        "openai",
    }
    forbidden_markers = {
        "send_newsletter",
        "sync_to_fly",
        "sync_data_to_fly",
        "flyctl",
        "vercel",
        "chat_postMessage",
        "files_getUploadURLExternal",
        "files_completeUploadExternal",
        "post_to_platforms",
        "BlueskyClient",
        "LinkedInClient",
        "generate_video(",
    }

    for path in FEATURE_MODULES:
        source = path.read_text()
        assert _imports_for(path).isdisjoint(forbidden_imports), path
        for marker in forbidden_markers:
            assert marker not in source, f"{path} contains forbidden marker {marker}"


def test_slack_video_dry_path_does_not_post_upload_or_run_social_pipeline():
    from slack_bot.handlers.posts import PostsHandler

    client = MagicMock()
    handler = PostsHandler(client=client, channel_id="C_POSTS", owner_user_id="U_OWNER")
    handler.react = MagicMock()
    handler._run_and_approve = MagicMock()
    handler._post_to_platforms = MagicMock()
    handler._handle_url = MagicMock()
    handler._handle_idea = MagicMock()

    video_result = {
        "status": "ready",
        "package": {
            "duration_seconds": 45,
            "hook": "Source-backed hook.",
            "spoken_script": "A short source-backed script.",
            "shot_list": ["Open on the source."],
            "captions": ["Manual publish only."],
            "source_urls": ["https://example.com/story"],
            "labels": ["AI-assisted script", "manual publish only"],
            "risk_labels": ["source-backed"],
        },
        "artifacts": {"json": "/tmp/video.json", "markdown": "/tmp/video.md"},
        "recommendation": "Ready for Slack review.",
        "error": None,
    }

    with patch("slack_bot.handlers.posts.generate_video_script_package", return_value=video_result):
        handler.handle({"text": "video script: https://example.com/story", "ts": "123.456"})

    handler._run_and_approve.assert_not_called()
    handler._post_to_platforms.assert_not_called()
    handler._handle_url.assert_not_called()
    handler._handle_idea.assert_not_called()
    client.files_getUploadURLExternal.assert_not_called()
    client.files_completeUploadExternal.assert_not_called()
    client.files_upload.assert_not_called()
    assert "manual publish only" in client.chat_postMessage.call_args.kwargs["text"]


def test_unclear_social_angle_reply_changes_no_state_or_posting():
    from slack_bot.handlers.posts import PostsHandler

    client = MagicMock()
    handler = PostsHandler(client=client, channel_id="C_POSTS", owner_user_id="U_OWNER")
    handler.react = MagicMock()
    handler.wait_for_reply = MagicMock(return_value="please do it")
    handler._run_and_approve = MagicMock()
    handler._post_to_platforms = MagicMock()

    angle_result = {
        "status": "completed",
        "mode": "dry_run",
        "shown_angles": [
            {
                "angle_id": "angle_1",
                "angle_type": "builder_lesson",
                "platform": "linkedin",
                "hook": "Source-backed hook.",
                "thesis": "Source-backed thesis.",
                "source_urls": ["https://example.com/story"],
                "confidence": 0.8,
                "risk_note": "Source-backed.",
                "score": 8.0,
                "verdict": "keep",
            }
        ],
        "summary": {"generated_count": 1, "shown_count": 1, "rejected_count": 0},
        "artifact": "/tmp/social-angles.json",
        "request": {"query_preview": "source reliability"},
        "error": None,
    }

    with patch("slack_bot.handlers.posts.generate_social_angles", return_value=angle_result):
        handler.handle({"text": "angles: https://example.com/story", "ts": "123.456"})

    handler._run_and_approve.assert_not_called()
    handler._post_to_platforms.assert_not_called()
    messages = [call.kwargs["text"] for call in client.chat_postMessage.call_args_list]
    assert any("No draft action matched" in message for message in messages)
    assert all("Posting to:" not in message for message in messages)


def test_slack_file_helper_uses_mocked_upload_boundary_in_focused_tests():
    from slack_bot.files import upload_file_external

    client = MagicMock()
    client.files_getUploadURLExternal.return_value = {
        "ok": True,
        "upload_url": "https://files.slack.com/upload/v1/test",
        "file_id": "F123",
    }
    client.files_completeUploadExternal.return_value = {"ok": True, "files": []}

    with patch("slack_bot.files.urllib_request.urlopen") as urlopen:
        upload_file_external(
            client,
            channel_id="C_POSTS",
            thread_ts="1234567890.123456",
            content=b"script",
            filename="script.md",
            upload_post=MagicMock(return_value={"status": 200}),
        )

    urlopen.assert_not_called()


def test_media_public_outputs_redact_private_user_and_slack_data(tmp_path):
    from orchestrator.video_scripts import generate_video_script_package, parse_video_script_request

    request = parse_video_script_request("video script: https://example.com/story")
    result = generate_video_script_package(
        request,
        date="2026-06-28",
        reports_root=tmp_path,
        source_context={
            "title": "Slack note <@U123ABC> xoxb-123-secret",
            "summary": "Email owner@example.com and api_key=abc123 are private.",
            "source_urls": ["https://example.com/story?token=xoxb-123-secret"],
        },
    )
    public_payload = json.dumps(result)

    assert "xoxb" not in public_payload
    assert "owner@example.com" not in public_payload
    assert "<@U123ABC>" not in public_payload
    assert "api_key=abc123" not in public_payload
    assert "[redacted]" in public_payload

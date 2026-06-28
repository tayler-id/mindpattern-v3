"""Tests for Slack external file upload helper.

These tests mock Slack and the raw upload HTTP boundary. They must not make
network calls or require slack_sdk.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_external_upload_flow_uses_get_upload_raw_post_and_complete_parent_thread():
    from slack_bot.files import upload_file_external

    client = MagicMock()
    client.files_getUploadURLExternal.return_value = {
        "ok": True,
        "upload_url": "https://files.slack.com/upload/v1/test",
        "file_id": "F123",
    }
    client.files_completeUploadExternal.return_value = {
        "ok": True,
        "files": [{"id": "F123", "title": "Video script"}],
    }
    upload_post = MagicMock(return_value={"status": 200})

    result = upload_file_external(
        client,
        channel_id="C_POSTS",
        thread_ts="1234567890.123456",
        content=b"# Video script",
        filename="video-script.md",
        title="Video script",
        initial_comment="Script artifact",
        upload_post=upload_post,
    )

    client.files_getUploadURLExternal.assert_called_once_with(
        filename="video-script.md",
        length=len(b"# Video script"),
    )
    upload_post.assert_called_once_with(
        "https://files.slack.com/upload/v1/test",
        b"# Video script",
        "text/markdown; charset=utf-8",
    )
    client.files_completeUploadExternal.assert_called_once_with(
        files=[{"id": "F123", "title": "Video script"}],
        channel_id="C_POSTS",
        thread_ts="1234567890.123456",
        initial_comment="Script artifact",
    )
    assert result["ok"] is True
    assert result["file_id"] == "F123"
    assert result["bytes"] == len(b"# Video script")


def test_external_upload_never_uses_legacy_files_upload():
    from slack_bot.files import upload_file_external

    client = MagicMock()
    client.files_getUploadURLExternal.return_value = {
        "ok": True,
        "upload_url": "https://files.slack.com/upload/v1/test",
        "file_id": "F123",
    }
    client.files_completeUploadExternal.return_value = {"ok": True, "files": []}
    upload_post = MagicMock(return_value={"status": 200})

    upload_file_external(
        client,
        channel_id="C_POSTS",
        thread_ts="1234567890.123456",
        content=b"script",
        filename="video-script.md",
        upload_post=upload_post,
    )

    client.files_upload.assert_not_called()


def test_external_upload_requires_parent_thread_ts():
    from slack_bot.files import SlackFileUploadError, upload_file_external

    client = MagicMock()

    with pytest.raises(SlackFileUploadError, match="parent thread_ts"):
        upload_file_external(
            client,
            channel_id="C_POSTS",
            thread_ts="",
            content=b"script",
            filename="video-script.md",
            upload_post=MagicMock(),
        )

    client.files_getUploadURLExternal.assert_not_called()


def test_external_upload_stops_before_complete_when_raw_upload_fails():
    from slack_bot.files import SlackFileUploadError, upload_file_external

    client = MagicMock()
    client.files_getUploadURLExternal.return_value = {
        "ok": True,
        "upload_url": "https://files.slack.com/upload/v1/test",
        "file_id": "F123",
    }
    upload_post = MagicMock(return_value={"status": 503, "body": "temporary"})

    with pytest.raises(SlackFileUploadError, match="raw upload failed"):
        upload_file_external(
            client,
            channel_id="C_POSTS",
            thread_ts="1234567890.123456",
            content=b"script",
            filename="video-script.md",
            upload_post=upload_post,
        )

    client.files_completeUploadExternal.assert_not_called()


def test_failed_get_upload_mentions_files_write_scope_without_tokens():
    from slack_bot.files import SlackFileUploadError, upload_file_external

    client = MagicMock()
    client.files_getUploadURLExternal.return_value = {
        "ok": False,
        "error": "missing_scope",
        "needed": "files:write",
        "provided": "chat:write",
    }

    with pytest.raises(SlackFileUploadError) as exc:
        upload_file_external(
            client,
            channel_id="C_POSTS",
            thread_ts="1234567890.123456",
            content=b"script",
            filename="video-script.md",
            upload_post=MagicMock(),
        )

    message = str(exc.value)
    assert "files:write" in message
    assert "xox" not in message.lower()
    assert "token" not in message.lower()


def test_external_upload_can_read_script_artifact_file(tmp_path: Path):
    from slack_bot.files import upload_file_external

    artifact = tmp_path / "video-script.md"
    artifact.write_text("# Video script")
    client = MagicMock()
    client.files_getUploadURLExternal.return_value = {
        "ok": True,
        "upload_url": "https://files.slack.com/upload/v1/test",
        "file_id": "F123",
    }
    client.files_completeUploadExternal.return_value = {"ok": True, "files": []}
    upload_post = MagicMock(return_value={"status": 200})

    result = upload_file_external(
        client,
        channel_id="C_POSTS",
        thread_ts="1234567890.123456",
        file_path=artifact,
        title="Video script",
        upload_post=upload_post,
    )

    client.files_getUploadURLExternal.assert_called_once_with(
        filename="video-script.md",
        length=len(b"# Video script"),
    )
    assert result["filename"] == "video-script.md"

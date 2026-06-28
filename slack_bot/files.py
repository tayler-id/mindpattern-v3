"""Slack external file upload helpers.

Slack's legacy ``files.upload`` endpoint is deprecated. This module implements
the current external upload sequence:

1. ``files.getUploadURLExternal`` to reserve an upload URL and file ID.
2. Raw-byte POST to the returned URL.
3. ``files.completeUploadExternal`` with the parent thread timestamp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib import request as urllib_request

REQUIRED_SCOPE = "files:write"
DEFAULT_CONTENT_TYPE = "text/markdown; charset=utf-8"
MAX_UPLOAD_BYTES = 1_000_000


class SlackFileUploadError(RuntimeError):
    """Raised when a Slack external file upload cannot be completed."""


RawUploadFn = Callable[[str, bytes, str], dict[str, Any]]


def upload_file_external(
    client: Any,
    *,
    channel_id: str,
    thread_ts: str,
    file_path: str | Path | None = None,
    content: str | bytes | None = None,
    filename: str | None = None,
    title: str | None = None,
    initial_comment: str | None = None,
    content_type: str = DEFAULT_CONTENT_TYPE,
    upload_post: RawUploadFn | None = None,
) -> dict[str, Any]:
    """Upload a small artifact to Slack using the external upload flow.

    ``thread_ts`` must be the parent message timestamp, not a reply timestamp.
    The function intentionally does not accept or log tokens; authentication
    stays inside the Slack WebClient.
    """
    _validate_channel_id(channel_id)
    _validate_parent_thread_ts(thread_ts)
    payload, resolved_filename = _resolve_upload_payload(
        file_path=file_path,
        content=content,
        filename=filename,
    )
    if len(payload) > MAX_UPLOAD_BYTES:
        raise SlackFileUploadError("Slack file upload is limited to 1MB for this helper.")

    reserve_response = client.files_getUploadURLExternal(
        filename=resolved_filename,
        length=len(payload),
    )
    if not reserve_response.get("ok"):
        raise SlackFileUploadError(_slack_error("getUploadURLExternal", reserve_response))

    upload_url = reserve_response.get("upload_url")
    file_id = reserve_response.get("file_id")
    if not upload_url or not file_id:
        raise SlackFileUploadError("Slack getUploadURLExternal returned no upload URL or file ID.")

    raw_upload = upload_post or _post_raw_bytes
    raw_response = raw_upload(upload_url, payload, content_type)
    if int(raw_response.get("status", 0)) != 200:
        raise SlackFileUploadError(
            f"Slack raw upload failed with status {raw_response.get('status', 'unknown')}."
        )

    complete_kwargs = {
        "files": [{"id": file_id, "title": title or resolved_filename}],
        "channel_id": channel_id,
        "thread_ts": thread_ts,
    }
    if initial_comment:
        complete_kwargs["initial_comment"] = initial_comment
    complete_response = client.files_completeUploadExternal(**complete_kwargs)
    if not complete_response.get("ok"):
        raise SlackFileUploadError(_slack_error("completeUploadExternal", complete_response))

    return {
        "ok": True,
        "file_id": file_id,
        "filename": resolved_filename,
        "title": title or resolved_filename,
        "bytes": len(payload),
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "slack_response": complete_response,
    }


def _resolve_upload_payload(
    *,
    file_path: str | Path | None,
    content: str | bytes | None,
    filename: str | None,
) -> tuple[bytes, str]:
    if file_path and content is not None:
        raise SlackFileUploadError("Provide file_path or content, not both.")
    if not file_path and content is None:
        raise SlackFileUploadError("Provide file_path or content for Slack upload.")

    if file_path:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise SlackFileUploadError("Slack upload artifact file does not exist.")
        resolved_filename = filename or path.name
        payload = path.read_bytes()
    else:
        resolved_filename = filename or "artifact.md"
        payload = content.encode("utf-8") if isinstance(content, str) else bytes(content or b"")

    _validate_filename(resolved_filename)
    if not payload:
        raise SlackFileUploadError("Slack upload artifact is empty.")
    return payload, resolved_filename


def _post_raw_bytes(upload_url: str, payload: bytes, content_type: str) -> dict[str, Any]:
    req = urllib_request.Request(
        upload_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
        },
    )
    with urllib_request.urlopen(req, timeout=30) as response:
        return {"status": int(response.status), "body": response.read().decode("utf-8", "replace")}


def _validate_channel_id(channel_id: str) -> None:
    if not channel_id or any(char.isspace() for char in channel_id):
        raise SlackFileUploadError("Slack file upload requires a channel_id.")


def _validate_parent_thread_ts(thread_ts: str) -> None:
    if not thread_ts or "." not in thread_ts or any(char.isspace() for char in thread_ts):
        raise SlackFileUploadError("Slack file upload requires the parent thread_ts.")


def _validate_filename(filename: str) -> None:
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise SlackFileUploadError("Slack upload filename must be a safe basename.")


def _slack_error(step: str, response: dict[str, Any]) -> str:
    error = response.get("error") or "unknown_error"
    if error == "missing_scope" or response.get("needed") == REQUIRED_SCOPE:
        return f"Slack {step} failed: missing required {REQUIRED_SCOPE} scope."
    return f"Slack {step} failed: {error}."

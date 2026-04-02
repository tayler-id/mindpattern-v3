"""Tests for social/posting.py — LinkedIn and Bluesky posting clients.

Covers:
- LinkedInClient.post() success path (text post, post ID from header)
- LinkedInClient.post() API error path (HTTPError handling)
- BlueskyClient.post() success path (text post with AT URI → web URL)
- BlueskyClient.post() API error path (HTTPError handling)
- LinkedInClient._upload_document() success path (initializeUpload + PUT)
- LinkedInClient._upload_document() missing file path
- compress_image does not use deprecated tempfile.mktemp
- _upload_blob cleans up compressed temp files after upload
- _upload_blob cleans up compressed temp files on failure
"""

import inspect
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from social.posting import LinkedInClient, BlueskyClient, compress_image


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def linkedin_config():
    """Minimal LinkedIn config for testing."""
    return {
        "api_base": "https://api.linkedin.com",
        "api_version": "202501",
        "target_chars": 1350,
        "keychain": {"access_token": "li-test-token"},
    }


@pytest.fixture
def bluesky_config():
    """Minimal Bluesky config for testing."""
    return {
        "handle": "testuser.bsky.social",
        "api_base": "https://bsky.social/xrpc",
        "max_chars": 300,
        "keychain": {"app_password": "bsky-test-password"},
    }


@pytest.fixture
def linkedin_client(linkedin_config):
    """Create a LinkedInClient with mocked keychain."""
    with patch("social.posting.keychain_get", return_value="fake-access-token"):
        client = LinkedInClient(linkedin_config)
    # Pre-set person URN so _get_person_urn() doesn't need a network call
    client._person_urn = "urn:li:person:abc123"
    return client


@pytest.fixture
def bluesky_client(bluesky_config):
    """Create a BlueskyClient with mocked keychain and pre-authenticated session."""
    with patch("social.posting.keychain_get", return_value="fake-app-password"):
        client = BlueskyClient(bluesky_config)
    # Pre-set session state so _ensure_session() thinks we're authenticated
    client._jwt = "fake-jwt-token"
    client._refresh_jwt = "fake-refresh-token"
    client._did = "did:plc:testuser123"
    client._session_created_at = 9999999999  # far future so session appears fresh
    client.session.headers["Authorization"] = "Bearer fake-jwt-token"
    return client


# ── LinkedIn Tests ────────────────────────────────────────────────────────


def test_post_to_linkedin_success(linkedin_client):
    """LinkedInClient.post() returns success with post URL when API returns 201."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 201
    mock_resp.headers = {"x-restli-id": "urn:li:share:7654321"}
    mock_resp.text = ""
    mock_resp.json.return_value = {}

    with patch("social.posting._api_call_with_retry", return_value=mock_resp):
        result = linkedin_client.post("Test post content")

    assert result["success"] is True
    assert result["id"] == "urn:li:share:7654321"
    assert result["url"] == "https://www.linkedin.com/feed/update/urn:li:share:7654321"
    assert "error" not in result


def test_post_to_linkedin_api_error(linkedin_client):
    """LinkedInClient.post() returns success=False when API raises HTTPError."""
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 403
    mock_response.text = "Insufficient permissions"

    http_error = requests.HTTPError(response=mock_response)

    with patch("social.posting._api_call_with_retry", side_effect=http_error):
        result = linkedin_client.post("Test post content")

    assert result["success"] is False
    assert result["url"] == ""
    assert result["id"] == ""
    assert "error" in result


# ── Bluesky Tests ─────────────────────────────────────────────────────────


def test_post_to_bluesky_success(bluesky_client):
    """BlueskyClient.post() returns success with web URL derived from AT URI."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "uri": "at://did:plc:testuser123/app.bsky.feed.post/abc123rkey",
        "cid": "bafyreicid123",
    }

    with patch("social.posting._api_call_with_retry", return_value=mock_resp):
        result = bluesky_client.post("Hello Bluesky!")

    assert result["success"] is True
    assert result["uri"] == "at://did:plc:testuser123/app.bsky.feed.post/abc123rkey"
    assert result["cid"] == "bafyreicid123"
    assert result["url"] == "https://bsky.app/profile/testuser.bsky.social/post/abc123rkey"
    assert "error" not in result


def test_post_to_bluesky_api_error(bluesky_client):
    """BlueskyClient.post() returns success=False when API raises HTTPError."""
    mock_response = MagicMock(spec=requests.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal server error"

    http_error = requests.HTTPError(response=mock_response)

    with patch("social.posting._api_call_with_retry", side_effect=http_error):
        result = bluesky_client.post("Hello Bluesky!")

    assert result["success"] is False
    assert result["url"] == ""
    assert result["uri"] == ""
    assert result["cid"] == ""
    assert "error" in result


# ── LinkedIn Document Upload Tests ────────────────────────────────────────


def test_upload_linkedin_document_success(linkedin_client, tmp_path):
    """LinkedInClient._upload_document() returns document URN on success."""
    # Create a fake PDF file
    doc_file = tmp_path / "test-doc.pdf"
    doc_file.write_bytes(b"%PDF-1.4 fake pdf content")

    # Mock initializeUpload response
    init_resp = MagicMock(spec=requests.Response)
    init_resp.status_code = 200
    init_resp.json.return_value = {
        "value": {
            "uploadUrl": "https://api.linkedin.com/mediaUpload/doc-upload-url",
            "document": "urn:li:document:98765",
        }
    }

    # Mock binary PUT response
    put_resp = MagicMock(spec=requests.Response)
    put_resp.status_code = 201

    with patch(
        "social.posting._api_call_with_retry", side_effect=[init_resp, put_resp]
    ):
        result = linkedin_client._upload_document(doc_file)

    assert result == "urn:li:document:98765"


def test_upload_linkedin_document_missing_file(linkedin_client, tmp_path):
    """LinkedInClient._upload_document() returns None when file does not exist."""
    missing_file = tmp_path / "nonexistent.pdf"

    # initializeUpload succeeds but the file open will fail
    init_resp = MagicMock(spec=requests.Response)
    init_resp.status_code = 200
    init_resp.json.return_value = {
        "value": {
            "uploadUrl": "https://api.linkedin.com/mediaUpload/doc-upload-url",
            "document": "urn:li:document:98765",
        }
    }

    with patch("social.posting._api_call_with_retry", return_value=init_resp):
        result = linkedin_client._upload_document(missing_file)

    assert result is None


# ── compress_image / _upload_blob cleanup tests ──────────────────────────


def test_compress_image_does_not_use_mktemp():
    """compress_image must not use the deprecated tempfile.mktemp()."""
    source = inspect.getsource(compress_image)
    assert "mktemp" not in source, (
        "compress_image still uses deprecated tempfile.mktemp()"
    )


def test_upload_blob_cleans_up_compressed_file(bluesky_client, tmp_path):
    """_upload_blob removes the temp compressed file after successful upload."""
    # Create a fake image file
    image_file = tmp_path / "big-image.png"
    image_file.write_bytes(b"x" * 100)

    # Track which file compress_image returns so we can check it was deleted
    compressed = tmp_path / "compressed.jpg"
    compressed.write_bytes(b"small-jpeg-data")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"blob": {"ref": "blob-ref-123"}}

    with (
        patch("social.posting.compress_image", return_value=compressed) as mock_compress,
        patch("social.posting._api_call_with_retry", return_value=mock_resp),
    ):
        result = bluesky_client._upload_blob(image_file)

    assert result == {"ref": "blob-ref-123"}
    # The compressed temp file must have been cleaned up
    assert not compressed.exists(), "Compressed temp file was not cleaned up after upload"


def test_upload_blob_cleans_up_on_failure(bluesky_client, tmp_path):
    """_upload_blob removes the temp compressed file even if the upload fails."""
    image_file = tmp_path / "big-image.png"
    image_file.write_bytes(b"x" * 100)

    compressed = tmp_path / "compressed.jpg"
    compressed.write_bytes(b"small-jpeg-data")

    with (
        patch("social.posting.compress_image", return_value=compressed),
        patch("social.posting._api_call_with_retry", side_effect=RuntimeError("upload boom")),
    ):
        result = bluesky_client._upload_blob(image_file)

    assert result is None
    # Even on failure, the compressed temp file must be cleaned up
    assert not compressed.exists(), "Compressed temp file was not cleaned up after failed upload"

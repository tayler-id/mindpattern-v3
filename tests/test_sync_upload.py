"""HTTPS sync-bundle upload endpoint + client path selection."""

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


def _bundle(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_PIPELINE_SECRET", "test-secret")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return TestClient(app), tmp_path


def _post(client, body, secret="test-secret", sha=None):
    http, _ = client
    headers = {"X-Pipeline-Secret": secret}
    if sha is None:
        sha = hashlib.sha256(body).hexdigest()
    if sha:
        headers["X-Bundle-Sha256"] = sha
    return http.post("/api/sync/bundle?user=ramsay", content=body, headers=headers)


def test_rejects_bad_or_missing_secret(client):
    body = _bundle({"ramsay/memory.db": b"db"})
    assert _post(client, body, secret="wrong").status_code == 401
    http, _ = client
    assert http.post("/api/sync/bundle?user=ramsay", content=body).status_code == 401


def test_rejects_sha_mismatch_and_missing_sha(client):
    body = _bundle({"ramsay/memory.db": b"db"})
    assert _post(client, body, sha="0" * 64).status_code == 400
    assert _post(client, body, sha="").status_code == 400


def test_rejects_members_outside_layout(client):
    for name in ("../evil.db", "etc/passwd", "other-user/memory.db"):
        body = _bundle({name: b"x"})
        response = _post(client, body)
        assert response.status_code == 400, name


def test_happy_path_extracts_and_cleans_wal(client):
    http, root = client
    (root / "ramsay").mkdir()
    (root / "ramsay" / "memory.db-wal").write_bytes(b"stale")
    body = _bundle({
        "ramsay/memory.db": b"fresh database bytes",
        "reports/ramsay/2026-07-02.md": b"# Briefing",
        "reports/ramsay/site-stories/2026-07-02/a.json": b"{}",
    })
    response = _post(client, body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["extracted_files"] == 3
    assert (root / "ramsay" / "memory.db").read_bytes() == b"fresh database bytes"
    assert (root / "reports" / "ramsay" / "2026-07-02.md").exists()
    assert not (root / "ramsay" / "memory.db-wal").exists()


def test_pipeline_secret_file_fallback(tmp_path, monkeypatch):
    from orchestrator import sync as sync_mod

    monkeypatch.delenv("MP_PIPELINE_SECRET", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".mindpattern-pipeline-secret").write_text("file-secret\n")
    assert sync_mod._pipeline_secret() == "file-secret"

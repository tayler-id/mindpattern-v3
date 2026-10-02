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


def test_flushes_to_disk_before_reporting_success(client, monkeypatch):
    """The pipeline restarts the machine seconds after this response; an
    unflushed extract is lost and served as empty files (2026-08-04)."""
    from dashboard.routes import sync_upload

    calls: list[str] = []
    monkeypatch.setattr(sync_upload.os, "sync", lambda: calls.append("sync"))
    body = _bundle({"reports/ramsay/site-stories/2026-08-04/a.json": b'{"k":1}'})
    assert _post(client, body).status_code == 200
    assert calls == ["sync"], "extract must be fsynced before the caller is told it is safe"


def test_rejects_truncated_extraction(client, monkeypatch):
    """A tar that returns success but leaves short files must not report ok."""
    from dashboard.routes import sync_upload

    http, root = client
    real_extractall = tarfile.TarFile.extractall

    def truncating_extractall(self, path, **kwargs):
        real_extractall(self, path, **kwargs)
        # Simulate the half-flushed unpack: the story artifact lands empty.
        Path(path, "reports/ramsay/site-stories/2026-08-04/a.json").write_bytes(b"")

    monkeypatch.setattr(tarfile.TarFile, "extractall", truncating_extractall)
    body = _bundle({"reports/ramsay/site-stories/2026-08-04/a.json": b'{"k":1}'})
    response = _post(client, body)
    assert response.status_code == 500, response.text
    payload = response.json()
    assert payload["short_count"] == 1
    assert "site-stories/2026-08-04/a.json" in payload["short_files"][0]


def test_short_extractions_flags_missing_and_truncated(tmp_path):
    from dashboard.routes.sync_upload import _short_extractions

    good = tarfile.TarInfo("reports/ramsay/good.json")
    good.size = 3
    truncated = tarfile.TarInfo("reports/ramsay/truncated.json")
    truncated.size = 10
    absent = tarfile.TarInfo("reports/ramsay/absent.json")
    absent.size = 4
    directory = tarfile.TarInfo("reports/ramsay")
    directory.type = tarfile.DIRTYPE

    (tmp_path / "reports" / "ramsay").mkdir(parents=True)
    (tmp_path / "reports" / "ramsay" / "good.json").write_bytes(b"abc")
    (tmp_path / "reports" / "ramsay" / "truncated.json").write_bytes(b"")

    short = _short_extractions([good, truncated, absent, directory], tmp_path)
    assert short == ["reports/ramsay/truncated.json", "reports/ramsay/absent.json"]


def test_pipeline_secret_file_fallback(tmp_path, monkeypatch):
    from orchestrator import sync as sync_mod

    monkeypatch.delenv("MP_PIPELINE_SECRET", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".mindpattern-pipeline-secret").write_text("file-secret\n")
    assert sync_mod._pipeline_secret() == "file-secret"

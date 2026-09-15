"""Behavior checks for the isolated verification command."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import httpx

from verification import cli, runtime
from verification.features import verify_story_search
from verification.models import RequestResult


ROOT = Path(__file__).resolve().parent.parent


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "verification", *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )


def test_all_features_produce_retained_evidence(tmp_path):
    evidence = tmp_path / "proof"
    result = run_cli("verify", "all", "--evidence", str(evidence))
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed"
    manifest_text = (evidence / "manifest.json").read_text()
    manifest = json.loads(manifest_text)
    assert {feature["id"] for feature in manifest["features"]} == {
        "stories", "story-search", "site-artifacts", "sitemap", "private-access",
    }
    assert all(feature["assertions"] and feature["passed"] for feature in manifest["features"])
    assert manifest["cache_artifacts"]
    assert manifest["source"]["sha256"]["dashboard/app.py"]
    assert manifest["lifespan"] == "skipped"
    assert '"authorization":' not in manifest_text.lower()
    assert "API_TOKEN_HASH" not in manifest_text
    assert "Bearer " not in manifest_text
    assert (evidence / "manifest.json").exists()


def test_existing_evidence_is_preserved(tmp_path):
    sentinel = tmp_path / "manifest.json"
    sentinel.write_text("previous evidence")
    result = run_cli("verify", "all", "--evidence", str(tmp_path))
    assert result.returncode == 2
    assert "already exists" in json.loads(result.stdout)["error"]
    assert sentinel.read_text() == "previous evidence"


@pytest.mark.parametrize("arguments", [
    ("verify", "unknown"),
    ("request", "/api/search/site?q=verification"),
    ("request", "/api/users-unmapped"),
    ("request", "https://example.com/api/stories"),
    ("request", "/api/stories", "--base-url", "https://example.com"),
    ("serve", "--port", "0"),
    ("_worker", "serve", "18011"),
    ("_worker", "request", "/healthz"),
])
def test_invalid_commands_fail(arguments):
    assert run_cli(*arguments).returncode != 0


def test_fixture_request_and_doctor_use_real_routes():
    request = run_cli("request", "/api/stories/verification-story?user=ramsay")
    assert request.returncode == 0, request.stdout + request.stderr
    payload = json.loads(request.stdout)
    assert payload["request"]["status"] == 200
    assert payload["request"]["body"]["slug"] == "verification-story"
    doctor = run_cli("doctor")
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert json.loads(doctor.stdout)["health"]["body"]["database"] == "connected"


def test_runtime_excludes_personal_state_and_credentials(tmp_path, monkeypatch):
    source = tmp_path / "repo"
    source.mkdir()
    (source / "app.py").write_text("VALUE = 1\n")
    for directory in ("data", "reports", ".venv", ".agents"):
        (source / directory).mkdir()
        (source / directory / "private.py").write_text("private sentinel")
    (source / "users.json").write_text("personal registry")
    (source / ".env").write_text("SECRET=personal")
    (source / "linked.py").symlink_to(source / "data/private.py")
    monkeypatch.setattr(runtime, "PROJECT_ROOT", source)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-key-sentinel")
    monkeypatch.setenv("MP_PIPELINE_SECRET", "private-pipeline-sentinel")
    snapshot = runtime.create_runtime()
    copied = snapshot.source_root
    try:
        assert snapshot.source_hashes.keys() == {"app.py"}
        assert json.loads((copied / "users.json").read_text())["users"][0]["name"] == "Verification User"
        assert not (copied / "linked.py").exists()
        assert "ANTHROPIC_API_KEY" not in snapshot.environment
        assert "MP_PIPELINE_SECRET" not in snapshot.environment
        assert snapshot.environment["MP_DISABLE_OUTBOUND"] == "1"
        assert "HOME" not in snapshot.environment
    finally:
        snapshot.cleanup()
    assert not copied.exists()
    assert (source / "users.json").read_text() == "personal registry"
    assert (source / "data/private.py").read_text() == "private sentinel"


def test_setup_failure_keeps_error_evidence(tmp_path, monkeypatch, capsys):
    def unavailable():
        raise OSError("fixture setup unavailable")

    monkeypatch.setattr(cli, "create_runtime", unavailable)
    evidence = tmp_path / "failure"
    assert cli.main(["verify", "stories", "--evidence", str(evidence)]) == 1
    manifest = json.loads((evidence / "manifest.json").read_text())
    assert manifest["status"] == "error"
    assert "fixture setup unavailable" in manifest["error"]
    assert json.loads(capsys.readouterr().out)["passed"] is False


def test_server_error_cannot_pass_as_empty_search():
    async def fetch(path, headers):
        if "q=verification&" in path:
            return RequestResult("GET", path, 200, {
                "kind": "site_search", "groups": {"stories": [{"slug": "verification-story"}]},
            }, 1)
        return RequestResult("GET", path, 500, "Internal Server Error", 1)

    _, assertions = asyncio.run(verify_story_search(fetch))
    assert any(not item.passed and item.observed == 500 for item in assertions)


def test_http_server_stops_when_parent_is_terminated(tmp_path):
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "verification", "serve", "--port", str(port)],
        cwd=ROOT, env={**os.environ, "TMPDIR": str(tmp_path)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 10
            while True:
                try:
                    response = client.get(f"http://127.0.0.1:{port}/api/stories/verification-story")
                    break
                except httpx.ConnectError:
                    assert process.poll() is None, process.communicate()
                    assert time.monotonic() < deadline, "server did not start"
                    time.sleep(0.05)
            assert response.status_code == 200
            assert response.json()["slug"] == "verification-story"
            process.terminate()
            assert process.wait(timeout=5) == 143
            with pytest.raises(httpx.ConnectError):
                client.get(f"http://127.0.0.1:{port}/healthz")
        assert not list(tmp_path.glob("mindpattern-verification-runtime-*"))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.communicate()

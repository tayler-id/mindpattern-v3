"""Tests for the default-deny auth middleware (M0 task 7).

The public allowlist is the Vercel contract; everything else must 401
without a valid bearer token — including when no token is configured at
all (fail closed).
"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app

TEST_TOKEN = "test-token-for-auth-middleware"
TEST_HASH = hashlib.sha256(TEST_TOKEN.encode()).hexdigest()


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("API_TOKEN_HASH", TEST_HASH)
    monkeypatch.setenv("MP_PIPELINE_SECRET", "pipeline-secret-xyz")


class TestPublicRoutes:
    def test_contract_endpoints_open(self, client):
        for path in ("/api/stats?user=ramsay", "/api/findings?user=ramsay&limit=1",
                     "/api/reports?user=ramsay", "/healthz"):
            assert client.get(path).status_code == 200, path

    def test_public_prefix_does_not_allow_post(self, client):
        assert client.post("/api/findings").status_code == 401


class TestPrivateRoutes:
    def test_state_changing_routes_401_without_token(self, client):
        assert client.post("/api/editors-desk/1/approve").status_code == 401
        assert client.post("/prompts/some-agent/revert").status_code == 401
        assert client.post("/api/engagement/post").status_code == 401

    def test_private_reads_401_without_token(self, client):
        assert client.get("/").status_code == 401
        assert client.get("/traces").status_code == 401

    def test_fails_closed_when_no_hash_configured(self, client, monkeypatch):
        monkeypatch.delenv("API_TOKEN_HASH", raising=False)
        resp = client.post(
            "/api/editors-desk/1/approve",
            headers={"Authorization": "Bearer anything"},
        )
        assert resp.status_code == 401

    def test_wrong_token_401(self, client, configured):
        resp = client.get("/", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_valid_token_passes_middleware(self, client, configured):
        resp = client.get("/traces", headers={"Authorization": f"Bearer {TEST_TOKEN}"})
        assert resp.status_code != 401


class TestPipelineSecret:
    def test_approvals_with_secret_passes_middleware(self, client, configured):
        resp = client.get(
            "/api/approvals/some-token",
            headers={"X-Pipeline-Secret": "pipeline-secret-xyz"},
        )
        assert resp.status_code != 401

    def test_approvals_without_secret_401(self, client, configured):
        assert client.get("/api/approvals/some-token").status_code == 401

    def test_secret_only_works_on_approvals(self, client, configured):
        resp = client.post(
            "/api/editors-desk/1/approve",
            headers={"X-Pipeline-Secret": "pipeline-secret-xyz"},
        )
        assert resp.status_code == 401

    def test_unconfigured_secret_fails_closed(self, client, monkeypatch):
        monkeypatch.delenv("MP_PIPELINE_SECRET", raising=False)
        resp = client.get(
            "/api/approvals/some-token",
            headers={"X-Pipeline-Secret": ""},
        )
        assert resp.status_code == 401

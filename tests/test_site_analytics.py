"""Internal analytics dash: private, summarizes reader behavior."""

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_EVENTS_DB", str(tmp_path / "site_events.db"))
    return TestClient(app)


def test_summary_requires_auth(client):
    assert client.get("/api/site-analytics/summary").status_code == 401
    assert client.get("/site-analytics").status_code == 401


def test_summary_shape_with_bearer(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "reader01"})
    client.post("/api/event", json={"type": "subscribe_submitted", "target": "band"})
    client.post("/api/event", json={"type": "subscribe_success", "target": "band"})

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["top_stories"][0]["target"] == "hot-story"
    assert payload["subscribe"]["conversion"] == 1.0
    assert payload["totals"]["events"] == 3

    page = client.get("/site-analytics", headers=headers)
    assert page.status_code == 200
    assert "hot-story" in page.text


def test_dash_query_token(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "browser-token")
    assert client.get("/site-analytics?token=wrong").status_code == 401
    ok = client.get("/site-analytics?token=browser-token")
    assert ok.status_code == 200
    assert "token=browser-token" in ok.text  # window links stay authed
    # query token must NOT unlock other private routes
    assert client.get("/api/site-analytics/summary?token=browser-token").status_code == 401

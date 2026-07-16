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


def test_campaigns_requires_auth(client):
    assert client.get("/api/site-analytics/campaigns").status_code == 401
    # a browser query token unlocks only the dash page, never the API
    assert client.get(
        "/api/site-analytics/campaigns?token=whatever").status_code == 401


def test_campaigns_aggregates_counts_only(client, monkeypatch):
    import json

    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    campaign_a, campaign_b = "a" * 64, "b" * 64
    # campaign A via X: two views by two readers, a source click, a subscribe
    for anon in ("reader01", "reader02"):
        client.post("/api/event", json={
            "type": "story_view", "target": "hot-story", "anon_id": anon,
            "campaign_id": campaign_a, "source_channel": "x",
        })
    client.post("/api/event", json={
        "type": "source_click", "target": "example.com", "anon_id": "reader01",
        "campaign_id": campaign_a, "source_channel": "x",
    })
    client.post("/api/event", json={
        "type": "subscribe_success", "target": "band", "anon_id": "reader02",
        "campaign_id": campaign_a, "source_channel": "x",
    })
    # campaign A via bluesky: one view
    client.post("/api/event", json={
        "type": "story_view", "target": "hot-story", "anon_id": "reader03",
        "campaign_id": campaign_a, "source_channel": "bluesky",
    })
    # campaign B: one share
    client.post("/api/event", json={
        "type": "share", "target": "copy:Hot", "anon_id": "reader04",
        "campaign_id": campaign_b, "source_channel": "reddit",
    })
    # owner-flagged and untagged events never reach the aggregate
    client.post("/api/event", json={
        "type": "story_view", "target": "hot-story", "anon_id": "tayler01",
        "owner": 1, "campaign_id": campaign_a, "source_channel": "x",
    })
    client.post("/api/event", json={
        "type": "story_view", "target": "hot-story", "anon_id": "reader05",
    })

    payload = client.get(
        "/api/site-analytics/campaigns?window=7d", headers=headers).json()
    assert payload["kind"] == "campaign_attribution"
    assert payload["window"] == "7d"
    rows = payload["rows"]
    assert [(r["campaign_id"], r["source_channel"]) for r in rows] == [
        (campaign_a, "bluesky"), (campaign_a, "x"), (campaign_b, "reddit"),
    ]
    a_x = rows[1]
    assert a_x["counts"] == {
        "story_view": 2, "source_click": 1, "subscribe_success": 1}
    assert a_x["readers"] == 2  # distinct count only — never ids
    assert rows[0]["counts"] == {"story_view": 1}
    assert rows[2]["counts"] == {"share": 1}
    # aggregate counts only: no per-visitor identity, path, or referrer
    serialized = json.dumps(payload)
    for private in ("reader01", "reader02", "reader03", "reader04",
                    "tayler01", "anon", "path", "ref_domain"):
        assert private not in serialized


def test_campaigns_rejects_unknown_window(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}
    for bad in ("today", "all", "1d", ""):
        response = client.get(
            f"/api/site-analytics/campaigns?window={bad}", headers=headers)
        assert response.status_code == 400  # never a silent default window
    for good in ("24h", "7d", "28d"):
        response = client.get(
            f"/api/site-analytics/campaigns?window={good}", headers=headers)
        assert response.status_code == 200
        assert response.json()["rows"] == []


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


def test_summary_splits_crawlers_from_humans(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "agent_hit", "target": "GPTBot", "path": "/s/hot-story"})
    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "reader01"})
    client.post("/api/event", json={"type": "scroll_depth", "target": "hot-story", "value": 50})
    client.post("/api/event", json={"type": "related_click", "target": "next-story"})

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["totals"]["events"] == 4
    assert payload["totals"]["crawler_hits"] == 1
    assert payload["totals"]["human_events"] == 3
    assert payload["totals"]["reader_events"] == 3
    assert payload["totals"]["owner_events"] == 0
    assert payload["totals"]["crawler_share"] == 25.0
    assert payload["totals"]["story_views"] == 1
    assert payload["agents"]["by_bot"][0]["target"] == "GPTBot"
    # daily series covers today with the bot/reader/owner split
    assert payload["daily"][-1]["bots"] == 1
    assert payload["daily"][-1]["readers"] == 3
    assert payload["daily"][-1]["owner"] == 0
    assert payload["daily"][-1]["views"] == 1
    # human event mix excludes crawler hits
    assert {m["type"] for m in payload["mix"]} == {"story_view", "scroll_depth", "related_click"}
    assert payload["scroll"] == [{"value": 50, "n": 1}]


def test_owner_events_marked_not_counted_as_readers(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "visitor1"})
    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "tayler01", "owner": 1})
    client.post("/api/event", json={"type": "story_view", "target": "own-story", "anon_id": "tayler01", "owner": 1})
    client.post("/api/event", json={"type": "search_query", "target": "agents", "anon_id": "tayler01", "owner": 1})

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["totals"]["owner_events"] == 3
    assert payload["totals"]["reader_events"] == 1
    assert payload["totals"]["readers"] == 1  # tayler01 is not a reader
    assert payload["totals"]["story_views"] == 1  # owner views not reader views
    hot = next(s for s in payload["top_stories"] if s["target"] == "hot-story")
    assert hot["views"] == 1 and hot["owner_views"] == 1
    own = next(s for s in payload["top_stories"] if s["target"] == "own-story")
    assert own["views"] == 0 and own["owner_views"] == 1
    assert payload["daily"][-1]["owner"] == 3
    assert payload["search_terms"][0]["count"] == 0
    assert payload["search_terms"][0]["owner_count"] == 1


def test_page_escapes_user_supplied_targets(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "search_query", "target": "<script>alert(1)</script>"})

    page = client.get("/site-analytics", headers=headers)
    assert page.status_code == 200
    assert "<script>alert" not in page.text  # injected JSON escapes all '<'


def test_dash_query_token(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "browser-token")
    assert client.get("/site-analytics?token=wrong").status_code == 401
    ok = client.get("/site-analytics?token=browser-token")
    assert ok.status_code == 200
    assert "token=browser-token" in ok.text  # window links stay authed
    # query token must NOT unlock other private routes
    assert client.get("/api/site-analytics/summary?token=browser-token").status_code == 401

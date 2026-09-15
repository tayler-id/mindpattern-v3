"""First-party event ingestion + trending/popular endpoints."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from memory.events_db import open_events_db

client_module = TestClient(app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_EVENTS_DB", str(tmp_path / "site_events.db"))
    return TestClient(app), tmp_path / "site_events.db"


def test_event_post_is_public_and_stores_allowlisted(client):
    http, db_path = client
    response = http.post("/api/event", json={
        "type": "story_view", "target": "2026-07-02-some-story",
        "path": "/s/2026-07-02-some-story", "anon_id": "abc12345",
    })
    assert response.status_code == 202
    assert response.json()["status"] == "ok"

    conn = open_events_db(db_path)
    row = conn.execute("SELECT * FROM events").fetchone()
    assert row["type"] == "story_view"
    assert row["target"] == "2026-07-02-some-story"
    assert row["anon_id"] == "abc12345"


def test_page_view_stores_valid_anon_id(client):
    http, db_path = client
    response = http.post("/api/event", json={
        "type": "page_view",
        "target": "home",
        "path": "/",
        "anon_id": "page_reader-01",
    })

    assert response.status_code == 202
    assert response.json()["status"] == "ok"
    conn = open_events_db(db_path)
    row = conn.execute("SELECT type, target, path, anon_id FROM events").fetchone()
    assert dict(row) == {
        "type": "page_view",
        "target": "home",
        "path": "/",
        "anon_id": "page_reader-01",
    }
    conn.close()


def test_invalid_anon_id_is_blanked_but_page_view_is_stored(client):
    http, db_path = client
    response = http.post("/api/event", json={
        "type": "page_view",
        "path": "/topics/agents",
        "anon_id": "short",
    })

    assert response.status_code == 202
    assert response.json()["status"] == "ok"
    conn = open_events_db(db_path)
    row = conn.execute("SELECT type, anon_id FROM events").fetchone()
    assert dict(row) == {"type": "page_view", "anon_id": ""}
    conn.close()


def test_stored_rows_contain_no_pii_columns(client):
    http, db_path = client
    http.post("/api/event", json={"type": "story_view", "target": "x"},
              headers={"User-Agent": "SecretBrowser/1.0", "X-Forwarded-For": "1.2.3.4"})
    conn = open_events_db(db_path)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    # owner is a self-declared 0/1 "this is Tayler" flag and durable is a 0/1
    # "the client could persist its reader id" flag. Neither is PII.
    assert columns == {"id", "ts", "type", "target", "path", "ref_domain", "anon_id", "value", "owner", "durable"}
    row = dict(conn.execute("SELECT * FROM events").fetchone())
    serialized = json.dumps(row)
    assert "1.2.3.4" not in serialized
    assert "SecretBrowser" not in serialized


def test_junk_events_ignored_not_errored(client):
    http, db_path = client
    assert http.post("/api/event", json={"type": "evil_event"}).json()["status"] == "ignored"
    assert http.post("/api/event", content=b"x" * 2000).json()["status"] == "ignored"
    assert http.post("/api/event", content=b"not json").json()["status"] == "ignored"
    conn = open_events_db(db_path)
    assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 0


def test_query_strings_stripped_from_paths(client):
    http, db_path = client
    http.post("/api/event", json={
        "type": "story_view", "target": "s", "path": "/s/x?email=me@example.com",
    })
    conn = open_events_db(db_path)
    assert conn.execute("SELECT path FROM events").fetchone()["path"] == "/s/x"


def test_popular_counts_views_and_unique_readers(client, monkeypatch, tmp_path):
    http, db_path = client
    for anon in ("reader-one", "reader-two", "reader-one"):
        http.post("/api/event", json={
            "type": "story_view", "target": "2026-07-02-hot-story", "anon_id": anon,
        })
    from dashboard.routes import api as api_routes

    async def fake_stories(user):
        return [{"slug": "2026-07-02-hot-story", "title": "Hot",
                 "issue_date": "2026-07-02", "summary": "", "target_url": "/s/x"}]
    monkeypatch.setattr(api_routes, "_all_public_stories", fake_stories)

    payload = http.get("/api/popular?user=ramsay").json()
    assert payload["items"][0]["views"] == 3
    assert payload["items"][0]["unique_readers"] == 2


def test_trending_reorders_on_events_and_corpus(client, monkeypatch):
    http, db_path = client
    from dashboard.routes import api as api_routes, events as events_routes

    events_routes._TRENDING_CACHE.clear()
    stories = [
        {"slug": "quiet-story", "title": "Quiet", "issue_date": "2026-07-01",
         "summary": "", "target_url": "/s/q", "graph_connectors": {"source_domains": []},
         "arc_ids": []},
        {"slug": "read-story", "title": "Read", "issue_date": "2026-07-01",
         "summary": "", "target_url": "/s/r", "graph_connectors": {"source_domains": []},
         "arc_ids": []},
        {"slug": "internet-story", "title": "Repo hit 40,000 stars overnight",
         "issue_date": "2026-07-01", "summary": "", "target_url": "/s/i",
         "graph_connectors": {"source_domains": ["github.com"]}, "arc_ids": ["oss"]},
    ]

    async def fake_stories(user):
        return stories
    monkeypatch.setattr(api_routes, "_all_public_stories", fake_stories)
    monkeypatch.setattr(events_routes, "_domain_recurrence", lambda user: {"github.com": 15})

    for _ in range(5):
        http.post("/api/event", json={"type": "story_view", "target": "read-story"})

    payload = http.get("/api/trending?user=ramsay&limit=3").json()
    order = [item["slug"] for item in payload["items"]]
    assert order[0] == "read-story"          # on-site reads dominate
    assert order[1] == "internet-story"       # corpus-only signal beats silence
    assert order[2] == "quiet-story"
    assert payload["items"][0]["trend"] in {"up", "flat"}
    assert all("trending_score" in item for item in payload["items"])


def test_events_survive_daily_sync_bundle(tmp_path, monkeypatch):
    """Spec criterion 6: the sync bundle never contains or overwrites
    site_events.db - events recorded before a sync are intact after."""
    import hashlib
    import io
    import tarfile

    from dashboard.routes import sync_upload
    from memory.events_db import open_events_db, record_event

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("MP_EVENTS_DB", str(data_dir / "site_events.db"))
    monkeypatch.setattr(sync_upload, "_data_root", lambda: data_dir)
    monkeypatch.setattr(sync_upload, "_secret_ok", lambda provided: True)
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_pipeline_secret_valid", lambda provided: True)

    conn = open_events_db()
    assert record_event(conn, {"type": "story_view", "target": "pre-sync-story"})
    conn.close()

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        payload = tmp_path / "memory.db"
        payload.write_bytes(b"fresh daily database")
        tar.add(payload, arcname="ramsay/memory.db")
    body = buffer.getvalue()

    response = client_module.post(
        "/api/sync/bundle?user=ramsay",
        content=body,
        headers={
            "X-Pipeline-Secret": "anything",
            "X-Bundle-Sha256": hashlib.sha256(body).hexdigest(),
        },
    )
    assert response.status_code == 200, response.text

    assert (data_dir / "ramsay" / "memory.db").read_bytes() == b"fresh daily database"
    conn = open_events_db()
    row = conn.execute("SELECT target FROM events").fetchone()
    assert row["target"] == "pre-sync-story"
    conn.close()


def test_anon_id_history_lookup_uses_an_index(tmp_path):
    """The new/returning split asks 'was this anon_id here before T' once per
    reader. Without idx_events_anon_ts that probe becomes a table scan.

    The plan is taken over the production probe itself, imported from
    site_analytics rather than retyped: a hand-written lookalike with literal
    constants and no outer correlation plans differently, so it would stay
    green through exactly the rewrite this is meant to catch (a function on
    anon_id, an OR, a LIKE).
    """
    from dashboard.routes.site_analytics import _SEEN_BEFORE

    db_path = tmp_path / "site_events.db"
    conn = open_events_db(db_path)
    try:
        indexes = {
            row["name"] for row in conn.execute("PRAGMA index_list(events)")
        }
        assert "idx_events_anon_ts" in indexes

        plan = " ".join(
            str(row[3]) for row in conn.execute(
                f"""EXPLAIN QUERY PLAN
                    SELECT COUNT(*) FROM (
                      SELECT DISTINCT anon_id FROM events
                      WHERE ts>=? AND owner=0 AND type!='agent_hit' AND anon_id!=''
                    ) w
                    WHERE {_SEEN_BEFORE.format(alias='w')}""",
                (0, 0),
            )
        )
        assert "idx_events_anon_ts (anon_id=? AND ts<?)" in plan, plan
    finally:
        conn.close()

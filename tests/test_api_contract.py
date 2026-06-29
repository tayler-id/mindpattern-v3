"""Contract tests for the public JSON API consumed by vercel-mindpattern.

These 12 GET endpoints ARE the contract with the live site (mindpattern.ai →
mindpattern.fly.dev). Fixtures in tests/fixtures/api/ were snapshotted from the
deployed app on 2026-06-11.

Shape rule: every key present in the fixture must exist in the response with
the same JSON type. Additive fields are allowed; removed keys and type changes
are breaking. (/mcp is deliberately absent: the live backend 404s it today —
it becomes a real endpoint in v4 M1.)

Run modes:
    default            — in-process TestClient against dashboard.app
    MP_CONTRACT_LIVE=1 — hits https://mindpattern.fly.dev (post-deploy check)
"""

import json
import os
import sqlite3
import struct
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "api"
LIVE_BASE = "https://mindpattern.fly.dev"

ENDPOINTS = [
    ("search_q_ai_limit_3", "/api/search?q=ai&limit=3&user=ramsay"),
    ("findings_limit_5", "/api/findings?limit=5&user=ramsay"),
    ("stats", "/api/stats?user=ramsay"),
    ("patterns", "/api/patterns?user=ramsay"),
    ("sources", "/api/sources?user=ramsay"),
    ("skills", "/api/skills?user=ramsay"),
    ("skills_search_q_agents_limit_3", "/api/skills/search?q=agents&limit=3&user=ramsay"),
    ("skill-domains", "/api/skill-domains?user=ramsay"),
    ("health", "/api/health?user=ramsay"),
    ("reports", "/api/reports?user=ramsay"),
    ("reports_single", "/api/reports/2026-06-10?user=ramsay"),
    ("reports_search", "/api/reports/search?q=agents&limit=3&user=ramsay"),
]


def _load_fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _embedding_blob(score=1.0):
    return struct.pack("2f", float(score), 0.0)


def _deserialize_test_embedding(blob):
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def _insert_finding(conn, item):
    conn.execute(
        """INSERT OR REPLACE INTO findings
           (id, run_date, agent, title, summary, importance, category,
            source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item["id"],
            item.get("run_date", "2026-01-01"),
            item.get("agent", "fixture-agent"),
            item.get("title", "Fixture finding"),
            item.get("summary", ""),
            item.get("importance", "medium"),
            item.get("category", "fixture"),
            item.get("source_url", ""),
            item.get("source_name", ""),
            item.get("created_at", "2026-01-01T00:00:00"),
        ),
    )


def _insert_skill(conn, item):
    conn.execute(
        """INSERT OR REPLACE INTO skills
           (id, run_date, domain, title, description, steps, difficulty,
            source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item["id"],
            item.get("run_date", "2026-01-01"),
            item.get("domain", "fixture"),
            item.get("title", "Fixture skill"),
            item.get("description", ""),
            item.get("steps", ""),
            item.get("difficulty", "beginner"),
            item.get("source_url", ""),
            item.get("source_name", ""),
            item.get("created_at"),
        ),
    )


def _create_contract_db(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE findings (
                id INTEGER PRIMARY KEY,
                run_date TEXT,
                agent TEXT,
                title TEXT,
                summary TEXT,
                importance TEXT,
                category TEXT,
                source_url TEXT,
                source_name TEXT,
                created_at TEXT
            );
            CREATE TABLE findings_embeddings (
                finding_id INTEGER PRIMARY KEY,
                embedding BLOB
            );
            CREATE TABLE sources (
                id INTEGER PRIMARY KEY,
                url_domain TEXT,
                display_name TEXT,
                hit_count INTEGER,
                high_value_count INTEGER,
                last_seen TEXT,
                created_at TEXT
            );
            CREATE TABLE patterns (
                id INTEGER PRIMARY KEY,
                run_date TEXT,
                theme TEXT,
                description TEXT,
                recurrence_count INTEGER,
                first_seen TEXT,
                last_seen TEXT,
                created_at TEXT
            );
            CREATE TABLE skills (
                id INTEGER PRIMARY KEY,
                run_date TEXT,
                domain TEXT,
                title TEXT,
                description TEXT,
                steps TEXT,
                difficulty TEXT,
                source_url TEXT,
                source_name TEXT,
                created_at TEXT
            );
            CREATE TABLE skills_embeddings (
                skill_id INTEGER PRIMARY KEY,
                embedding BLOB
            );
            """
        )

        for item in _load_fixture("findings_limit_5") + _load_fixture("search_q_ai_limit_3"):
            _insert_finding(conn, item)
        for item in _load_fixture("search_q_ai_limit_3"):
            conn.execute(
                "INSERT OR REPLACE INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)",
                (item["id"], _embedding_blob(item.get("similarity", 1.0))),
            )

        stats = _load_fixture("stats")
        next_id = 900_000
        for agent in stats["by_agent"]:
            _insert_finding(
                conn,
                {
                    "id": next_id,
                    "run_date": "2026-01-01",
                    "agent": agent,
                    "title": f"{agent} fixture row",
                    "summary": "Fixture row for API contract agent stats.",
                },
            )
            next_id += 1
        for run_date in stats["by_date"]:
            _insert_finding(
                conn,
                {
                    "id": next_id,
                    "run_date": run_date,
                    "agent": "fixture-stats-agent",
                    "title": f"{run_date} fixture row",
                    "summary": "Fixture row for API contract date stats.",
                },
            )
            next_id += 1

        for item in _load_fixture("sources"):
            conn.execute(
                """INSERT OR REPLACE INTO sources
                   (id, url_domain, display_name, hit_count, high_value_count, last_seen, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["id"],
                    item.get("url_domain", ""),
                    item.get("display_name", ""),
                    item.get("hit_count", 0),
                    item.get("high_value_count", 0),
                    item.get("last_seen"),
                    item.get("created_at"),
                ),
            )

        for item in _load_fixture("patterns"):
            conn.execute(
                """INSERT OR REPLACE INTO patterns
                   (id, run_date, theme, description, recurrence_count,
                    first_seen, last_seen, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["id"],
                    item.get("run_date", "2026-01-01"),
                    item.get("theme", ""),
                    item.get("description", ""),
                    item.get("recurrence_count", 1),
                    item.get("first_seen"),
                    item.get("last_seen"),
                    item.get("created_at"),
                ),
            )

        for item in _load_fixture("skills") + _load_fixture("skills_search_q_agents_limit_3"):
            _insert_skill(conn, item)
        for item in _load_fixture("skills_search_q_agents_limit_3"):
            conn.execute(
                "INSERT OR REPLACE INTO skills_embeddings (skill_id, embedding) VALUES (?, ?)",
                (item["id"], _embedding_blob(item.get("similarity", 1.0))),
            )

        next_skill_id = 800_000
        for domain in _load_fixture("skill-domains"):
            _insert_skill(
                conn,
                {
                    "id": next_skill_id,
                    "run_date": "2026-01-01",
                    "domain": domain,
                    "title": f"{domain} fixture skill",
                    "description": "Fixture row for API contract skill domains.",
                    "steps": "Use fixture data.",
                },
            )
            next_skill_id += 1

        conn.commit()
    finally:
        conn.close()


def _create_contract_reports(reports_dir):
    user_dir = reports_dir / "ramsay"
    user_dir.mkdir(parents=True)
    single = _load_fixture("reports_single")
    for report in _load_fixture("reports"):
        if report["filename"] == single["filename"]:
            text = single["content"]
        else:
            text = (
                f"# {report['title']}\n\n"
                f"{report.get('subtitle', '')}\n\n"
                "Fixture report content mentioning agents for contract search.\n"
            )
        (user_dir / report["filename"]).write_text(text)


def _create_contract_audio(reports_dir):
    audio_dir = reports_dir / "ramsay" / "audio"
    audio_dir.mkdir(parents=True)
    (audio_dir / "2026-06-28.mp3").write_bytes(b"fixture mp3 bytes")
    (audio_dir / "2026-06-28.transcript.md").write_text(
        "# MindPattern Audio Briefing - 2026-06-28\n\n"
        "Status: ready\n\n"
        "Fixture audio transcript.\n\n"
        "## Source notes\n\n"
        "- [Primary source](https://example.com/audio-source)\n"
    )
    (audio_dir / "2026-06-28.json").write_text(json.dumps({
        "id": "2026-06-28-audio-morning-briefing",
        "type": "audio_briefing",
        "date": "2026-06-28",
        "user": "ramsay",
        "status": "ready",
        "generated_at": "2026-06-28T12:00:00+00:00",
        "provider": "dry_run",
        "model": "dry-run-tts-v1",
        "voice": "dry-run",
        "source_count": 1,
        "duration_seconds": 9.5,
        "has_audio_file": True,
        "audio_placeholder": False,
        "source_report_hash": "sha256:sourcefixture",
        "script_hash": "sha256:scriptfixture",
        "audio_hash": "sha256:audiofixture",
        "labels": ["AI-generated audio", "manual publish only"],
        "show_notes": [
            {"label": "Primary source", "url": "https://example.com/audio-source"}
        ],
        "artifact_files": {
            "audio": "2026-06-28.mp3",
            "transcript": "2026-06-28.transcript.md",
            "metadata": "2026-06-28.json",
            "provenance": "2026-06-28.provenance.json",
        },
    }))
    (audio_dir / "2026-06-28.provenance.json").write_text(json.dumps({
        "type": "audio_briefing",
        "date": "2026-06-28",
        "status": "ready",
    }))


def _json_type(value):
    """Collapse JSON types: ints and floats are both 'number'."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "null"


def assert_same_shape(fixture, actual, path="$"):
    """Every fixture key must exist in actual with the same JSON type."""
    ftype = _json_type(fixture)
    if ftype == "null":
        return  # fixture gave no type information for this field
    atype = _json_type(actual)
    if atype == "null":
        # live data may legitimately have nulls where the fixture had values
        return
    assert atype == ftype, f"{path}: expected {ftype}, got {atype}"
    if ftype == "dict":
        for key, fval in fixture.items():
            assert key in actual, f"{path}.{key}: key missing from response"
            assert_same_shape(fval, actual[key], f"{path}.{key}")
    elif ftype == "list" and fixture and actual:
        assert_same_shape(fixture[0], actual[0], f"{path}[0]")


@pytest.fixture(scope="module")
def fixture_storage(tmp_path_factory):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        yield
        return

    from dashboard.routes import api as api_routes

    root = tmp_path_factory.mktemp("api-contract")
    data_dir = root / "data"
    reports_dir = root / "reports"
    user_dir = data_dir / "ramsay"
    user_dir.mkdir(parents=True)
    _create_contract_db(user_dir / "memory.db")
    _create_contract_reports(reports_dir)
    _create_contract_audio(reports_dir)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(api_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(api_routes, "_embed_text", lambda _text: [1.0, 0.0])
    monkeypatch.setattr(api_routes, "_deserialize_f32", _deserialize_test_embedding)
    try:
        yield
    finally:
        monkeypatch.undo()


@pytest.fixture(scope="module")
def client(fixture_storage):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        import httpx

        with httpx.Client(base_url=LIVE_BASE, timeout=30) as c:
            yield c
    else:
        from fastapi.testclient import TestClient

        from dashboard.app import app

        with TestClient(app) as c:
            yield c


@pytest.mark.parametrize("fixture_name,path", ENDPOINTS, ids=[e[0] for e in ENDPOINTS])
def test_endpoint_contract(client, fixture_name, path):
    fixture = _load_fixture(fixture_name)
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    body = resp.json()
    # An endpoint that returned data on 2026-06-11 must not start returning empty.
    if _json_type(fixture) == "list" and fixture:
        assert body, f"{path}: returned empty list, fixture had data"
    assert_same_shape(fixture, body, path)


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_audio_briefing_endpoints(client):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        pytest.skip("audio briefing endpoints are verified locally before deploy")

    listing = client.get("/api/audio-briefings?user=ramsay")
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["date"] == "2026-06-28"
    assert body[0]["public_url"].endswith("/api/audio-briefings/2026-06-28/file?user=ramsay")
    assert body[0]["transcript_url"].endswith(
        "/api/audio-briefings/2026-06-28/transcript?user=ramsay"
    )
    assert "artifact_files" not in body[0]

    detail = client.get("/api/audio-briefings/2026-06-28?user=ramsay")
    assert detail.status_code == 200
    metadata = detail.json()
    assert metadata["status"] == "ready"
    assert metadata["source_count"] == 1
    assert metadata["labels"] == ["AI-generated audio", "manual publish only"]
    assert metadata["show_notes"][0]["url"] == "https://example.com/audio-source"

    audio = client.get("/api/audio-briefings/2026-06-28/file?user=ramsay")
    assert audio.status_code == 200
    assert audio.content == b"fixture mp3 bytes"
    assert audio.headers["content-type"].startswith("audio/")

    transcript = client.get("/api/audio-briefings/2026-06-28/transcript?user=ramsay")
    assert transcript.status_code == 200
    assert "Fixture audio transcript." in transcript.text
    assert transcript.headers["content-type"].startswith("text/plain")


def test_audio_briefing_endpoints_reject_unsafe_or_missing_artifacts(client):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        pytest.skip("audio briefing endpoints are verified locally before deploy")

    assert client.get("/api/audio-briefings?user=../ramsay").json() == []
    assert client.get("/api/audio-briefings/2026-99-99?user=ramsay").status_code == 404
    assert client.get("/api/audio-briefings/2026-06-27?user=ramsay").status_code == 404
    assert client.get("/api/audio-briefings/2026-06-28/file?user=../ramsay").status_code == 404
    assert client.get("/api/audio-briefings/2026-06-27/transcript?user=ramsay").status_code == 404


def test_single_finding_endpoint_returns_public_finding(client):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        pytest.skip("new graph endpoints are verified locally before deploy")

    resp = client.get("/api/finding/13776?user=ramsay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 13776
    assert body["title"].startswith("Cerebras IPO")
    assert body["source_url"].startswith("https://")
    assert body["kind"] == "finding"

    assert client.get("/api/finding/999999?user=ramsay").status_code == 404
    assert client.get("/api/finding/13776?user=../ramsay").status_code == 404


def test_related_endpoint_returns_semantic_neighbors(client):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        pytest.skip("new graph endpoints are verified locally before deploy")

    resp = client.get("/api/related/7063?mode=semantic&limit=2&user=ramsay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["finding_id"] == 7063
    assert body["mode"] == "semantic"
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [4257, 129]
    assert all(item["id"] != 7063 for item in body["items"])
    assert all(item["kind"] == "finding" for item in body["items"])
    assert all(item["relationship"] == "semantic_similarity" for item in body["items"])
    assert all(isinstance(item["score"], float) for item in body["items"])
    assert all(item["reason"] for item in body["items"])

    missing_embedding = client.get("/api/related/13776?mode=semantic&user=ramsay")
    assert missing_embedding.status_code == 200
    assert missing_embedding.json()["items"] == []
    assert client.get("/api/related/7063?mode=graph&user=ramsay").status_code == 400
    assert client.get("/api/related/7063?mode=semantic&user=../ramsay").status_code == 404


def test_feed_endpoint_wraps_findings_for_wire(client):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        pytest.skip("new graph endpoints are verified locally before deploy")

    resp = client.get("/api/feed?limit=3&offset=0&user=ramsay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "feed"
    assert body["limit"] == 3
    assert body["offset"] == 0
    assert body["total"] >= 3
    assert len(body["items"]) == 3
    assert body["items"][0]["kind"] == "finding"
    assert body["items"][0]["rank"] == 1
    assert body["items"][0]["target_url"].startswith("/f/")
    assert "source_url" in body["items"][0]

    assert client.get("/api/feed?user=../ramsay").status_code == 200
    assert client.get("/api/feed?user=../ramsay").json()["items"] == []


def test_structured_issue_endpoints_parse_public_report(client):
    if os.environ.get("MP_CONTRACT_LIVE") == "1":
        pytest.skip("structured issue endpoints are verified locally before deploy")

    listing = client.get("/api/issues?user=ramsay")
    assert listing.status_code == 200
    issues = listing.json()
    assert issues
    assert {"date", "title", "filename", "structured_url"} <= set(issues[0])

    detail = client.get("/api/issues/2026-06-10/structured?user=ramsay")
    assert detail.status_code == 200
    issue = detail.json()
    assert issue["date"] == "2026-06-10"
    assert issue["slug"] == "2026-06-10"
    assert issue["provenance"]["generated_by"] == "mindpattern.site_content.issue_splitter"
    assert "sections" in issue
    assert "story_units" in issue
    assert "entities" in issue
    assert "source_trail" in issue

    assert client.get("/api/issues/2026-99-99/structured?user=ramsay").status_code == 404
    assert client.get("/api/issues/2026-06-10/structured?user=../ramsay").status_code == 404

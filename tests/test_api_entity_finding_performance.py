"""Cost tests for the public entity and finding endpoints.

These assert on work done, not on wall clock. /api/entities/{slug} measured
10.5s warm and /api/entities 22.4s on the Fly box while both answered in
milliseconds on a laptop, because what is slow there is unindexed sqlite scans,
report-file reads on a network volume, and a blocked event loop. Counting
scans, file reads and index rebuilds reproduces that here; timing it does not.
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from kg.schema import init_kg_schema

# Enough dates that a per-request walk over all of them is visibly different
# from one walk shared by every request.
ISSUE_DATES = [f"2026-06-{day:02d}" for day in range(10, 22)]


def _report_markdown(date: str, index: int) -> str:
    """A report the issue splitter turns into story units with entity refs."""
    return (
        f"# Rabbit Hole briefing {date}\n\n"
        "## Agent Platforms\n\n"
        f"**OpenAI shipped agent runtime changes on {date}.** "
        "OpenAI and Anthropic both moved runtime reliability into buying criteria. "
        + "Full dynamic story body sentence. " * 40
        + "Source: [OpenAI](https://openai.com/news/agents).\n\n"
        "## Tooling\n\n"
        f"**Vercel Platform shipped build tooling on {date}.** "
        f"Vercel Platform changed how deploy caches behave for run {index}. "
        + "Second story body sentence. " * 40
        + "Source: [Vercel](https://vercel.com/changelog).\n"
    )


def _create_memory_db(path):
    conn = sqlite3.connect(path)
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
        CREATE TABLE entity_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT NOT NULL,
            entity_a_type TEXT,
            relationship TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            entity_b_type TEXT,
            finding_id INTEGER,
            created_at TEXT
        );
        """
    )
    init_kg_schema(conn)
    conn.executemany(
        """INSERT INTO findings
           (id, run_date, agent, title, summary, importance, category,
            source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                100 + index,
                date,
                "fixture-agent",
                f"OpenAI runtime reliability update {index}",
                f"OpenAI moved runtime reliability into buying criteria on {date}.",
                "high",
                "agents",
                "https://openai.com/news/agents",
                "OpenAI",
                f"{date}T12:00:00",
            )
            for index, date in enumerate(ISSUE_DATES)
        ],
    )
    conn.executemany(
        """INSERT INTO entity_graph
           (entity_a, entity_a_type, relationship, entity_b, entity_b_type,
            finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                "OpenAI",
                "company",
                "mentions",
                "Vercel Platform",
                "company",
                100 + index,
                f"{date}T12:00:00",
            )
            for index, date in enumerate(ISSUE_DATES)
        ],
    )
    openai_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("OpenAI", "Company", 12, 0.94, ISSUE_DATES[0], ISSUE_DATES[-1]),
    ).lastrowid
    vercel_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Vercel Platform", "Company", 6, 0.61, ISSUE_DATES[0], ISSUE_DATES[-1]),
    ).lastrowid
    # A punctuated canonical name that no report mentions. The slug the site
    # asks for is "opus-4-7"; the name the reader must see is "Opus 4.7".
    opus_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Opus 4.7", "Product", 4, 0.55, ISSUE_DATES[0], ISSUE_DATES[-1]),
    ).lastrowid
    conn.executemany(
        "INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)",
        [(openai_id, "OpenAI"), (vercel_id, "Vercel Platform"), (opus_id, "Opus 4.7")],
    )
    conn.executemany(
        """INSERT INTO kg_edges
           (subject_id, predicate, object_id, fact_text, fact_type, confidence,
            finding_id, valid_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                openai_id,
                "RELEASED",
                vercel_id,
                "OpenAI released runtime reliability updates.",
                "Fact",
                0.94,
                100,
                ISSUE_DATES[-1],
            ),
            (
                opus_id,
                "POWERS",
                openai_id,
                "Opus 4.7 powers the runtime.",
                "Fact",
                0.71,
                100,
                ISSUE_DATES[-1],
            ),
        ],
    )
    conn.commit()
    conn.close()


def _entity_dossier(slug: str, name: str) -> dict:
    return {
        "kind": "entity_dossier",
        "slug": slug,
        "name": name,
        "status": "published",
        "confidence": "source-backed",
        "date": ISSUE_DATES[-1],
        "entity_kind": "entity",
        "json_ld_ready": True,
        "counts": {"findings": 40, "relationships": 152, "sources": 10},
        "relationships": [
            {
                "source": "kg_edges",
                "relationship": "RELEASED",
                "related_entity": "Vercel Platform",
                "related_entity_slug": "vercel-platform",
                "related_entity_type": "Company",
                "entity_a": name,
                "entity_a_type": "Company",
                "entity_b": "Vercel Platform",
                "entity_b_type": "Company",
                "fact_text": "OpenAI released runtime reliability updates.",
                "fact_type": "Fact",
                "confidence": 1.0,
                "finding_id": 100,
                "target_url": "/f/100",
                "evidence_edges": [
                    {"kind": "kg_edge", "relationship": "RELEASED", "id": "1", "target_url": "/f/100"}
                ],
            }
        ],
        "timeline": [
            {
                "date": date,
                "items": [
                    {
                        "finding_id": 100 + index,
                        "title": f"OpenAI runtime reliability update {index}",
                        "source_name": "OpenAI",
                        "source_url": "https://openai.com/news/agents",
                        "target_url": f"/f/{100 + index}",
                    }
                ],
            }
            for index, date in reversed(list(enumerate(ISSUE_DATES)))
        ],
        "top_sources": [
            {"domain": "openai.com", "finding_count": len(ISSUE_DATES), "target_url": "/source/openai.com"}
        ],
        "summary": "",
        "take": "",
        "target_url": f"/e/{slug}",
        "provenance": {
            "generated_by": "mindpattern.site_dossiers.entity_builder",
            "graph_sources": ["entity_graph", "kg_edges", "kg_entities"],
            "provider": "deterministic",
            "redaction_status": "passed",
        },
    }


def _clear_caches(api_routes) -> None:
    """Drop the module-level caches this test file can collide with."""
    for name in (
        "_PUBLIC_RESPONSE_CACHE",
        "_STRUCTURED_ISSUE_CACHE",
        "_ENTITY_ISSUE_INDEX_CACHE",
        "_ENTITY_LIST_INDEX_CACHE",
        "_FINDING_ID_INDEX_CACHE",
    ):
        cache = getattr(api_routes, name, None)
        if cache is not None:
            cache.clear()


@pytest.fixture
def entity_client(tmp_path, monkeypatch):
    from dashboard.routes import api as api_routes

    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    user_dir = data_dir / "ramsay"
    user_dir.mkdir(parents=True)
    _create_memory_db(user_dir / "memory.db")

    report_dir = reports_dir / "ramsay"
    report_dir.mkdir(parents=True)
    for index, date in enumerate(ISSUE_DATES):
        (report_dir / f"{date}.md").write_text(_report_markdown(date, index))

    dossier_dir = report_dir / "site-dossiers" / "entities"
    dossier_dir.mkdir(parents=True)
    (dossier_dir / "openai.json").write_text(json.dumps(_entity_dossier("openai", "OpenAI")))
    # Written before kg_entities carried the punctuated name, the way the real
    # 2026-07-07 opus-4-7.json was.
    (dossier_dir / "opus-4-7.json").write_text(
        json.dumps(_entity_dossier("opus-4-7", "Opus 4 7"))
    )

    monkeypatch.setattr(api_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    # Every cache in api.py is keyed on the data fingerprint, and each test gets
    # a fresh tmp_path whose mtimes differ, so clear the module state that a
    # previous test may have filled under a colliding key.
    api_routes._reset_fingerprint_cache()
    _clear_caches(api_routes)

    from dashboard.app import app

    with TestClient(app) as client:
        yield client

    _clear_caches(api_routes)


def _count_calls(monkeypatch, target, name):
    """Wrap an attribute with a call counter and return the counter list."""
    calls: list = []
    original = getattr(target, name)

    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, counted)
    return calls


def test_entity_pages_read_the_issue_archive_once_not_once_per_page(entity_client, monkeypatch):
    """One walk of the report tree serves every entity page.

    _entity_impl used to open every issue itself and ask each one whether it
    named this entity, so 84 sitemap entities meant 84 walks of 205 files.
    """
    from dashboard.routes import api as api_routes

    lookups = _count_calls(monkeypatch, api_routes, "_structured_issue_from_report_file")

    for slug in ("openai", "vercel-platform", "openai", "vercel-platform"):
        assert entity_client.get(f"/api/entities/{slug}?user=ramsay&limit=40").status_code == 200

    assert len(lookups) == len(ISSUE_DATES)


def test_a_stale_dossier_never_shrinks_the_page_it_is_attached_to(entity_client, monkeypatch):
    """The dossier rides along. It does not answer.

    An earlier pass read the dossier instead of the graph, on the theory that
    the graph scans were what put this endpoint past 10s. They are not: the
    whole live path is 23-62ms per slug once the issue index is warm. What the
    shortcut did cost was the numbers, because run_dossier_generation only
    rewrites the top 25 entities per run, so 61 of the 86 files on disk are
    frozen and 31 of those are dated July.

    This dossier is the shape of a stale one: it names one relationship where
    the graph holds two, and it spells the entity differently. The page must
    report the graph.
    """
    resp = entity_client.get("/api/entities/openai?user=ramsay&limit=40")
    assert resp.status_code == 200
    body = resp.json()

    stale = _entity_dossier("openai", "OpenAI")
    assert len(stale["relationships"]) == 1, "fixture guard: the dossier is thin"

    # The graph carries both the kg_edge and the entity_graph rows.
    assert len(body["relationships"]) >= 2
    assert {rel["source"] for rel in body["relationships"]} == {"kg_edges", "entity_graph"}
    # Counts come from the graph, not from the dossier's frozen snapshot.
    assert body["counts"]["relationships"] == len(body["relationships"])
    assert body["counts"]["relationships"] != stale["counts"]["relationships"]
    assert body["counts"]["findings"] != stale["counts"]["findings"]
    # graph_sources is the live set, not the dossier's provenance list.
    assert "findings_text" in body["graph_sources"]
    assert "newsletter_issues" in body["graph_sources"]
    # And the dossier is still served alongside, for the page's own sections.
    assert body["dossier"]["kind"] == "entity_dossier"


def test_the_display_name_comes_from_the_live_graph_not_the_dossier(entity_client):
    """A dossier written before kg_entities gained the punctuated name.

    Live, /e/opus-4-7 rendered its H1 as "Opus 4 7" where the graph holds
    "Opus 4.7", because that dossier was written 2026-07-07. No newsletter
    names this entity, so nothing else supplies the display name and the
    dossier's copy went straight to the headline. The name a reader sees is
    not a publish-time-cacheable field.
    """
    body = entity_client.get("/api/entities/opus-4-7?user=ramsay&limit=40").json()

    assert body["story_units"] == [], "fixture guard: no issue supplies the name"
    assert body["dossier"]["name"] == "Opus 4 7"
    assert body["name"] == "Opus 4.7"


def test_entity_without_a_dossier_still_reads_the_live_corpus(entity_client):
    """The fallback has to stay whole: most slugs have no dossier."""
    resp = entity_client.get("/api/entities/vercel-platform?user=ramsay&limit=40")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dossier"] is None
    assert "entity_graph" in body["graph_sources"]
    assert body["story_units"]


def test_entity_list_ranks_the_corpus_once_for_every_page(entity_client, monkeypatch):
    """Paging /api/entities must not re-rank 19k entities per page."""
    from orchestrator.site_graph import CorpusGraphReadModel

    ranks = _count_calls(monkeypatch, CorpusGraphReadModel, "list_entities")

    first = entity_client.get("/api/entities?user=ramsay&limit=1&offset=0")
    second = entity_client.get("/api/entities?user=ramsay&limit=1&offset=1")
    filtered = entity_client.get("/api/entities?user=ramsay&q=openai&limit=10")

    assert first.status_code == second.status_code == filtered.status_code == 200
    assert len(ranks) == 1

    assert first.json()["items"][0]["slug"] != second.json()["items"][0]["slug"]
    assert first.json()["has_more"] is True
    assert [item["slug"] for item in filtered.json()["items"]] == ["openai"]
    assert filtered.json()["total"] == 1
    assert "kg_entities" in first.json()["graph_sources"]


def test_a_crawl_burst_cannot_evict_the_corpus_indexes(entity_client, monkeypatch):
    """The response cache clears wholesale. The indexes must not live in it.

    _public_cache_put calls .clear() once _PUBLIC_RESPONSE_CACHE holds 4096
    entries, and crawlers are 99.1% of traffic walking /f/ ids, each adding two
    keys. So roughly 2,000 finding requests wipe it. Rebuilding the 19,092-item
    ranked list and the 22,117-id finding set on the request path because a bot
    walked past is not a cache.
    """
    from dashboard.routes import api as api_routes
    from orchestrator.site_graph import CorpusGraphReadModel

    ranks = _count_calls(monkeypatch, CorpusGraphReadModel, "list_entities")
    ids = _count_calls(monkeypatch, api_routes, "_finding_id_index_impl")

    assert entity_client.get("/api/entities?user=ramsay&limit=1").status_code == 200
    assert entity_client.get("/api/finding/99?user=ramsay").status_code == 404
    assert len(ranks) == 1 and len(ids) == 1

    # What a crawl burst does to the shared response cache.
    api_routes._PUBLIC_RESPONSE_CACHE.clear()

    assert entity_client.get("/api/entities?user=ramsay&limit=1").status_code == 200
    assert entity_client.get("/api/finding/99?user=ramsay").status_code == 404
    assert len(ranks) == 1, "the ranked entity list was rebuilt after an eviction"
    assert len(ids) == 1, "the finding id set was rebuilt after an eviction"


def test_a_filtered_entity_search_does_not_filter_on_the_event_loop(entity_client, monkeypatch):
    """Matching q against 19,092 ranked items is a Python loop, not a query.

    Keeping /api/entities off the loop was the whole reason for the index, so
    the filter has to run in the worker thread with everything else.
    """
    from dashboard.routes import api as api_routes

    offloaded: list[tuple] = []
    real_offload = api_routes._cached_offload

    async def watched(key, user, compute):
        offloaded.append(key)
        return await real_offload(key, user, compute)

    monkeypatch.setattr(api_routes, "_cached_offload", watched)

    assert entity_client.get("/api/entities?user=ramsay&q=openai&limit=10").status_code == 200

    assert offloaded == [("entities", "ramsay", "openai", 10, 0)], (
        "the filtered page has to be computed inside the offload, not after it"
    )


def test_entity_list_reports_missing_database_without_a_rank(tmp_path, monkeypatch):
    from dashboard.routes import api as api_routes
    from dashboard.app import app

    monkeypatch.setattr(api_routes, "DATA_DIR", tmp_path / "nope")
    monkeypatch.setattr(api_routes, "REPORTS_DIR", tmp_path / "nope-reports")
    api_routes._reset_fingerprint_cache()
    api_routes._PUBLIC_RESPONSE_CACHE.clear()

    with TestClient(app) as client:
        body = client.get("/api/entities?user=ramsay").json()

    assert body["status"] == "missing"
    assert body["items"] == []
    assert body["degraded_reasons"] == ["missing memory database"]
    api_routes._PUBLIC_RESPONSE_CACHE.clear()


def test_missing_finding_404s_without_building_a_finding_page(entity_client, monkeypatch):
    """A dead /f/ link must not cost what a live one costs.

    _finding_impl walks the related-paths graph before it can report the miss,
    which is hundreds of queries, and it queues on the shared offload semaphore
    to do it. Behind a crawl burst that took minutes and the site's 10s abort
    turned the 404 into a 500.
    """
    from dashboard.routes import api as api_routes

    def refuse(*args, **kwargs):
        raise AssertionError("missing finding built the full finding page")

    monkeypatch.setattr(api_routes, "_finding_impl", refuse)
    monkeypatch.setattr(api_routes, "_related_findings_impl", refuse)

    for path in (
        "/api/finding/99?user=ramsay",
        "/api/findings/99?user=ramsay",
        "/api/related/99?user=ramsay&mode=blended&limit=8",
    ):
        resp = entity_client.get(path)
        assert resp.status_code == 404, path
        assert resp.json() == {"error": "Finding not found"}


def test_missing_finding_404_never_queues_on_the_offload_semaphore(entity_client, monkeypatch):
    """After the id index is built, a miss answers from memory.

    The semaphore is what a crawl burst saturates, so the cheap answer has to
    be reachable without holding one of its four slots.
    """
    from dashboard.routes import api as api_routes

    assert entity_client.get("/api/finding/99?user=ramsay").status_code == 404

    real_offload = api_routes._cached_offload

    async def guarded(key, user, compute):
        if key[0] != "finding-id-index":
            raise AssertionError(f"missing finding queued on the semaphore for {key[0]}")
        return await real_offload(key, user, compute)

    monkeypatch.setattr(api_routes, "_cached_offload", guarded)
    assert entity_client.get("/api/finding/98?user=ramsay").status_code == 404
    assert entity_client.get("/api/related/98?user=ramsay").status_code == 404


def test_finding_id_above_the_index_high_water_mark_is_not_404d(entity_client, tmp_path):
    """A stale index must never bury a finding that was just written.

    Ids rise, so anything past the highest one the index saw goes to the real
    query instead of being reported as missing.
    """
    from dashboard.routes import api as api_routes

    assert entity_client.get("/api/finding/99?user=ramsay").status_code == 404

    new_id = 100 + len(ISSUE_DATES) + 500
    conn = sqlite3.connect(tmp_path / "data" / "ramsay" / "memory.db")
    conn.execute(
        """INSERT INTO findings
           (id, run_date, agent, title, summary, importance, category,
            source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            new_id,
            ISSUE_DATES[-1],
            "fixture-agent",
            "Written after the id index was built",
            "The index has not seen this row yet.",
            "high",
            "agents",
            "https://openai.com/news/agents",
            "OpenAI",
            f"{ISSUE_DATES[-1]}T13:00:00",
        ),
    )
    conn.commit()
    conn.close()

    # Freeze the fingerprint so the caches cannot notice the write and rebuild.
    api_routes._reset_fingerprint_cache()
    frozen = api_routes._data_fingerprint("ramsay")
    api_routes._FINGERPRINT_CACHE["ramsay"] = (float("inf"), frozen)
    try:
        resp = entity_client.get(f"/api/finding/{new_id}?user=ramsay")
        assert resp.status_code == 200
        assert resp.json()["id"] == new_id
    finally:
        api_routes._reset_fingerprint_cache()


def test_entity_detail_keeps_its_public_shape_on_both_paths(entity_client):
    required = {
        "kind",
        "slug",
        "dossier",
        "name",
        "user",
        "status",
        "confidence",
        "counts",
        "pagination",
        "story_units",
        "findings",
        "relationships",
        "kg_entities",
        "source_trail",
        "issue_dates",
        "graph_sources",
        "total",
        "limit",
        "provenance",
    }
    for slug in ("openai", "vercel-platform"):
        body = entity_client.get(f"/api/entities/{slug}?user=ramsay&limit=40").json()
        assert required <= set(body), slug
        assert body["kind"] == "entity"
        assert body["slug"] == slug
        assert body["pagination"]["limit"] == 40
        assert body["provenance"]["redaction_status"] == "passed"
        for story in body["story_units"]:
            assert story["target_url"].startswith("/briefings/")

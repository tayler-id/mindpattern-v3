"""Cold-cost and restart contracts for /api/finding(s) and /api/related.

Measured on the 22k-finding mirror on 2026-08-26, one cold /api/findings/12721
ran 2,118 sqlite queries: the related-paths walk in
orchestrator/site_graph.py re-derives entities, kg edges and embeddings for
every one of ~300 candidate findings, per request. On the Fly volume each
query pays a network round trip, which is how a page that computes in 83ms
locally hangs past 30s in production. /api/related mode=semantic ran only 2
queries but 1.07s of python, deserializing all 22,167 embeddings and building
22,166 public dicts per request.

These tests assert on work done, not wall clock, the same discipline as
tests/test_api_entity_finding_performance.py:

1. One fingerprint-keyed index build serves every finding and related request.
2. A cold finding page runs a bounded number of sqlite statements.
3. Semantic related does not deserialize the corpus per request.
4. Indexed responses are byte-identical to the unindexed walk.
5. A restart with the disk store intact serves both endpoints from disk,
   with the expensive computes rigged to fail loudly by name.
6. A poisoned disk entry (stale fingerprint key, corrupt json, truncated
   write) is served around and repaired.
7. Ids that are not positive ints never reach the disk store or the computes.
"""

import json
import sqlite3
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from dashboard import site_cache
from kg.schema import init_kg_schema
from orchestrator.site_graph import CorpusGraphReadModel

USER = "ramsay"

# Findings with embeddings, entity rows, kg edges, shared sources and shared
# dates, so the blended walk fires most connector kinds. 104 has no embedding
# and 105 has no entity rows, on purpose.
FINDINGS = [
    # id, run_date, agent, title, summary, source_url, source_name
    (101, "2026-06-12", "agent-a", "OpenAI runtime reliability update",
     "OpenAI shipped runtime reliability updates and the agent stack policy review widens.",
     "https://openai.com/news/agents", "OpenAI"),
    (102, "2026-06-12", "agent-b", "OpenAI runtime reliability benchmark",
     "OpenAI released a runtime reliability benchmark versus rivals, security threat coverage included.",
     "https://openai.com/news/agents", "OpenAI"),
    (103, "2026-06-11", "agent-a", "OpenAI infrastructure update",
     "OpenAI pushed infrastructure changes and regulation export policy dependency questions follow.",
     "https://openai.com/blog/infra", "OpenAI Blog"),
    (104, "2026-06-11", "agent-c", "Vercel Platform build tooling",
     "Vercel Platform shipped build tooling changes for the deploy runtime stack.",
     "https://vercel.com/changelog", "Vercel"),
    (105, "2026-06-10", "agent-b", "Ransomware leak hits registry",
     "A ransomware leak hit a package registry and the security threat research goes deeper.",
     "https://example-security.com/report", "Security Weekly"),
    (106, "2026-06-10", "agent-a", "Model runtime code released",
     "A model runtime code drop released this week competes against the incumbent stack.",
     "https://github.com/example/model", "GitHub"),
    (107, "2026-06-09", "agent-c", "Export regulation update",
     "Export regulation commerce policy changes made dependency management harder.",
     "https://news.example.com/policy", "Example News"),
    (108, "2026-06-09", "agent-b", "Follow-up research on agents",
     "Follow-up research goes deeper on agent runtime reliability with new benchmarks.",
     "https://arxiv.org/abs/2606.00001", "arXiv"),
    (109, "2026-06-08", "agent-a", "OpenAI and Vercel Platform pairing",
     "OpenAI positioned Vercel Platform integrations and shipped runtime updates.",
     "https://openai.com/news/agents", "OpenAI"),
    (110, "2026-06-08", "agent-c", "CVE lands in build chain",
     "A CVE landed in the build chain and threat researchers contrast vendor responses.",
     "https://example-security.com/cve", "Security Weekly"),
    (111, "2026-06-07", "agent-a", "Infrastructure spending update",
     "Infrastructure spending update widens as the model stack changes shipped.",
     "https://news.example.com/infra", "Example News"),
    (112, "2026-06-07", "agent-b", "Agent evals versus benchmarks",
     "Agent evals versus benchmarks contrast sharply, research community follows.",
     "https://arxiv.org/abs/2606.00002", "arXiv"),
]

# Six dimensions is enough to exercise the same float32 dot products the real
# 384-dim vectors go through. 101/102 and 105/110 dot above the 0.45
# semantic-neighbor floor.
EMBEDDINGS = {
    101: [0.71, 0.42, 0.13, 0.05, 0.021, 0.011],
    102: [0.68, 0.44, 0.11, 0.07, 0.019, 0.013],
    103: [0.31, 0.22, 0.61, 0.13, 0.05, 0.02],
    # 104 has no embedding row.
    105: [0.11, 0.09, 0.13, 0.72, 0.41, 0.06],
    106: [0.28, 0.31, 0.44, 0.21, 0.13, 0.09],
    107: [0.13, 0.11, 0.52, 0.33, 0.21, 0.14],
    108: [0.61, 0.39, 0.21, 0.11, 0.09, 0.05],
    109: [0.66, 0.41, 0.17, 0.09, 0.03, 0.02],
    110: [0.13, 0.11, 0.15, 0.69, 0.44, 0.08],
    111: [0.22, 0.19, 0.41, 0.28, 0.17, 0.11],
    112: [0.57, 0.36, 0.24, 0.13, 0.11, 0.07],
}


def _serialize(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _create_memory_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    # Production databases are WAL already. Creating the fixture in WAL keeps
    # the serving layer's own "PRAGMA journal_mode=WAL" a no-op, so the file's
    # mtime, which feeds the cache invalidation key, never moves at serve time.
    conn.execute("PRAGMA journal_mode=WAL")
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
            (fid, date, agent, title, summary, "high", "agents", url, source,
             f"{date}T12:00:{fid % 60:02d}")
            for fid, date, agent, title, summary, url, source in FINDINGS
        ],
    )
    conn.executemany(
        "INSERT INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)",
        [(fid, _serialize(vec)) for fid, vec in EMBEDDINGS.items()],
    )
    # Entity rows for every finding except 105, so the walk sees shared
    # entities on most pairs and an empty entity list on one.
    conn.executemany(
        """INSERT INTO entity_graph
           (entity_a, entity_a_type, relationship, entity_b, entity_b_type,
            finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            ("OpenAI", "company", "mentions", "Vercel Platform", "company",
             fid, "2026-06-12T12:00:00")
            for fid, *_ in FINDINGS
            if fid not in (105, 110)
        ],
    )
    openai_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("OpenAI", "Company", 12, 0.94, "2026-06-07", "2026-06-12"),
    ).lastrowid
    vercel_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Vercel Platform", "Company", 6, 0.61, "2026-06-07", "2026-06-12"),
    ).lastrowid
    conn.executemany(
        "INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)",
        [(openai_id, "OpenAI"), (vercel_id, "Vercel Platform")],
    )
    conn.executemany(
        """INSERT INTO kg_edges
           (subject_id, predicate, object_id, fact_text, fact_type, confidence,
            finding_id, valid_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (openai_id, "RELEASED", vercel_id,
             "OpenAI released runtime reliability updates.", "Fact", 0.94,
             101, "2026-06-12"),
            (openai_id, "PARTNERS_WITH", vercel_id,
             "OpenAI positioned Vercel Platform integrations.", "Fact", 0.81,
             109, "2026-06-08"),
        ],
    )
    conn.commit()
    conn.close()


def _simulate_restart(api_routes) -> None:
    """What a deploy does to the process: every module-level dict goes away."""
    for name, value in list(vars(api_routes).items()):
        if name.endswith(("_CACHE", "_INDEX", "_LOCKS")) and isinstance(value, dict):
            value.clear()


def _forbid(monkeypatch, target, name: str) -> None:
    """The named compute must not run. If it does, say so by name."""

    def tripped(*args, **kwargs):
        raise AssertionError(
            f"{name} ran on a path that must be served without it. A restarted "
            "process must serve finding and related pages from the disk store, "
            "and invalid ids must never reach the computes."
        )

    monkeypatch.setattr(target, name, tripped)


def _count_calls(monkeypatch, target, name):
    """Wrap an attribute with a call counter and return the counter list."""
    calls: list = []
    original = getattr(target, name)

    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, counted)
    return calls


@pytest.fixture
def finding_site(tmp_path, monkeypatch):
    from dashboard import warmup
    from dashboard.routes import api as api_routes

    # The background warm-up task belongs to production boot, not to these
    # tests. It would race the restart simulation below.
    async def _no_warmup():
        return None

    monkeypatch.setattr(warmup, "startup_warmup", _no_warmup)

    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    user_data = data_dir / USER
    user_data.mkdir(parents=True)
    (reports_dir / USER).mkdir(parents=True)
    _create_memory_db(user_data / "memory.db")
    cache_dir = user_data / "site-cache"
    cache_dir.mkdir()

    monkeypatch.setattr(api_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    api_routes._reset_fingerprint_cache()
    _simulate_restart(api_routes)

    from dashboard.app import app

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            api=api_routes,
            data_dir=data_dir,
            cache_dir=cache_dir,
            db_path=user_data / "memory.db",
        )

    _simulate_restart(api_routes)
    api_routes._reset_fingerprint_cache()


def _get_ok(client, url: str):
    response = client.get(url)
    assert response.status_code == 200, f"{url} -> {response.status_code}"
    return response


# ── 1. one index build serves every request ──────────────────────────────


def test_cold_finding_and_related_requests_share_one_index_build(
    finding_site, monkeypatch
):
    """The corpus-constant part of the walk is derived once, not per request.

    Five cold requests across three findings and both related modes must
    trigger exactly one _related_graph_index_impl build. The old code
    re-derived entities, kg edges and embeddings inside every request.
    """
    api = finding_site.api
    builds = _count_calls(monkeypatch, api, "_related_graph_index_impl")

    _get_ok(finding_site.client, f"/api/findings/101?user={USER}")
    _get_ok(finding_site.client, f"/api/findings/103?user={USER}")
    _get_ok(finding_site.client, f"/api/findings/109?user={USER}")
    _get_ok(finding_site.client, f"/api/related/101?mode=blended&limit=8&user={USER}")
    _get_ok(finding_site.client, f"/api/related/102?mode=semantic&limit=8&user={USER}")

    assert len(builds) == 1, (
        f"_related_graph_index_impl ran {len(builds)} times for 5 requests; "
        "the index must build once per content change and be shared"
    )


# ── 2. bounded sqlite work per request ───────────────────────────────────


def test_cold_finding_page_runs_a_bounded_number_of_sqlite_statements(
    finding_site, monkeypatch
):
    """The per-candidate query storm is gone.

    The unindexed walk runs ~6 queries per candidate finding plus ~4
    sqlite_master probes each, which is 2,118 statements on the production
    corpus and about 100 on this fixture. The indexed path needs the index
    build (a handful of bulk scans) plus a few point reads. 40 is far below
    the old cost and leaves room for schema probes.
    """
    api = finding_site.api
    statements: list[str] = []
    original_get_db = api.get_memory_db

    def traced_get_db(user=USER):
        conn = original_get_db(user)
        if conn is not None:
            conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(api, "get_memory_db", traced_get_db)

    _get_ok(finding_site.client, f"/api/findings/101?user={USER}")

    assert len(statements) < 40, (
        f"a cold finding page ran {len(statements)} sqlite statements; "
        "the related-paths walk is re-deriving per-candidate data per request "
        f"(first statements: {statements[:5]})"
    )


def test_related_semantic_does_not_deserialize_the_corpus_per_request(
    finding_site, monkeypatch
):
    """Only the source embedding is deserialized at request time.

    The old path called _deserialize_f32 once per embedding row per request
    (22,167 calls on the mirror). The indexed path reads the corpus matrix
    from the shared index; per request it deserializes the source vector and
    nothing else.
    """
    api = finding_site.api
    calls = _count_calls(monkeypatch, api, "_deserialize_f32")

    _get_ok(finding_site.client, f"/api/related/101?mode=semantic&limit=8&user={USER}")
    _get_ok(finding_site.client, f"/api/related/108?mode=semantic&limit=8&user={USER}")

    corpus_size = len(EMBEDDINGS)
    assert len(calls) <= 4, (
        f"_deserialize_f32 ran {len(calls)} times for 2 semantic requests over "
        f"a {corpus_size}-embedding corpus; the per-request corpus deserialize "
        "must be replaced by the shared index"
    )


# ── 3. byte-identical to the unindexed walk ──────────────────────────────


def _old_finding_payload(api, finding_id: int) -> dict:
    """The pre-index /api/findings/{id} body: bare model, per-request walk."""
    conn = api.get_memory_db(USER)
    assert conn is not None
    try:
        model = CorpusGraphReadModel(conn)
        finding = model.get_finding(finding_id)
        assert finding is not None
        related = model.get_related_paths_for_finding(finding_id, limit=5)
        finding["related_paths"] = related["items"] if related else []
        return finding
    finally:
        conn.close()


def _old_blended_payload(api, finding_id: int, limit: int) -> dict:
    conn = api.get_memory_db(USER)
    assert conn is not None
    try:
        model = CorpusGraphReadModel(conn)
        payload = model.get_related_paths_for_finding(finding_id, limit=limit)
        assert payload is not None
        return payload
    finally:
        conn.close()


def _old_semantic_payload(api, finding_id: int, limit: int) -> dict:
    """The pre-index semantic body via the retained full-scan fallback."""
    conn = api.get_memory_db(USER)
    assert conn is not None
    try:
        payload = api._related_semantic_scan(conn, finding_id, limit)
        assert payload is not None
        return payload
    finally:
        conn.close()


@pytest.mark.parametrize("finding_id", [101, 104, 105])
def test_indexed_finding_page_matches_the_unindexed_walk_byte_for_byte(
    finding_site, finding_id
):
    """No behavior change: same bytes as the per-request walk.

    101 has entities, an embedding and rich connectors. 104 has no embedding.
    105 has no entity rows. All three must serialize identically to the old
    path, connector weights, entity order and float rounding included.
    """
    expected = JSONResponse(_old_finding_payload(finding_site.api, finding_id)).body
    response = _get_ok(finding_site.client, f"/api/findings/{finding_id}?user={USER}")
    assert response.content == expected


@pytest.mark.parametrize("finding_id", [101, 104, 105])
def test_indexed_blended_related_matches_the_unindexed_walk_byte_for_byte(
    finding_site, finding_id
):
    expected = JSONResponse(_old_blended_payload(finding_site.api, finding_id, 8)).body
    response = _get_ok(
        finding_site.client, f"/api/related/{finding_id}?mode=blended&limit=8&user={USER}"
    )
    assert response.content == expected


@pytest.mark.parametrize("finding_id", [101, 104, 108])
def test_indexed_semantic_related_matches_the_full_scan_byte_for_byte(
    finding_site, finding_id
):
    """104 has no embedding, so both paths must return the empty payload."""
    expected = JSONResponse(_old_semantic_payload(finding_site.api, finding_id, 8)).body
    response = _get_ok(
        finding_site.client, f"/api/related/{finding_id}?mode=semantic&limit=8&user={USER}"
    )
    assert response.content == expected


# ── 4. restart with the disk store intact ────────────────────────────────


FINDING_URL = f"/api/findings/101?user={USER}"
BLENDED_URL = f"/api/related/101?mode=blended&limit=8&user={USER}"
SEMANTIC_URL = f"/api/related/101?mode=semantic&limit=8&user={USER}"


def test_a_restart_with_the_disk_store_intact_serves_both_endpoints_from_disk(
    finding_site, monkeypatch
):
    """Warm once, restart, answer from files. The computes stay cold.

    Every restart used to wipe the in-memory caches, so after a deploy nearly
    every finding was cold and the drill-down hung. The finished bodies must
    persist under site-cache/findings and site-cache/related and be served
    back without _finding_impl, _related_findings_impl or the index build.
    """
    api = finding_site.api

    warm_finding = _get_ok(finding_site.client, FINDING_URL)
    warm_blended = _get_ok(finding_site.client, BLENDED_URL)
    warm_semantic = _get_ok(finding_site.client, SEMANTIC_URL)

    findings_dir = finding_site.cache_dir / "findings"
    related_dir = finding_site.cache_dir / "related"
    assert (findings_dir / "101.json").is_file(), (
        "the finding handler persisted nothing under site-cache/findings; a "
        "restart will recompute every finding page"
    )
    assert (related_dir / "101-blended-8.json").is_file(), (
        "the related handler persisted nothing under site-cache/related"
    )
    assert (related_dir / "101-semantic-8.json").is_file()

    _simulate_restart(api)
    _forbid(monkeypatch, api, "_finding_impl")
    _forbid(monkeypatch, api, "_related_findings_impl")
    _forbid(monkeypatch, api, "_related_graph_index_impl")

    assert _get_ok(finding_site.client, FINDING_URL).content == warm_finding.content
    assert _get_ok(finding_site.client, BLENDED_URL).content == warm_blended.content
    assert _get_ok(finding_site.client, SEMANTIC_URL).content == warm_semantic.content


def test_poisoned_disk_entries_are_served_around_and_repaired(finding_site):
    """Stale key, corrupt json and truncated write each cost one recompute.

    The three shapes a bad deploy or a killed writer leaves behind: an
    envelope whose key no longer matches the data fingerprint, a file that is
    not json, and a zero-byte file. Each must read as a miss, serve the
    computed body, and be rewritten whole.
    """
    api = finding_site.api

    warm_finding = _get_ok(finding_site.client, FINDING_URL)
    warm_blended = _get_ok(finding_site.client, BLENDED_URL)
    warm_semantic = _get_ok(finding_site.client, SEMANTIC_URL)

    finding_file = finding_site.cache_dir / "findings" / "101.json"
    blended_file = finding_site.cache_dir / "related" / "101-blended-8.json"
    semantic_file = finding_site.cache_dir / "related" / "101-semantic-8.json"
    assert finding_file.is_file() and blended_file.is_file() and semantic_file.is_file()

    # Stale fingerprint: valid envelope, wrong key, body that must not be
    # served. If this body ever comes back, the fingerprint check is dead.
    finding_file.write_text(
        json.dumps({
            "v": site_cache.SCHEMA_VERSION,
            "key": "0.0:stale",
            "body": {"kind": "finding", "id": 101, "title": "STALE CACHE BODY"},
        })
    )
    blended_file.write_bytes(b'{"truncated')
    semantic_file.write_bytes(b"")

    _simulate_restart(api)

    cold_finding = _get_ok(finding_site.client, FINDING_URL)
    cold_blended = _get_ok(finding_site.client, BLENDED_URL)
    cold_semantic = _get_ok(finding_site.client, SEMANTIC_URL)

    assert b"STALE CACHE BODY" not in cold_finding.content
    assert cold_finding.content == warm_finding.content
    assert cold_blended.content == warm_blended.content
    assert cold_semantic.content == warm_semantic.content

    # The read that hit the rot repairs it in place, atomically.
    for path, warm in (
        (finding_file, warm_finding),
        (blended_file, warm_blended),
        (semantic_file, warm_semantic),
    ):
        envelope = json.loads(path.read_bytes())
        assert envelope["v"] == site_cache.SCHEMA_VERSION
        assert envelope["key"] != "0.0:stale"
        assert envelope["body"] == warm.json()


# ── 5. id validation ─────────────────────────────────────────────────────


def test_nonpositive_ids_never_reach_the_computes_or_the_disk_store(
    finding_site, monkeypatch
):
    """0 and negative ids 404 before any path is built.

    normalize_slug("-5") would strip to "5" and alias another finding's cache
    file, so the positive-int gate must sit in front of the disk layer.
    """
    api = finding_site.api
    _forbid(monkeypatch, api, "_finding_impl")
    _forbid(monkeypatch, api, "_related_findings_impl")
    _forbid(monkeypatch, api, "_related_graph_index_impl")

    for url in (
        f"/api/finding/0?user={USER}",
        f"/api/finding/-5?user={USER}",
        f"/api/findings/-5?user={USER}",
        f"/api/related/0?mode=blended&user={USER}",
        f"/api/related/-5?mode=semantic&user={USER}",
    ):
        assert finding_site.client.get(url).status_code == 404, url

    # FastAPI rejects non-int path params before the handler runs.
    assert finding_site.client.get(f"/api/finding/abc?user={USER}").status_code == 422
    assert finding_site.client.get(
        f"/api/related/9e9?mode=blended&user={USER}"
    ).status_code == 422

    leftovers = [
        str(path)
        for path in finding_site.cache_dir.rglob("*.json")
        if path.parent.name in ("findings", "related")
    ]
    assert not leftovers, f"invalid ids wrote cache files: {leftovers}"


def test_cache_path_accepts_the_new_kinds_and_confines_them():
    root = Path("/tmp/site-cache-root")
    assert site_cache.cache_path(root, "findings", "101") is not None
    assert site_cache.cache_path(root, "related", "101-blended-8") is not None
    assert site_cache.cache_path(root, "nonsense", "101") is None
    assert site_cache.cache_path(root, "findings", "../escape") is None

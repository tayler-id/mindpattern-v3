"""Knowledge-graph population (kg/extract.py, kg/resolve.py, kg/build.py)."""

import json
import sqlite3

import pytest

from core.claude_cli import ClaudeProcessResult
from kg.build import (
    apply_batch_result,
    BuildStats,
    build_kg,
    consolidate,
    init_build_schema,
    select_unprocessed_findings,
)
from kg.extract import (
    build_extraction_prompt,
    parse_extraction_output,
    validate_extraction,
)
from kg.resolve import is_junk_entity, normalize_alias, resolve_entity
from orchestrator.site_graph import CorpusGraphReadModel


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE findings (
            id INTEGER PRIMARY KEY, run_date TEXT, agent TEXT, title TEXT,
            summary TEXT, importance TEXT, category TEXT, source_url TEXT,
            source_name TEXT, created_at TEXT)"""
    )
    rows = [
        (1, "2026-07-01", "agent", "Anthropic releases Claude Fable 5",
         "Anthropic released Claude Fable 5, a new frontier model.",
         "high", "ai", "https://anthropic.com/news", "Anthropic", "2026-07-01"),
        (2, "2026-06-30", "agent", "OpenAI acquires Windsurf",
         "OpenAI acquired Windsurf to bolster coding agents.",
         "high", "ai", "https://openai.com/news", "OpenAI", "2026-06-30"),
        (3, "2026-06-29", "agent", "Quiet infrastructure day",
         "Nothing notable happened.",
         "low", "ai", "https://example.com", "Example", "2026-06-29"),
    ]
    conn.executemany("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    init_build_schema(conn)
    return conn


def _extraction_payload():
    return {
        "findings": [
            {
                "id": 1,
                "entities": [
                    {"name": "Anthropic", "type": "Company"},
                    {"name": "Claude Fable 5", "type": "Product"},
                ],
                "edges": [
                    {"subject": "Anthropic", "predicate": "RELEASED",
                     "object": "Claude Fable 5",
                     "fact": "Anthropic released Claude Fable 5.",
                     "fact_type": "Fact", "confidence": 1.0},
                ],
            },
            {
                "id": 2,
                "entities": [
                    {"name": "OpenAI", "type": "Company"},
                    {"name": "Windsurf", "type": "Company"},
                ],
                "edges": [
                    {"subject": "OpenAI", "predicate": "ACQUIRED",
                     "object": "Windsurf",
                     "fact": "OpenAI acquired Windsurf.",
                     "fact_type": "Fact", "confidence": 1.0},
                ],
            },
            {"id": 3, "entities": [], "edges": []},
        ]
    }


def fake_runner(cmd, *, timeout, **kwargs):
    return ClaudeProcessResult(json.dumps(_extraction_payload()), "", 0)


# ── schema is additive ────────────────────────────────────────────────

def test_init_build_schema_is_idempotent_and_additive(conn):
    before = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    init_build_schema(conn)
    after = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert before == after
    assert {"kg_entities", "kg_entity_aliases", "kg_edges",
            "kg_communities", "kg_build_log"} <= after
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 3


# ── extraction parsing/validation ─────────────────────────────────────

def test_init_schema_migrates_pre_slug_tables():
    """A kg_entities table created before the slug column existed (the pilot
    DB) must migrate via the guarded ALTER — regression for the index-order bug."""
    from kg.schema import init_kg_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE kg_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, canonical_name TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'Other', description TEXT,
            embedding BLOB, mention_count INTEGER DEFAULT 0,
            importance REAL DEFAULT 0.0, first_seen TEXT, last_seen TEXT,
            created_at TEXT DEFAULT (datetime('now')))"""
    )
    conn.execute("INSERT INTO kg_entities (canonical_name) VALUES ('Anthropic')")
    init_kg_schema(conn)  # must not raise
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(kg_entities)")}
    assert "slug" in columns
    init_kg_schema(conn)  # idempotent


def test_parse_extraction_handles_fences_and_garbage():
    payload = json.dumps(_extraction_payload())
    assert len(parse_extraction_output(payload)) == 3
    assert len(parse_extraction_output(f"```json\n{payload}\n```")) == 3
    assert len(parse_extraction_output(f"Preamble text.\n{payload}\nTrailing.")) == 3
    assert parse_extraction_output("no json here") == []
    assert parse_extraction_output("") == []
    assert parse_extraction_output('{"findings": "nope"}') == []


def test_validate_extraction_enforces_vocabularies():
    item = {
        "id": 1,
        "entities": [
            {"name": "Anthropic", "type": "Company"},
            {"name": "Claude Fable 5", "type": "Product"},
            {"name": "Bad Type", "type": "Startup"},          # unknown type
            {"name": "A sentence long enough to be a headline not an entity name",
             "type": "Company"},                                # too long
        ],
        "edges": [
            {"subject": "Anthropic", "predicate": "RELEASED",
             "object": "Claude Fable 5", "fact": "x", "fact_type": "Fact",
             "confidence": 2.5},                                # clamped
            {"subject": "Anthropic", "predicate": "SHIPPED",
             "object": "Claude Fable 5", "fact": "x", "fact_type": "Fact"},  # bad predicate
            {"subject": "Ghost", "predicate": "RELEASED",
             "object": "Claude Fable 5", "fact": "x", "fact_type": "Fact"},  # unknown subject
            {"subject": "Anthropic", "predicate": "PREDICTS",
             "object": "Claude Fable 5", "fact": "y", "fact_type": "Fact"},  # forced Prediction
        ],
    }
    clean = validate_extraction(item, allowed_ids={1})
    names = {e["name"] for e in clean["entities"]}
    assert names == {"Anthropic", "Claude Fable 5"}
    predicates = [e["predicate"] for e in clean["edges"]]
    assert "SHIPPED" not in predicates
    released = next(e for e in clean["edges"] if e["predicate"] == "RELEASED")
    assert released["confidence"] == 1.0
    predicted = next(e for e in clean["edges"] if e["predicate"] == "PREDICTS")
    assert predicted["fact_type"] == "Prediction"


def test_validate_extraction_rejects_foreign_finding_ids():
    assert validate_extraction({"id": 99, "entities": [], "edges": []},
                               allowed_ids={1}) is None


def test_prompt_contains_findings_and_vocabulary(conn):
    rows = select_unprocessed_findings(conn)
    prompt = build_extraction_prompt([dict(r) for r in rows])
    assert "RELEASED" in prompt and "COMPETES_WITH" in prompt
    assert "Anthropic releases Claude Fable 5" in prompt


# ── resolution ────────────────────────────────────────────────────────

def test_junk_entities_rejected():
    assert is_junk_entity("Milvus Blog — Best Embedding Model for RAG 2026")
    assert is_junk_entity("Fortune / Bloomberg")
    assert is_junk_entity("https://example.com")
    assert is_junk_entity("announced")
    assert is_junk_entity("")
    assert not is_junk_entity("Anthropic")
    assert not is_junk_entity("Claude Fable 5")
    assert not is_junk_entity("SWE-bench")


def test_resolve_entity_reuses_aliases_case_insensitively(conn):
    a = resolve_entity(conn, "Anthropic", "Company", seen_date="2026-06-01")
    b = resolve_entity(conn, "anthropic", "Company", seen_date="2026-07-01")
    c = resolve_entity(conn, "ANTHROPIC", "Other", seen_date="2026-05-01")
    assert a == b == c
    row = conn.execute(
        "SELECT entity_type, first_seen, last_seen FROM kg_entities WHERE id = ?", (a,)
    ).fetchone()
    assert row["entity_type"] == "Company"      # Other never downgrades a type
    assert row["first_seen"] == "2026-05-01"
    assert row["last_seen"] == "2026-07-01"


def test_resolve_entity_upgrades_other_type(conn):
    a = resolve_entity(conn, "Windsurf", "Other", seen_date="2026-06-01")
    b = resolve_entity(conn, "Windsurf", "Company", seen_date="2026-06-02")
    assert a == b
    row = conn.execute("SELECT entity_type FROM kg_entities WHERE id = ?", (a,)).fetchone()
    assert row["entity_type"] == "Company"


def test_normalize_alias_matches_punctuation_variants(conn):
    a = resolve_entity(conn, "GPT-5.2", "Product", seen_date="2026-06-01")
    b = resolve_entity(conn, "GPT 5 2", "Product", seen_date="2026-06-02")
    assert normalize_alias("GPT-5.2") == "gpt 5 2"
    assert a == b


def test_resolve_returns_none_for_junk(conn):
    assert resolve_entity(conn, "Fortune / Bloomberg", "Company") is None
    assert conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0] == 0


# ── build loop ────────────────────────────────────────────────────────

def test_build_kg_populates_and_is_resumable(conn):
    stats = build_kg(conn, runner=fake_runner, batch_size=10)
    assert stats.findings_processed == 3
    assert stats.edges_added == 2
    assert conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0] == 4
    edge = conn.execute(
        """SELECT e.predicate, e.fact_type, e.valid_at, e.finding_id,
                  s.canonical_name AS subj, o.canonical_name AS obj
           FROM kg_edges e
           JOIN kg_entities s ON s.id = e.subject_id
           JOIN kg_entities o ON o.id = e.object_id
           WHERE e.predicate = 'RELEASED'"""
    ).fetchone()
    assert edge["subj"] == "Anthropic"
    assert edge["obj"] == "Claude Fable 5"
    assert edge["valid_at"] == "2026-07-01"
    assert edge["finding_id"] == 1

    # second run: everything already processed, nothing duplicated
    again = build_kg(conn, runner=fake_runner, batch_size=10)
    assert again.findings_processed == 0
    assert conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0] == 2


def test_build_kg_marks_failures_and_supports_retry(conn):
    def broken_runner(cmd, *, timeout, **kwargs):
        return ClaudeProcessResult("", "boom", 1)

    stats = build_kg(conn, runner=broken_runner, batch_size=10)
    assert stats.findings_failed == 3
    assert stats.batches_failed == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM kg_build_log WHERE status = 'failed'"
    ).fetchone()[0] == 3
    # not selected again without --retry-failed …
    assert select_unprocessed_findings(conn) == []
    # … but retry picks them up and succeeds
    retry = build_kg(conn, runner=fake_runner, batch_size=10, retry_failed=True)
    assert retry.findings_processed == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM kg_build_log WHERE status = 'failed'"
    ).fetchone()[0] == 0


def test_apply_batch_dedupes_repeated_edges(conn):
    rows = select_unprocessed_findings(conn)
    batch = [r for r in rows if int(r["id"]) == 1]
    validated = {1: validate_extraction(_extraction_payload()["findings"][0],
                                        allowed_ids={1})}
    stats = BuildStats()
    apply_batch_result(conn, batch, validated, stats)
    conn.execute("DELETE FROM kg_build_log")  # force reprocessing of finding 1
    apply_batch_result(conn, batch, validated, stats)
    assert conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0] == 1


# ── consolidation + read-model integration ────────────────────────────

def test_consolidate_scores_and_communities(conn):
    build_kg(conn, runner=fake_runner, batch_size=10)
    summary = consolidate(conn, run_date="2026-07-02")
    assert summary["entities"] == 4
    row = conn.execute(
        "SELECT mention_count, importance FROM kg_entities WHERE canonical_name = 'Anthropic'"
    ).fetchone()
    assert row["mention_count"] == 1
    assert 0.0 < row["importance"] <= 1.0
    # rerun is idempotent (no duplicate community rows for the date)
    consolidate(conn, run_date="2026-07-02")
    dates = conn.execute(
        "SELECT COUNT(*) FROM kg_communities WHERE run_date = '2026-07-02'"
    ).fetchone()[0]
    assert dates <= 2


def test_punctuated_names_roundtrip_from_list_to_detail(conn):
    """'Node.js'-style names must resolve at the slug the list emits (was a 404)."""
    entity_id = resolve_entity(conn, "GPT-5.2", "Product", seen_date="2026-07-01")
    assert entity_id is not None
    row = conn.execute("SELECT slug FROM kg_entities WHERE id = ?", (entity_id,)).fetchone()
    assert row["slug"] == "gpt-5-2"
    model = CorpusGraphReadModel(conn)
    listing = model.list_entities(q="gpt", limit=5)
    slugs = {item["slug"] for item in listing["items"]}
    assert "gpt-5-2" in slugs
    detail = model.get_entity("gpt-5-2")
    assert detail["name"] == "GPT-5.2"


def test_consolidate_backfills_missing_slugs(conn):
    conn.execute(
        "INSERT INTO kg_entities (canonical_name, entity_type) VALUES ('Node.js', 'Technology')"
    )
    consolidate(conn, run_date="2026-07-02")
    row = conn.execute(
        "SELECT slug FROM kg_entities WHERE canonical_name = 'Node.js'"
    ).fetchone()
    assert row["slug"] == "node-js"


def test_kg_edges_emit_related_entity_for_both_directions(conn):
    build_kg(conn, runner=fake_runner, batch_size=10)
    model = CorpusGraphReadModel(conn)
    # Anthropic is the edge SUBJECT → related is the object
    rels = [r for r in model.get_entity("anthropic")["relationships"]
            if r.get("source") == "kg_edges"]
    assert rels[0]["related_entity"] == "Claude Fable 5"
    assert rels[0]["related_entity_slug"] == "claude-fable-5"
    # Windsurf is the edge OBJECT → related must be the subject, not itself
    rels = [r for r in model.get_entity("windsurf")["relationships"]
            if r.get("source") == "kg_edges"]
    assert rels[0]["related_entity"] == "OpenAI"
    # and the neighbors endpoint derives from it
    neighbors = model.get_entity_neighbors("windsurf")
    assert "openai" in {item["slug"] for item in neighbors["items"]}


def test_apply_result_files_matches_in_process_build(conn, tmp_path):
    """The file-based applier (multi-agent path) produces the same graph as
    the in-process builder, skips already-processed findings, and survives a
    missing/corrupt result file."""
    from kg.apply_files import apply_result_files

    chunks = tmp_path / "chunks"
    results = tmp_path / "results"
    chunks.mkdir(), results.mkdir()
    rows = [dict(r) for r in select_unprocessed_findings(conn)]
    (chunks / "chunk-0000.json").write_text(json.dumps(
        [{"id": r["id"], "date": r["run_date"], "title": r["title"],
          "summary": r["summary"]} for r in rows[:2]]))
    (results / "result-0000.json").write_text(json.dumps(
        {"findings": _extraction_payload()["findings"][:2]}))
    (chunks / "chunk-0001.json").write_text(json.dumps(
        [{"id": rows[2]["id"], "date": rows[2]["run_date"],
          "title": rows[2]["title"], "summary": rows[2]["summary"]}]))
    (results / "result-0001.json").write_text("{not json")

    stats = apply_result_files(conn, chunks_dir=chunks, results_dir=results)
    assert stats.findings_processed == 2
    assert stats.findings_failed == 1          # corrupt result → retryable
    assert conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0] == 2
    edge = conn.execute(
        "SELECT predicate FROM kg_edges WHERE finding_id = 1").fetchone()
    assert edge["predicate"] == "RELEASED"

    # idempotent: reapplying the same files changes nothing
    again = apply_result_files(conn, chunks_dir=chunks, results_dir=results)
    assert again.findings_processed == 0
    assert conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0] == 2


def test_read_model_serves_kg_entities_after_build(conn):
    build_kg(conn, runner=fake_runner, batch_size=10)
    consolidate(conn, run_date="2026-07-02")
    model = CorpusGraphReadModel(conn)
    listing = model.list_entities(limit=10)
    assert "kg_entities" in listing["graph_sources"]
    assert all("missing table: kg_entities" != r for r in listing["degraded_reasons"])
    names = {item["name"] for item in listing["items"]}
    assert "Anthropic" in names

    detail = model.get_entity("anthropic")
    kg_rels = [r for r in detail["relationships"] if r.get("source") == "kg_edges"]
    assert kg_rels and kg_rels[0]["relationship"] == "RELEASED"
    assert kg_rels[0]["fact_type"] == "Fact"
    assert kg_rels[0]["target_url"] == "/f/1"


# ── Review fixes (2026-07-10): fail-open, slug integrity, CLI entrypoints ──


def test_select_unprocessed_limit_zero_selects_nothing(conn):
    """limit=0 is a spend cap ('select nothing'), never 'no limit'."""
    assert select_unprocessed_findings(conn, limit=0) == []
    assert len(select_unprocessed_findings(conn, limit=None)) == 3
    assert len(select_unprocessed_findings(conn, limit=2)) == 2


def test_validate_extraction_tolerates_malformed_shapes():
    """Non-dict items and non-list entities/edges return None, never raise."""
    assert validate_extraction("oops", allowed_ids={1}) is None
    assert validate_extraction(None, allowed_ids={1}) is None
    clean = validate_extraction(
        {"id": 1, "entities": {"a": 1}, "edges": "nope"}, allowed_ids={1}
    )
    assert clean == {"id": 1, "entities": [], "edges": []}


def test_parse_extraction_output_salvages_prose_and_filters_non_dicts():
    payload = json.dumps({"findings": [{"id": 1, "entities": [], "edges": []}, "junk"]})
    prose = f"Here is the extraction you asked for:\n```json\n{payload}\n```\nDone!"
    items = parse_extraction_output(prose)
    assert items == [{"id": 1, "entities": [], "edges": []}]
    # bare array payload is off-contract (no findings key) -> []
    assert parse_extraction_output("[1, 2, 3]") == []


def test_slug_unique_index_blocks_duplicates(conn):
    conn.execute(
        "INSERT INTO kg_entities (canonical_name, slug) VALUES ('GPT-5.2', 'gpt-5-2')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO kg_entities (canonical_name, slug) VALUES ('GPT 5.2', 'gpt-5-2')"
        )


def test_init_schema_dedupes_existing_slug_collisions():
    """Pre-UNIQUE databases with colliding slugs migrate: newcomers get -<id>."""
    from kg.schema import init_kg_schema

    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    # old-world table: slug column, non-unique index, duplicate slugs
    raw.execute(
        """CREATE TABLE kg_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, canonical_name TEXT NOT NULL,
            slug TEXT, entity_type TEXT NOT NULL DEFAULT 'Other', description TEXT,
            embedding BLOB, mention_count INTEGER DEFAULT 0,
            importance REAL DEFAULT 0.0, first_seen TEXT, last_seen TEXT,
            created_at TEXT DEFAULT (datetime('now')))"""
    )
    raw.execute("CREATE INDEX idx_kg_entities_slug ON kg_entities(slug)")
    raw.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('GPT-5.2', 'gpt-5-2')")
    raw.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('GPT 5.2', 'gpt-5-2')")
    raw.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('Empty', '')")
    raw.commit()

    init_kg_schema(raw)

    slugs = [r["slug"] for r in raw.execute("SELECT slug FROM kg_entities ORDER BY id")]
    assert slugs[0] == "gpt-5-2"
    assert slugs[1] == "gpt-5-2-2"  # suffixed with its id
    assert slugs[2] is None  # '' normalized to NULL (allowed by UNIQUE)
    # and the index is now UNIQUE
    with pytest.raises(sqlite3.IntegrityError):
        raw.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('x', 'gpt-5-2')")


class _RacingConn:
    """Simulates the concurrent-writer window: the tier-3 slug SELECT misses
    once (the other writer's row not yet visible to our lookups), then the
    INSERT hits the UNIQUE index and the post-conflict re-select adopts it."""

    def __init__(self, real):
        self._real = real
        self._raced = False

    def execute(self, sql, params=()):
        if (
            not self._raced
            and "SELECT id FROM kg_entities WHERE slug = ?" in sql
        ):
            self._raced = True

            class _Empty:
                @staticmethod
                def fetchone():
                    return None

            return _Empty()
        return self._real.execute(sql, params)


def test_resolve_entity_adopts_existing_row_on_slug_race(conn):
    conn.execute(
        "INSERT INTO kg_entities (canonical_name, slug, entity_type) "
        "VALUES ('Acme Corp', 'acme-corp', 'Company')"
    )
    winner_id = conn.execute("SELECT id FROM kg_entities").fetchone()[0]

    entity_id = resolve_entity(_RacingConn(conn), "Acme-Corp", "Company")

    assert entity_id == winner_id
    assert conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0] == 1


def test_consolidate_heal_suffixes_colliding_slugs(conn):
    conn.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('GPT-5.2', NULL)")
    conn.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('GPT 5.2', NULL)")
    conn.commit()

    consolidate(conn, run_date="2026-07-02")

    rows = conn.execute(
        "SELECT id, slug FROM kg_entities ORDER BY id"
    ).fetchall()
    assert rows[0]["slug"] == "gpt-5-2"
    assert rows[1]["slug"] == f"gpt-5-2-{rows[1]['id']}"


def test_apply_batch_stats_not_inflated_by_midbatch_rollback(conn, monkeypatch):
    """A mid-batch failure rolls back rows AND must not count them in stats."""
    import kg.build as kg_build

    calls = {"n": 0}
    real_resolve = kg_build.resolve_entity

    def flaky_resolve(c, name, etype, **kwargs):
        calls["n"] += 1
        if calls["n"] > 2:  # finding 1 resolves both entities, finding 2 blows up
            raise sqlite3.OperationalError("database is locked")
        return real_resolve(c, name, etype, **kwargs)

    monkeypatch.setattr(kg_build, "resolve_entity", flaky_resolve)
    batch = select_unprocessed_findings(conn, limit=2)
    validated = {}
    for item in _extraction_payload()["findings"]:
        clean = validate_extraction(item, allowed_ids={1, 2})
        if clean:
            validated[clean["id"]] = clean
    stats = BuildStats()

    with pytest.raises(sqlite3.OperationalError):
        apply_batch_result(conn, batch, validated, stats)

    assert stats.findings_processed == 0
    assert stats.edges_added == 0
    assert conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0] == 0


def test_build_kg_extraction_exception_fails_open(conn):
    def exploding_runner(cmd, *, timeout, **kwargs):
        raise RuntimeError("subprocess machinery broke")

    stats = build_kg(conn, runner=exploding_runner, batch_size=10)

    assert stats.batches_failed == stats.batches > 0  # failed open, no raise


def test_apply_result_files_survives_malformed_result_file(conn, tmp_path):
    from kg.apply_files import apply_result_files

    chunks = tmp_path / "chunks"
    results = tmp_path / "results"
    chunks.mkdir()
    results.mkdir()
    rows = [dict(r) for r in select_unprocessed_findings(conn)]
    # pair 1: malformed result (non-dict findings entries)
    (chunks / "chunk-0001.json").write_text(json.dumps([rows[0]]))
    (results / "result-0001.json").write_text(json.dumps({"findings": ["oops", None]}))
    # pair 2: valid result for finding 2
    (chunks / "chunk-0002.json").write_text(json.dumps([rows[1]]))
    (results / "result-0002.json").write_text(json.dumps({
        "findings": [{
            "id": int(rows[1]["id"]),
            "entities": [{"name": "OpenAI", "type": "Company"},
                         {"name": "Windsurf", "type": "Company"}],
            "edges": [{"subject": "OpenAI", "predicate": "ACQUIRED",
                       "object": "Windsurf", "fact": "OpenAI acquired Windsurf.",
                       "fact_type": "Fact", "confidence": 1.0}],
        }],
    }))

    stats = apply_result_files(conn, chunks_dir=chunks, results_dir=results)

    assert stats.batches == 2
    assert stats.batches_failed == 1  # the malformed pair failed open
    assert conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0] == 1


def test_extraction_command_is_read_only_and_env_tunable(monkeypatch):
    from kg.extract import DEFAULT_KG_MODEL, extraction_command

    cmd = extraction_command("PROMPT")
    assert cmd[:3] == ["claude", "-p", "PROMPT"]
    assert cmd[cmd.index("--model") + 1] == DEFAULT_KG_MODEL
    assert cmd[cmd.index("--max-turns") + 1] == "1"
    disallowed = cmd[cmd.index("--disallowedTools") + 1]
    for tool in ("Bash", "Write", "Edit", "WebFetch", "Agent"):
        assert tool in disallowed

    monkeypatch.setenv("MP_KG_MODEL", "claude-test-model")
    cmd = extraction_command("PROMPT")
    assert cmd[cmd.index("--model") + 1] == "claude-test-model"


def test_public_slug_matches_site_normalizer():
    from kg.resolve import public_slug

    assert public_slug("Node.js") == "node-js"
    assert public_slug("GPT-5.2") == "gpt-5-2"
    assert public_slug("") == ""


def test_get_entity_null_slug_fallback_uses_write_normalizer(conn):
    """Legacy NULL-slug rows must resolve via the same normalizer that writes
    slugs — the old SQL replace() fallback missed punctuated names entirely."""
    conn.execute("INSERT INTO kg_entities (canonical_name, slug) VALUES ('Node.js', NULL)")
    conn.commit()

    detail = CorpusGraphReadModel(conn).get_entity("node-js")

    assert detail["name"] == "Node.js"


def test_build_main_consolidate_only(tmp_path, capsys):
    from kg.build import main as build_main
    from memory.db import get_db

    db_path = tmp_path / "memory.db"
    get_db(db_path).close()  # create a real memory.db schema

    rc = build_main(["--db-path", str(db_path), "--consolidate-only"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"consolidate"' in out


def test_build_main_errors_on_missing_db(tmp_path):
    from kg.build import main as build_main

    with pytest.raises(SystemExit):
        build_main(["--db-path", str(tmp_path / "nope.db"), "--consolidate-only"])


def test_apply_files_main(tmp_path, capsys):
    from kg.apply_files import main as apply_main
    from memory.db import get_db

    db_path = tmp_path / "memory.db"
    seed = get_db(db_path)
    seed.execute(
        "INSERT INTO findings (run_date, agent, title, summary) "
        "VALUES ('2026-07-01', 'agent', 'T', 'S')"
    )
    seed.commit()
    finding_id = seed.execute("SELECT id FROM findings").fetchone()[0]
    seed.close()

    chunks = tmp_path / "chunks"
    results = tmp_path / "results"
    chunks.mkdir()
    results.mkdir()
    (chunks / "chunk-0001.json").write_text(json.dumps([
        {"id": int(finding_id), "date": "2026-07-01", "title": "T", "summary": "S"}
    ]))
    (results / "result-0001.json").write_text(json.dumps({
        "findings": [{"id": int(finding_id),
                      "entities": [{"name": "Anthropic", "type": "Company"}],
                      "edges": []}],
    }))

    rc = apply_main([
        "--db-path", str(db_path),
        "--chunks-dir", str(chunks),
        "--results-dir", str(results),
    ])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"apply"' in out and '"consolidate"' in out

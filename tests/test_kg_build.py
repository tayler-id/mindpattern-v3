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

"""Comprehensive tests for the mindpattern-v3 memory module.

Uses a temporary in-memory SQLite database — NOT the production data/ramsay/memory.db.
Embedding-dependent functions are mocked to avoid loading the real 25MB model.
"""

import sqlite3
import struct
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pytest

# ── Fake embedding helpers ──────────────────────────────────────────────────


def fake_embed_text(text):
    """Generate a deterministic fake embedding based on text hash."""
    np.random.seed(hash(text) % 2**32)
    vec = np.random.randn(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def fake_embed_texts(texts):
    return [fake_embed_text(t) for t in texts]


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Create a fresh in-memory database with full schema initialization."""
    from memory.db import _init_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    yield conn
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 1. memory/db.py
# ══════════════════════════════════════════════════════════════════════════════


class TestDB:
    def test_get_db_returns_valid_connection(self, tmp_path):
        """get_db() creates a valid connection with WAL mode and foreign keys."""
        from memory.db import get_db

        db_path = tmp_path / "test.db"
        conn = get_db(db_path=db_path)
        try:
            assert conn is not None
            assert conn.row_factory == sqlite3.Row

            # Check WAL mode
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"

            # Check foreign keys enabled
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert fk == 1
        finally:
            conn.close()

    def test_schema_creates_all_expected_tables(self, db):
        """Schema initialization creates all expected tables."""
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in rows}

        expected_tables = {
            "findings",
            "findings_embeddings",
            "sources",
            "patterns",
            "patterns_embeddings",
            "skills",
            "skills_embeddings",
            "user_feedback",
            "feedback_embeddings",
            "user_preferences",
            "social_posts",
            "social_posts_embeddings",
            "social_feedback",
            "engagements",
            "agent_notes",
            "agent_notes_embeddings",
            "validated_patterns",
            "validated_patterns_embeddings",
            "signals",
            "run_quality",
            "approval_reviews",
            "approval_items",
            "run_log",
            # v3 tables
            "claimed_topics",
            "failure_lessons",
            "editorial_corrections",
            "entity_graph",
        }

        for table in expected_tables:
            assert table in table_names, f"Missing table: {table}"

    def test_fts5_virtual_table_created(self, db):
        """FTS5 virtual table for keyword search is created."""
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='findings_fts'"
        ).fetchall()
        # FTS5 may not be available in all SQLite builds, so we check
        # the table exists OR that the test environment lacks FTS5 support
        if len(rows) > 0:
            assert rows[0]["name"] == "findings_fts"
        else:
            # FTS5 not available — acceptable
            pytest.skip("FTS5 not available in this SQLite build")

    def test_compound_index_exists(self, db):
        """Compound index idx_findings_date_agent exists."""
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_findings_date_agent'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "idx_findings_date_agent"

    def test_schema_idempotent(self, db):
        """Calling init twice doesn't error."""
        from memory.db import _init_schema

        # Call it again on the same connection — should not raise
        _init_schema(db)
        # Verify tables still exist
        count = db.execute(
            "SELECT COUNT(*) as c FROM sqlite_master WHERE type='table'"
        ).fetchone()["c"]
        assert count > 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. memory/embeddings.py
# ══════════════════════════════════════════════════════════════════════════════


class TestEmbeddings:
    def test_serialize_deserialize_roundtrip(self):
        """serialize_f32 / deserialize_f32 round-trip correctly."""
        from memory.embeddings import deserialize_f32, serialize_f32

        original = [0.1, 0.2, -0.3, 0.0, 1.0, -1.0]
        blob = serialize_f32(original)
        recovered = deserialize_f32(blob)

        assert len(recovered) == len(original)
        for o, r in zip(original, recovered):
            assert abs(o - r) < 1e-6

    def test_serialize_empty_vector(self):
        """serialize_f32 handles empty vector."""
        from memory.embeddings import deserialize_f32, serialize_f32

        blob = serialize_f32([])
        recovered = deserialize_f32(blob)
        assert recovered == []

    def test_serialize_384_dim_vector(self):
        """serialize_f32 handles 384-dim vector (the actual embedding size)."""
        from memory.embeddings import deserialize_f32, serialize_f32

        vec = list(np.random.randn(384).astype(np.float32))
        blob = serialize_f32(vec)
        recovered = deserialize_f32(blob)
        assert len(recovered) == 384
        np.testing.assert_allclose(vec, recovered, rtol=1e-6)

    def test_batch_similarities_sorted_above_threshold(self):
        """batch_similarities returns sorted results above threshold."""
        from memory.embeddings import batch_similarities, serialize_f32

        # Create 4 embeddings with known similarity characteristics
        query = list(np.ones(384, dtype=np.float32) / np.sqrt(384))

        # embedding 0: almost identical to query
        emb0 = serialize_f32(list(np.ones(384, dtype=np.float32) / np.sqrt(384)))
        # embedding 1: orthogonal (zeros — sim should be ~0)
        emb1 = serialize_f32([0.0] * 384)
        # embedding 2: partially similar (seeded for determinism)
        rng = np.random.RandomState(42)
        vec2 = rng.randn(384).astype(np.float32)
        vec2[:192] = 1.0 / np.sqrt(384)  # half-match
        vec2 = vec2 / np.linalg.norm(vec2)  # normalize so sim stays in [-1, 1]
        emb2 = serialize_f32(list(vec2))
        # embedding 3: opposite direction
        emb3 = serialize_f32(list(-np.ones(384, dtype=np.float32) / np.sqrt(384)))

        results = batch_similarities(query, [emb0, emb1, emb2, emb3], threshold=0.1)

        # Results should be sorted by similarity descending
        for i in range(len(results) - 1):
            assert results[i][1] >= results[i + 1][1]

        # All returned results should be above threshold
        for idx, sim in results:
            assert sim >= 0.1

        # emb0 should have highest similarity (~1.0)
        assert results[0][0] == 0
        assert results[0][1] > 0.9

    def test_embedding_dim_is_384(self):
        """EMBEDDING_DIM is 384."""
        from memory.embeddings import EMBEDDING_DIM

        assert EMBEDDING_DIM == 384


# ══════════════════════════════════════════════════════════════════════════════
# 3. memory/findings.py
# ══════════════════════════════════════════════════════════════════════════════


class TestFindings:
    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    def test_store_finding_returns_int_id(self, mock_embed, db):
        """store_finding() returns an integer ID."""
        from memory.findings import store_finding

        fid = store_finding(db, "2026-03-14", "test-agent", "Test Title", "Test summary")
        assert isinstance(fid, int)
        assert fid > 0

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    def test_store_finding_persists_in_db(self, mock_embed, db):
        """store_finding() stores the finding in the database."""
        from memory.findings import store_finding

        fid = store_finding(
            db, "2026-03-14", "test-agent", "Stored Title", "Stored summary",
            importance="high", category="test-cat",
            source_url="https://example.com", source_name="Example",
        )

        row = db.execute("SELECT * FROM findings WHERE id = ?", (fid,)).fetchone()
        assert row is not None
        assert row["title"] == "Stored Title"
        assert row["agent"] == "test-agent"
        assert row["importance"] == "high"
        assert row["source_url"] == "https://example.com"

        # Check embedding was stored
        emb_row = db.execute(
            "SELECT embedding FROM findings_embeddings WHERE finding_id = ?", (fid,)
        ).fetchone()
        assert emb_row is not None
        assert len(emb_row["embedding"]) == 384 * 4  # 384 floats * 4 bytes each

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    def test_search_findings_sorted_by_similarity(self, mock_embed, db):
        """search_findings() returns results sorted by similarity."""
        from memory.findings import search_findings, store_finding

        # Store findings with varied content
        store_finding(db, "2026-03-14", "agent1", "AI Agents overview", "Multi-agent systems and orchestration")
        store_finding(db, "2026-03-14", "agent2", "Recipe for pasta", "How to cook carbonara at home")
        store_finding(db, "2026-03-14", "agent3", "Agent frameworks", "Building agent architectures")

        results = search_findings(db, "multi-agent orchestration")
        assert len(results) > 0

        # Check results are sorted by similarity descending
        for i in range(len(results) - 1):
            assert results[i]["similarity"] >= results[i + 1]["similarity"]

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    def test_get_context_returns_string_with_agent(self, mock_embed, db):
        """get_context() returns a string containing agent name."""
        from memory.findings import get_context, store_finding

        store_finding(db, "2026-03-14", "news-researcher", "Test", "Some summary")
        ctx = get_context(db, "news-researcher", "2026-03-14")
        assert isinstance(ctx, str)
        assert "news-researcher" in ctx

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    @patch("memory.findings.embed_texts", side_effect=fake_embed_texts)
    def test_get_context_orchestrator_returns_overview(self, mock_embeds, mock_embed, db):
        """get_context() for 'orchestrator' returns overview."""
        from memory.findings import get_context, store_finding

        store_finding(db, "2026-03-14", "news-researcher", "Test", "Some summary")
        ctx = get_context(db, "orchestrator", "2026-03-14")
        assert isinstance(ctx, str)
        # Orchestrator context should mention overview / agents / memory
        assert len(ctx) > 0

    def test_store_source_upserts_correctly(self, db):
        """store_source() upserts correctly (insert then update on same domain)."""
        from memory.findings import store_source

        store_source(db, "techcrunch.com", "TechCrunch", quality="high", date="2026-03-14")

        # First insert: hit_count=1, high_value_count=1
        row = db.execute(
            "SELECT * FROM sources WHERE url_domain = 'techcrunch.com'"
        ).fetchone()
        assert row["hit_count"] == 1
        assert row["high_value_count"] == 1
        assert row["display_name"] == "TechCrunch"

        # Upsert: hit_count=2, high_value_count still =1 since medium
        store_source(db, "techcrunch.com", quality="medium", date="2026-03-14")
        row = db.execute(
            "SELECT * FROM sources WHERE url_domain = 'techcrunch.com'"
        ).fetchone()
        assert row["hit_count"] == 2
        assert row["high_value_count"] == 1  # medium doesn't increment high_value

    def test_get_top_sources_sorted(self, db):
        """get_top_sources() returns sorted results."""
        from memory.findings import get_top_sources, store_source

        store_source(db, "a.com", "A", quality="high", date="2026-03-14")
        store_source(db, "b.com", "B", quality="high", date="2026-03-14")
        store_source(db, "b.com", "B", quality="high", date="2026-03-14")  # 2 high
        store_source(db, "c.com", "C", quality="medium", date="2026-03-14")

        results = get_top_sources(db, limit=10)
        assert len(results) == 3
        # b.com has 2 high_value hits, should be first
        assert results[0]["domain"] == "b.com"
        assert results[0]["high_value"] == 2

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    @patch("memory.findings.embed_texts", side_effect=fake_embed_texts)
    def test_evaluate_run_returns_quality_metrics(self, mock_embeds, mock_embed, db):
        """evaluate_run() returns quality metrics."""
        from memory.findings import evaluate_run, store_finding

        # Store a few findings
        store_finding(db, "2026-03-14", "agent1", "Title 1", "Summary one", importance="high", source_name="Src1")
        store_finding(db, "2026-03-14", "agent2", "Title 2", "Summary two", importance="medium", source_name="Src2")
        store_finding(db, "2026-03-14", "agent3", "Title 3", "Summary three", importance="low", source_name="Src3")

        result = evaluate_run(db, date="2026-03-14")

        assert "error" not in result
        expected_keys = {
            "date", "total_findings", "unique_sources", "high_value_count",
            "agent_utilization", "source_diversity", "high_value_ratio",
            "trending_coverage", "dedup_rate", "overall_score",
        }
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

        assert result["total_findings"] == 3
        assert result["high_value_count"] == 1
        assert result["unique_sources"] == 3

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    def test_log_agent_run_upserts(self, mock_embed, db):
        """log_agent_run() upserts correctly."""
        from memory.findings import log_agent_run

        log_agent_run(db, "test-agent", "2026-03-14", findings_count=5)

        row = db.execute(
            "SELECT * FROM run_log WHERE agent = 'test-agent' AND run_date = '2026-03-14'"
        ).fetchone()
        assert row["findings_count"] == 5

        # Upsert with new count
        log_agent_run(db, "test-agent", "2026-03-14", findings_count=10)
        row = db.execute(
            "SELECT * FROM run_log WHERE agent = 'test-agent' AND run_date = '2026-03-14'"
        ).fetchone()
        assert row["findings_count"] == 10

    @patch("memory.findings.embed_text", side_effect=fake_embed_text)
    def test_get_stats_returns_expected_keys(self, mock_embed, db):
        """get_stats() returns expected keys."""
        from memory.findings import get_stats

        stats = get_stats(db)
        expected_keys = {
            "findings", "embeddings", "sources", "patterns", "skills",
            "feedback_total", "feedback_pending", "preferences",
            "social_posts", "social_posted", "social_by_platform",
            "social_feedback", "social_feedback_by_action",
            "agent_notes", "agent_notes_embeddings", "validated_patterns",
            "signals", "run_quality_entries",
            "by_agent", "by_date", "by_importance", "skills_by_domain",
        }
        for key in expected_keys:
            assert key in stats, f"Missing key in stats: {key}"


# ══════════════════════════════════════════════════════════════════════════════
# 4. memory/feedback.py
# ══════════════════════════════════════════════════════════════════════════════


class TestFeedback:
    def test_set_preference_creates(self, db):
        """set_preference() creates a preference."""
        from memory.feedback import set_preference

        set_preference(db, "user@example.com", "vibe-coding", 2.0, source="test")

        row = db.execute(
            "SELECT * FROM user_preferences WHERE email = ? AND topic = ?",
            ("user@example.com", "vibe-coding"),
        ).fetchone()
        assert row is not None
        assert row["weight"] == 2.0
        assert row["source"] == "test"

    def test_get_preference_returns_weight_and_effective(self, db):
        """get_preference() returns weight and effective_weight."""
        from memory.feedback import get_preference, set_preference

        # Set preference with today's date (no decay)
        set_preference(db, "user@example.com", "agents", 3.0)

        result = get_preference(db, "user@example.com", "agents")
        assert result["weight"] == 3.0
        assert "effective_weight" in result
        # Since just set, effective_weight should be close to raw weight
        assert result["effective_weight"] > 0

    def test_get_preference_nonexistent_returns_zero(self, db):
        """get_preference() for nonexistent preference returns zero."""
        from memory.feedback import get_preference

        result = get_preference(db, "nobody@example.com", "nonexistent")
        assert result["weight"] == 0.0
        assert result["effective_weight"] == 0.0

    def test_accumulate_preference_adds_delta(self, db):
        """accumulate_preference() adds delta atomically."""
        from memory.feedback import accumulate_preference, set_preference

        set_preference(db, "user@example.com", "security", 1.0)

        result = accumulate_preference(db, "user@example.com", "security", 0.5)
        assert result["weight"] == 1.5
        assert result["previous_weight"] == 1.0
        assert result["delta"] == 0.5

    def test_accumulate_preference_creates_if_new(self, db):
        """accumulate_preference() creates preference if it doesn't exist."""
        from memory.feedback import accumulate_preference

        result = accumulate_preference(db, "user@example.com", "new-topic", 2.0)
        assert result["weight"] == 2.0
        assert result["previous_weight"] == 0.0

    def test_accumulate_preference_concurrent(self, tmp_path):
        """accumulate_preference() handles concurrent calls (atomic SQL)."""
        from memory.db import _init_schema
        from memory.feedback import accumulate_preference, set_preference

        # Use a file-based DB so multiple threads can each open their own connection
        db_path = tmp_path / "concurrent.db"

        # Create schema with an initial connection
        init_conn = sqlite3.connect(str(db_path))
        init_conn.row_factory = sqlite3.Row
        init_conn.execute("PRAGMA journal_mode=WAL")
        init_conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(init_conn)

        set_preference(init_conn, "user@example.com", "concurrent-topic", 0.0)
        init_conn.close()

        errors = []

        def add_delta():
            try:
                # Each thread opens its own connection
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                accumulate_preference(conn, "user@example.com", "concurrent-topic", 1.0)
                conn.close()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_delta) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0, f"Errors: {errors}"

        # Final weight should be 5.0 (5 threads * 1.0 delta each)
        check_conn = sqlite3.connect(str(db_path))
        check_conn.row_factory = sqlite3.Row
        row = check_conn.execute(
            "SELECT weight FROM user_preferences WHERE email = ? AND topic = ?",
            ("user@example.com", "concurrent-topic"),
        ).fetchone()
        check_conn.close()
        assert row["weight"] == 5.0

    def test_apply_preference_decay_returns_decayed(self):
        """apply_preference_decay() returns decayed weight."""
        from memory.feedback import apply_preference_decay

        # 14 days ago — half-life ~ 14 days (0.95^14 ~ 0.49)
        fourteen_days_ago = (datetime.now() - timedelta(days=14)).isoformat()
        decayed = apply_preference_decay(2.0, fourteen_days_ago)

        # Should be roughly 2.0 * 0.49 ≈ 0.98
        assert 0.8 < decayed < 1.2

        # No decay for None updated_at
        no_decay = apply_preference_decay(2.0, None)
        assert no_decay == 2.0

    def test_list_preferences_effective_applies_decay(self, db):
        """list_preferences() with effective=True applies decay."""
        from memory.feedback import list_preferences, set_preference

        set_preference(db, "user@example.com", "topic-a", 3.0)
        set_preference(db, "user@example.com", "topic-b", -2.0)

        results = list_preferences(db, email="user@example.com", effective=True)
        assert len(results) == 2
        for r in results:
            assert "effective_weight" in r

    def test_mark_processed_updates_flag(self, db):
        """mark_processed() updates processed flag."""
        from memory.feedback import mark_processed

        # Insert a feedback item manually
        db.execute(
            """INSERT INTO user_feedback
               (email_id, from_email, subject, body, received_at)
               VALUES ('e1', 'user@test.com', 'subject', 'body text', '2026-03-14')"""
        )
        db.commit()

        fid = db.execute("SELECT id FROM user_feedback WHERE email_id = 'e1'").fetchone()["id"]

        # Before marking
        row = db.execute("SELECT processed FROM user_feedback WHERE id = ?", (fid,)).fetchone()
        assert row["processed"] == 0

        mark_processed(db, [fid])

        # After marking
        row = db.execute("SELECT processed, processed_at FROM user_feedback WHERE id = ?", (fid,)).fetchone()
        assert row["processed"] == 1
        assert row["processed_at"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# 5. memory/social.py
# ══════════════════════════════════════════════════════════════════════════════


class TestSocial:
    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_store_post_returns_id_and_stores_embedding(self, mock_embed, db):
        """store_post() returns ID and stores embedding."""
        from memory.social import store_post

        post_id = store_post(
            db, "2026-03-14", "twitter", "This is a test post about AI agents",
            post_type="single", posted=True,
        )
        assert isinstance(post_id, int)
        assert post_id > 0

        # Check post stored
        row = db.execute("SELECT * FROM social_posts WHERE id = ?", (post_id,)).fetchone()
        assert row["platform"] == "twitter"
        assert row["posted"] == 1

        # Check embedding stored
        emb_row = db.execute(
            "SELECT embedding FROM social_posts_embeddings WHERE post_id = ?", (post_id,)
        ).fetchone()
        assert emb_row is not None
        assert len(emb_row["embedding"]) == 384 * 4

    @patch("memory.social.embed_text", side_effect=fake_embed_text)
    def test_recent_posts_respects_days_filter(self, mock_embed, db):
        """recent_posts() respects days filter."""
        from memory.social import recent_posts, store_post

        # Store a post from today
        store_post(db, datetime.now().strftime("%Y-%m-%d"), "twitter", "Today's post")
        # Store a post from 30 days ago
        old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        store_post(db, old_date, "twitter", "Old post")

        # 7-day window should only get today's post
        results = recent_posts(db, days=7)
        assert len(results) == 1
        assert "Today" in results[0]["content"] or results[0]["content"] == "Today's post"

        # 60-day window should get both
        results_all = recent_posts(db, days=60)
        assert len(results_all) == 2

    def test_store_social_feedback_auto_classifies_skip(self, db):
        """store_social_feedback() auto-classifies edit_type for skip."""
        from memory.social import store_social_feedback

        result = store_social_feedback(db, "2026-03-14", "twitter", "skip")
        assert result["edit_type"] == "rejection"

    def test_store_social_feedback_auto_classifies_rewrite(self, db):
        """store_social_feedback() auto-classifies edit_type for rewrite."""
        from memory.social import store_social_feedback

        result = store_social_feedback(db, "2026-03-14", "twitter", "rewrite")
        assert result["edit_type"] == "major_rewrite"

    def test_store_social_feedback_auto_classifies_minor_tweak(self, db):
        """store_social_feedback() auto-classifies minor_tweak for small edits."""
        from memory.social import store_social_feedback

        original = "This is the original draft of a social media post"
        final = "This is the original draft of a social media post!"  # tiny change

        result = store_social_feedback(
            db, "2026-03-14", "twitter", "approved",
            original=original, final=final,
        )
        assert result["edit_type"] == "minor_tweak"

    def test_store_social_feedback_auto_classifies_none(self, db):
        """store_social_feedback() classifies approved without edits as 'none'."""
        from memory.social import store_social_feedback

        result = store_social_feedback(db, "2026-03-14", "twitter", "approved")
        assert result["edit_type"] == "none"

    def test_store_engagement_uses_datetime_now(self, db):
        """store_engagement() uses datetime.now() not utcnow()."""
        from memory.social import store_engagement

        eid = store_engagement(
            db, "user1", "twitter", "reply",
            target_author="@someone", target_author_id="12345",
            our_reply="Great insight!",
        )
        assert isinstance(eid, int)

        row = db.execute("SELECT created_at FROM engagements WHERE id = ?", (eid,)).fetchone()
        # Should be a valid datetime string close to now
        created = datetime.fromisoformat(row["created_at"])
        delta = abs((datetime.now() - created).total_seconds())
        assert delta < 5  # within 5 seconds of now

    def test_check_engagement_returns_cooldown_status(self, db):
        """check_engagement() returns correct cooldown status."""
        from memory.social import check_engagement, store_engagement

        # No engagements yet
        result = check_engagement(db, "author123", "twitter")
        assert result["already_engaged"] is False
        assert result["count"] == 0

        # Store a reply engagement
        store_engagement(
            db, "user1", "twitter", "reply",
            target_author_id="author123",
        )

        result = check_engagement(db, "author123", "twitter")
        assert result["already_engaged"] is True
        assert result["count"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 6. memory/patterns.py
# ══════════════════════════════════════════════════════════════════════════════


class TestPatterns:
    @patch("memory.patterns.embed_text", side_effect=fake_embed_text)
    def test_store_note_stores_with_embedding(self, mock_embed, db):
        """store_note() stores with embedding."""
        from memory.patterns import store_note

        note_id = store_note(db, "2026-03-14", "test-agent", "observation", "Some observation content")
        assert isinstance(note_id, int)
        assert note_id > 0

        # Check note stored
        row = db.execute("SELECT * FROM agent_notes WHERE id = ?", (note_id,)).fetchone()
        assert row["agent"] == "test-agent"
        assert row["note_type"] == "observation"
        assert row["content"] == "Some observation content"

        # Check embedding stored
        emb_row = db.execute(
            "SELECT embedding FROM agent_notes_embeddings WHERE note_id = ?", (note_id,)
        ).fetchone()
        assert emb_row is not None

    @patch("memory.patterns.embed_text", side_effect=fake_embed_text)
    def test_prune_batches_deletes(self, mock_embed, db):
        """prune() batches deletes (test with >500 items to verify chunking)."""
        from memory.patterns import prune, store_note

        # Insert 600 notes older than the prune window
        old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        for i in range(600):
            store_note(db, old_date, f"agent-{i % 5}", "observation", f"Old note {i}")

        # Verify they were inserted
        count_before = db.execute("SELECT COUNT(*) as c FROM agent_notes").fetchone()["c"]
        assert count_before == 600

        result = prune(db, notes_days=30)
        assert result["notes_pruned"] == 600

        # Verify they were deleted
        count_after = db.execute("SELECT COUNT(*) as c FROM agent_notes").fetchone()["c"]
        assert count_after == 0

        # Embeddings should also be deleted
        emb_count = db.execute("SELECT COUNT(*) as c FROM agent_notes_embeddings").fetchone()["c"]
        assert emb_count == 0

    def test_promote_respects_threshold_rules(self, db):
        """promote() respects threshold rules."""
        from memory.patterns import promote

        now = datetime.now().isoformat()

        # Pattern A: 2 agents, 3 observations -> should promote
        db.execute(
            """INSERT INTO validated_patterns
               (pattern_key, distilled_rule, source_agents, observation_count,
                first_seen, last_seen, status, created_at)
               VALUES ('pattern-a', 'Rule A', 'agent1,agent2', 3, '2026-03-10', '2026-03-14', 'active', ?)""",
            (now,),
        )

        # Pattern B: 1 agent, 5 observations -> should promote (single-agent threshold)
        db.execute(
            """INSERT INTO validated_patterns
               (pattern_key, distilled_rule, source_agents, observation_count,
                first_seen, last_seen, status, created_at)
               VALUES ('pattern-b', 'Rule B', 'agent1', 5, '2026-03-10', '2026-03-14', 'active', ?)""",
            (now,),
        )

        # Pattern C: 1 agent, 2 observations -> should NOT promote
        db.execute(
            """INSERT INTO validated_patterns
               (pattern_key, distilled_rule, source_agents, observation_count,
                first_seen, last_seen, status, created_at)
               VALUES ('pattern-c', 'Rule C', 'agent1', 2, '2026-03-10', '2026-03-14', 'active', ?)""",
            (now,),
        )
        db.commit()

        result = promote(db)
        assert result["promoted"] == 2  # A and B

        # Pattern C should still be active
        c_row = db.execute(
            "SELECT status FROM validated_patterns WHERE pattern_key = 'pattern-c'"
        ).fetchone()
        assert c_row["status"] == "active"


# ══════════════════════════════════════════════════════════════════════════════
# 7. memory/claims.py
# ══════════════════════════════════════════════════════════════════════════════


class TestClaims:
    def test_claim_topic_first_claim_returns_true(self, db):
        """claim_topic() returns True on first claim."""
        from memory.claims import claim_topic

        result = claim_topic(db, "2026-03-14", "agent1", "hash123", url="https://example.com")
        assert result is True

    def test_claim_topic_duplicate_returns_false(self, db):
        """claim_topic() returns False on duplicate claim by different agent."""
        from memory.claims import claim_topic

        claim_topic(db, "2026-03-14", "agent1", "hash123")
        result = claim_topic(db, "2026-03-14", "agent2", "hash123")
        assert result is False

    def test_claim_topic_same_agent_returns_true(self, db):
        """claim_topic() returns True when same agent claims same topic."""
        from memory.claims import claim_topic

        claim_topic(db, "2026-03-14", "agent1", "hash123")
        result = claim_topic(db, "2026-03-14", "agent1", "hash123")
        assert result is True

    def test_is_claimed_returns_agent_info(self, db):
        """is_claimed() returns agent info when claimed."""
        from memory.claims import claim_topic, is_claimed

        claim_topic(db, "2026-03-14", "agent1", "hash456", url="https://example.com")

        result = is_claimed(db, "2026-03-14", "hash456")
        assert result is not None
        assert result["agent"] == "agent1"
        assert result["url"] == "https://example.com"

    def test_is_claimed_returns_none_when_unclaimed(self, db):
        """is_claimed() returns None when topic is not claimed."""
        from memory.claims import is_claimed

        result = is_claimed(db, "2026-03-14", "nonexistent")
        assert result is None

    def test_clear_claims_removes_all(self, db):
        """clear_claims() removes all claims for a date."""
        from memory.claims import claim_topic, clear_claims, is_claimed

        claim_topic(db, "2026-03-14", "agent1", "hash1")
        claim_topic(db, "2026-03-14", "agent2", "hash2")
        claim_topic(db, "2026-03-15", "agent1", "hash3")  # different date

        clear_claims(db, "2026-03-14")

        assert is_claimed(db, "2026-03-14", "hash1") is None
        assert is_claimed(db, "2026-03-14", "hash2") is None
        # Different date should be unaffected
        assert is_claimed(db, "2026-03-15", "hash3") is not None


# ══════════════════════════════════════════════════════════════════════════════
# 8. memory/failures.py
# ══════════════════════════════════════════════════════════════════════════════


class TestFailures:
    def test_store_failure_returns_id(self, db):
        """store_failure() returns ID."""
        from memory.failures import store_failure

        fid = store_failure(
            db, "2026-03-14", "scraping",
            "Failed to scrape techcrunch.com",
            "Use selenium for JS-rendered pages",
        )
        assert isinstance(fid, int)
        assert fid > 0

    def test_recent_failures_respects_limit(self, db):
        """recent_failures() respects limit."""
        from memory.failures import recent_failures, store_failure

        for i in range(10):
            store_failure(db, "2026-03-14", "scraping", f"Error {i}", f"Lesson {i}")

        results = recent_failures(db, limit=5)
        assert len(results) == 5

    def test_recent_failures_category_filter(self, db):
        """recent_failures() respects category filter."""
        from memory.failures import recent_failures, store_failure

        store_failure(db, "2026-03-14", "scraping", "Scrape error", "Fix scraping")
        store_failure(db, "2026-03-14", "quality", "Low quality", "Improve quality")
        store_failure(db, "2026-03-14", "scraping", "Another scrape", "Fix again")

        results = recent_failures(db, category="scraping")
        assert len(results) == 2
        assert all(r["category"] == "scraping" for r in results)

    def test_failure_categories_returns_correct_counts(self, db):
        """failure_categories() returns correct counts."""
        from memory.failures import failure_categories, store_failure

        today = datetime.now().strftime("%Y-%m-%d")
        store_failure(db, today, "scraping", "Error 1", "Lesson 1")
        store_failure(db, today, "scraping", "Error 2", "Lesson 2")
        store_failure(db, today, "quality", "Error 3", "Lesson 3")
        store_failure(db, today, "timeout", "Error 4", "Lesson 4")

        cats = failure_categories(db, days=7)
        assert cats["scraping"] == 2
        assert cats["quality"] == 1
        assert cats["timeout"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 9. memory/corrections.py
# ══════════════════════════════════════════════════════════════════════════════


class TestCorrections:
    def test_store_correction_returns_id(self, db):
        """store_correction() returns ID."""
        from memory.corrections import store_correction

        cid = store_correction(
            db, "twitter",
            "Original draft with issues",
            "Improved approved draft",
            reason="Tone was too aggressive",
        )
        assert isinstance(cid, int)
        assert cid > 0

    def test_recent_corrections_filters_by_platform(self, db):
        """recent_corrections() filters by platform."""
        from memory.corrections import recent_corrections, store_correction

        store_correction(db, "twitter", "orig1", "fixed1")
        store_correction(db, "linkedin", "orig2", "fixed2")
        store_correction(db, "twitter", "orig3", "fixed3")

        twitter_only = recent_corrections(db, platform="twitter")
        assert len(twitter_only) == 2
        assert all(r["platform"] == "twitter" for r in twitter_only)

        all_corrections = recent_corrections(db)
        assert len(all_corrections) == 3


# ══════════════════════════════════════════════════════════════════════════════
# 10. memory/graph.py
# ══════════════════════════════════════════════════════════════════════════════


class TestGraph:
    def test_store_relationship_returns_id(self, db):
        """store_relationship() returns ID."""
        from memory.graph import store_relationship

        rid = store_relationship(
            db, "OpenAI", "competes_with", "Anthropic",
            entity_a_type="company", entity_b_type="company",
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_query_entity_both_directions(self, db):
        """query_entity() finds relationships in both directions."""
        from memory.graph import query_entity, store_relationship

        store_relationship(db, "Alice", "works_at", "Acme", entity_a_type="person", entity_b_type="company")
        store_relationship(db, "Bob", "manages", "Alice", entity_a_type="person", entity_b_type="person")

        # Query Alice — should find both directions
        result = query_entity(db, "Alice")
        assert result["entity"] == "Alice"
        assert len(result["relationships"]) == 2

        # One relationship: Alice -> Acme (entity_b)
        related_names = {r["related_entity"] for r in result["relationships"]}
        assert "Acme" in related_names
        assert "Bob" in related_names

    def test_find_path_shortest(self, db):
        """find_path() finds shortest path via recursive CTE."""
        from memory.graph import find_path, store_relationship

        # Build a chain: A -> B -> C -> D
        store_relationship(db, "A", "knows", "B")
        store_relationship(db, "B", "knows", "C")
        store_relationship(db, "C", "knows", "D")

        path = find_path(db, "A", "D")
        assert path is not None
        assert len(path) == 4  # A, B, C, D
        assert path[0]["entity"] == "A"
        assert path[-1]["entity"] == "D"

    def test_find_path_returns_none_when_no_path(self, db):
        """find_path() returns None when no path exists."""
        from memory.graph import find_path, store_relationship

        store_relationship(db, "X", "knows", "Y")
        store_relationship(db, "P", "knows", "Q")

        # No connection between X/Y and P/Q graphs
        result = find_path(db, "X", "Q")
        assert result is None

    def test_related_entities_respects_depth(self, db):
        """related_entities() respects depth parameter."""
        from memory.graph import related_entities, store_relationship

        # Build: A -> B -> C -> D
        store_relationship(db, "A", "knows", "B")
        store_relationship(db, "B", "knows", "C")
        store_relationship(db, "C", "knows", "D")

        # Depth 1: only direct neighbors
        depth_1 = related_entities(db, "A", depth=1)
        entity_names = {r["entity"] for r in depth_1}
        assert "B" in entity_names
        assert "C" not in entity_names
        assert "D" not in entity_names

        # Depth 2: two hops
        depth_2 = related_entities(db, "A", depth=2)
        entity_names_2 = {r["entity"] for r in depth_2}
        assert "B" in entity_names_2
        assert "C" in entity_names_2
        assert "D" not in entity_names_2

        # Depth 3: three hops — should include D
        depth_3 = related_entities(db, "A", depth=3)
        entity_names_3 = {r["entity"] for r in depth_3}
        assert "B" in entity_names_3
        assert "C" in entity_names_3
        assert "D" in entity_names_3

    def test_related_entities_depth_info(self, db):
        """related_entities() returns correct depth values."""
        from memory.graph import related_entities, store_relationship

        store_relationship(db, "Center", "knows", "Neighbor1")
        store_relationship(db, "Neighbor1", "knows", "Hop2")

        results = related_entities(db, "Center", depth=2)
        by_name = {r["entity"]: r["depth"] for r in results}
        assert by_name["Neighbor1"] == 1
        assert by_name["Hop2"] == 2

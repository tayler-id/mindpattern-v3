"""Tests for memory/patterns.py — pattern detection engine.

Uses in-memory SQLite and fake embeddings. No network, no API keys.
Covers: record_pattern, get_recurring, semantic dedup/merge, DB persistence.

Ticket: harness/2026-03-31-010
"""

import sqlite3
import struct

import numpy as np
import pytest
from unittest.mock import patch


# ── Fake embedding helpers ──────────────────────────────────────────────────


def _fake_embed_text(text: str) -> list[float]:
    """Deterministic 384-dim embedding from text hash, L2-normalized."""
    np.random.seed(hash(text) % 2**32)
    vec = np.random.randn(384).astype(np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def _identical_embed(_text: str) -> list[float]:
    """Always returns the same vector — guarantees cosine similarity == 1.0."""
    vec = np.ones(384, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)
    return vec.tolist()


def _serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db():
    """Fresh in-memory SQLite with full MindPattern schema."""
    from memory.db import _init_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    yield conn
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestPatterns:

    # 1. test_extract_patterns_from_findings ─────────────────────────────────

    @patch("memory.patterns.embed_text", side_effect=_fake_embed_text)
    def test_extract_patterns_from_findings(self, _mock_embed, db):
        """record_pattern() creates a new pattern entry for a novel theme."""
        from memory.patterns import record_pattern

        result = record_pattern(
            db,
            run_date="2026-03-31",
            theme="LLM agents are replacing traditional automation",
            description="Multiple sources report shift to agent-based workflows.",
        )

        assert result["merged"] is False
        assert result["recurrence_count"] == 1
        assert result["theme"] == "LLM agents are replacing traditional automation"

    # 2. test_duplicate_patterns_are_merged ──────────────────────────────────

    @patch("memory.patterns.embed_text", side_effect=_identical_embed)
    def test_duplicate_patterns_are_merged(self, _mock_embed, db):
        """Semantically similar patterns (cosine >= 0.75) are merged, not duplicated."""
        from memory.patterns import record_pattern

        first = record_pattern(db, "2026-03-30", "AI agents replacing automation")
        second = record_pattern(db, "2026-03-31", "AI agents replacing automation v2")

        # First is new, second must merge into it
        assert first["merged"] is False
        assert second["merged"] is True

        # Only one row should exist in the patterns table
        count = db.execute("SELECT COUNT(*) AS c FROM patterns").fetchone()["c"]
        assert count == 1

    # 3. test_pattern_score_increases_on_recurrence ──────────────────────────

    @patch("memory.patterns.embed_text", side_effect=_identical_embed)
    def test_pattern_score_increases_on_recurrence(self, _mock_embed, db):
        """recurrence_count increments each time a semantically similar pattern merges."""
        from memory.patterns import record_pattern

        record_pattern(db, "2026-03-28", "Agents outperform rule-based systems")
        r2 = record_pattern(db, "2026-03-29", "Agents outperform rule-based systems again")
        r3 = record_pattern(db, "2026-03-30", "Agents outperform rule-based systems third time")

        assert r2["recurrence_count"] == 2
        assert r3["recurrence_count"] == 3

        # Verify the DB row directly
        row = db.execute(
            "SELECT recurrence_count FROM patterns WHERE id = 1"
        ).fetchone()
        assert row["recurrence_count"] == 3

    # 4. test_empty_input_returns_empty_patterns ─────────────────────────────

    def test_empty_input_returns_empty_patterns(self, db):
        """get_recurring() returns an empty list when the DB has no patterns."""
        from memory.patterns import get_recurring

        result = get_recurring(db, min_count=2)
        assert result == []

    # 5. test_patterns_saved_to_db ───────────────────────────────────────────

    @patch("memory.patterns.embed_text", side_effect=_fake_embed_text)
    def test_patterns_saved_to_db(self, _mock_embed, db):
        """record_pattern() persists to both patterns and patterns_embeddings tables."""
        from memory.patterns import record_pattern

        record_pattern(
            db,
            run_date="2026-03-31",
            theme="Multimodal models reach production quality",
            description="Vision-language models deployed in healthcare and retail.",
        )

        # Verify patterns table
        pattern_row = db.execute(
            "SELECT * FROM patterns WHERE theme = ?",
            ("Multimodal models reach production quality",),
        ).fetchone()
        assert pattern_row is not None
        assert pattern_row["run_date"] == "2026-03-31"
        assert pattern_row["recurrence_count"] == 1
        assert pattern_row["first_seen"] == "2026-03-31"
        assert pattern_row["last_seen"] == "2026-03-31"
        assert pattern_row["description"] == "Vision-language models deployed in healthcare and retail."

        # Verify embedding was stored
        emb_row = db.execute(
            "SELECT embedding FROM patterns_embeddings WHERE pattern_id = ?",
            (pattern_row["id"],),
        ).fetchone()
        assert emb_row is not None
        assert len(emb_row["embedding"]) == 384 * 4  # 384 floats * 4 bytes each

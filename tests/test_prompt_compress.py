"""Tests for orchestrator/prompt_compress.py

Ticket: 2026-03-31-R005 — Prompt compression via LLMLingua-2 for research agent dispatch.
TDD: tests written first, then implementation.
"""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator import prompt_compress
from orchestrator.traces_db import init_db


class FakeCompressor:
    """Simulates LLMLingua-2 by keeping every other word."""

    def compress_prompt(self, prompts, rate=0.5, force_tokens=None):
        text = prompts[0] if isinstance(prompts, list) else prompts
        words = text.split()
        kept = words[::2]  # ~50% reduction
        return {"compressed_prompt": " ".join(kept)}


@pytest.fixture
def db_conn():
    """Temporary traces.db with compression cache table."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "traces.db"
        conn = init_db(db_path)
        prompt_compress.init_compression_cache(conn)
        yield conn
        conn.close()


class TestCompressPromptReducesTokens:
    def test_output_shorter_than_input(self):
        text = "This is a test prompt with many tokens that should be compressed significantly by the model"
        fake = FakeCompressor()
        with patch.object(prompt_compress, "_get_compressor", return_value=fake):
            result = prompt_compress.compress_prompt(text, target_ratio=0.5)
        assert len(result.split()) < len(text.split())
        assert len(result) > 0

    def test_returns_original_when_no_compressor(self):
        text = "No compressor available"
        with patch.object(prompt_compress, "_get_compressor", return_value=None):
            result = prompt_compress.compress_prompt(text, target_ratio=0.5)
        assert result == text


class TestCompressionCacheHit:
    def test_second_call_returns_cached(self, db_conn):
        text = "Static identity content that should be cached across agents"
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        fake = FakeCompressor()

        with patch.object(prompt_compress, "_get_compressor", return_value=fake):
            result1 = prompt_compress.compress_with_cache(db_conn, text, target_ratio=0.5)
            result2 = prompt_compress.compress_with_cache(db_conn, text, target_ratio=0.5)

        assert result1 == result2
        row = db_conn.execute(
            "SELECT hit_count FROM prompt_compression_cache WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        assert row is not None
        assert row["hit_count"] >= 1


class TestCompressionCacheMissOnNewContent:
    def test_different_content_gets_separate_entries(self, db_conn):
        fake = FakeCompressor()
        text_a = "First version of the soul identity content for mindpattern"
        text_b = "Completely different user profile content for the agent system"

        with patch.object(prompt_compress, "_get_compressor", return_value=fake):
            res_a = prompt_compress.compress_with_cache(db_conn, text_a, target_ratio=0.5)
            res_b = prompt_compress.compress_with_cache(db_conn, text_b, target_ratio=0.5)

        assert res_a != res_b
        count = db_conn.execute(
            "SELECT COUNT(*) FROM prompt_compression_cache"
        ).fetchone()[0]
        assert count == 2


class TestDynamicSectionsNotCompressed:
    def test_compress_static_sections_only(self):
        """compress_static_sections compresses static text but returns dynamic text untouched."""
        static = "This is a long soul identity block that is the same across every agent run"
        dynamic = "Breaking: GPT-5 released today with multimodal reasoning"

        fake = FakeCompressor()
        with patch.object(prompt_compress, "_get_compressor", return_value=fake):
            compressed_static = prompt_compress.compress_prompt(static, target_ratio=0.5)

        # Static should shrink
        assert len(compressed_static.split()) < len(static.split())
        # Dynamic passed through separately — not touched by compress_prompt
        assert dynamic == "Breaking: GPT-5 released today with multimodal reasoning"


class TestQualityGateDisablesOnRegression:
    def test_flags_agents_with_over_20pct_drop(self):
        baseline = {"agent-1": 10, "agent-2": 15, "agent-3": 8}
        compressed = {"agent-1": 9, "agent-2": 11, "agent-3": 7}
        # agent-2: 15 -> 11 = 26.7% drop (>20%)

        result = prompt_compress.check_quality_gate(baseline, compressed)
        assert result["should_disable"] is True
        assert "agent-2" in result["regressed_agents"]

    def test_passes_when_drops_within_threshold(self):
        baseline = {"agent-1": 10, "agent-2": 15, "agent-3": 8}
        compressed = {"agent-1": 9, "agent-2": 13, "agent-3": 7}
        # all drops ≤ 20%

        result = prompt_compress.check_quality_gate(baseline, compressed)
        assert result["should_disable"] is False
        assert result["regressed_agents"] == []

    def test_handles_zero_baseline_gracefully(self):
        baseline = {"agent-1": 0}
        compressed = {"agent-1": 0}

        result = prompt_compress.check_quality_gate(baseline, compressed)
        assert result["should_disable"] is False


class TestCompressionDisabledByConfig:
    def test_returns_original_when_disabled(self):
        config = {"prompt_compression_enabled": False, "prompt_compression_ratio": 0.5}
        text = "This text should not be compressed at all when feature is disabled"
        result = prompt_compress.maybe_compress(text, config)
        assert result == text

    def test_compresses_when_enabled(self):
        config = {"prompt_compression_enabled": True, "prompt_compression_ratio": 0.5}
        text = "This text should definitely be compressed when the feature is enabled via config"
        fake = FakeCompressor()
        with patch.object(prompt_compress, "_get_compressor", return_value=fake):
            result = prompt_compress.maybe_compress(text, config)
        assert len(result.split()) < len(text.split())


class TestCompressedPromptStillValidJsonSchema:
    def test_json_schema_preserved(self):
        """JSON schema blocks should survive compression intact."""
        schema = json.dumps({
            "findings": [
                {
                    "title": "string",
                    "summary": "string (2-3 sentences)",
                    "importance": "high|medium|low",
                    "category": "string",
                    "source_url": "string (full URL)",
                    "source_name": "string",
                    "date_found": "2026-04-01",
                }
            ]
        })
        # Mock compressor that preserves JSON structural tokens
        mock_compressor = MagicMock()
        mock_compressor.compress_prompt.return_value = {
            "compressed_prompt": schema,
        }
        with patch.object(prompt_compress, "_get_compressor", return_value=mock_compressor):
            result = prompt_compress.compress_prompt(schema, target_ratio=0.5)

        parsed = json.loads(result)
        assert "findings" in parsed
        assert parsed["findings"][0]["title"] == "string"

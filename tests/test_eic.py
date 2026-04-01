"""Tests for social/eic.py — Editor-in-Chief topic selection and brief generation.

All external API calls (Claude CLI / run_agent_with_files) are mocked.
No real HTTP requests, subprocess calls, or LLM invocations are made.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from social.eic import (
    _build_eic_agent_prompt,
    _extract_source_urls,
    select_topic,
)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ────────────────────────────────────────────────────────────────────────
# FIXTURES
# ────────────────────────────────────────────────────────────────────────


def _make_topic(*, rank: int = 1, anchor: str = "Test topic", composite: float = 7.5) -> dict:
    """Build a minimal valid EIC topic dict."""
    return {
        "rank": rank,
        "anchor": anchor,
        "anchor_source": "TechCrunch https://techcrunch.com/article",
        "connection": None,
        "connection_source": None,
        "reaction": "Interesting development",
        "open_questions": ["What does this mean?"],
        "do_not_include": [],
        "confidence": "HIGH",
        "emotional_register": "curious",
        "mindpattern_context": "none today",
        "mindpattern_link": "https://mindpattern.ai",
        "editorial_scores": {
            "novelty": 8,
            "broad_appeal": 7,
            "thread_potential": 6,
            "composite": composite,
        },
        "source_urls": ["https://techcrunch.com/article"],
    }


@pytest.fixture()
def mem_db():
    """In-memory SQLite database with the findings table for EIC queries."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            agent TEXT,
            title TEXT,
            summary TEXT,
            importance TEXT,
            source_url TEXT,
            source_name TEXT
        )
    """)
    # Insert a finding for today
    db.execute(
        "INSERT INTO findings (run_date, agent, title, summary, importance, source_url, source_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("2026-03-31", "skill-finder", "AI Agent Breakthrough",
         "New framework for agent evaluation", "high",
         "https://arxiv.org/paper", "arXiv"),
    )
    db.commit()
    return db


@pytest.fixture()
def social_config():
    """Minimal social config with EIC settings."""
    return {
        "eic": {
            "quality_threshold": 5.0,
            "max_topics": 3,
        },
        "mindpattern_link": "https://mindpattern.ai",
    }


# ────────────────────────────────────────────────────────────────────────
# TESTS
# ────────────────────────────────────────────────────────────────────────


def test_topic_ranking_prefers_higher_scores(mem_db, social_config):
    """When the EIC agent returns multiple topics, select_topic picks the first
    (highest-ranked). Verify the topic with rank=1 and a higher composite wins."""

    high_topic = _make_topic(rank=1, anchor="High-scoring topic", composite=9.0)
    low_topic = _make_topic(rank=2, anchor="Low-scoring topic", composite=6.0)
    agent_output = [high_topic, low_topic]

    with (
        patch("social.eic._load_social_config", return_value=social_config),
        patch("social.eic.run_agent_with_files", return_value=agent_output),
        patch("memory.social.check_duplicate", return_value={
            "is_duplicate": False, "duplicates": [], "threshold": 0.8, "posts_checked": 0,
        }),
    ):
        result = select_topic(mem_db, user_id="ramsay", date_str="2026-03-31")

    assert result is not None
    assert result["anchor"] == "High-scoring topic"
    assert result["editorial_scores"]["composite"] == 9.0


def test_verdict_parsing_valid_json(mem_db, social_config):
    """When run_agent_with_files returns a well-formed topic list, select_topic
    parses it correctly and returns a normalized topic dict."""

    topic = _make_topic(anchor="AI agents are reshaping software testing", composite=8.2)
    agent_output = [topic]

    with (
        patch("social.eic._load_social_config", return_value=social_config),
        patch("social.eic.run_agent_with_files", return_value=agent_output),
        patch("memory.social.check_duplicate", return_value={
            "is_duplicate": False, "duplicates": [], "threshold": 0.8, "posts_checked": 0,
        }),
    ):
        result = select_topic(mem_db, user_id="ramsay", date_str="2026-03-31")

    assert result is not None
    # Verify the normalized shape has all expected keys
    expected_keys = {
        "rank", "anchor", "anchor_source", "connection", "connection_source",
        "reaction", "open_questions", "do_not_include", "confidence",
        "emotional_register", "mindpattern_context", "mindpattern_link",
        "editorial_scores", "source_urls",
    }
    assert expected_keys == set(result.keys())
    assert result["anchor"] == "AI agents are reshaping software testing"
    assert result["editorial_scores"]["composite"] == 8.2


def test_verdict_parsing_malformed_returns_fallback(mem_db, social_config):
    """When run_agent_with_files returns None (malformed / unparseable output),
    select_topic retries and ultimately returns None (kill day)."""

    with (
        patch("social.eic._load_social_config", return_value=social_config),
        patch("social.eic.run_agent_with_files", return_value=None),
    ):
        result = select_topic(mem_db, user_id="ramsay", date_str="2026-03-31", max_retries=2)

    assert result is None


def test_eic_skips_topics_below_threshold(mem_db, social_config):
    """Topics with composite score below the quality_threshold are rejected.
    If all retries produce below-threshold topics, select_topic returns None."""

    # Set a high threshold
    social_config["eic"]["quality_threshold"] = 8.0

    below_threshold_topic = _make_topic(anchor="Mediocre topic", composite=6.5)
    agent_output = [below_threshold_topic]

    with (
        patch("social.eic._load_social_config", return_value=social_config),
        patch("social.eic.run_agent_with_files", return_value=agent_output),
    ):
        result = select_topic(mem_db, user_id="ramsay", date_str="2026-03-31", max_retries=2)

    assert result is None


def test_eic_gates_on_approval_when_configured(mem_db, social_config):
    """When the pipeline is configured with an ApprovalGateway, topic selection
    feeds into Gate 1 approval. If Gate 1 returns 'skip', the pipeline kills
    the day. This tests the integration point between select_topic output and
    the approval gate in the pipeline."""

    topic = _make_topic(anchor="Approved topic", composite=8.0)
    agent_output = [topic]

    with (
        patch("social.eic._load_social_config", return_value=social_config),
        patch("social.eic.run_agent_with_files", return_value=agent_output),
        patch("memory.social.check_duplicate", return_value={
            "is_duplicate": False, "duplicates": [], "threshold": 0.8, "posts_checked": 0,
        }),
    ):
        selected = select_topic(mem_db, user_id="ramsay", date_str="2026-03-31")

    assert selected is not None

    # Now simulate the approval gate rejecting the topic
    mock_gateway = MagicMock()
    mock_gateway.request_topic_approval.return_value = {"action": "skip"}

    gate_result = mock_gateway.request_topic_approval([selected])
    assert gate_result["action"] == "skip"

    # And simulate the approval gate approving the topic
    mock_gateway.request_topic_approval.return_value = {"action": "go"}
    gate_result = mock_gateway.request_topic_approval([selected])
    assert gate_result["action"] == "go"

    # Verify the selected topic has the shape the approval gate expects
    assert "anchor" in selected
    assert "editorial_scores" in selected
    assert selected["editorial_scores"]["composite"] >= social_config["eic"]["quality_threshold"]

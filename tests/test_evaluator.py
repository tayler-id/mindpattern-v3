"""Tests for orchestrator/evaluator.py newsletter quality scoring."""

from unittest.mock import MagicMock

from orchestrator.evaluator import NewsletterEvaluator


def _make_evaluator():
    return NewsletterEvaluator(db=MagicMock())


# ── Length checks ────────────────────────────────────────────────────────


def test_check_length_penalizes_short_newsletter():
    """A very short newsletter (well under 3000 words) should score < 1.0."""
    ev = _make_evaluator()
    short_text = "Hello world. " * 50  # ~100 words
    score = ev._check_length(short_text)
    assert 0.0 < score < 0.5, f"Short newsletter should be penalized, got {score}"


def test_check_length_rewards_ideal_length():
    """A newsletter in the 3000-5000 word sweet spot should score 1.0."""
    ev = _make_evaluator()
    ideal_text = "word " * 4000  # 4000 words, within [3000, 5000]
    score = ev._check_length(ideal_text)
    assert score == 1.0, f"Ideal-length newsletter should score 1.0, got {score}"


# ── Dedup check ──────────────────────────────────────────────────────────


def test_check_dedup_penalizes_repeated_phrases():
    """Two sections with nearly identical content should lower the dedup score."""
    ev = _make_evaluator()
    duplicated = (
        "## Section One\n"
        "Artificial intelligence agents are transforming software development "
        "workflows and engineering productivity across the industry.\n\n"
        "## Section Two\n"
        "Artificial intelligence agents are transforming software development "
        "workflows and engineering productivity across the industry.\n"
    )
    score = ev._check_dedup(duplicated)
    assert score < 1.0, f"Duplicated sections should be penalized, got {score}"


# ── Sources check ────────────────────────────────────────────────────────


def test_check_sources_rewards_citations():
    """Sections that all contain URLs should score 1.0."""
    ev = _make_evaluator()
    well_sourced = (
        "## Topic A\n"
        "Some findings here. Source: https://example.com/a\n\n"
        "## Topic B\n"
        "More findings here. Source: https://example.com/b\n"
    )
    score = ev._check_sources(well_sourced)
    assert score == 1.0, f"All sections have URLs, expected 1.0, got {score}"


# ── Full evaluate() ──────────────────────────────────────────────────────


def test_evaluate_returns_score_between_0_and_1():
    """evaluate() should return all dimension scores in [0.0, 1.0]."""
    ev = _make_evaluator()
    newsletter = (
        "## AI Updates\n"
        "GPT-5 released with better reasoning. Why it matters: huge leap.\n"
        "Source: https://openai.com/gpt5\n\n"
        "## Developer Tools\n"
        "Copilot agent mode launched. Try this: enable it in VS Code.\n"
        "Source: https://github.blog/copilot\n"
    )
    reports = [
        {"agent": "news", "title": "GPT-5 Released", "importance": "high"},
        {"agent": "tools", "title": "Copilot Agent Mode", "importance": "high"},
    ]
    prefs = [
        {"topic": "artificial intelligence", "weight": 2.0},
        {"topic": "developer tools", "weight": 1.5},
    ]
    result = ev.evaluate(newsletter, reports, prefs)

    expected_keys = {"coverage", "dedup", "sources", "actionability", "length", "topic_balance", "overall"}
    assert set(result.keys()) == expected_keys

    for key, val in result.items():
        assert 0.0 <= val <= 1.0, f"{key} = {val} is out of [0.0, 1.0]"


def test_evaluate_empty_newsletter_does_not_crash():
    """An empty newsletter with no reports or preferences should not raise."""
    ev = _make_evaluator()
    result = ev.evaluate("", [], [])

    for key, val in result.items():
        assert 0.0 <= val <= 1.0, f"{key} = {val} is out of [0.0, 1.0]"

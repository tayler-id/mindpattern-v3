"""Tests for orchestrator/evaluator.py newsletter quality scoring."""

from unittest.mock import MagicMock

from orchestrator.evaluator import NewsletterEvaluator, assess_quality_floor


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


# ── Quality floor helper ─────────────────────────────────────────────────


def _synthetic_findings(
    *,
    count: int,
    agents: int,
    sources: int,
    unique_urls: int | None = None,
):
    unique_urls = count if unique_urls is None else unique_urls
    rows = []
    for idx in range(count):
        url_idx = idx % max(1, unique_urls)
        rows.append({
            "agent": f"agent-{idx % agents}",
            "title": f"Story {idx}",
            "source_url": f"https://source{idx % sources}.example/story-{url_idx}",
            "source_name": f"source-{idx % sources}",
        })
    return rows


def test_assess_quality_floor_passes_good_synthetic_run():
    findings = _synthetic_findings(count=100, agents=13, sources=6)
    preflight_data = {
        "source_counts": {
            "rss": 20, "hn": 15, "reddit": 12, "twitter": 12,
            "exa": 14, "youtube": 10,
        },
        "source_health_summary": {
            "expected_source_count": 8,
            "responsive_source_count": 8,
            "unavailable_sources": [],
            "degraded_sources": [],
        },
    }

    result = assess_quality_floor(
        {"overall": 0.86, "coverage": 0.9, "dedup": 0.95, "sources": 0.9},
        findings=findings,
        preflight_data=preflight_data,
    )

    assert result["status"] == "pass"
    assert result["passed"] is True
    assert result["reasons"] == []
    assert result["metrics"]["agent_count"] == 13


def test_assess_quality_floor_marks_degraded_synthetic_run():
    findings = _synthetic_findings(count=75, agents=9, sources=3, unique_urls=60)
    preflight_data = {
        "source_counts": {"rss": 25, "hn": 20, "arxiv": 30},
        "source_health_summary": {
            "expected_source_count": 6,
            "responsive_source_count": 4,
            "unavailable_sources": ["reddit"],
            "degraded_sources": [],
        },
    }

    result = assess_quality_floor(
        {"overall": 0.68, "coverage": 0.66, "dedup": 0.82, "sources": 0.7},
        findings=findings,
        preflight_data=preflight_data,
    )

    assert result["status"] == "degraded"
    assert result["passed"] is False
    assert result["retryable"] is False
    assert any("agent coverage" in reason for reason in result["reasons"])
    assert any("source diversity" in reason for reason in result["reasons"])


def test_assess_quality_floor_marks_retryable_bad_synthetic_run():
    findings = _synthetic_findings(count=25, agents=6, sources=1, unique_urls=8)
    preflight_data = {
        "source_counts": {"arxiv": 25},
        "source_health_summary": {
            "expected_source_count": 8,
            "responsive_source_count": 1,
            "unavailable_sources": [],
            "degraded_sources": ["rss", "hn", "twitter"],
        },
    }

    result = assess_quality_floor(
        {"overall": 0.42, "coverage": 0.38, "dedup": 0.55, "sources": 0.25},
        findings=findings,
        preflight_data=preflight_data,
    )

    assert result["status"] == "fail_retryable"
    assert result["degraded"] is True
    assert result["retryable"] is True
    assert any("finding volume" in reason for reason in result["reasons"])
    assert any("unique URL ratio" in reason for reason in result["reasons"])

"""Tests for orchestrator/evaluator.py newsletter quality scoring."""

from unittest.mock import MagicMock

from orchestrator.evaluator import (
    NewsletterEvaluator,
    assess_quality_floor,
    detect_duplicate_story_risk,
)


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


def test_duplicate_story_risk_flags_repeated_url():
    current = [{
        "title": "OpenAI ships agent workflow SDK",
        "summary": "Developers can orchestrate multi-step coding agents.",
        "source_url": "https://example.com/openai-agent-sdk?utm=feed",
        "source_name": "Example",
    }]
    recent = [{
        "title": "OpenAI ships agent workflow SDK",
        "summary": "Developers can orchestrate multi-step coding agents.",
        "source_url": "https://example.com/openai-agent-sdk",
        "source_name": "Example",
    }]

    risk = detect_duplicate_story_risk(current, recent)

    assert risk["duplicate_count"] == 1
    assert risk["repeated_urls"][0]["current_title"] == "OpenAI ships agent workflow SDK"


def test_quality_floor_flags_repeated_adjacent_day_angle():
    current = _synthetic_findings(count=80, agents=13, sources=5)
    current[0] = {
        "agent": "agent-0",
        "title": "OpenAI agent SDK automates developer workflows",
        "summary": "The SDK coordinates tool calls, coding agents, and workflow steps for developers.",
        "source_url": "https://fresh.example/openai-agent-sdk-followup",
        "source_name": "Fresh Source",
    }
    recent = [{
        "agent": "agent-1",
        "title": "OpenAI launches agent SDK for workflow automation",
        "summary": "The launch coordinates tool calls, coding agents, and developer workflow steps.",
        "source_url": "https://old.example/openai-agent-sdk",
        "source_name": "Old Source",
        "run_date": "2026-06-25",
    }]

    result = assess_quality_floor(
        {"overall": 0.86, "coverage": 0.9, "dedup": 0.95, "sources": 0.9},
        findings=current,
        recent_findings=recent,
        preflight_data={
            "source_counts": {"rss": 20, "hn": 20, "reddit": 15, "twitter": 10, "exa": 10},
            "source_health_summary": {
                "expected_source_count": 8,
                "responsive_source_count": 8,
            },
        },
    )

    # The detector must still SEE the repeat — that diagnostic is the point.
    assert result["duplicate_story_risk"]["repeated_angles"]
    # ...but one follow-up in 80 findings (risk 0.0125) is normal coverage, not
    # a quality failure. Before the 2026-07-24 recalibration the ceiling was
    # exactly 0.0, so this degraded every issue that ever followed up a story.
    assert result["metrics"]["duplicate_story_risk"] < 0.15
    assert result["status"] == "pass"


def test_quality_floor_degrades_when_repeats_dominate_the_issue():
    """Recalibrated ceiling still fires when an issue is mostly rehash."""
    current = _synthetic_findings(count=10, agents=13, sources=5)
    recent = []
    for idx in range(4):
        current[idx] = {
            "agent": "agent-0",
            "title": f"OpenAI agent SDK automates developer workflows {idx}",
            "summary": "The SDK coordinates tool calls, coding agents, and workflow steps for developers.",
            "source_url": f"https://fresh.example/openai-agent-sdk-followup-{idx}",
            "source_name": "Fresh Source",
        }
        recent.append({
            "agent": "agent-1",
            "title": f"OpenAI launches agent SDK for workflow automation {idx}",
            "summary": "The launch coordinates tool calls, coding agents, and developer workflow steps.",
            "source_url": f"https://old.example/openai-agent-sdk-{idx}",
            "source_name": "Old Source",
            "run_date": "2026-06-25",
        })

    result = assess_quality_floor(
        {"overall": 0.86, "coverage": 0.9, "dedup": 0.95, "sources": 0.9},
        findings=current,
        recent_findings=recent,
        preflight_data={
            "source_counts": {"rss": 20, "hn": 20, "reddit": 15, "twitter": 10, "exa": 10},
            "source_health_summary": {
                "expected_source_count": 8,
                "responsive_source_count": 8,
            },
        },
    )

    assert result["metrics"]["duplicate_story_risk"] >= 0.15
    assert result["status"] != "pass"
    assert any("duplicate story risk" in reason for reason in result["reasons"])


def test_duplicate_story_risk_does_not_overblock_related_story():
    current = [{
        "title": "Anthropic cuts Claude batch API pricing",
        "summary": "The new price tier changes cost planning for long-running document analysis jobs.",
        "source_url": "https://example.com/claude-batch-pricing",
    }]
    recent = [{
        "title": "OpenAI releases agent SDK for workflow automation",
        "summary": "The launch coordinates tool calls, coding agents, and developer workflow steps.",
        "source_url": "https://example.com/openai-agent-sdk",
    }]

    risk = detect_duplicate_story_risk(current, recent)

    assert risk["duplicate_count"] == 0
    assert risk["risk"] == 0.0


# ═══════════════════════════════════════════════════════════════════════
# Quality-floor recalibration (2026-07-24)
#
# The floor returned degraded/fail on all 27 logged verdicts and never once
# passed. Two thresholds were unreachable by construction:
#
#  * max_duplicate_story_risk = 0.0 — a ceiling of literally zero. Observed
#    healthy runs sit at 0.046-0.108, so it fired every single day.
#  * max_single_source_ratio = 0.35 applied to `single_source_ratio`, which
#    counted RAW PREFLIGHT CANDIDATES. RSS dominates that pool because feeds
#    are verbose (176 items vs github 123 vs arxiv 30), not because the
#    newsletter is narrow. July range was 0.367-0.550; even with reddit
#    restored it breaches 0.35 on 19 of 24 days.
#
# The concentration that matters is among findings that actually reached
# the newsletter. That is top_domain_ratio, whose observed July range is
# 0.138-0.298 — a 0.35 ceiling on it is both meaningful and achievable.
# ═══════════════════════════════════════════════════════════════════════


def _findings_with_domains(domain_counts: dict[str, int]):
    rows = []
    idx = 0
    for domain, n in domain_counts.items():
        for _ in range(n):
            rows.append({
                "agent": f"agent-{idx % 13}",
                "title": f"Story {idx}",
                "source_url": f"https://{domain}/story-{idx}",
                "source_name": domain,
            })
            idx += 1
    return rows


class TestTopDomainRatio:
    def test_measures_findings_not_preflight_candidates(self):
        """A verbose RSS candidate pool must not fail an otherwise diverse issue."""
        findings = _findings_with_domains(
            {"arxiv.org": 19, "github.com": 10, "x.com": 8, "techcrunch.com": 7,
             "aws.amazon.com": 5, "theverge.com": 3, "openai.com": 3}
        )
        result = assess_quality_floor(
            {"overall": 0.8, "coverage": 0.8, "dedup": 0.9, "sources": 0.8},
            findings=findings,
            # rss is 43% of raw candidates — the old gate failed on this alone
            preflight_data={
                "source_counts": {"rss": 176, "github": 123, "arxiv": 30,
                                  "exa": 25, "hn": 21, "twitter": 18, "youtube": 15},
                "source_health_summary": {
                    "expected_source_count": 8, "responsive_source_count": 8,
                },
            },
        )
        assert result["metrics"]["top_domain_ratio"] < 0.35
        assert not any("dominance" in r for r in result["reasons"])

    def test_flags_a_genuinely_single_source_issue(self):
        findings = _findings_with_domains({"arxiv.org": 40, "github.com": 5})
        result = assess_quality_floor(
            {"overall": 0.8, "coverage": 0.8, "dedup": 0.9, "sources": 0.8},
            findings=findings,
            preflight_data={
                "source_counts": {"rss": 50, "github": 50, "arxiv": 50, "hn": 50},
                "source_health_summary": {
                    "expected_source_count": 8, "responsive_source_count": 8,
                },
            },
        )
        assert result["metrics"]["top_domain_ratio"] > 0.50
        assert result["status"] == "fail_retryable"
        assert any("domain concentration" in r for r in result["reasons"])

    def test_ignores_www_and_scheme_when_grouping(self):
        findings = _findings_with_domains({"www.arxiv.org": 5, "arxiv.org": 5})
        result = assess_quality_floor(
            {}, findings=findings, preflight_data={}
        )
        assert result["metrics"]["top_domain_ratio"] == 1.0


class TestDuplicateStoryRiskCeiling:
    def test_zero_ceiling_is_gone(self):
        """A ceiling of exactly 0.0 made every run fail; follow-up coverage is normal."""
        from orchestrator.evaluator import QUALITY_FLOOR_THRESHOLDS as T
        assert T["max_duplicate_story_risk"] > 0.0
        assert T["retryable_max_duplicate_story_risk"] > T["max_duplicate_story_risk"]

    def test_observed_healthy_risk_does_not_degrade(self):
        """0.046-0.108 was the real July range on issues Tayler judged fine."""
        from orchestrator.evaluator import QUALITY_FLOOR_THRESHOLDS as T
        assert T["max_duplicate_story_risk"] > 0.108

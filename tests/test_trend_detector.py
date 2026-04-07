"""Tests for deterministic trend detection from preflight data.

Replaces the old Haiku-based trend scanner with a pure Python approach
that clusters preflight items by topic similarity, scores by engagement
and source diversity, and learns which trends led to newsletter inclusion.
"""

import sqlite3
from datetime import datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def preflight_items():
    """Sample preflight items simulating a real run."""
    return [
        # Cluster 1: "Claude Code" — 3 items from 3 sources (strong trend)
        {
            "source": "hn", "source_name": "Hacker News",
            "title": "Claude Code becomes #1 AI coding assistant",
            "url": "https://example.com/1", "published": "2026-04-05T10:00:00",
            "content_preview": "Claude Code overtakes Copilot in market share",
            "metrics": {"points": 450, "comments": 200},
            "already_covered": False, "match_info": None,
        },
        {
            "source": "reddit", "source_name": "r/MachineLearning",
            "title": "Claude Code review: the best AI coding tool in 2026",
            "url": "https://example.com/2", "published": "2026-04-05T11:00:00",
            "content_preview": "After 3 months with Claude Code, here are my thoughts",
            "metrics": {"score": 800, "comments": 150},
            "already_covered": False, "match_info": None,
        },
        {
            "source": "rss", "source_name": "Simon Willison",
            "title": "Why Claude Code changed my development workflow",
            "url": "https://example.com/3", "published": "2026-04-05T09:00:00",
            "content_preview": "Claude Code has fundamentally changed how I write code",
            "metrics": {},
            "already_covered": False, "match_info": None,
        },
        # Cluster 2: "GPT-5" — 2 items from 2 sources (moderate trend)
        {
            "source": "twitter", "source_name": "X/Twitter",
            "title": "GPT-5 benchmarks leaked showing massive improvements",
            "url": "https://example.com/4", "published": "2026-04-05T12:00:00",
            "content_preview": "New benchmarks show GPT-5 outperforming Claude on coding",
            "metrics": {"likes": 5000, "retweets": 1200},
            "already_covered": False, "match_info": None,
        },
        {
            "source": "hn", "source_name": "Hacker News",
            "title": "GPT-5 performance analysis and comparison",
            "url": "https://example.com/5", "published": "2026-04-05T13:00:00",
            "content_preview": "Detailed analysis of GPT-5 vs Claude vs Gemini",
            "metrics": {"points": 300, "comments": 180},
            "already_covered": False, "match_info": None,
        },
        # Singleton: only 1 item, 1 source (weak signal)
        {
            "source": "arxiv", "source_name": "arXiv",
            "title": "A novel approach to transformer quantization",
            "url": "https://example.com/6", "published": "2026-04-05T08:00:00",
            "content_preview": "We present a new method for 4-bit quantization",
            "metrics": {},
            "already_covered": False, "match_info": None,
        },
        # Already covered item (should be excluded from trend detection)
        {
            "source": "hn", "source_name": "Hacker News",
            "title": "Old news about AI agents from last week",
            "url": "https://example.com/7", "published": "2026-04-05T07:00:00",
            "content_preview": "This was already covered",
            "metrics": {"points": 100},
            "already_covered": True,
            "match_info": {"matched_finding": "AI agents roundup", "similarity": 0.92},
        },
    ]


class TestDetectTrends:
    """detect_trends() clusters preflight items and scores them."""

    def test_returns_list_of_trend_dicts(self, preflight_items):
        from preflight.trends import detect_trends
        trends = detect_trends(preflight_items)
        assert isinstance(trends, list)
        assert len(trends) > 0
        for t in trends:
            assert "topic" in t
            assert "evidence" in t
            assert "score" in t
            assert "source_count" in t
            assert "item_count" in t
            assert "items" in t

    def test_excludes_already_covered_items(self, preflight_items):
        from preflight.trends import detect_trends
        trends = detect_trends(preflight_items)
        all_urls = []
        for t in trends:
            all_urls.extend(item["url"] for item in t["items"])
        assert "https://example.com/7" not in all_urls

    def test_multi_source_cluster_scores_higher(self, preflight_items):
        """Claude Code cluster (3 items, 3 sources) should score higher than singleton."""
        from preflight.trends import detect_trends
        trends = detect_trends(preflight_items)
        # Trends should be sorted by score descending
        assert trends[0]["source_count"] >= 2
        assert trends[0]["score"] > trends[-1]["score"]

    def test_sorted_by_score_descending(self, preflight_items):
        from preflight.trends import detect_trends
        trends = detect_trends(preflight_items)
        scores = [t["score"] for t in trends]
        assert scores == sorted(scores, reverse=True)

    def test_max_trends_cap(self, preflight_items):
        from preflight.trends import detect_trends
        trends = detect_trends(preflight_items, max_trends=2)
        assert len(trends) <= 2

    def test_empty_input_returns_empty(self):
        from preflight.trends import detect_trends
        assert detect_trends([]) == []

    def test_engagement_score_uses_metrics(self, preflight_items):
        """Items with high HN points / Reddit upvotes should boost cluster score."""
        from preflight.trends import detect_trends
        trends = detect_trends(preflight_items)
        # The Claude Code cluster has 450 HN points + 800 Reddit score
        top_trend = trends[0]
        assert top_trend["score"] > 0


class TestNormalizeEngagement:
    """_normalize_engagement() extracts a comparable score from source-specific metrics."""

    def test_hn_points(self):
        from preflight.trends import _normalize_engagement
        score = _normalize_engagement({"points": 400, "comments": 100}, "hn")
        assert score > 0

    def test_reddit_score(self):
        from preflight.trends import _normalize_engagement
        score = _normalize_engagement({"score": 500, "comments": 80}, "reddit")
        assert score > 0

    def test_twitter_likes(self):
        from preflight.trends import _normalize_engagement
        score = _normalize_engagement({"likes": 3000, "retweets": 500}, "twitter")
        assert score > 0

    def test_github_stars(self):
        from preflight.trends import _normalize_engagement
        score = _normalize_engagement({"stars": 1200}, "github")
        assert score > 0

    def test_empty_metrics_returns_zero(self):
        from preflight.trends import _normalize_engagement
        assert _normalize_engagement({}, "rss") == 0.0


class TestFormatTrendsForAgents:
    """format_trends_for_agents() produces the section agents see in their prompt."""

    def test_includes_topic_and_evidence(self, preflight_items):
        from preflight.trends import detect_trends, format_trends_for_agents
        trends = detect_trends(preflight_items)
        text = format_trends_for_agents(trends)
        assert "## Today's Trending Topics" in text
        # Should include source count and engagement info, not just topic name
        assert "sources" in text.lower() or "source" in text.lower()

    def test_empty_trends_returns_empty_string(self):
        from preflight.trends import format_trends_for_agents
        assert format_trends_for_agents([]) == ""

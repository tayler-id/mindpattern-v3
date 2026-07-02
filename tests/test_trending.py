"""Trending score math (orchestrator/trending.py)."""

import time

from orchestrator.trending import (
    blend_scores,
    corpus_score,
    onsite_score,
    trend_direction,
)

NOW = 1_800_000_000.0


def test_decay_favors_recent_events():
    fresh = onsite_score([{"type": "story_view", "ts": NOW - 600}], now=NOW)
    stale = onsite_score([{"type": "story_view", "ts": NOW - 72 * 3600}], now=NOW)
    assert fresh > stale * 5


def test_event_weights_and_scroll_value():
    outbound = onsite_score([{"type": "outbound_source_click", "ts": NOW}], now=NOW)
    view = onsite_score([{"type": "story_view", "ts": NOW}], now=NOW)
    assert outbound == view * 3
    deep_read = onsite_score([{"type": "scroll_depth", "ts": NOW, "value": 100}], now=NOW)
    assert deep_read == view * 2


def test_corpus_score_moves_without_any_reader():
    story = {
        "title": "Repo hits 42,000 stars overnight",
        "summary": "",
        "graph_connectors": {"source_domains": ["github.com"]},
        "arc_ids": ["agent-tooling"],
    }
    score = corpus_score(story, domain_recurrence={"github.com": 12})
    assert score > 5


def test_blend_ranks_internet_only_story_above_dead_story():
    onsite = {"read-story": 3.0, "internet-story": 0.0, "dead-story": 0.0}
    corpus = {"read-story": 0.0, "internet-story": 8.0, "dead-story": 0.0}
    blended = blend_scores(onsite, corpus)
    assert blended["read-story"] > blended["internet-story"] > blended["dead-story"]


def test_direction_bands():
    assert trend_direction(2.0, 1.0) == "up"
    assert trend_direction(1.0, 2.0) == "down"
    assert trend_direction(1.05, 1.0) == "flat"
    assert trend_direction(0.0, 0.0) == "flat"
    assert trend_direction(1.0, 0.0) == "up"

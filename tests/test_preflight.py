"""Tests for preflight module — all source scripts + orchestration."""
import json
from pathlib import Path

from preflight import make_entry, parse_ndjson, TOOLS_DIR


# ── Foundation tests ──────────────────────────────────────────────

def test_make_entry_minimal():
    entry = make_entry(source="rss", source_name="Test Blog", title="Test Post", url="https://example.com")
    assert entry["source"] == "rss"
    assert entry["source_name"] == "Test Blog"
    assert entry["title"] == "Test Post"
    assert entry["url"] == "https://example.com"
    assert entry["already_covered"] is False
    assert entry["match_info"] is None
    assert entry["metrics"] == {}


def test_make_entry_with_metrics():
    entry = make_entry(source="hn", source_name="HN", title="Post", url="https://hn.com", metrics={"points": 500})
    assert entry["metrics"]["points"] == 500


def test_make_entry_truncates_content_preview():
    long_text = "x" * 1000
    entry = make_entry(source="rss", source_name="T", title="T", url="u", content_preview=long_text)
    assert len(entry["content_preview"]) == 500


def test_tools_dir_exists():
    assert TOOLS_DIR.exists()


def test_parse_ndjson():
    text = '{"a": 1}\n{"b": 2}\nbadline\n{"c": 3}\n'
    items = parse_ndjson(text)
    assert len(items) == 3
    assert items[0]["a"] == 1
    assert items[2]["c"] == 3


def test_parse_ndjson_empty():
    assert parse_ndjson("") == []
    assert parse_ndjson("\n\n") == []


# ── RSS tests ─────────────────────────────────────────────────────

def test_rss_transform():
    from preflight.rss import _transform
    raw = {"source": "Simon Willison", "title": "Context Engineering", "url": "https://sw.net/1", "published": "2026-03-16T08:30:00Z", "summary": "A deep dive into..."}
    entry = _transform(raw)
    assert entry["source"] == "rss"
    assert entry["source_name"] == "Simon Willison"
    assert entry["title"] == "Context Engineering"
    assert entry["url"] == "https://sw.net/1"
    assert entry["published"] == "2026-03-16T08:30:00Z"
    assert entry["content_preview"] == "A deep dive into..."


def test_rss_transform_missing_fields():
    from preflight.rss import _transform
    raw = {"title": "No source", "url": "https://x.com"}
    entry = _transform(raw)
    assert entry["source_name"] == ""
    assert entry["published"] == ""


# ── arXiv tests ───────────────────────────────────────────────────

def test_arxiv_transform():
    from preflight.arxiv import _transform
    raw = {"id": "2401.15123", "title": "Paper Title", "summary": "Abstract text", "url": "https://arxiv.org/abs/2401.15123", "pdf_url": "...", "published": "2026-03-15T12:00:00Z", "authors": ["Alice", "Bob"], "categories": ["cs.AI"]}
    entry = _transform(raw)
    assert entry["source"] == "arxiv"
    assert entry["source_name"] == "arXiv"
    assert entry["title"] == "Paper Title"
    assert "Alice" in entry["content_preview"]


# ── GitHub tests ──────────────────────────────────────────────────

def test_github_transform():
    from preflight.github import _transform
    raw = {"name": "anthropics/claude-code", "description": "CLI for Claude", "url": "https://github.com/anthropics/claude-code", "stars": 5000, "language": "TypeScript", "topics": ["ai", "cli"], "pushed_at": "2026-03-16T01:00:00Z", "query_topic": "llm"}
    entry = _transform(raw)
    assert entry["source"] == "github"
    assert entry["source_name"] == "anthropics/claude-code"
    assert entry["metrics"]["stars"] == 5000
    assert entry["url"] == "https://github.com/anthropics/claude-code"


# ── HN tests ──────────────────────────────────────────────────────

def test_hn_transform():
    from preflight.hn import _transform
    raw = {"title": "Show HN: New AI Tool", "url": "https://example.com", "hn_url": "https://news.ycombinator.com/item?id=123", "points": 450, "comments": 120, "time": "2026-03-16T12:00:00.000Z", "author": "dang", "query": "AI"}
    entry = _transform(raw)
    assert entry["source"] == "hn"
    assert entry["source_name"] == "Hacker News"
    assert entry["metrics"]["points"] == 450
    assert entry["metrics"]["comments"] == 120
    assert "450 points" in entry["content_preview"]


# ── Reddit tests ──────────────────────────────────────────────────

def test_reddit_transform():
    from preflight.reddit import _transform
    raw = {"subreddit": "MachineLearning", "title": "New paper on transformers", "url": "https://arxiv.org/abs/123", "reddit_url": "https://reddit.com/r/ML/...", "score": 550, "comments": 45, "author": "user1", "created_utc": 1742083200, "selftext": "Discussion about..."}
    entry = _transform(raw)
    assert entry["source"] == "reddit"
    assert entry["source_name"] == "r/MachineLearning"
    assert entry["metrics"]["score"] == 550


# ── Twitter tests ─────────────────────────────────────────────────

def test_twitter_transform():
    from preflight.twitter import _transform, _parse_twitter_date
    raw = {
        "id": "123456",
        "text": "AI agents are the future of software...",
        "createdAt": "Sun Mar 16 10:00:00 +0000 2026",
        "user": {"restId": "789"},
        "likeCount": 500,
        "retweetCount": 100,
        "viewCount": 50000,
    }
    entry = _transform(raw, query="AI agents")
    assert entry["source"] == "twitter"
    assert entry["metrics"]["likes"] == 500
    assert entry["metrics"]["retweets"] == 100
    assert entry["url"] == "https://x.com/i/status/123456"


def test_parse_twitter_date():
    from preflight.twitter import _parse_twitter_date
    dt = _parse_twitter_date("Sun Mar 16 10:00:00 +0000 2026")
    assert dt.startswith("2026-03-16")


# ── Exa tests ─────────────────────────────────────────────────────

def test_exa_parse_single_result():
    from preflight.exa import _parse_mcporter_output
    text = 'Title: AI Agents in 2026\nAuthor: Jane Smith\nPublished Date: 2026-03-16T08:30:00.000Z\nURL: https://example.com/ai-agents\nText: AI agents are changing how we build software...\n'
    results = _parse_mcporter_output(text)
    assert len(results) == 1
    assert results[0]["title"] == "AI Agents in 2026"
    assert results[0]["url"] == "https://example.com/ai-agents"
    assert "2026-03-16" in results[0]["published"]


def test_exa_parse_multiple_results():
    from preflight.exa import _parse_mcporter_output
    text = 'Title: First Result\nURL: https://a.com\nText: Content A\n\nTitle: Second Result\nURL: https://b.com\nText: Content B\n'
    results = _parse_mcporter_output(text)
    assert len(results) == 2


# ── YouTube tests ─────────────────────────────────────────────────

def test_youtube_transform():
    from preflight.youtube import _transform
    raw = {"id": "abc123", "title": "AI Coding in 2026", "description": "Deep dive...", "webpage_url": "https://www.youtube.com/watch?v=abc123", "view_count": 50000, "duration": 600}
    entry = _transform(raw, channel="AI Explained")
    assert entry["source"] == "youtube"
    assert entry["source_name"] == "AI Explained"
    assert entry["metrics"]["views"] == 50000
    assert "youtube.com" in entry["url"]


# ── run_all tests ─────────────────────────────────────────────────

def test_dedup_annotate_marks_covered():
    from preflight.run_all import _dedup_annotate
    items = [
        {"source": "rss", "title": "Claude 4 Released", "url": "u1", "content_preview": "Anthropic releases Claude 4", "already_covered": False, "match_info": None, "source_name": "", "published": "", "metrics": {}},
    ]
    existing = [{"title": "Claude 4 Launch", "similarity": 0.90, "agent": "news", "date": "2026-03-15"}]
    annotated = _dedup_annotate(items, existing_fn=lambda q: existing, threshold=0.85)
    assert annotated[0]["already_covered"] is True
    assert annotated[0]["match_info"]["matched_finding"] == "Claude 4 Launch"


def test_dedup_annotate_new_item():
    from preflight.run_all import _dedup_annotate
    items = [
        {"source": "rss", "title": "Brand New Thing", "url": "u1", "content_preview": "Never seen before", "already_covered": False, "match_info": None, "source_name": "", "published": "", "metrics": {}},
    ]
    annotated = _dedup_annotate(items, existing_fn=lambda q: [], threshold=0.85)
    assert annotated[0]["already_covered"] is False


def test_dedup_annotate_no_db_no_fn():
    from preflight.run_all import _dedup_annotate
    items = [
        {"source": "rss", "title": "Anything", "url": "u1", "content_preview": "...", "already_covered": False, "match_info": None, "source_name": "", "published": "", "metrics": {}},
    ]
    annotated = _dedup_annotate(items, db=None, existing_fn=None, threshold=0.85)
    assert annotated[0]["already_covered"] is False


def test_assign_to_agents():
    from preflight.run_all import _assign_to_agents
    items = [
        {"source": "arxiv", "title": "Paper", "url": "u1", "source_name": "arXiv", "content_preview": "", "published": "", "metrics": {}, "already_covered": False, "match_info": None},
        {"source": "hn", "title": "HN Story", "url": "u2", "source_name": "HN", "content_preview": "", "published": "", "metrics": {}, "already_covered": False, "match_info": None},
    ]
    assignments = _assign_to_agents(items)
    assert "arxiv-researcher" in assignments
    assert any(i["title"] == "Paper" for i in assignments["arxiv-researcher"])
    assert "hn-researcher" in assignments


# ── Integration smoke test ────────────────────────────────────────

def test_preflight_run_all_smoke():
    """Smoke test: run_all executes without crashing."""
    from preflight.run_all import run_all

    feeds_file = Path(__file__).parent.parent / "verticals" / "ai-tech" / "rss-feeds.json"
    result = run_all(date_str="2026-03-16", db=None, feeds_file=feeds_file)

    assert "total_items" in result
    assert "assignments" in result
    assert "source_counts" in result
    assert result["total_items"] >= 0
    assert isinstance(result["assignments"], dict)

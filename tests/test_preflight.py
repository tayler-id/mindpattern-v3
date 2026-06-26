"""Tests for preflight module — all source scripts + orchestration."""
import json
import subprocess
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


def test_rss_fetch_with_diagnostics_normal_feed(monkeypatch, tmp_path):
    import preflight.rss as rss

    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text("[]")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({
                "source": "Good Feed",
                "title": "Post",
                "url": "https://example.com/post",
                "summary": "Summary",
            }) + "\n",
            stderr="",
        )

    monkeypatch.setattr(rss.subprocess, "run", fake_run)

    items, diagnostics = rss.fetch_with_diagnostics(feeds_file)

    assert len(items) == 1
    assert items[0]["source_name"] == "Good Feed"
    assert diagnostics["status"] == "ok"
    assert diagnostics["reason"] == ""
    assert diagnostics["feed_errors"] == []


def test_rss_fetch_with_diagnostics_empty_feed(monkeypatch, tmp_path):
    import preflight.rss as rss

    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text("[]")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(rss.subprocess, "run", fake_run)

    items, diagnostics = rss.fetch_with_diagnostics(feeds_file)

    assert items == []
    assert diagnostics["status"] == "empty"
    assert diagnostics["reason"] == "no items"


def test_rss_fetch_with_diagnostics_names_bad_feed(monkeypatch, tmp_path):
    import preflight.rss as rss

    feeds_file = tmp_path / "feeds.json"
    feeds_file.write_text("[]")
    stderr = "\n".join([
        json.dumps({
            "error": "Warning for feed 'Bad Feed': broken XML",
            "tool": "rss-fetch",
            "context": "https://bad.example/feed",
        }),
        json.dumps({
            "error": "1/2 feeds failed",
            "tool": "rss-fetch",
        }),
    ])

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=json.dumps({
                "source": "Good Feed",
                "title": "Good Post",
                "url": "https://example.com/good",
                "summary": "Summary",
            }) + "\n",
            stderr=stderr,
        )

    monkeypatch.setattr(rss.subprocess, "run", fake_run)

    items, diagnostics = rss.fetch_with_diagnostics(feeds_file)

    assert len(items) == 1
    assert diagnostics["status"] == "partial"
    assert "Bad Feed" in diagnostics["reason"]
    assert diagnostics["feed_errors"][0]["context"] == "https://bad.example/feed"


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


def test_twitter_fetch_falls_back_to_twitter_cli(monkeypatch):
    import preflight.twitter as twitter

    calls = []

    def fake_which(name):
        return "/bin/twitter" if name == "twitter" else None

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps([
                {
                    "id": "123456",
                    "text": "AI agents are the future of software...",
                    "createdAtISO": "2026-03-16T10:00:00Z",
                    "metrics": {"likes": 500, "retweets": 100, "views": 50000},
                }
            ]),
            stderr="",
        )

    monkeypatch.setattr(twitter.shutil, "which", fake_which)
    monkeypatch.setattr(twitter.subprocess, "run", fake_run)

    entries = twitter.fetch(queries=["AI agents"], count=1)

    assert calls == [[
        "twitter", "search", "AI agents", "-n", "1", "--json",
        "--exclude", "retweets", "--exclude", "replies",
    ]]
    assert entries[0]["source"] == "twitter"
    assert entries[0]["url"] == "https://x.com/i/status/123456"
    assert entries[0]["published"] == "2026-03-16T10:00:00Z"
    assert entries[0]["metrics"]["views"] == 50000


def test_twitter_fetch_prefers_xreach(monkeypatch):
    import preflight.twitter as twitter

    calls = []

    def fake_which(name):
        return f"/bin/{name}" if name == "xreach" else None

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({
                "items": [
                    {
                        "id": "legacy123",
                        "text": "Legacy xreach shape",
                        "createdAt": "Sun Mar 16 10:00:00 +0000 2026",
                        "likeCount": 7,
                        "retweetCount": 2,
                        "viewCount": 900,
                    }
                ]
            }),
            stderr="",
        )

    monkeypatch.setattr(twitter.shutil, "which", fake_which)
    monkeypatch.setattr(twitter.subprocess, "run", fake_run)

    entries = twitter.fetch(queries=["AI agents"], count=2)

    assert calls == [["xreach", "search", "AI agents", "--count", "2", "--json"]]
    assert entries[0]["url"] == "https://x.com/i/status/legacy123"
    assert entries[0]["metrics"] == {"likes": 7, "retweets": 2, "views": 900}


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


def test_source_health_success():
    from preflight.run_all import _run_source_with_health

    items = [make_entry(source="rss", source_name="Feed", title="Post", url="u")]
    fetched, health = _run_source_with_health("rss", lambda: items)

    assert fetched == items
    assert health["status"] == "ok"
    assert health["count"] == 1
    assert health["duration_ms"] >= 0
    assert health["reason"] == ""


def test_source_health_empty():
    from preflight.run_all import _run_source_with_health

    fetched, health = _run_source_with_health("hn", lambda: [])

    assert fetched == []
    assert health["status"] == "empty"
    assert health["count"] == 0
    assert health["reason"] == "no items"


def test_source_health_exception():
    from preflight.run_all import _run_source_with_health

    def fail():
        raise RuntimeError("backend failed")

    fetched, health = _run_source_with_health("reddit", fail)

    assert fetched == []
    assert health["status"] == "failed"
    assert health["count"] == 0
    assert "backend failed" in health["reason"]


def test_source_health_timeout():
    from preflight.run_all import _run_source_with_health

    def fail():
        raise TimeoutError("rss-fetch timed out")

    fetched, health = _run_source_with_health("rss", fail)

    assert fetched == []
    assert health["status"] == "timeout"
    assert health["count"] == 0
    assert "timed out" in health["reason"]


def test_source_health_missing_cli():
    from preflight.run_all import _run_source_with_health

    def fail():
        raise FileNotFoundError("twitter")

    fetched, health = _run_source_with_health("twitter", fail)

    assert fetched == []
    assert health["status"] == "missing"
    assert health["count"] == 0
    assert "twitter" in health["reason"]


def test_source_health_merges_rss_diagnostics():
    from preflight.run_all import _run_source_with_health

    items = [make_entry(source="rss", source_name="Good Feed", title="Post", url="u")]

    def fetch():
        return items, {
            "status": "partial",
            "reason": "Bad Feed failed",
            "feed_errors": [{"context": "https://bad.example/feed"}],
        }

    fetched, health = _run_source_with_health("rss", fetch)

    assert fetched == items
    assert health["status"] == "partial"
    assert health["count"] == 1
    assert health["reason"] == "Bad Feed failed"
    assert health["feed_errors"][0]["context"] == "https://bad.example/feed"


# ── Integration smoke test ────────────────────────────────────────

def test_preflight_run_all_smoke():
    """Smoke test: run_all executes without crashing."""
    from preflight.run_all import run_all

    feeds_file = Path(__file__).parent.parent / "verticals" / "ai-tech" / "rss-feeds.json"
    result = run_all(date_str="2026-03-16", db=None, feeds_file=feeds_file)

    assert "total_items" in result
    assert "assignments" in result
    assert "source_counts" in result
    assert "source_health" in result
    assert result["total_items"] >= 0
    assert isinstance(result["assignments"], dict)
    assert isinstance(result["source_health"], dict)


# ── Dedup decay tests ────────────────────────────────────────────

def test_dedup_batch_decay_old_finding_passes():
    """9-day-old finding at 0.75 similarity does NOT block — story has evolved."""
    from unittest.mock import patch, MagicMock
    import numpy as np
    from datetime import datetime, timedelta
    from preflight.run_all import _dedup_batch, DEDUP_SIMILARITY_THRESHOLD

    # Vectors engineered for 0.75 dot-product similarity
    item_vec = np.array([1.0, 0.0], dtype=np.float32)
    stored_vec = np.array([0.75, np.sqrt(1 - 0.75**2)], dtype=np.float32)

    nine_days_ago = (datetime.now() - timedelta(days=9)).strftime("%Y-%m-%d")

    mock_row = {
        "title": "Old Finding",
        "agent": "test-agent",
        "run_date": nine_days_ago,
        "embedding": b"fake",
    }
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [mock_row]

    items = [
        {"title": "New Finding", "content_preview": "test content",
         "already_covered": False, "match_info": None},
    ]

    with patch("memory.embeddings.embed_texts", return_value=[item_vec.tolist()]), \
         patch("memory.embeddings.deserialize_f32", return_value=stored_vec.tolist()):
        result = _dedup_batch(items, mock_db, DEDUP_SIMILARITY_THRESHOLD)

    # 9-day-old finding at 0.75 similarity should NOT block
    assert result[0]["already_covered"] is False


def test_dedup_batch_decay_recent_finding_blocks():
    """1-day-old finding at 0.75 similarity DOES block — true duplicate."""
    from unittest.mock import patch, MagicMock
    import numpy as np
    from datetime import datetime, timedelta
    from preflight.run_all import _dedup_batch, DEDUP_SIMILARITY_THRESHOLD

    item_vec = np.array([1.0, 0.0], dtype=np.float32)
    stored_vec = np.array([0.75, np.sqrt(1 - 0.75**2)], dtype=np.float32)

    one_day_ago = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    mock_row = {
        "title": "Recent Finding",
        "agent": "test-agent",
        "run_date": one_day_ago,
        "embedding": b"fake",
    }
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [mock_row]

    items = [
        {"title": "New Finding", "content_preview": "test content",
         "already_covered": False, "match_info": None},
    ]

    with patch("memory.embeddings.embed_texts", return_value=[item_vec.tolist()]), \
         patch("memory.embeddings.deserialize_f32", return_value=stored_vec.tolist()):
        result = _dedup_batch(items, mock_db, DEDUP_SIMILARITY_THRESHOLD)

    # 1-day-old finding at 0.75 similarity SHOULD block
    assert result[0]["already_covered"] is True
    assert result[0]["match_info"]["matched_finding"] == "Recent Finding"


def test_dedup_batch_decay_annotations_include_age():
    """Blocked items include age_days and effective_threshold in match_info."""
    from unittest.mock import patch, MagicMock
    import numpy as np
    from datetime import datetime, timedelta
    from preflight.run_all import _dedup_batch, DEDUP_SIMILARITY_THRESHOLD

    item_vec = np.array([1.0, 0.0], dtype=np.float32)
    stored_vec = np.array([0.75, np.sqrt(1 - 0.75**2)], dtype=np.float32)

    three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

    mock_row = {
        "title": "Mid-age Finding",
        "agent": "test-agent",
        "run_date": three_days_ago,
        "embedding": b"fake",
    }
    mock_db = MagicMock()
    mock_db.execute.return_value.fetchall.return_value = [mock_row]

    items = [
        {"title": "New Finding", "content_preview": "test content",
         "already_covered": False, "match_info": None},
    ]

    with patch("memory.embeddings.embed_texts", return_value=[item_vec.tolist()]), \
         patch("memory.embeddings.deserialize_f32", return_value=stored_vec.tolist()):
        result = _dedup_batch(items, mock_db, DEDUP_SIMILARITY_THRESHOLD)

    # 3-day-old at 0.75 — check if blocked, then verify annotations
    info = result[0]["match_info"]
    assert info is not None, "Expected match_info for blocked item"
    assert "age_days" in info
    assert info["age_days"] == 3
    assert "effective_threshold" in info
    assert isinstance(info["effective_threshold"], float)

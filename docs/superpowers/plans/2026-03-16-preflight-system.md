# Research Agent Preflight System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python preflight system that gathers ~280 items from 8 sources before research agents run, dedup-annotates them against the last 7 days, routes them to agents, and restructures agent prompts into Phase 1 (evaluate preflight data) + Phase 2 (explore with Agent Reach tools).

**Architecture:** New `preflight/` module. Each source has a `fetch()` function that calls existing tools via subprocess or external commands. `run_all.py` orchestrates all 8 sources in parallel via ThreadPoolExecutor, dedup-annotates using the existing embedding system (BAAI/bge-small-en-v1.5), and assigns items to agents by source/topic. The prompt builder in `agents.py` renders preflight items into Phase 1/Phase 2 prompt sections. Agent .md skill files are stripped of old Research Protocol sections and gain Phase 2 Exploration Preferences.

**Tech Stack:** Python 3.14, subprocess, ThreadPoolExecutor, fastembed, xreach 0.3.3, yt-dlp, mcporter (Exa), feedparser

**Spec:** `docs/superpowers/specs/2026-03-16-research-agent-preflight-redesign.md`

---

## Dependency Graph

```
Task 1 (preflight/__init__.py) ─── FOUNDATION
├── Task 2 (preflight/rss.py)           ─┐
├── Task 3 (preflight/arxiv.py)          │
├── Task 4 (preflight/github.py)         │ PARALLEL GROUP A
├── Task 5 (preflight/hn.py)             │ (8 agents, all independent)
├── Task 6 (preflight/reddit.py)         │
├── Task 7 (preflight/twitter.py)        │
├── Task 8 (preflight/exa.py)            │
├── Task 9 (preflight/youtube.py)       ─┘
│   └── Task 10 (preflight/run_all.py)   ── SEQUENTIAL
│       └── Task 11 (orchestrator/agents.py)
│           └── Task 12 (orchestrator/runner.py)
│               └── Task 14 (integration test)
└── Task 13 (agent .md rewrites) ──────── INDEPENDENT (parallel with 2-12)
    └── Task 14 (integration test)
```

**Maximum parallelism:** After Task 1, dispatch 9 agents simultaneously (Tasks 2-9 + Task 13).

---

## File Structure

### New Files
- `preflight/__init__.py` — `make_entry()` helper, `TOOLS_DIR` constant
- `preflight/rss.py` — Wraps `tools/rss-fetch.py`
- `preflight/arxiv.py` — Wraps `tools/arxiv-fetch.py`
- `preflight/github.py` — Wraps `tools/github-fetch.py`
- `preflight/hn.py` — Wraps `tools/hn-fetch.py`
- `preflight/reddit.py` — Wraps `tools/reddit-fetch.py`
- `preflight/twitter.py` — Calls `xreach search`
- `preflight/exa.py` — Calls `mcporter call exa.web_search_exa`
- `preflight/youtube.py` — Calls `yt-dlp --dump-json --flat-playlist`
- `preflight/run_all.py` — Orchestrates all sources, dedup-annotates, assigns to agents
- `tests/test_preflight.py` — Unit + integration tests

### Modified Files
- `orchestrator/agents.py:114-212` — `build_agent_prompt()` accepts `preflight_items` and `already_covered` params
- `orchestrator/agents.py:320-400` — `dispatch_research_agents()` passes preflight data
- `orchestrator/runner.py:311-434` — `_phase_research()` calls preflight before dispatch
- `verticals/ai-tech/agents/*.md` — All 13 agent files: remove Research Protocol, add Phase 2 preferences

---

## Chunk 1: Foundation + Source Scripts

### Task 1: Create preflight/__init__.py

**Files:**
- Create: `preflight/__init__.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_preflight.py
"""Tests for preflight module."""
import json
from preflight import make_entry, TOOLS_DIR


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
    entry = make_entry(
        source="hn", source_name="HN", title="Post",
        url="https://hn.com", metrics={"points": 500},
    )
    assert entry["metrics"]["points"] == 500


def test_make_entry_truncates_content_preview():
    long_text = "x" * 1000
    entry = make_entry(source="rss", source_name="T", title="T", url="u", content_preview=long_text)
    assert len(entry["content_preview"]) == 500


def test_tools_dir_exists():
    assert TOOLS_DIR.exists()


def test_parse_ndjson():
    from preflight import parse_ndjson
    text = '{"a": 1}\n{"b": 2}\nbadline\n{"c": 3}\n'
    items = parse_ndjson(text)
    assert len(items) == 3
    assert items[0]["a"] == 1
    assert items[2]["c"] == 3


def test_parse_ndjson_empty():
    from preflight import parse_ndjson
    assert parse_ndjson("") == []
    assert parse_ndjson("\n\n") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py::test_make_entry_minimal -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'preflight'`

- [ ] **Step 3: Write the implementation**

```python
# preflight/__init__.py
"""Preflight data collection for research agents.

Gathers structured data from 8 sources BEFORE agents run.
Each source module exports a `fetch() -> list[dict]` function
that returns items in the standard preflight entry schema.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR = PROJECT_ROOT / "tools"


def make_entry(
    *,
    source: str,
    source_name: str,
    title: str,
    url: str,
    published: str = "",
    content_preview: str = "",
    metrics: dict | None = None,
    already_covered: bool = False,
    match_info: dict | None = None,
) -> dict:
    """Create a standardized preflight entry dict."""
    return {
        "source": source,
        "source_name": source_name,
        "title": title,
        "url": url,
        "published": published,
        "content_preview": content_preview[:500],
        "metrics": metrics or {},
        "already_covered": already_covered,
        "match_info": match_info,
    }


def parse_ndjson(text: str) -> list[dict]:
    """Parse newline-delimited JSON from tool stdout."""
    import json
    items = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3
git add preflight/__init__.py tests/test_preflight.py
git commit -m "feat: add preflight module foundation with make_entry helper"
```

---

### Task 2: Create preflight/rss.py

**Files:**
- Create: `preflight/rss.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Wraps `tools/rss-fetch.py` which outputs NDJSON: `{"source": "...", "title": "...", "url": "...", "published": "...", "summary": "..."}`

- [ ] **Step 1: Write the test**

Append to `tests/test_preflight.py`:
```python
from preflight.rss import _transform


def test_rss_transform():
    raw = {"source": "Simon Willison", "title": "Context Engineering", "url": "https://sw.net/1", "published": "2026-03-16T08:30:00Z", "summary": "A deep dive into..."}
    entry = _transform(raw)
    assert entry["source"] == "rss"
    assert entry["source_name"] == "Simon Willison"
    assert entry["title"] == "Context Engineering"
    assert entry["url"] == "https://sw.net/1"
    assert entry["published"] == "2026-03-16T08:30:00Z"
    assert entry["content_preview"] == "A deep dive into..."


def test_rss_transform_missing_fields():
    raw = {"title": "No source", "url": "https://x.com"}
    entry = _transform(raw)
    assert entry["source_name"] == ""
    assert entry["published"] == ""
```

- [ ] **Step 2: Run test, verify fail**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py::test_rss_transform -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'preflight.rss'`

- [ ] **Step 3: Implement**

```python
# preflight/rss.py
"""Preflight: RSS feed items via tools/rss-fetch.py."""

import logging
import subprocess
from pathlib import Path

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    """Transform rss-fetch.py output item to preflight entry."""
    return make_entry(
        source="rss",
        source_name=raw.get("source", ""),
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=raw.get("published", ""),
        content_preview=raw.get("summary", ""),
    )


def fetch(feeds_file: Path, hours: int = 48) -> list[dict]:
    """Fetch RSS items and return as preflight entries."""
    cmd = [
        "python3", str(TOOLS_DIR / "rss-fetch.py"),
        "--feeds-file", str(feeds_file),
        "--hours", str(hours),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        logger.warning("rss-fetch.py timed out after 120s")
        return []
    except Exception as e:
        logger.error(f"rss-fetch.py failed: {e}")
        return []

    if proc.stderr:
        for line in proc.stderr.strip().split("\n"):
            if line.strip():
                logger.debug(f"rss-fetch stderr: {line}")

    items = parse_ndjson(proc.stdout)
    return [_transform(item) for item in items]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py -k rss -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add preflight/rss.py tests/test_preflight.py
git commit -m "feat: add preflight/rss.py wrapper for RSS feed fetching"
```

---

### Task 3: Create preflight/arxiv.py

**Files:**
- Create: `preflight/arxiv.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Wraps `tools/arxiv-fetch.py`. Output: `{"id": "...", "title": "...", "summary": "...", "url": "...", "pdf_url": "...", "published": "...", "authors": [...], "categories": [...]}`

- [ ] **Step 1: Write test**

```python
from preflight.arxiv import _transform


def test_arxiv_transform():
    raw = {"id": "2401.15123", "title": "Paper Title", "summary": "Abstract text", "url": "https://arxiv.org/abs/2401.15123", "pdf_url": "...", "published": "2026-03-15T12:00:00Z", "authors": ["Alice", "Bob"], "categories": ["cs.AI"]}
    entry = _transform(raw)
    assert entry["source"] == "arxiv"
    assert entry["source_name"] == "arXiv"
    assert entry["title"] == "Paper Title"
    assert "Alice" in entry["content_preview"]
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Implement**

```python
# preflight/arxiv.py
"""Preflight: arXiv papers via tools/arxiv-fetch.py."""

import logging
import subprocess

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    authors = ", ".join(raw.get("authors", [])[:3])
    cats = ", ".join(raw.get("categories", []))
    preview = raw.get("summary", "")
    if authors:
        preview = f"[{authors}] [{cats}] {preview}"
    return make_entry(
        source="arxiv",
        source_name="arXiv",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=raw.get("published", ""),
        content_preview=preview,
    )


def fetch(categories: str = "cs.AI,cs.LG,cs.CL", days: int = 2, max_results: int = 30) -> list[dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "arxiv-fetch.py"),
        "--categories", categories,
        "--days", str(days),
        "--max", str(max_results),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"arxiv-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/arxiv.py tests/test_preflight.py
git commit -m "feat: add preflight/arxiv.py wrapper for arXiv papers"
```

---

### Task 4: Create preflight/github.py

**Files:**
- Create: `preflight/github.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Wraps `tools/github-fetch.py`. Output: `{"name": "user/repo", "description": "...", "url": "...", "stars": 1250, "language": "Python", "topics": [...], "created_at": "...", "pushed_at": "...", "query_topic": "..."}`

- [ ] **Step 1: Write test**

```python
from preflight.github import _transform


def test_github_transform():
    raw = {"name": "anthropics/claude-code", "description": "CLI for Claude", "url": "https://github.com/anthropics/claude-code", "stars": 5000, "language": "TypeScript", "topics": ["ai", "cli"], "pushed_at": "2026-03-16T01:00:00Z", "query_topic": "llm"}
    entry = _transform(raw)
    assert entry["source"] == "github"
    assert entry["source_name"] == "anthropics/claude-code"
    assert entry["metrics"]["stars"] == 5000
    assert entry["url"] == "https://github.com/anthropics/claude-code"
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/github.py
"""Preflight: GitHub trending repos via tools/github-fetch.py."""

import logging
import subprocess

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    desc = raw.get("description", "") or ""
    lang = raw.get("language", "")
    topics = ", ".join(raw.get("topics", [])[:5])
    preview = f"[{lang}] {desc}"
    if topics:
        preview += f" Topics: {topics}"
    return make_entry(
        source="github",
        source_name=raw.get("name", ""),
        title=f"{raw.get('name', '')}: {desc[:100]}",
        url=raw.get("url", ""),
        published=raw.get("pushed_at", ""),
        content_preview=preview,
        metrics={"stars": raw.get("stars", 0)},
    )


def fetch(
    topics: str = "llm,ai-agent,rag,mcp,ai-coding,vibe-coding,ai-sdk,llm-framework",
    days: int = 7,
    min_stars: int = 25,
) -> list[dict]:
    """Fetch GitHub repos. Expanded topics and lower min_stars vs tool defaults for broader coverage."""
    cmd = [
        "python3", str(TOOLS_DIR / "github-fetch.py"),
        "--topics", topics,
        "--days", str(days),
        "--min-stars", str(min_stars),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"github-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/github.py tests/test_preflight.py
git commit -m "feat: add preflight/github.py wrapper for GitHub repos"
```

---

### Task 5: Create preflight/hn.py

**Files:**
- Create: `preflight/hn.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Wraps `tools/hn-fetch.py`. Output: `{"title": "...", "url": "...", "hn_url": "...", "points": 450, "comments": 120, "time": "...", "author": "...", "query": "..."}`

- [ ] **Step 1: Write test**

```python
from preflight.hn import _transform


def test_hn_transform():
    raw = {"title": "Show HN: New AI Tool", "url": "https://example.com", "hn_url": "https://news.ycombinator.com/item?id=123", "points": 450, "comments": 120, "time": "2026-03-16T12:00:00.000Z", "author": "dang", "query": "AI"}
    entry = _transform(raw)
    assert entry["source"] == "hn"
    assert entry["source_name"] == "Hacker News"
    assert entry["metrics"]["points"] == 450
    assert entry["metrics"]["comments"] == 120
    assert "450 points" in entry["content_preview"]
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/hn.py
"""Preflight: Hacker News stories via tools/hn-fetch.py."""

import logging
import subprocess

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)


def _transform(raw: dict) -> dict:
    pts = raw.get("points", 0)
    cmts = raw.get("comments", 0)
    return make_entry(
        source="hn",
        source_name="Hacker News",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=raw.get("time", ""),
        content_preview=f"{pts} points, {cmts} comments on HN. Query: {raw.get('query', '')}",
        metrics={"points": pts, "comments": cmts},
    )


def fetch(queries: str = "AI,LLM,agents,vibe coding,MCP", hours: int = 24, min_points: int = 30) -> list[dict]:
    cmd = [
        "python3", str(TOOLS_DIR / "hn-fetch.py"),
        "--queries", queries,
        "--hours", str(hours),
        "--min-points", str(min_points),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"hn-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/hn.py tests/test_preflight.py
git commit -m "feat: add preflight/hn.py wrapper for Hacker News stories"
```

---

### Task 6: Create preflight/reddit.py

**Files:**
- Create: `preflight/reddit.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Wraps `tools/reddit-fetch.py`. Output: `{"subreddit": "...", "title": "...", "url": "...", "reddit_url": "...", "score": 550, "comments": 45, "author": "...", "created_utc": 1705329600, "selftext": "..."}`

- [ ] **Step 1: Write test**

```python
from preflight.reddit import _transform


def test_reddit_transform():
    raw = {"subreddit": "MachineLearning", "title": "New paper on transformers", "url": "https://arxiv.org/abs/123", "reddit_url": "https://reddit.com/r/ML/...", "score": 550, "comments": 45, "author": "user1", "created_utc": 1742083200, "selftext": "Discussion about..."}
    entry = _transform(raw)
    assert entry["source"] == "reddit"
    assert entry["source_name"] == "r/MachineLearning"
    assert entry["metrics"]["score"] == 550
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/reddit.py
"""Preflight: Reddit posts via tools/reddit-fetch.py."""

import logging
import subprocess
from datetime import datetime, timezone

from . import TOOLS_DIR, make_entry, parse_ndjson

logger = logging.getLogger(__name__)

# Expanded from tool default (3) to match spec target of 30-50 items
DEFAULT_SUBREDDITS = (
    "MachineLearning,LocalLLaMA,artificial,singularity,"
    "ChatGPT,ClaudeAI,SaaS,fintech,startups,programming"
)


def _transform(raw: dict) -> dict:
    created = raw.get("created_utc")
    published = ""
    if created:
        try:
            published = datetime.fromtimestamp(int(created), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            pass

    return make_entry(
        source="reddit",
        source_name=f"r/{raw.get('subreddit', '')}",
        title=raw.get("title", ""),
        url=raw.get("url", ""),
        published=published,
        content_preview=raw.get("selftext", "")[:500],
        metrics={"score": raw.get("score", 0), "comments": raw.get("comments", 0)},
    )


def fetch(subreddits: str | None = None, min_score: int = 50) -> list[dict]:
    """Fetch Reddit posts. Default: 10 subreddits, min_score=50 (lower than tool default of 100)."""
    cmd = [
        "python3", str(TOOLS_DIR / "reddit-fetch.py"),
        "--subreddits", subreddits or DEFAULT_SUBREDDITS,
        "--min-score", str(min_score),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error(f"reddit-fetch.py failed: {e}")
        return []

    return [_transform(item) for item in parse_ndjson(proc.stdout)]
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/reddit.py tests/test_preflight.py
git commit -m "feat: add preflight/reddit.py wrapper for Reddit posts"
```

---

### Task 7: Create preflight/twitter.py

**Files:**
- Create: `preflight/twitter.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Calls `xreach search "query" --count N --json`. Output is JSON with `{"items": [{"id": "...", "text": "...", "createdAt": "Thu Mar 05 12:30:08 +0000 2026", "user": {...}, "likeCount": N, "retweetCount": N, "viewCount": N, ...}], "hasMore": bool}`.

- [ ] **Step 1: Write test**

```python
from preflight.twitter import _transform, _parse_twitter_date


def test_twitter_transform():
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
    dt = _parse_twitter_date("Sun Mar 16 10:00:00 +0000 2026")
    assert dt.startswith("2026-03-16")
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/twitter.py
"""Preflight: Twitter/X posts via xreach search."""

import json
import logging
import subprocess
from datetime import datetime

from . import make_entry

logger = logging.getLogger(__name__)

# Queries to run — covers AI, fintech, SaaS disruption
DEFAULT_QUERIES = [
    "AI agents coding",
    "Claude Anthropic",
    "vibe coding",
    "SaaS disruption AI",
    "fintech AI 2026",
]


def _parse_twitter_date(date_str: str) -> str:
    """Parse Twitter's date format to ISO 8601."""
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""


def _transform(raw: dict, query: str = "") -> dict:
    tweet_id = raw.get("id", "")
    return make_entry(
        source="twitter",
        source_name=f"x.com (query: {query})",
        title=raw.get("text", "")[:120],
        url=f"https://x.com/i/status/{tweet_id}",
        published=_parse_twitter_date(raw.get("createdAt", "")),
        content_preview=raw.get("text", ""),
        metrics={
            "likes": raw.get("likeCount", 0),
            "retweets": raw.get("retweetCount", 0),
            "views": raw.get("viewCount", 0),
        },
    )


def fetch(queries: list[str] | None = None, count: int = 10) -> list[dict]:
    """Fetch recent tweets matching queries via xreach search."""
    queries = queries or DEFAULT_QUERIES
    all_items = []
    seen_ids = set()

    for query in queries:
        cmd = ["xreach", "search", query, "--count", str(count), "--json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"xreach search failed for '{query}': {proc.stderr[:200]}")
                continue

            data = json.loads(proc.stdout)
            for item in data.get("items", []):
                tid = item.get("id", "")
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
                # Skip retweets and replies
                if item.get("isRetweet") or item.get("isReply"):
                    continue
                all_items.append(_transform(item, query=query))

        except subprocess.TimeoutExpired:
            logger.warning(f"xreach search timed out for '{query}'")
        except json.JSONDecodeError:
            logger.warning(f"xreach returned invalid JSON for '{query}'")
        except FileNotFoundError:
            logger.error("xreach not found — install with: pip install xreach")
            return []
        except Exception as e:
            logger.error(f"xreach failed for '{query}': {e}")

    return all_items
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/twitter.py tests/test_preflight.py
git commit -m "feat: add preflight/twitter.py for X/Twitter search via xreach"
```

---

### Task 8: Create preflight/exa.py

**Files:**
- Create: `preflight/exa.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Calls `mcporter call exa.web_search_exa query="..." numResults=N`. Output is plain text with entries separated by `Title:` headers. Each entry has: `Title: ...`, `Author: ...` (optional), `Published Date: ...` (optional), `URL: ...`, `Text: ...`.

- [ ] **Step 1: Write test**

```python
from preflight.exa import _parse_mcporter_output


def test_exa_parse_single_result():
    text = 'Title: AI Agents in 2026\nAuthor: Jane Smith\nPublished Date: 2026-03-16T08:30:00.000Z\nURL: https://example.com/ai-agents\nText: AI agents are changing how we build software...\n'
    results = _parse_mcporter_output(text)
    assert len(results) == 1
    assert results[0]["title"] == "AI Agents in 2026"
    assert results[0]["url"] == "https://example.com/ai-agents"
    assert "2026-03-16" in results[0]["published"]


def test_exa_parse_multiple_results():
    text = 'Title: First Result\nURL: https://a.com\nText: Content A\n\nTitle: Second Result\nURL: https://b.com\nText: Content B\n'
    results = _parse_mcporter_output(text)
    assert len(results) == 2
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/exa.py
"""Preflight: Exa semantic search via mcporter."""

import logging
import re
import subprocess

from . import make_entry

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    "AI agent framework launch 2026",
    "LLM benchmark results latest",
    "AI coding assistant update",
    "SaaS AI disruption startup",
    "fintech AI automation",
]


def _parse_mcporter_output(text: str) -> list[dict]:
    """Parse mcporter text output into structured results.

    mcporter outputs results with Title:/URL:/Text: headers.
    Multiple results are separated by the next Title: line.
    """
    results = []
    # Split on Title: at start of line, keeping the delimiter
    blocks = re.split(r"(?=^Title: )", text, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block.startswith("Title: "):
            continue

        title_m = re.match(r"Title: (.+)", block)
        url_m = re.search(r"^URL: (.+)", block, re.MULTILINE)
        date_m = re.search(r"^Published Date: (.+)", block, re.MULTILINE)
        author_m = re.search(r"^Author: (.+)", block, re.MULTILINE)
        text_m = re.search(r"^Text: (.+)", block, re.MULTILINE | re.DOTALL)

        if not title_m or not url_m:
            continue

        published = ""
        if date_m:
            raw_date = date_m.group(1).strip()
            # Extract just the date portion (YYYY-MM-DD)
            pub_match = re.match(r"(\d{4}-\d{2}-\d{2})", raw_date)
            published = pub_match.group(1) + "T00:00:00Z" if pub_match else raw_date

        content = text_m.group(1).strip()[:500] if text_m else ""
        source_name = author_m.group(1).strip() if author_m else "Exa"

        results.append({
            "title": title_m.group(1).strip(),
            "url": url_m.group(1).strip(),
            "published": published,
            "content": content,
            "source_name": source_name,
        })

    return results


def fetch(queries: list[str] | None = None, num_results: int = 5) -> list[dict]:
    """Fetch results from Exa semantic search via mcporter."""
    queries = queries or DEFAULT_QUERIES
    all_items = []
    seen_urls = set()

    for query in queries:
        cmd = [
            "mcporter", "call", "exa.web_search_exa",
            f"query={query}", f"numResults={num_results}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"mcporter exa failed for '{query}': {proc.stderr[:200]}")
                continue

            results = _parse_mcporter_output(proc.stdout)
            for r in results:
                if r["url"] in seen_urls:
                    continue
                seen_urls.add(r["url"])
                all_items.append(make_entry(
                    source="exa",
                    source_name=r.get("source_name", "Exa"),
                    title=r["title"],
                    url=r["url"],
                    published=r.get("published", ""),
                    content_preview=r.get("content", ""),
                ))

        except subprocess.TimeoutExpired:
            logger.warning(f"mcporter timed out for '{query}'")
        except FileNotFoundError:
            logger.error("mcporter not found — install from https://mcporter.dev")
            return []
        except Exception as e:
            logger.error(f"mcporter failed for '{query}': {e}")

    return all_items
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/exa.py tests/test_preflight.py
git commit -m "feat: add preflight/exa.py for Exa semantic search via mcporter"
```

---

### Task 9: Create preflight/youtube.py

**Files:**
- Create: `preflight/youtube.py`
- Test: `tests/test_preflight.py` (append)

**Context:** Calls `yt-dlp --dump-json --flat-playlist "URL"`. Output per video: `{"id": "...", "title": "...", "description": "...", "url": "...", "view_count": N, "duration": N, "webpage_url": "..."}`. Note: `upload_date`, `channel`, `like_count` are null in flat-playlist mode.

- [ ] **Step 1: Write test**

```python
from preflight.youtube import _transform


def test_youtube_transform():
    raw = {"id": "abc123", "title": "AI Coding in 2026", "description": "Deep dive...", "webpage_url": "https://www.youtube.com/watch?v=abc123", "view_count": 50000, "duration": 600}
    entry = _transform(raw, channel="AI Explained")
    assert entry["source"] == "youtube"
    assert entry["source_name"] == "AI Explained"
    assert entry["metrics"]["views"] == 50000
    assert "youtube.com" in entry["url"]
```

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/youtube.py
"""Preflight: YouTube videos from key AI channels via yt-dlp."""

import json
import logging
import subprocess

from . import make_entry

logger = logging.getLogger(__name__)

# Key AI/tech YouTube channels
DEFAULT_CHANNELS = {
    "AI Explained": "https://www.youtube.com/@aiexplained-official/videos",
    "Fireship": "https://www.youtube.com/@Fireship/videos",
    "Matthew Berman": "https://www.youtube.com/@matthew_berman/videos",
    "Yannic Kilcher": "https://www.youtube.com/@YannicKilcher/videos",
    "Dwarkesh Patel": "https://www.youtube.com/@DwarkeshPatel/videos",
}


def _transform(raw: dict, channel: str = "") -> dict:
    url = raw.get("webpage_url") or raw.get("url", "")
    return make_entry(
        source="youtube",
        source_name=channel or raw.get("channel", "YouTube"),
        title=raw.get("title", ""),
        url=url,
        published="",  # Not available in flat-playlist mode
        content_preview=(raw.get("description", "") or "")[:500],
        metrics={"views": raw.get("view_count", 0) or 0},
    )


def fetch(channels: dict[str, str] | None = None, max_per_channel: int = 3) -> list[dict]:
    """Fetch recent videos from key YouTube channels."""
    channels = channels or DEFAULT_CHANNELS
    all_items = []

    for name, url in channels.items():
        cmd = [
            "yt-dlp", "--dump-json", "--flat-playlist",
            "--playlist-items", f"1:{max_per_channel}",
            url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                logger.warning(f"yt-dlp failed for {name}: {proc.stderr[:200]}")
                continue

            for line in proc.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    video = json.loads(line)
                    all_items.append(_transform(video, channel=name))
                except json.JSONDecodeError:
                    continue

        except subprocess.TimeoutExpired:
            logger.warning(f"yt-dlp timed out for {name}")
        except FileNotFoundError:
            logger.error("yt-dlp not found — install with: pip install yt-dlp")
            return []
        except Exception as e:
            logger.error(f"yt-dlp failed for {name}: {e}")

    return all_items
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add preflight/youtube.py tests/test_preflight.py
git commit -m "feat: add preflight/youtube.py for YouTube channel videos via yt-dlp"
```

---

## Chunk 2: Orchestration + Pipeline Integration

### Task 10: Create preflight/run_all.py

**Files:**
- Create: `preflight/run_all.py`
- Test: `tests/test_preflight.py` (append)

**Depends on:** Tasks 2-9 (all source scripts)

This is the core orchestrator. It:
1. Runs all 8 source fetchers in parallel (ThreadPoolExecutor)
2. Dedup-annotates items against last 7 days of findings (using `memory.search_findings`)
3. Assigns items to agents by source type and topic

- [ ] **Step 1: Write tests**

```python
from preflight.run_all import _dedup_annotate, _assign_to_agents


def test_dedup_annotate_marks_covered_via_fallback():
    """Test that items matching existing findings get marked already_covered (fallback path)."""
    items = [
        {"source": "rss", "title": "Claude 4 Released", "url": "u1", "content_preview": "Anthropic releases Claude 4", "already_covered": False, "match_info": None, "source_name": "", "published": "", "metrics": {}},
    ]
    # Mock: simulate a matching finding via legacy existing_fn
    existing = [{"title": "Claude 4 Launch", "similarity": 0.90, "agent": "news", "date": "2026-03-15"}]
    annotated = _dedup_annotate(items, existing_fn=lambda q: existing, threshold=0.85)
    assert annotated[0]["already_covered"] is True
    assert annotated[0]["match_info"]["matched_finding"] == "Claude 4 Launch"


def test_dedup_annotate_new_item():
    items = [
        {"source": "rss", "title": "Brand New Thing", "url": "u1", "content_preview": "Never seen before", "already_covered": False, "match_info": None, "source_name": "", "published": "", "metrics": {}},
    ]
    annotated = _dedup_annotate(items, existing_fn=lambda q: [], threshold=0.85)
    assert annotated[0]["already_covered"] is False


def test_dedup_annotate_no_db_no_fn():
    """Without db or existing_fn, all items remain new."""
    items = [
        {"source": "rss", "title": "Anything", "url": "u1", "content_preview": "...", "already_covered": False, "match_info": None, "source_name": "", "published": "", "metrics": {}},
    ]
    annotated = _dedup_annotate(items, db=None, existing_fn=None, threshold=0.85)
    assert annotated[0]["already_covered"] is False


def test_assign_to_agents():
    items = [
        {"source": "arxiv", "title": "Paper", "url": "u1", "source_name": "arXiv", "content_preview": "", "published": "", "metrics": {}, "already_covered": False, "match_info": None},
        {"source": "hn", "title": "HN Story", "url": "u2", "source_name": "HN", "content_preview": "", "published": "", "metrics": {}, "already_covered": False, "match_info": None},
        {"source": "rss", "title": "VC Analysis", "url": "u3", "source_name": "Tomasz Tunguz", "content_preview": "SaaS metrics...", "published": "", "metrics": {}, "already_covered": False, "match_info": None},
    ]
    assignments = _assign_to_agents(items)
    # arxiv goes to arxiv-researcher
    assert "arxiv-researcher" in assignments
    assert any(i["title"] == "Paper" for i in assignments["arxiv-researcher"])
    # hn goes to hn-researcher
    assert "hn-researcher" in assignments
```

- [ ] **Step 2: Run tests, verify fail**
- [ ] **Step 3: Implement**

```python
# preflight/run_all.py
"""Orchestrate all preflight sources, dedup-annotate, assign to agents."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import make_entry

logger = logging.getLogger(__name__)

# Agent assignment routing table
# source -> (primary_agent, secondary_agents)
SOURCE_ROUTING = {
    "arxiv": ("arxiv-researcher", ["agents-researcher"]),
    "github": ("github-pulse-researcher", ["projects-researcher", "vibe-coding-researcher"]),
    "hn": ("hn-researcher", ["news-researcher"]),
    "reddit": ("reddit-researcher", ["vibe-coding-researcher"]),
    "twitter": ("thought-leaders-researcher", ["news-researcher"]),
    "youtube": ("sources-researcher", ["vibe-coding-researcher"]),
    "exa": (None, []),  # Exa results are distributed by topic
}

# RSS routing by feed source name patterns
RSS_ROUTING = {
    # VC/SaaS/fintech feeds → saas-disruption-researcher
    "saas": ["Tomasz Tunguz", "SaaStr", "Bessemer", "Crunchbase", "Stripe", "Plaid",
             "a16z", "Sequoia", "Y Combinator", "First Round"],
    # Newsletter/analysis feeds → sources-researcher
    "sources": ["Simon Willison", "Latent Space", "The Batch", "Import AI",
                "Nathan Lambert", "Ahead of AI", "Ben's Bites"],
    # Company/news → news-researcher (default for RSS)
}


def _dedup_annotate(
    items: list[dict],
    existing_fn=None,
    threshold: float = 0.85,
    db=None,
) -> list[dict]:
    """Tag each item as NEW or ALREADY_COVERED via batch embedding comparison.

    Performance: batch-embeds all preflight titles upfront, loads stored
    embeddings once, does vectorized dot-product comparison. O(N*M) but
    with numpy vectorization instead of N individual DB queries.

    Args:
        items: List of preflight entry dicts.
        existing_fn: Legacy callable(query) -> list[dict]. Used as fallback.
        threshold: Similarity threshold for marking as covered.
        db: SQLite connection for batch dedup (preferred over existing_fn).
    """
    if not items:
        return items

    # Prefer batch approach when db is available
    if db is not None:
        try:
            return _dedup_batch(items, db, threshold)
        except Exception as e:
            logger.warning(f"Batch dedup failed, falling back to per-item: {e}")

    # Fallback: per-item dedup via existing_fn
    if existing_fn is None:
        return items

    for item in items:
        query = f"{item['title']}. {item.get('content_preview', '')}"
        try:
            matches = existing_fn(query)
            if matches and matches[0].get("similarity", 0) >= threshold:
                best = matches[0]
                item["already_covered"] = True
                item["match_info"] = {
                    "matched_finding": best.get("title", ""),
                    "matched_date": best.get("date", ""),
                    "matched_agent": best.get("agent", ""),
                    "similarity": round(best["similarity"], 3),
                }
        except Exception as e:
            logger.debug(f"Dedup check failed for '{item['title'][:50]}': {e}")

    return items


def _dedup_batch(items: list[dict], db, threshold: float) -> list[dict]:
    """Batch dedup: embed all items at once, compare against stored findings vectorized."""
    import numpy as np
    from memory.embeddings import embed_texts, deserialize_f32
    from datetime import datetime, timedelta

    # Load stored findings embeddings from last 7 days (one query)
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = db.execute(
        """SELECT f.title, f.agent, f.run_date, e.embedding
           FROM findings f
           JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.run_date >= ?""",
        (cutoff,),
    ).fetchall()

    if not rows:
        return items  # No stored findings = everything is new

    # Build stored embeddings matrix (M x 384)
    stored_titles = [r["title"] for r in rows]
    stored_agents = [r["agent"] for r in rows]
    stored_dates = [r["run_date"] for r in rows]
    stored_matrix = np.array([deserialize_f32(r["embedding"]) for r in rows], dtype=np.float32)

    # Batch-embed all preflight items (N x 384)
    texts = [f"{item['title']}. {item.get('content_preview', '')[:200]}" for item in items]
    item_vecs = np.array(embed_texts(texts), dtype=np.float32)

    # Vectorized similarity: (N x 384) @ (384 x M) = (N x M)
    sim_matrix = item_vecs @ stored_matrix.T

    # For each item, check if max similarity exceeds threshold
    for i, item in enumerate(items):
        max_idx = int(np.argmax(sim_matrix[i]))
        max_sim = float(sim_matrix[i, max_idx])
        if max_sim >= threshold:
            item["already_covered"] = True
            item["match_info"] = {
                "matched_finding": stored_titles[max_idx],
                "matched_date": stored_dates[max_idx],
                "matched_agent": stored_agents[max_idx],
                "similarity": round(max_sim, 3),
            }

    return items


def _assign_rss_item(item: dict) -> tuple[str, list[str]]:
    """Route an RSS item to the right agent(s) based on source name."""
    name = item.get("source_name", "").lower()

    for agent_key, patterns in RSS_ROUTING.items():
        for pattern in patterns:
            if pattern.lower() in name:
                if agent_key == "saas":
                    return "saas-disruption-researcher", ["news-researcher"]
                elif agent_key == "sources":
                    return "sources-researcher", ["rss-researcher"]

    # Default RSS → rss-researcher primary, news-researcher secondary
    return "rss-researcher", ["news-researcher"]


def _assign_to_agents(items: list[dict]) -> dict[str, list[dict]]:
    """Route preflight items to agents by source and topic.

    Returns dict of agent_name -> list of items assigned to that agent.
    """
    assignments: dict[str, list[dict]] = {}

    for item in items:
        source = item.get("source", "")

        if source == "rss":
            primary, secondaries = _assign_rss_item(item)
        elif source == "exa":
            # Exa results: route to news-researcher as primary, topic-specific as secondary
            primary = "news-researcher"
            secondaries = []
            title_lower = item.get("title", "").lower() + " " + item.get("content_preview", "").lower()
            if any(kw in title_lower for kw in ["saas", "fintech", "startup", "venture"]):
                secondaries.append("saas-disruption-researcher")
            if any(kw in title_lower for kw in ["agent", "mcp", "tool use"]):
                secondaries.append("agents-researcher")
            if any(kw in title_lower for kw in ["vibe", "cursor", "copilot", "coding"]):
                secondaries.append("vibe-coding-researcher")
        else:
            route = SOURCE_ROUTING.get(source, (None, []))
            primary, secondaries = route[0], route[1]

        if primary:
            assignments.setdefault(primary, []).append(item)
        for sec in secondaries:
            assignments.setdefault(sec, []).append(item)

    return assignments


def run_all(
    date_str: str,
    db=None,
    feeds_file: Path | None = None,
) -> dict:
    """Run all preflight sources in parallel, dedup-annotate, assign to agents.

    Returns:
        {
            "items": [...],               # All items (annotated)
            "assignments": {agent: [...]}, # Items routed to each agent
            "already_covered": [...],      # Items marked as already covered
            "total_items": int,
            "new_count": int,
            "covered_count": int,
            "source_counts": {source: int},
            "duration_ms": int,
        }
    """
    from . import PROJECT_ROOT
    start = time.monotonic()

    # Default feeds file
    if feeds_file is None:
        feeds_file = PROJECT_ROOT / "verticals" / "ai-tech" / "rss-feeds.json"

    # Import source modules
    from . import rss, arxiv, github, hn, reddit, twitter, exa, youtube

    # Define fetch tasks
    tasks = {
        "rss": lambda: rss.fetch(feeds_file=feeds_file),
        "arxiv": lambda: arxiv.fetch(),
        "github": lambda: github.fetch(),
        "hn": lambda: hn.fetch(),
        "reddit": lambda: reddit.fetch(),
        "twitter": lambda: twitter.fetch(),
        "exa": lambda: exa.fetch(),
        "youtube": lambda: youtube.fetch(),
    }

    # Run all sources in parallel
    all_items: list[dict] = []
    source_counts: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}

        for future in as_completed(futures):
            source_name = futures[future]
            try:
                items = future.result()
                all_items.extend(items)
                source_counts[source_name] = len(items)
                logger.info(f"Preflight {source_name}: {len(items)} items")
            except Exception as e:
                logger.error(f"Preflight {source_name} failed: {e}")
                source_counts[source_name] = 0

    logger.info(f"Preflight total: {len(all_items)} raw items from {len(source_counts)} sources")

    # Dedup-annotate against recent findings (batch-vectorized when db available)
    all_items = _dedup_annotate(all_items, db=db, threshold=0.85)

    new_items = [i for i in all_items if not i["already_covered"]]
    covered_items = [i for i in all_items if i["already_covered"]]

    # Assign to agents
    assignments = _assign_to_agents(all_items)

    duration_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        f"Preflight complete: {len(all_items)} total, {len(new_items)} new, "
        f"{len(covered_items)} already covered, {duration_ms}ms"
    )

    return {
        "items": all_items,
        "assignments": assignments,
        "already_covered": covered_items,
        "total_items": len(all_items),
        "new_count": len(new_items),
        "covered_count": len(covered_items),
        "source_counts": source_counts,
        "duration_ms": duration_ms,
    }
```

- [ ] **Step 4: Run all preflight tests**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add preflight/run_all.py tests/test_preflight.py
git commit -m "feat: add preflight/run_all.py orchestrator with dedup and agent assignment"
```

---

### Task 11: Modify orchestrator/agents.py

**Files:**
- Modify: `orchestrator/agents.py:114-212` — `build_agent_prompt()` new params
- Modify: `orchestrator/agents.py:320-400` — `dispatch_research_agents()` passes preflight
- Test: `tests/test_preflight.py` (append)

**Depends on:** Task 10

- [ ] **Step 1: Write test**

```python
from pathlib import Path
from orchestrator.agents import build_agent_prompt


def test_build_prompt_with_preflight(tmp_path):
    soul = tmp_path / "SOUL.md"
    soul.write_text("# SOUL\nYou are a research agent.")
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent\nFocus on AI news.")

    preflight_items = [
        {"source": "rss", "source_name": "Simon Willison", "title": "New Post", "url": "https://sw.net/1", "published": "2026-03-16T08:00:00Z", "content_preview": "About context engineering...", "metrics": {}, "already_covered": False, "match_info": None},
    ]
    already_covered = [
        {"source": "rss", "source_name": "TechCrunch", "title": "Old News", "url": "https://tc.com/1", "published": "2026-03-15T08:00:00Z", "content_preview": "Yesterday's story", "metrics": {}, "already_covered": True, "match_info": {"matched_finding": "Same Story", "matched_agent": "news", "similarity": 0.91}},
    ]

    prompt = build_agent_prompt(
        agent_name="news-researcher",
        user_id="ramsay",
        date_str="2026-03-16",
        soul_path=soul,
        agent_skill_path=skill,
        context="Recent findings...",
        preflight_items=preflight_items,
        already_covered=already_covered,
    )

    assert "Phase 1" in prompt
    assert "Phase 2" in prompt
    assert "New Post" in prompt
    assert "ALREADY COVERED" in prompt
    assert "Old News" in prompt


def test_build_prompt_without_preflight(tmp_path):
    """Backward compatible: works without preflight data."""
    soul = tmp_path / "SOUL.md"
    soul.write_text("# SOUL")
    skill = tmp_path / "agent.md"
    skill.write_text("# Agent")

    prompt = build_agent_prompt(
        agent_name="news-researcher",
        user_id="ramsay",
        date_str="2026-03-16",
        soul_path=soul,
        agent_skill_path=skill,
        context="",
    )

    assert "Phase 1" not in prompt  # No preflight = no Phase 1
    assert "CRITICAL" in prompt  # JSON schema still present
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Modify `build_agent_prompt()` — add preflight_items and already_covered params**

Add two new parameters to the function signature at line 114:

```python
def build_agent_prompt(
    agent_name: str,
    user_id: str,
    date_str: str,
    soul_path: Path,
    agent_skill_path: Path,
    context: str,
    trends: list[dict] | None = None,
    claims: list[str] | None = None,
    preflight_items: list[dict] | None = None,      # NEW
    already_covered: list[dict] | None = None,       # NEW
) -> str:
```

Replace the prompt string construction (lines 150-211) with the following. The key change: when `preflight_items` is provided, inject Phase 1 and Phase 2 sections instead of the old Search Instructions section:

```python
    # Build preflight sections if data available
    preflight_section = ""
    if preflight_items:
        new_items = [i for i in preflight_items if not i.get("already_covered")]
        covered_items = already_covered or [i for i in preflight_items if i.get("already_covered")]

        # Phase 1: Evaluate preflight data
        items_md = []
        for i, item in enumerate(new_items, 1):
            metrics_str = ""
            if item.get("metrics"):
                parts = [f"{k}={v}" for k, v in item["metrics"].items() if v]
                if parts:
                    metrics_str = f" ({', '.join(parts)})"
            items_md.append(
                f"{i}. **[{item['source'].upper()}]** [{item.get('source_name', '')}] "
                f"{item['title']}\n"
                f"   URL: {item['url']}\n"
                f"   {item.get('content_preview', '')[:200]}{metrics_str}"
            )

        covered_md = []
        for item in covered_items[:20]:  # Limit to 20 to save context
            mi = item.get("match_info") or {}
            covered_md.append(
                f"- ~~{item['title']}~~ — covered by {mi.get('matched_agent', '?')} "
                f"on {mi.get('matched_date', '?')} (sim={mi.get('similarity', 0):.2f})"
            )

        preflight_section = f"""

---

## Phase 1: Evaluate Pre-Fetched Data

Below are {len(new_items)} NEW items pre-fetched from your domain sources.

Select the 8-12 most important NEW items as findings. For each:
- Verify the content is real and recent (not old news resurfacing)
- Write a 2-3 sentence summary with specific details (names, numbers, dates)
- Rate importance (high/medium/low)
- Include the source_url from the preflight data

{chr(10).join(items_md)}

### ALREADY COVERED (skip unless major update)

{chr(10).join(covered_md) if covered_md else 'None.'}

---

## Phase 2: Explore Beyond Preflight

The preflight data covers known sources. Now find what it MISSED.
Use these tools to discover 2-5 additional findings:

- Exa semantic search: mcporter call exa.web_search_exa query="..." numResults=5
- Jina Reader (deep read any URL): curl -s "https://r.jina.ai/{{URL}}" 2>/dev/null | head -300
- Twitter search: xreach search "query" --count 10 --json
- YouTube transcripts: yt-dlp --dump-json "URL"
- WebSearch (last resort): only if Exa doesn't cover it

Look for:
- Stories that broke in the last 6 hours (too recent for RSS/feeds)
- Primary sources not in our feed list
- Reactions and follow-ups to stories in the preflight data

Target: 10-15 total findings (8-12 from Phase 1 + 2-5 from Phase 2).

"""

    # Old search instructions — only used when no preflight data
    search_section = ""
    if not preflight_items:
        search_section = """
---

## Search Instructions (SMTL)

PHASE A: Execute ALL search queries. Collect all results. Do NOT evaluate yet.
PHASE B: Now reason over collected evidence. Score each finding.
PHASE C: Filter against the Recent Findings list. Remove anything already covered.

For each finding evaluation, use max 5 words per reasoning step.
Do not explain your full reasoning — just output the finding.
"""

    prompt = f"""CRITICAL: Output ONLY valid JSON matching this schema. No markdown, no commentary.
{{
  "findings": [
    {{
      "title": "string",
      "summary": "string (2-3 sentences)",
      "importance": "high|medium|low",
      "category": "string",
      "source_url": "string (full URL)",
      "source_name": "string",
      "date_found": "{date_str}"
    }}
  ]
}}

---

{soul_content}

---

{skill_content}

---

## Research Context — {date_str}
{trends_section}
{claims_section}
{context}

---

## NOVELTY REQUIREMENT (CRITICAL)

You MUST find NEW content that is NOT in the "Recent Findings" list above.
If a topic, company, product, or event is already listed, DO NOT include it
unless there is a genuinely new development (new data, new announcement,
new reaction). "More coverage of the same story" is NOT new.

Search for what happened in the LAST 24 HOURS. Prioritize:
- Brand new announcements, launches, releases
- Breaking developments not yet widely covered
- Primary sources (blog posts, papers, repos) over secondary coverage

Every finding you return must pass this test: "Would someone who read
yesterday's newsletter learn something NEW from this?"
{preflight_section}{search_section}
---

CRITICAL REMINDER: Output ONLY the JSON object with "findings" array. No other text.
"""
    return prompt
```

- [ ] **Step 4: Modify `dispatch_research_agents()` — add preflight_data param**

Add `preflight_data` parameter to `dispatch_research_agents()` at line 320:

```python
def dispatch_research_agents(
    user_id: str,
    date_str: str,
    context_fn,
    trends: list[dict] | None = None,
    claims: list[str] | None = None,
    max_workers: int = 6,
    vertical: str = "ai-tech",
    preflight_data: dict | None = None,  # NEW
) -> list[AgentResult]:
```

Update the prompt building section (around line 361) to pass preflight items:

```python
            # Get preflight items assigned to this agent
            agent_preflight = None
            agent_covered = None
            if preflight_data and preflight_data.get("assignments"):
                agent_preflight = preflight_data["assignments"].get(agent_name, [])
                agent_covered = preflight_data.get("already_covered", [])

            prompt = build_agent_prompt(
                agent_name=agent_name,
                user_id=user_id,
                date_str=date_str,
                soul_path=soul_path,
                agent_skill_path=skill_path,
                context=context,
                trends=trends,
                claims=claims,
                preflight_items=agent_preflight,
                already_covered=agent_covered,
            )
```

- [ ] **Step 5: Run tests, verify pass**

Run: `cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py -k "build_prompt" -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add orchestrator/agents.py tests/test_preflight.py
git commit -m "feat: add preflight data to agent prompt builder and dispatch"
```

---

### Task 12: Modify orchestrator/runner.py

**Files:**
- Modify: `orchestrator/runner.py:311-337` — `_phase_research()` calls preflight

**Depends on:** Task 11

- [ ] **Step 1: Modify `_phase_research()`**

Replace lines 311-337 of `_phase_research()` to call preflight before dispatch. Insert the preflight call after `memory.clear_claims()` and before the agent dispatch:

```python
    def _phase_research(self) -> dict:
        """Phase 3: Research (13x Sonnet, parallel)."""
        memory.clear_claims(self.db, self.date_str)

        # NEW: Run preflight to gather structured data from all sources
        preflight_data = None
        try:
            from preflight.run_all import run_all as run_preflight
            preflight_data = run_preflight(
                date_str=self.date_str,
                db=self.db,
                feeds_file=PROJECT_ROOT / "verticals" / "ai-tech" / "rss-feeds.json",
            )
            logger.info(
                f"Preflight: {preflight_data['total_items']} items, "
                f"{preflight_data['new_count']} new, "
                f"{preflight_data['covered_count']} already covered, "
                f"{preflight_data['duration_ms']}ms"
            )

            # Log preflight stats to traces
            log_event(self.traces_conn, self.traces_run_id,
                      "preflight_complete",
                      json.dumps({
                          "total_items": preflight_data["total_items"],
                          "new_count": preflight_data["new_count"],
                          "covered_count": preflight_data["covered_count"],
                          "source_counts": preflight_data["source_counts"],
                          "duration_ms": preflight_data["duration_ms"],
                      }))
        except Exception as e:
            logger.warning(f"Preflight failed (non-critical, agents will use WebSearch): {e}")

        # Get cross-pipeline signal context
        signal_context = ""
        try:
            signal_context = memory.get_signal_context(self.db)
        except Exception as e:
            logger.warning(f"Signal context retrieval failed: {e}")

        def context_fn(agent_name, date_str):
            ctx = memory.get_context(self.db, agent_name, date_str)
            if signal_context and "No cross-pipeline signals" not in signal_context:
                ctx = ctx + "\n\n" + signal_context if ctx else signal_context
            return ctx

        current_claims = [c["topic_hash"] for c in memory.list_claims(self.db, self.date_str)]

        self.agent_results = agent_dispatch.dispatch_research_agents(
            user_id=self.user_id,
            date_str=self.date_str,
            context_fn=context_fn,
            trends=self.trends,
            claims=current_claims,
            max_workers=6,
            preflight_data=preflight_data,  # NEW
        )
```

The rest of `_phase_research()` (lines 339-434: dedup, store findings, log agent runs, policy validation) stays unchanged.

- [ ] **Step 2: Verify the pipeline still runs**

Quick syntax check:
```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -c "from orchestrator.runner import ResearchPipeline; print('Import OK')"
```

- [ ] **Step 3: Commit**

```bash
git add orchestrator/runner.py
git commit -m "feat: call preflight system before dispatching research agents"
```

---

## Chunk 3: Agent Skill Rewrites + Integration Test

### Task 13: Rewrite agent .md skill files

**Files:**
- Modify: all 13 files in `verticals/ai-tech/agents/*.md`

**Independent:** Can run in parallel with Tasks 2-12.

For each agent file:
1. **Remove** the `## Research Protocol (MANDATORY)` section (and everything below it)
2. **Remove** any `## Tool Invocation` or `## Search Queries to Try` sections
3. **Keep** everything else: title, learnings, description, focus areas, priority sources, output format, self-improvement notes
4. **Add** a `## Phase 2 Exploration Preferences` section at the end

The Phase 2 section tells each agent which Agent Reach tools to prioritize during Phase 2 exploration.

- [ ] **Step 1: Rewrite all 13 agent files**

Apply these changes to each file:

**`arxiv-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for recent AI/ML papers not on arXiv yet
- Secondary: Jina Reader for detailed paper analysis
- Skip: Twitter, YouTube (not relevant for academic papers)
```

**`news-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for breaking AI news from last 6 hours
- Secondary: Jina Reader for deep reads on company blog posts
- Tertiary: Twitter via xreach for breaking announcements
```

**`thought-leaders-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: xreach search for tracked accounts (Karpathy, swyx, Willison, Levels, etc.)
- Secondary: Exa search for thought leader blog posts
- Tertiary: Jina Reader for long-form posts and threads
```

**`github-pulse-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for new open-source AI tool launches
- Secondary: Jina Reader for README analysis of trending repos
- Skip: Twitter, YouTube
```

**`hn-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Jina Reader for deep reads on top HN discussions
- Secondary: Exa search for stories referenced in HN comments
- Skip: Twitter, YouTube
```

**`reddit-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Jina Reader for linked articles in top Reddit posts
- Secondary: Exa search for topics trending on Reddit
- Skip: Twitter, YouTube
```

**`rss-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Jina Reader for full article reads from RSS summaries
- Secondary: Exa search for related analysis pieces
- Skip: Twitter, YouTube
```

**`sources-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for new AI newsletters and publications
- Secondary: YouTube transcripts via yt-dlp for key AI channels
- Tertiary: Jina Reader for deep reads on new sources
```

**`agents-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for AI agent frameworks and launches
- Secondary: Jina Reader for documentation and announcement posts
- Tertiary: xreach for agent-related discussions on Twitter
```

**`vibe-coding-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: xreach search for vibe coding discussions and demos
- Secondary: YouTube transcripts for coding with AI videos
- Tertiary: Exa search for vibe coding blog posts and tutorials
```

**`projects-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for AI project launches and demos
- Secondary: Jina Reader for project documentation deep reads
- Skip: Twitter, YouTube
```

**`saas-disruption-researcher.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Exa search for SaaS disruption, fintech AI, startup launches
- Secondary: Jina Reader for investor analysis and market reports
- Tertiary: xreach for VC and founder discussions on Twitter
```

**`skill-finder.md`:**
```markdown
## Phase 2 Exploration Preferences
- Primary: Jina Reader for extracting actionable skills from top findings
- Secondary: Exa search for skill-building resources and tutorials
- Skip: Twitter, YouTube
```

For each file, the removal pattern is:
1. Find `## Research Protocol` or `## Search Queries to Try` or `## Tool Invocation`
2. Delete from that heading to the end of the file (or next `##` heading)
3. Append the Phase 2 section

- [ ] **Step 2: Verify all 13 files are valid markdown**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3
for f in verticals/ai-tech/agents/*.md; do
    echo "--- $f ---"
    grep "## Phase 2" "$f" || echo "MISSING Phase 2 section!"
    grep "## Research Protocol" "$f" && echo "WARNING: Research Protocol not removed!"
done
```

Expected: All 13 files have Phase 2 section, none have Research Protocol.

- [ ] **Step 3: Commit**

```bash
git add verticals/ai-tech/agents/*.md
git commit -m "feat: rewrite agent skill files for Phase 1/Phase 2 preflight structure"
```

---

### Task 14: Integration test

**Files:**
- Test: `tests/test_preflight.py` (append)

**Depends on:** Tasks 12 + 13

- [ ] **Step 1: Write integration test**

```python
def test_preflight_run_all_smoke():
    """Smoke test: run_all executes without crashing (uses real tools if available)."""
    from preflight.run_all import run_all
    from pathlib import Path

    feeds_file = Path(__file__).parent.parent / "verticals" / "ai-tech" / "rss-feeds.json"

    # Run without DB (skips dedup annotation)
    result = run_all(date_str="2026-03-16", db=None, feeds_file=feeds_file)

    assert "total_items" in result
    assert "assignments" in result
    assert "source_counts" in result
    assert result["total_items"] >= 0  # May be 0 if all tools fail
    assert isinstance(result["assignments"], dict)

    # Check that at least some source ran
    ran = [s for s, c in result["source_counts"].items() if c > 0]
    print(f"Sources that returned data: {ran}")
    print(f"Total items: {result['total_items']}")
    print(f"Assigned to agents: {list(result['assignments'].keys())}")
```

- [ ] **Step 2: Run integration test**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py::test_preflight_run_all_smoke -v -s --timeout=300
```

Expected: PASS (some sources may fail if tools aren't configured, but the test verifies the orchestration works)

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/taylerramsay/Projects/mindpattern-v3 && python3 -m pytest tests/test_preflight.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_preflight.py
git commit -m "test: add integration smoke test for preflight system"
```

---

## Success Criteria

After all tasks complete, verify:

- [ ] `python3 -c "from preflight.run_all import run_all; print('OK')"` — imports clean
- [ ] `python3 -m pytest tests/test_preflight.py -v` — all tests pass
- [ ] `python3 -c "from orchestrator.runner import ResearchPipeline; print('OK')"` — runner imports
- [ ] All 13 agent files have `## Phase 2 Exploration Preferences` section
- [ ] No agent files have `## Research Protocol (MANDATORY)` section
- [ ] Preflight gathers items from at least 5/8 sources when run locally
- [ ] Agent prompts include Phase 1/Phase 2 sections when preflight data is provided
- [ ] Agent prompts work without preflight data (backward compatible)

## Deferred: Phase 1 vs Phase 2 Tracking

The spec's success criterion "at least 30% of findings come from Phase 2 exploration" requires tagging each finding with its source phase. This is deferred because it requires changing the JSON output schema that agents produce, which would need prompt + parsing changes. To implement later: add `"source_phase": 1|2` to the findings JSON schema, have agents tag each finding, and store in the DB for measurement.

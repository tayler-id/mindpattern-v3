"""Claim ledger for multi-agent backfill (orchestrator/site_backfill.py)."""

import json
import threading
from pathlib import Path

import pytest

from orchestrator import site_backfill as bf


@pytest.fixture
def pool(tmp_path, monkeypatch):
    """A fake story pool of 20 unwritten dynamic stories."""
    stories = [
        {
            "slug": f"2026-06-0{1 + i % 9}-story-{i:02d}",
            "issue_date": f"2026-06-0{1 + i % 9}",
            "title": f"Story {i}",
            "summary": "s",
            "body_markdown": "body",
            "source_refs": [{"url": "https://x.com/a", "domain": "x.com", "title": "X"}],
            "entity_refs": [],
            "provenance": {"ai_generated": False},
        }
        for i in range(20)
    ]
    monkeypatch.setattr(bf, "backfill_targets", lambda *, user, since, limit: stories[:limit])
    return tmp_path


def test_concurrent_claims_never_overlap(pool):
    results = []

    def worker(name):
        results.append(bf.claim_batch(user="ramsay", reports_root=pool, size=8, agent=name))

    threads = [threading.Thread(target=worker, args=(f"a{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    all_slugs = [slug for r in results for slug in r["slugs"]]
    assert len(all_slugs) == len(set(all_slugs)), "two agents claimed the same story"
    assert sum(len(r["slugs"]) for r in results) <= 20


def test_claimed_stories_excluded_from_next_claim(pool):
    first = bf.claim_batch(user="ramsay", reports_root=pool, size=5, agent="one")
    second = bf.claim_batch(user="ramsay", reports_root=pool, size=50, agent="two")
    assert not set(first["slugs"]) & set(second["slugs"])
    assert len(second["slugs"]) == 15


def test_expired_claims_are_reclaimable(pool):
    first = bf.claim_batch(user="ramsay", reports_root=pool, size=5, agent="one", ttl_hours=-1)
    second = bf.claim_batch(user="ramsay", reports_root=pool, size=50, agent="two")
    assert set(first["slugs"]) <= set(second["slugs"])


def test_release_frees_only_that_claim(pool):
    first = bf.claim_batch(user="ramsay", reports_root=pool, size=5, agent="one")
    second = bf.claim_batch(user="ramsay", reports_root=pool, size=5, agent="two")
    released = bf.release_claim(user="ramsay", reports_root=pool, claim_id=first["claim_id"])
    assert released == 5
    active = bf._active_claims("ramsay", pool)
    assert set(active) == set(second["slugs"])


def test_run_claim_touches_only_owned_and_releases(pool, monkeypatch):
    claim = bf.claim_batch(user="ramsay", reports_root=pool, size=4, agent="one")
    processed = []

    def fake_story(story, *, user, reports_root):
        processed.append(story["slug"])
        return "written"

    monkeypatch.setattr(bf, "backfill_story", fake_story)
    result = bf.run_claim(user="ramsay", reports_root=pool, claim_id=claim["claim_id"])
    assert sorted(processed) == sorted(claim["slugs"])
    assert result["outcomes"] == {"written": 4}
    assert bf._active_claims("ramsay", pool) == {}


def test_status_counts(pool):
    bf.claim_batch(user="ramsay", reports_root=pool, size=5, agent="one")
    stories_dir = pool / "ramsay" / "site-stories" / "2026-06-01"
    stories_dir.mkdir(parents=True)
    (stories_dir / "done.json").write_text(json.dumps({"provenance": {"writer": "claude-cli"}}))
    (stories_dir / "fallback.json").write_text(json.dumps({"provenance": {}}))

    status = bf.backfill_status(user="ramsay", reports_root=pool)
    assert status["written"] == 1
    assert status["fallback_artifacts"] == 1
    assert status["in_progress"] == 5
    assert status["in_progress_by_agent"] == {"one": 5}
    assert status["remaining_unclaimed"] == 15


def test_cmd_provider_receives_prompt_on_stdin(monkeypatch):
    from orchestrator import site_writer as sw

    monkeypatch.setenv("MP_SITE_STORY_WRITER", "cmd:my-writer --flag")
    cmd, stdin_text = sw.writer_command("PROMPT TEXT")
    assert cmd == ["sh", "-c", "my-writer --flag"]
    assert stdin_text == "PROMPT TEXT"
    assert sw.writer_label() == "cmd"

    monkeypatch.setenv("MP_SITE_STORY_WRITER", "codex")
    cmd, stdin_text = sw.writer_command("PROMPT TEXT")
    assert cmd[0] == "codex" and cmd[1] == "exec"
    assert sw.writer_label() == "codex"

    monkeypatch.setenv("MP_SITE_STORY_WRITER", "claude")
    cmd, stdin_text = sw.writer_command("PROMPT TEXT")
    assert cmd[0] == "claude"
    assert sw.writer_label() == "claude-cli"

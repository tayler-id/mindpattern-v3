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
    monkeypatch.setattr(
        bf, "backfill_targets",
        lambda *, user, since, limit, reports_root=None: stories[:limit],
    )
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


def test_notebook_tracks_claims_and_outcomes(pool, monkeypatch):
    claim = bf.claim_batch(user="ramsay", reports_root=pool, size=3, agent="nb")
    monkeypatch.setattr(bf, "backfill_story", lambda s, *, user, reports_root: "written")
    bf.run_claim(user="ramsay", reports_root=pool, claim_id=claim["claim_id"])

    notebook = (pool / "ramsay" / "site-backfill-notebook.md").read_text()
    assert claim["claim_id"] in notebook
    assert "claimed: 3 stories" in notebook
    assert notebook.count("— written at") == 3
    assert "finished at" in notebook
    status = bf.backfill_status(user="ramsay", reports_root=pool)
    assert status["notebook"].endswith("site-backfill-notebook.md")


def test_run_claim_output_artifact_passes_the_full_quality_gate(tmp_path, monkeypatch):
    """End-to-end artifact gate: what run_claim writes must be publishable."""
    import json as json_mod

    from orchestrator import site_backfill as bf_mod
    from orchestrator.site_content_engine import evaluate_site_story_confidence
    from orchestrator.site_writer import violates_voice_guide

    story = {
        "kind": "story",
        "id": "2026-07-02-openai-ships-agent-controls",
        "slug": "2026-07-02-openai-ships-agent-controls",
        "issue_date": "2026-07-02",
        "status": "published",
        "confidence": "source-backed",
        "title": "OpenAI ships agent controls",
        "summary": "OpenAI released new controls.",
        "body_markdown": "OpenAI released new controls with detail.",
        "source_refs": [{"url": "https://openai.com/news/controls", "domain": "openai.com", "title": "OpenAI"}],
        "entity_refs": [{"id": "openai", "slug": "openai", "name": "OpenAI", "kind": "company"}],
        "graph_edges": [{"kind": "source_domain", "relationship": "cites_source_domain",
                         "id": "openai.com", "label": "openai.com", "target_url": "/source/openai.com"}],
        "claim_evidence": [],
        "provenance": {"ai_generated": False, "redaction_status": "passed"},
    }
    monkeypatch.setattr(
        bf_mod, "backfill_targets",
        lambda *, user, since, limit, reports_root=None: [story],
    )
    monkeypatch.setattr(
        bf_mod, "write_story_with_review",
        lambda pack, experts: {
            "title": "OpenAI puts agent controls on the buyer's scorecard",
            "dek": "Controls become the procurement question for agent platforms.",
            "take": "Controls are the new moat, and OpenAI knows it.",
            "why_now": "The controls shipped with the July 2 briefing cycle.",
            "body_markdown": "OpenAI released new controls.\n\nThat changes procurement reviews.",
        },
    )

    claim = bf_mod.claim_batch(user="ramsay", reports_root=tmp_path, size=1, agent="gate")
    result = bf_mod.run_claim(user="ramsay", reports_root=tmp_path, claim_id=claim["claim_id"])
    assert result["outcomes"] == {"written": 1}

    artifact_path = (
        tmp_path / "ramsay" / "site-stories" / "2026-07-02"
        / "2026-07-02-openai-ships-agent-controls.json"
    )
    artifact = json_mod.loads(artifact_path.read_text())
    assert artifact["kind"] == "site_story"
    assert artifact["provenance"]["writer"]
    assert artifact["claim_evidence"], "headline claim must be anchored to a source"
    public_text = " ".join(str(artifact.get(k) or "") for k in ("title", "dek", "take", "why_now", "body_markdown"))
    assert violates_voice_guide(public_text) is None
    gate = evaluate_site_story_confidence(artifact)
    assert gate["publishable"], gate["reasons"]

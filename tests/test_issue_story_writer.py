"""Daily full-coverage issue story writer (write_issue_stories_for_date)."""

import json
from pathlib import Path

from orchestrator.site_content_engine import write_issue_stories_for_date

ISSUE_MD = """# Ramsay Research Agent — July 2, 2026

## Top 5 Stories Today

**OpenAI ships agent controls.** [OpenAI](https://openai.com/news/controls)
released new controls. Full body sentence about the release with detail.

---

**Anthropic adds memory tools.** [Anthropic](https://anthropic.com/news/memory)
shipped memory tooling. Another full body sentence with enough detail here.

## Security

**A CVE lands in a popular SDK.** Per the [advisory](https://nvd.example.com/cve),
the bug affects shared deployments. More body text follows for the unit.
"""


def _copy(title="OpenAI puts agent controls on the map"):
    return {
        "title": title,
        "dek": "Controls become the procurement question for agent buyers.",
        "take": "Controls are the new moat, and OpenAI knows it.",
        "why_now": "The controls shipped with the July 2 briefing cycle.",
        "body_markdown": "OpenAI released new controls.\n\nThat changes reviews.",
    }


def test_writes_every_source_backed_unit(tmp_path):
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)

    calls = []

    def copywriter(pack, experts):
        calls.append(pack["candidate_id"])
        return _copy(f"Written: {pack['candidate_id'][:30]}")

    outcome = write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path, story_copywriter=copywriter
    )
    assert outcome["written"] == 3
    files = list((tmp_path / "ramsay" / "site-stories" / "2026-07-02").glob("*.json"))
    assert len(files) == 3
    for f in files:
        d = json.loads(f.read_text())
        assert d["provenance"]["writer"] == "claude-cli"
        assert d["graph_connectors"]["source_urls"]


def test_failed_copy_is_withheld_not_published_without_a_take(tmp_path):
    """A writer that fails must not publish a headline over an empty take.

    2026-08-04 shipped 5 such stubs: the copywriter died (API drop, 300s
    timeout) or the copy gate rejected both draft and revision, and the
    evidence-only artifact went live with take/dek/why_now blank.
    """
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)

    outcome = write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path, story_copywriter=lambda p, e: None
    )
    assert outcome["withheld"] == 3
    assert outcome["fallback"] == 0
    assert not list((tmp_path / "ramsay" / "site-stories" / "2026-07-02").glob("*.json"))


def test_withheld_unit_is_retried_by_the_next_run(tmp_path):
    """No artifact on disk is what makes the next run pick the unit back up."""
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)

    write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path, story_copywriter=lambda p, e: None
    )
    recovered = write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path,
        story_copywriter=lambda p, e: _copy(),
    )
    assert recovered["written"] == 3
    assert recovered["skipped"] == 0
    payload = json.loads(
        next((tmp_path / "ramsay" / "site-stories" / "2026-07-02").glob("*.json")).read_text()
    )
    assert payload["take"].strip()


def test_copy_without_a_take_is_withheld(tmp_path):
    """The gate is the take itself, not merely whether the writer returned."""
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)

    takeless = dict(_copy())
    takeless["take"] = "   "
    outcome = write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path,
        story_copywriter=lambda p, e: takeless,
    )
    assert outcome["withheld"] == 3
    assert not list((tmp_path / "ramsay" / "site-stories" / "2026-07-02").glob("*.json"))


def test_rerun_skips_existing(tmp_path):
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)
    write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path,
        story_copywriter=lambda p, e: _copy(),
    )
    second = write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path,
        story_copywriter=lambda p, e: _copy(),
    )
    assert second["skipped"] == 3
    assert second["written"] == 0

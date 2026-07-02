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


def test_failed_copy_falls_back_and_stays_rewritable(tmp_path):
    (tmp_path / "ramsay").mkdir()
    (tmp_path / "ramsay" / "2026-07-02.md").write_text(ISSUE_MD)

    outcome = write_issue_stories_for_date(
        date="2026-07-02", user="ramsay", reports_root=tmp_path, story_copywriter=lambda p, e: None
    )
    assert outcome["fallback"] == 3
    files = list((tmp_path / "ramsay" / "site-stories" / "2026-07-02").glob("*.json"))
    assert len(files) == 3
    payload = json.loads(files[0].read_text())
    assert not payload["provenance"].get("writer")

    from orchestrator.site_backfill import _already_backfilled

    slug = files[0].stem
    assert not _already_backfilled(slug, "2026-07-02", user="ramsay", reports_root=tmp_path)


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

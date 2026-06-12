"""2026-06-12 regression — a January MCP Apps story reached the newsletter.

Two holes in the store-time dedup gate: a 10-day search window (re-coverage
older than the window was invisible) and rewording that scores below the
0.90 similarity bar. Calibration on real data showed similarity thresholds
cannot separate re-coverage from genuine developments — the deterministic
fix is the URL-embedded source date.
"""

import numpy as np
import pytest
from unittest.mock import patch

import memory
from core import migrations
from memory.findings import source_date_from_url


class TestSourceDateFromUrl:
    @pytest.mark.parametrize("url,expected", [
        ("https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/", "2026-01-26"),
        ("https://arstechnica.com/security/2026/06/a-single-errant-character/", "2026-06-01"),
        ("https://example.com/2026/05/14/story-title/", "2026-05-14"),
        ("https://github.com/foo/bar", None),
        ("https://arxiv.org/abs/2605.15184", None),
        (None, None),
        ("", None),
    ])
    def test_extraction(self, url, expected):
        assert source_date_from_url(url) == expected

    def test_rejects_impossible_dates(self):
        assert source_date_from_url("https://x.com/9999-99-99-foo/") is None


class TestStoreGateBehavior:
    """The exact 2026-06-12 case: the runner's gate must skip a finding
    whose source URL carries a date >30 days before the run date."""

    def test_january_source_is_stale_for_june_run(self):
        source_date = source_date_from_url(
            "https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/"
        )
        stale_cutoff = "2026-05-13"  # run date 2026-06-12 minus 30 days
        assert source_date is not None
        assert source_date < stale_cutoff  # → skipped

    def test_fresh_source_passes(self):
        source_date = source_date_from_url(
            "https://arstechnica.com/security/2026/06/errant-character/"
        )
        stale_cutoff = "2026-05-13"
        assert source_date >= stale_cutoff  # → stored

    def test_undated_url_is_not_blocked(self):
        # No date in URL → no stale verdict; semantic gate still applies.
        assert source_date_from_url("https://github.com/anthropics/claude-code/issues/18837") is None

    def test_runner_gate_wired(self):
        """The runner must consult source_date_from_url before storing and
        search 180 days (not 10) for semantic duplicates."""
        from pathlib import Path

        source = Path(__file__).parent.parent.joinpath(
            "orchestrator", "runner.py"
        ).read_text()
        research = source.split("def _phase_research")[1].split("def _phase_")[0]
        assert "source_date_from_url" in research
        assert "days=180" in research
        assert "days=10," not in research

"""The warm crawl must pick its targets from the source of truth.

2026-08-26: sitemap_site_paths() read https://mindpattern.ai/sitemap.xml and
got `x-vercel-cache: HIT, age: 69` holding the previous 187-URL sitemap, so a
--warm-only run warmed 36 blog dates and entry points, reported
"crawled 36, failed 0", and left all 6,806 stories and 84 entity pages cold.
The sitemap route carries revalidate=3600, so the copy a crawler happens to
get can be an hour stale.

The backend endpoint it renders from has no CDN in front of it.
"""

import json
from unittest.mock import patch

import pytest

from orchestrator import sync


GRAPH = {
    "stories": [{"slug": f"s{i}", "issue_date": "2026-08-25"} for i in range(500)],
    "entities": [f"e{i}" for i in range(84)],
    "sources": [f"d{i}.com" for i in range(18)],
    "briefings": [f"2026-08-{i:02d}" for i in range(1, 26)],
}


class TestPathsComeFromTheBackend:
    def test_the_backend_graph_is_preferred_over_the_cached_sitemap(self):
        with patch.object(sync, "_backend_sitemap_graph", return_value=GRAPH) as g, \
             patch("urllib.request.urlopen") as urlopen:
            paths = sync.sitemap_site_paths()
        assert g.called
        assert not urlopen.called, "read the CDN copy when the backend answered"
        assert any(p.startswith("/e/") for p in paths), "no entity pages queued"
        assert any(p.startswith("/s/") for p in paths), "no story pages queued"
        assert any(p.startswith("/source/") for p in paths)

    def test_entity_and_source_pages_come_before_the_story_tail(self):
        """Entity pages were the ones measured past the site's 10s abort."""
        with patch.object(sync, "_backend_sitemap_graph", return_value=GRAPH):
            paths = sync.sitemap_site_paths()
        first_story = next(i for i, p in enumerate(paths) if p.startswith("/s/"))
        last_entity = max(i for i, p in enumerate(paths) if p.startswith("/e/"))
        assert last_entity < first_story

    def test_every_entity_is_queued_not_a_sample(self):
        with patch.object(sync, "_backend_sitemap_graph", return_value=GRAPH):
            paths = sync.sitemap_site_paths()
        assert sum(1 for p in paths if p.startswith("/e/")) == 84

    def test_a_backend_that_cannot_answer_raises_rather_than_warming_a_stub(self):
        with patch.object(sync, "_backend_sitemap_graph", return_value=None):
            with pytest.raises(RuntimeError):
                sync.sitemap_site_paths()

    def test_a_graph_with_no_stories_raises(self):
        with patch.object(sync, "_backend_sitemap_graph", return_value={"stories": []}):
            with pytest.raises(RuntimeError):
                sync.sitemap_site_paths()

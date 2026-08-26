"""One story request must not walk the whole story tree.

2026-08-26: /api/stories/{slug} hung past 60s for stories whose JSON was
present on disk, and the backend warm-up reported gaps in story_details every
run. _public_story_files() rglobs reports/<user>/site-stories for *.json and
sorts the result on every call, and _resolve_story_response then scans that
list linearly for one stem. The tree holds 3,468 files locally and more on the
Fly volume, on network-backed storage.

The list only changes when the pipeline publishes, which is once a day.
"""

import json

import pytest

from dashboard.routes import api as api_mod


@pytest.fixture
def story_tree(tmp_path, monkeypatch):
    stories = tmp_path / "ramsay" / "site-stories"
    for day in range(6):
        d = stories / f"2026-08-{day + 1:02d}"
        d.mkdir(parents=True)
        for n in range(20):
            slug = f"2026-08-{day + 1:02d}-story-{n}"
            (d / f"{slug}.json").write_text(json.dumps({
                "slug": slug, "title": f"Story {n}", "status": "published",
                "issue_date": f"2026-08-{day + 1:02d}",
            }))
    monkeypatch.setattr(api_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path)
    api_mod._reset_fingerprint_cache()
    api_mod._reset_story_file_index()
    return tmp_path


class TestStoryFileIndex:
    def test_repeat_lookups_walk_the_tree_once(self, story_tree, monkeypatch):
        import pathlib as _pl

        walks = {"n": 0}
        real = _pl.Path.rglob

        def counting(self, pattern):
            if "site-stories" in str(self):
                walks["n"] += 1
            return real(self, pattern)

        monkeypatch.setattr(_pl.Path, "rglob", counting)

        for _ in range(40):
            api_mod._public_story_files("ramsay")

        assert walks["n"] == 1, f"40 lookups walked the tree {walks['n']} times"

    def test_a_slug_resolves_without_scanning_every_file(self, story_tree):
        path = api_mod._story_file_for_slug("ramsay", "2026-08-03-story-7")
        assert path is not None and path.stem == "2026-08-03-story-7"

    def test_an_unknown_slug_resolves_to_none_immediately(self, story_tree):
        assert api_mod._story_file_for_slug("ramsay", "no-such-story") is None

    def test_the_index_refreshes_when_the_fingerprint_moves(self, story_tree):
        assert api_mod._story_file_for_slug("ramsay", "brand-new") is None

        day = story_tree / "ramsay" / "site-stories" / "2026-08-01"
        (day / "brand-new.json").write_text(json.dumps({"slug": "brand-new"}))
        api_mod._reset_fingerprint_cache()
        api_mod._reset_story_file_index()

        assert api_mod._story_file_for_slug("ramsay", "brand-new") is not None

    def test_the_listing_keeps_its_newest_first_order(self, story_tree):
        files = api_mod._public_story_files("ramsay")
        names = [p.as_posix() for p in files]
        assert names == sorted(names, reverse=True)

    def test_a_traversal_slug_is_refused(self, story_tree):
        assert api_mod._story_file_for_slug("ramsay", "../../etc/passwd") is None

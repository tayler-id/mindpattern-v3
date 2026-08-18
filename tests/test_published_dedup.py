"""Tests for selection-time dedup against published newsletter issues."""

from pathlib import Path

from orchestrator.published_history import (
    flag_republished,
    format_published_block,
    published_stories,
)
from orchestrator.runner import _selected_titles_from_pass1


ISSUE = """# Daily Issue

## Top 5 Stories Today

### 1. Agents Are Now Hugging Face's Primary Users, and Claude Code Is 44.4% of Them

Body paragraph about the census.

### 2. Five Vendors Shipped the Same Tollbooth in Ten Days

Body paragraph.

## Security

**A llama.cpp build shipped today fixes an out-of-bounds read on LoRA adapters.** Rest of the item ([llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/b10451)).

Plain paragraph without a bold lead is not a story.

## Skills of the Day

**This bold lead must be skipped.** Recurring-by-design section ([skip](https://example.com/skip-me)).

## How This Newsletter Learns From You

**Reply to this email** boilerplate.
"""


def _write_issue(report_dir: Path, date: str, text: str = ISSUE) -> None:
    (report_dir / f"{date}.md").write_text(text)


def test_published_stories_extracts_top_stories_and_items(tmp_path):
    _write_issue(tmp_path, "2026-08-16")
    stories = published_stories(tmp_path, "2026-08-17", days=14)
    titles = [s["title"] for s in stories]
    assert (
        "Agents Are Now Hugging Face's Primary Users, and Claude Code Is 44.4% of Them"
        in titles
    )
    assert "Five Vendors Shipped the Same Tollbooth in Ten Days" in titles
    assert any(t.startswith("A llama.cpp build shipped today") for t in titles)
    kinds = {s["title"][:12]: s["kind"] for s in stories}
    assert kinds["Agents Are N"] == "top"
    assert kinds["A llama.cpp "] == "item"


def test_published_stories_skips_recurring_sections(tmp_path):
    _write_issue(tmp_path, "2026-08-16")
    titles = [s["title"] for s in published_stories(tmp_path, "2026-08-17")]
    assert "This bold lead must be skipped." not in titles
    assert "Reply to this email" not in titles


def test_published_stories_respects_window_and_filenames(tmp_path):
    _write_issue(tmp_path, "2026-08-16")   # inside window
    _write_issue(tmp_path, "2026-07-01")   # outside window
    _write_issue(tmp_path, "2026-08-17")   # today: excluded (not yet history)
    (tmp_path / "2099-01-01-dry-run.md").write_text(ISSUE)
    (tmp_path / "site-backfill-notebook.md").write_text(ISSUE)
    stories = published_stories(tmp_path, "2026-08-17", days=14)
    assert {s["date"] for s in stories} == {"2026-08-16"}


def test_published_stories_missing_dir_and_bad_date(tmp_path):
    assert published_stories(tmp_path / "nope", "2026-08-17") == []
    _write_issue(tmp_path, "2026-08-16")
    assert published_stories(tmp_path, "not-a-date") == []


def test_format_published_block_empty_and_filled():
    assert format_published_block([]) == ""
    block = format_published_block(
        [{"date": "2026-08-16", "title": "Some Story", "kind": "top"}]
    )
    assert "Already Published" in block
    assert "- (2026-08-16) Some Story" in block


def test_flag_republished_catches_reworded_repeat():
    published = [
        {"date": "2026-08-14", "kind": "top", "title": (
            "PIPES drops agent perception attack success from 84.7% to 2.3% "
            "by tagging provenance"
        )},
        {"date": "2026-08-13", "kind": "item", "title": (
            "uv 0.12.0 makes src/ layout and a build backend the default "
            "for uv init"
        )},
    ]
    flagged = flag_republished(
        [
            # Same stories, reworded the way the 2026-08-17 audit found them
            "PIPES cut perception attack success from 84.7% to 2.3% by "
            "tagging provenance",
            "uv 0.12.0 Makes Packaged src/ Layout the Default for uv init "
            "and Turns on hashes",
            # Unrelated story — must not flag
            "Anthropic begins watermarking every Claude text output worldwide",
        ],
        published,
    )
    assert len(flagged) == 2
    assert flagged[0]["selected_title"].startswith("PIPES cut")
    assert flagged[0]["published_date"] == "2026-08-14"
    assert flagged[0]["similarity"] >= 0.45


def test_flag_republished_ignores_distinct_stories_about_same_product():
    published = [
        {"date": "2026-08-07", "kind": "item",
         "title": "Claude Code 2.1.224 removed the 200-subagent cap"},
        {"date": "2026-08-16", "kind": "item",
         "title": "Qwen holds 151,448 derivative repos on Hugging Face"},
    ]
    flagged = flag_republished(
        [
            "Claude Code 2.1.233 fixes a Windows path handling bug",
            "Qwen3.8-27B weights landed on Hugging Face",
        ],
        published,
    )
    assert flagged == []


def test_flag_republished_empty_inputs():
    assert flag_republished([], [{"date": "d", "title": "x", "kind": "top"}]) == []
    assert flag_republished(["some title"], []) == []


def test_selected_titles_from_pass1_variants():
    bare = (
        '[{"story_title": "Story A", "agent": "x", "section": "s", '
        '"reason": "r"}, {"story_title": "Story B", "agent": "y", '
        '"section": "s", "reason": "r"}]'
    )
    assert _selected_titles_from_pass1(bare) == ["Story A", "Story B"]

    fenced = f"```json\n{bare}\n```"
    assert _selected_titles_from_pass1(fenced) == ["Story A", "Story B"]

    assert _selected_titles_from_pass1("no json here") == []
    assert _selected_titles_from_pass1('{"story_title": "not a list"}') == []
    assert _selected_titles_from_pass1("[not, valid, json") == []


class TestFlagRepublishedUrls:
    """URL tripwire: same source cited again = same story reworded."""

    def _history(self, dates, url="https://github.com/owner/repo"):
        return [
            {"date": d, "title": f"story on {d}", "kind": "item", "urls": [url]}
            for d in dates
        ]

    def test_story_extraction_captures_urls_per_story(self, tmp_path):
        _write_issue(tmp_path, "2026-08-16")
        stories = published_stories(tmp_path, "2026-08-17", days=14)
        by_title = {s["title"][:12]: s for s in stories}
        assert (
            "https://github.com/ggml-org/llama.cpp/releases/tag/b10451"
            in by_title["A llama.cpp "]["urls"]
        )
        # Skipped sections contribute no stories and no URLs
        assert all(
            "skip-me" not in u for s in stories for u in s["urls"]
        )

    def test_repeat_url_flags_with_prior_dates(self):
        from orchestrator.published_history import flag_republished_urls

        issue = (
            "## Hot Projects\n\n"
            "**repo hit 99k stars with fresh wording.** Body "
            "([repo](https://github.com/owner/repo/)).\n"
        )
        flags = flag_republished_urls(issue, self._history(["2026-08-09", "2026-08-17"]))
        assert len(flags) == 1
        assert flags[0]["prior_dates"] == ["2026-08-09", "2026-08-17"]
        assert flags[0]["url"] == "https://github.com/owner/repo"

    def test_tracker_url_is_exempt(self):
        from orchestrator.published_history import flag_republished_urls

        issue = (
            "## Tools\n\n"
            "**New release notes landed.** Body "
            "([changelog](https://docs.example.com/changelog)).\n"
        )
        history = self._history(
            ["2026-08-01", "2026-08-03", "2026-08-05", "2026-08-08", "2026-08-11"],
            url="https://docs.example.com/changelog",
        )
        assert flag_republished_urls(issue, history) == []

    def test_fresh_url_not_flagged_and_one_flag_per_story(self):
        from orchestrator.published_history import flag_republished_urls

        issue = (
            "## Tools\n\n"
            "**Story citing two repeats.** Body "
            "([a](https://github.com/owner/repo)) and "
            "([b](https://github.com/owner/repo)).\n"
            "**Brand new story.** Body ([new](https://example.com/new)).\n"
        )
        flags = flag_republished_urls(issue, self._history(["2026-08-09"]))
        assert len(flags) == 1
        assert flags[0]["title"] == "Story citing two repeats."

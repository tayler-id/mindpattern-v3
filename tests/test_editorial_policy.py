"""policies/editorial.json sets the story counts, and the prompts state the same count."""
import json
from pathlib import Path

import pytest

from orchestrator.editorial import EditorialPolicy, EditorialPolicyError, load

ROOT = Path(__file__).resolve().parent.parent


def test_the_shipped_policy():
    assert load() == EditorialPolicy(top_stories=5, deep_dive_stories=5, candidate_stories_per_day=5,
                                     issue_stories_per_day=20, tracker_url_threshold=5)


def test_the_prompts_state_the_same_top_story_count():
    count = load().top_stories
    assert f"That is {count} on a day with no lead stories" in (ROOT / "agents" / "synthesis-selector.md").read_text()
    assert f"**Top {count}:**" in (ROOT / "prompts" / "synthesis-pass2.md").read_text()


def test_the_runner_and_republish_check_read_the_policy():
    from orchestrator import published_history
    source = (ROOT / "orchestrator" / "runner.py").read_text()
    assert "top_stories = editorial.load().top_stories" in source
    assert "picks_needed = top_stories - len(leads)" in source and "Select exactly {picks_needed} stories" in source
    assert "MP_SITE_ISSUE_STORIES_MAX" not in source and "MP_SITE_CONTENT_MAX_STORIES" not in source
    assert published_history.TRACKER_URL_THRESHOLD == load().tracker_url_threshold


@pytest.mark.parametrize("change,message", [
    ({"newsletter": {"top_stories": 0, "deep_dive_stories": 0}}, "top_stories must be an integer from 1"),
    ({"newsletter": {"top_stories": 5, "deep_dive_stories": 6}}, "deep_dive_stories must be an integer from 0 to 5"),
    ({"site": {"candidate_stories_per_day": 11, "issue_stories_per_day": 20}}, "candidate_stories_per_day"),
    ({"site": {"candidate_stories_per_day": 5, "issue_stories_per_day": "20"}}, "issue_stories_per_day"),
])
def test_an_out_of_range_value_fails_the_load(tmp_path, change, message):
    data = json.loads((ROOT / "policies" / "editorial.json").read_text())
    data.update(change)
    path = tmp_path / "editorial.json"
    path.write_text(json.dumps(data))
    with pytest.raises(EditorialPolicyError, match=message):
        load(path)


def test_the_newsletter_length_comes_from_the_policy():
    policy = load()
    assert (policy.issue_words_min, policy.issue_words_max) == (10000, 14000)
    assert (policy.section_items_min, policy.section_items_max) == (6, 12)
    assert (policy.item_words_min, policy.item_words_max) == (80, 160)
    block = policy.length_block()
    assert "10,000 to 14,000 words" in block
    assert "6 to 12 items" in block and "80 to 160 words" in block
    assert "Give each of the Top 5 stories 300 to 500 words." in block


@pytest.mark.parametrize("leads,sentence", [
    (2, "Give each of the 2 lead stories 600 to 900 words and each of the other 3 Top stories 300 to 500 words."),
    (5, "Give each of the 5 lead stories 600 to 900 words. Give every other section"),
])
def test_lead_stories_get_their_own_length(leads, sentence):
    assert sentence in load().length_block(lead_stories=leads)


def test_the_writer_reads_its_length_from_the_policy_and_nowhere_else():
    runner = (ROOT / "orchestrator" / "runner.py").read_text()
    assert "editorial.load().length_block(lead_stories=len(leads))" in runner
    writer = (ROOT / "agents" / "synthesis-writer.md").read_text()
    for stale in ("4000-5000 words", "100-200 words per finding"):
        assert stale not in writer, stale


def test_a_length_range_that_runs_backwards_fails_the_load(tmp_path):
    data = json.loads((ROOT / "policies" / "editorial.json").read_text())
    data["newsletter"]["length"]["issue_words"] = {"min": 15000, "max": 10000}
    path = tmp_path / "editorial.json"
    path.write_text(json.dumps(data))
    with pytest.raises(EditorialPolicyError, match="newsletter.length.issue_words"):
        load(path)


def test_the_layout_comes_from_the_policy_and_reaches_the_writer(tmp_path):
    layout = load().layout
    assert (layout.top_max_lists, layout.top_max_list_items, layout.top_max_tables) == (1, 4, 0)
    assert (layout.section_max_lists, layout.section_max_tables, layout.list_sections) == (0, 0, ("Skills of the day",))
    block = layout.block()
    assert block.startswith("## Layout\nWrite every Top story as prose")
    assert "may end on one list of up to 4 items" in block and "Use no tables." in block
    assert "editorial.load().layout.block()" in (ROOT / "orchestrator" / "runner.py").read_text()
    data = json.loads((ROOT / "policies" / "editorial.json").read_text())
    data["newsletter"]["layout"]["section"]["max_tables"] = -1
    path = tmp_path / "editorial.json"
    path.write_text(json.dumps(data))
    with pytest.raises(EditorialPolicyError, match="newsletter.layout.section.max_tables"):
        load(path)

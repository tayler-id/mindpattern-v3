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
    assert f"Select exactly {count} stories" in (ROOT / "agents" / "synthesis-selector.md").read_text()
    assert f"**Top {count}:**" in (ROOT / "prompts" / "synthesis-pass2.md").read_text()


def test_the_republish_check_reads_the_policy():
    from orchestrator import published_history
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

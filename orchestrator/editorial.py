"""Editorial counts and caps from policies/editorial.json, checked when loaded."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "editorial.json"


class EditorialPolicyError(ValueError):
    """policies/editorial.json is missing a value or holds one out of range."""


@dataclass(frozen=True)
class EditorialPolicy:
    top_stories: int
    deep_dive_stories: int
    candidate_stories_per_day: int
    issue_stories_per_day: int
    tracker_url_threshold: int
    issue_words_min: int = 10000
    issue_words_max: int = 14000
    section_items_min: int = 6
    section_items_max: int = 12
    item_words_min: int = 80
    item_words_max: int = 160

    def length_block(self) -> str:
        """The writer's length instructions, rendered from the policy."""
        return (
            "## Length\n"
            f"Write {self.issue_words_min:,} to {self.issue_words_max:,} words. Give each of the Top "
            f"{self.top_stories} stories 300 to 500 words. Give every other section that has findings its own "
            f"`##` heading and {self.section_items_min} to {self.section_items_max} items, each opening with a "
            f"bold one-sentence headline and running {self.item_words_min} to {self.item_words_max} words with "
            "its source link and a \"**Why it matters:**\" line. Draw them from All Findings. Skip a section "
            "only when it has no findings.\n"
        )


def _int(data: dict, section: str, key: str, low: int, high: int) -> int:
    value = (data.get(section) or {}).get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise EditorialPolicyError(f"editorial.json {section}.{key} must be an integer from {low} to {high}, "
                                   f"got {value!r}")
    return value


def _range(data: dict, key: str, low: int, high: int) -> tuple[int, int]:
    raw = ((data.get("newsletter") or {}).get("length") or {}).get(key) or {}
    lo, hi = raw.get("min"), raw.get("max")
    for value in (lo, hi):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise EditorialPolicyError(f"editorial.json newsletter.length.{key} needs min and max integers "
                                       f"from {low} to {high}, got {raw!r}")
    if lo > hi:
        raise EditorialPolicyError(f"editorial.json newsletter.length.{key} min {lo} is above max {hi}")
    return lo, hi


def load(path: Path = POLICY_PATH) -> EditorialPolicy:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EditorialPolicyError(f"cannot read {path}: {exc}") from exc
    top = _int(data, "newsletter", "top_stories", 1, 10)
    counts = dict(
        top_stories=top,
        deep_dive_stories=_int(data, "newsletter", "deep_dive_stories", 0, top),
        candidate_stories_per_day=_int(data, "site", "candidate_stories_per_day", 1, 10),
        issue_stories_per_day=_int(data, "site", "issue_stories_per_day", 0, 100),
        tracker_url_threshold=_int(data, "republish_check", "tracker_url_threshold", 1, 50),
    )
    words = _range(data, "issue_words", 1000, 30000)
    items = _range(data, "section_items", 1, 30)
    item_words = _range(data, "item_words", 20, 500)
    return EditorialPolicy(
        **counts,
        issue_words_min=words[0], issue_words_max=words[1],
        section_items_min=items[0], section_items_max=items[1],
        item_words_min=item_words[0], item_words_max=item_words[1],
    )

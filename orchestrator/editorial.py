"""Editorial counts and caps from policies/editorial.json, checked when loaded."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "editorial.json"


class EditorialPolicyError(ValueError):
    """policies/editorial.json is missing a value or holds one out of range."""


@dataclass(frozen=True)
class Layout:
    """How many lists and tables a Top story and a section may carry. Counted by orchestrator/issue_format.py."""
    top_max_lists: int = 1
    top_max_list_items: int = 4
    top_max_tables: int = 0
    section_max_lists: int = 0
    section_max_tables: int = 0
    list_sections: tuple[str, ...] = ("Skills of the day",)

    def block(self) -> str:
        """The writer's layout instructions, rendered from the policy."""
        lists = "one list" if self.top_max_lists == 1 else f"up to {self.top_max_lists} lists"
        top_lists = (f"A Top story may end on {lists} of up to {self.top_max_list_items} items saying what a "
                     "builder should do, and has no other list.") if self.top_max_lists else "A Top story has no list."
        section_lists = ("with no list inside" if not self.section_max_lists
                         else f"with at most {self.section_max_lists} list in a section")
        tables = ("Use no tables." if not (self.top_max_tables or self.section_max_tables) else
                  f"Use at most {self.top_max_tables} table per Top story and {self.section_max_tables} per section.")
        listed = " and ".join(self.list_sections)
        return (
            "## Layout\n"
            f"Write every Top story as prose, in paragraphs with the source links inline. {top_lists} Write every "
            f"section item as prose too, as a bold headline, a paragraph and the \"**Why it matters:**\" line, "
            f"{section_lists}. {tables}"
            + (f" {listed} {'is the one section' if len(self.list_sections) == 1 else 'are the sections'} written "
               "as a numbered list." if listed else "")
            + " Code counts the lists and tables when you finish, and an editor folds any extra into prose.\n"
        )


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
    lead_story_words_min: int = 600
    lead_story_words_max: int = 900
    layout: Layout = Layout()

    def length_block(self, lead_stories: int = 0) -> str:
        """The writer's length instructions, rendered from the policy for today's mix of Top stories."""
        leads = f"each of the {lead_stories} lead stories {self.lead_story_words_min} to {self.lead_story_words_max} words"
        singles = self.top_stories - lead_stories
        if not lead_stories:
            top = f"Give each of the Top {self.top_stories} stories 300 to 500 words."
        elif not singles:
            top = f"Give {leads}."
        else:
            top = f"Give {leads} and each of the other {singles} Top stories 300 to 500 words."
        return (
            "## Length\n"
            f"Write {self.issue_words_min:,} to {self.issue_words_max:,} words. {top} "
            "Give every other section that has findings its own "
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


def _layout(data: dict) -> Layout:
    raw = (data.get("newsletter") or {}).get("layout") or {}
    values = {}
    for group, key, field, high in (("top_story", "max_lists", "top_max_lists", 3),
                                    ("top_story", "max_list_items", "top_max_list_items", 12),
                                    ("top_story", "max_tables", "top_max_tables", 3),
                                    ("section", "max_lists", "section_max_lists", 3),
                                    ("section", "max_tables", "section_max_tables", 3)):
        value = (raw.get(group) or {}).get(key, getattr(Layout, field))
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= high:
            raise EditorialPolicyError(f"editorial.json newsletter.layout.{group}.{key} must be an integer from 0 "
                                       f"to {high}, got {value!r}")
        values[field] = value
    sections = raw.get("list_sections", list(Layout.list_sections))
    if not isinstance(sections, list) or not all(isinstance(name, str) and name.strip() for name in sections):
        raise EditorialPolicyError("editorial.json newsletter.layout.list_sections must be a list of section names")
    return Layout(list_sections=tuple(sections), **values)


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
    lead_words = _range(data, "lead_story_words", 100, 3000)
    return EditorialPolicy(
        **counts,
        issue_words_min=words[0], issue_words_max=words[1],
        section_items_min=items[0], section_items_max=items[1],
        item_words_min=item_words[0], item_words_max=item_words[1],
        lead_story_words_min=lead_words[0], lead_story_words_max=lead_words[1],
        layout=_layout(data),
    )

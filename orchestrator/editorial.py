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


def _int(data: dict, section: str, key: str, low: int, high: int) -> int:
    value = (data.get(section) or {}).get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise EditorialPolicyError(f"editorial.json {section}.{key} must be an integer from {low} to {high}, "
                                   f"got {value!r}")
    return value


def load(path: Path = POLICY_PATH) -> EditorialPolicy:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EditorialPolicyError(f"cannot read {path}: {exc}") from exc
    top = _int(data, "newsletter", "top_stories", 1, 10)
    return EditorialPolicy(
        top_stories=top,
        deep_dive_stories=_int(data, "newsletter", "deep_dive_stories", 0, top),
        candidate_stories_per_day=_int(data, "site", "candidate_stories_per_day", 1, 10),
        issue_stories_per_day=_int(data, "site", "issue_stories_per_day", 0, 100),
        tracker_url_threshold=_int(data, "republish_check", "tracker_url_threshold", 1, 50),
    )

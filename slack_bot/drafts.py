"""Draft edit helpers for Slack content handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass


EDIT_RE = re.compile(r"^\s*edit\s+([a-z0-9_-]+)\s*:\s*(.*)\s*$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class DraftEdit:
    """A platform-specific draft replacement from an owner reply."""

    platform: str
    content: str


def parse_draft_edit(
    reply: str | None,
    platforms: list[str],
) -> tuple[DraftEdit | None, str | None]:
    """Parse `edit platform: replacement` replies.

    Returns `(None, None)` when the reply is not an edit command, so callers can
    continue to approval parsing. Returns `(None, error)` for malformed edit
    commands that should be reported to the owner.
    """
    text = reply or ""
    match = EDIT_RE.match(text)
    if not match:
        return None, None

    platform_token = match.group(1).lower()
    platform_map = {platform.lower(): platform for platform in platforms}
    platform = platform_map.get(platform_token)
    if not platform:
        return None, f"Unknown platform for edit: {platform_token}"

    content = match.group(2).strip()
    if not content:
        return None, f"No replacement text provided for {platform}."

    return DraftEdit(platform=platform, content=content), None


def apply_draft_edit(drafts: dict[str, str], edit: DraftEdit) -> dict[str, str]:
    """Return a copy of `drafts` with one platform draft replaced."""
    updated = dict(drafts)
    if edit.platform not in updated:
        raise KeyError(f"No draft exists for platform: {edit.platform}")
    updated[edit.platform] = edit.content
    return updated

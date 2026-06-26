"""Shared approval parsing for Slack content handlers."""

import re


AFFIRMATIVE_REPLIES = frozenset({
    "all",
    "yes",
    "y",
    "go",
    "post",
    "approve",
    "approved",
    "ok",
    "ship",
    "ship it",
    "post it",
})


def parse_platform_approval(reply: str | None, platforms: list[str]) -> list[str]:
    """Return approved platforms from an owner reply.

    Approval is fail-closed: only explicit affirmative replies or replies made
    entirely of platform names approve posting. Anything else, including
    partial skip commands or pasted draft text, approves nothing.
    """
    reply_lower = (reply or "").lower().strip()
    if not reply_lower:
        return []

    if reply_lower in AFFIRMATIVE_REPLIES:
        return platforms

    tokens = [
        token for token in re.split(r"[\s,/+&]+", reply_lower)
        if token and token != "and"
    ]
    platform_map = {platform.lower(): platform for platform in platforms}
    if tokens and all(token in platform_map for token in tokens):
        return list(dict.fromkeys(platform_map[token] for token in tokens))

    return []

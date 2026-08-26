"""Draft edit helpers for Slack content handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


EDIT_RE = re.compile(r"^\s*edit\s+([a-z0-9_-]+)\s*:\s*(.*)\s*$", re.IGNORECASE | re.DOTALL)
REVISE_RE = re.compile(r"^\s*revise\s+([a-z0-9_-]+)\s*:\s*(.*)\s*$", re.IGNORECASE | re.DOTALL)

# Hard platform limits the revision writer must respect. Bluesky's is the
# posting default in social/posting.py; LinkedIn's is the REST commentary cap.
PLATFORM_CHAR_LIMITS = {"bluesky": 300, "linkedin": 3000}


@dataclass(frozen=True)
class DraftEdit:
    """A platform-specific draft replacement from an owner reply."""

    platform: str
    content: str


@dataclass(frozen=True)
class DraftRevision:
    """Owner instructions for rewriting one platform draft.

    `edit` replaces a draft with the owner's literal text; `revise` re-runs a
    writer over the current draft with the owner's notes (2026-08-18: an owner
    reply full of revision instructions would otherwise be published verbatim).
    """

    platform: str
    instructions: str


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


def parse_draft_revision(
    reply: str | None,
    platforms: list[str],
) -> tuple[DraftRevision | None, str | None]:
    """Parse `revise platform: instructions` replies.

    Same contract as parse_draft_edit: `(None, None)` when the reply is not a
    revise command, `(None, error)` when it is one but malformed.
    """
    text = reply or ""
    match = REVISE_RE.match(text)
    if not match:
        return None, None

    platform_token = match.group(1).lower()
    platform_map = {platform.lower(): platform for platform in platforms}
    platform = platform_map.get(platform_token)
    if not platform:
        return None, f"Unknown platform for revise: {platform_token}"

    instructions = match.group(2).strip()
    if not instructions:
        return None, f"No revision notes provided for {platform}."

    return DraftRevision(platform=platform, instructions=instructions), None


def _writer_skill_runner(platform: str):
    """Build the default runner for one platform's writer skill.

    `agents/{platform}-writer.md` opens by ordering the model to emit the post
    with the Write tool and to put nothing on stdout. `run_claude_prompt`
    passes `--disallowedTools ...,Write,...`, so appending that skill to a
    stdout call denies the only output channel the skill knows and returns an
    empty string. Every `revise <platform>:` reply in Slack failed that way
    with `output_len=0` until 2026-08-23; the tips handler never hit it
    because it inlines voice.md instead of appending the skill.

    So take the path `social/writers.py` already uses: same skill, same draft
    file, same tool grant. If the skill file is missing there is no file
    contract to honour, and stdout is correct.
    """

    def runner(prompt: str, system_prompt_file: str | None = None):
        from orchestrator import agents as agents_mod

        if not system_prompt_file:
            return agents_mod.run_claude_prompt(prompt, "social_revision")

        output_file = (
            agents_mod.PROJECT_ROOT
            / "data" / "social-drafts" / f"{platform.lower()}-draft.md"
        )
        result = agents_mod.run_agent_with_files(
            system_prompt_file=system_prompt_file,
            prompt=prompt,
            output_file=str(output_file),
            allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
            task_type="writer",
        )
        text = (result or {}).get("text", "")
        return (text, 0) if text.strip() else ("", 1)

    return runner


def revise_draft(
    platform: str,
    current_draft: str,
    instructions: str,
    *,
    runner=None,
) -> str:
    """Rewrite one draft with the owner's notes via the platform writer.

    `runner(prompt, system_prompt_file=...)` must return `(output, exit_code)`;
    it defaults to `_writer_skill_runner(platform)`, which runs the platform's
    writer skill over the draft file rather than over stdout. Raises
    RuntimeError when the writer fails or returns nothing, so callers can
    report instead of silently keeping the old draft.
    """
    if runner is None:
        runner = _writer_skill_runner(platform)

    limit = PLATFORM_CHAR_LIMITS.get(platform.lower())
    limit_line = (
        f"Stay under the hard limit of {limit} characters.\n" if limit else ""
    )
    from orchestrator import word_bank

    prompt = (
        f"Revise this {platform} post draft for the owner.\n\n"
        f"## Current draft\n{current_draft}\n\n"
        f"## Owner's revision notes\n{instructions}\n\n"
        "Apply every note exactly. The owner's notes override any style "
        "preference, including the word bank below. Keep everything the owner "
        "did not ask to change.\n\n"
        # The bank is here so the owner never has to type a rule it already
        # holds. On 2026-08-23 the note was "do not use the word landed",
        # which is entry one.
        f"## Word bank\n\n{word_bank.prompt_block('social')}\n"
        f"{limit_line}"
        "Emit ONLY the revised post text, through whatever output channel "
        "your writer skill specifies. No preamble, no quotes, no markdown "
        "fences, no notes about what you changed."
    )

    skill = Path(f"agents/{platform.lower()}-writer.md")
    output, exit_code = runner(
        prompt,
        system_prompt_file=str(skill) if skill.exists() else None,
    )
    revised = _strip_fences((output or "").strip())
    if exit_code != 0 or not revised:
        raise RuntimeError(
            f"Revision writer failed for {platform} "
            f"(exit={exit_code}, output_len={len(revised)})."
        )
    return revised


def _strip_fences(text: str) -> str:
    """Drop a wrapping markdown code fence if the writer added one anyway."""
    match = re.match(r"^```[a-z]*\n(.*)\n```$", text, re.DOTALL)
    return match.group(1).strip() if match else text


def handle_draft_revision(
    handler,
    reply_text: str,
    drafts: dict[str, str],
    edit_targets: list[str],
    thread_ts: str,
    *,
    format_drafts,
    policy_errors: dict | None = None,
) -> bool:
    """Process a `revise platform: notes` reply inside an approval loop.

    Returns True when the reply was a revise command (well-formed or not), so
    the caller `continue`s its loop. Mutates `drafts` in place on success.
    """
    revision, error = parse_draft_revision(reply_text, edit_targets)
    if error:
        handler.reply(error, thread_ts=thread_ts)
        return True
    if not revision:
        return False

    current = drafts.get(revision.platform, "")
    if not current:
        handler.reply(
            f"No {revision.platform} draft to revise — use "
            f"`edit {revision.platform}: your text` to supply one.",
            thread_ts=thread_ts,
        )
        return True

    handler.reply(
        f"Revising the {revision.platform} draft with your notes...",
        thread_ts=thread_ts,
    )
    try:
        drafts[revision.platform] = revise_draft(
            revision.platform, current, revision.instructions,
        )
    except Exception as e:
        handler.reply(
            f"Revision failed for {revision.platform}: {e} — the previous "
            "draft is unchanged.",
            thread_ts=thread_ts,
        )
        return True

    if policy_errors is not None:
        policy_errors[revision.platform] = []
    handler.reply(
        f"Revised {revision.platform} draft.\n\n{format_drafts(drafts)}",
        thread_ts=thread_ts,
    )
    return True


def apply_draft_edit(
    drafts: dict[str, str], edit: DraftEdit, *, allow_new: bool = False
) -> dict[str, str]:
    """Return a copy of `drafts` with one platform draft replaced.

    `allow_new` lets the owner supply a draft for a platform whose writer
    returned nothing. Without it, a failed LinkedIn draft could not be fixed
    by hand — the exact dead end hit in #mp-tips on 2026-07-24.
    """
    updated = dict(drafts)
    if edit.platform not in updated and not allow_new:
        raise KeyError(f"No draft exists for platform: {edit.platform}")
    updated[edit.platform] = edit.content
    return updated

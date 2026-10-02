"""Line edits on the finished newsletter by a second model family (Sol), applied under a fact guard.

The writer (Opus) cannot see its own habits. The editor (GPT-6.1 Sol through
Codex, per config/models.json task "newsletter_editor") returns line edits under
contracts/editor_edits.schema.json. This module applies an edit only when:

* its `find` text occurs exactly once and is not a heading,
* the replacement keeps every number, URL, link, quotation, and capitalized
  name from `find`, and adds no number or URL of its own,
* the replacement adds no em dash and no banned word-bank term.

Everything else is rejected and logged. The editor fails open: any error leaves
the writer's text as it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
from typing import Any, Callable

from core import contracts
from core.claude_cli import run_claude_process
from core.config import route_for
from core.llm import extract_json
from core.model_cli import CallRequest, call_model
from orchestrator import word_bank

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EDITOR_SYSTEM_PROMPT = PROJECT_ROOT / "agents" / "newsletter-editor.md"
TASK = "newsletter_editor"

_NUMBER = re.compile(r"[$€£]?\d[\d,.]*(?:%|x|ms|k|m|b|bn)?", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s)\]>]+")
_LINK = re.compile(r"\[[^\]\n]+\]\([^)\s]+\)")
_QUOTE = re.compile(r"\"[^\"\n]{1,400}\"|“[^”\n]{1,400}”")
_NAME = re.compile(r"\b[A-Z][a-zA-Z0-9.+-]*[A-Z0-9][a-zA-Z0-9.+-]*\b|\b[A-Z][a-z]{2,}\b")


@dataclass
class EditOutcome:
    text: str
    applied: list[dict[str, str]] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    violations_before: list[str] = field(default_factory=list)
    violations_after: list[str] = field(default_factory=list)
    skipped: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "skipped": self.skipped,
            "applied": len(self.applied),
            "rejected": len(self.rejected),
            "rejections": [r["why"] for r in self.rejected][:20],
            "violations_before": len(self.violations_before),
            "violations_after": len(self.violations_after),
        }


# Words that open sentences without naming anything. A capitalized word outside
# this list is a name wherever it sits ("Acme shipped", "Google said").
_SENTENCE_OPENERS = frozenset("""
a about after again against all also although among an and another any as at
because before besides beyond both but by despite during each either especially
even every few finally first for from further here how however if in instead it
its just last later many meanwhile more most much my next no none not now of on
once one only or other otherwise our over overall per perhaps second since so
some still such than that the their them then there these they this those though
three through thus to today two under unlike until up we what when where whether
which while who why with within without worse yet you your
""".split())


def _names(text: str) -> set[str]:
    names = set()
    for match in _NAME.finditer(text):
        word = match.group(0)
        if word.lower() in _SENTENCE_OPENERS:
            continue
        names.add(word)
    return names


def check_edit(find: str, replace: str, text: str) -> str | None:
    """Why an edit is rejected, or None when it is safe to apply."""
    count = text.count(find)
    if count != 1:
        return f"find occurs {count} times"
    start = text.index(find)
    line_start = text.rfind("\n", 0, start) + 1
    if text[line_start:start + len(find)].lstrip().startswith("#") or "\n#" in find:
        return "touches a heading"
    for label, pattern in (("number", _NUMBER), ("url", _URL), ("link", _LINK), ("quote", _QUOTE)):
        kept = set(pattern.findall(replace))
        missing = set(pattern.findall(find)) - kept
        if missing:
            return f"drops {label} {sorted(missing)[0]!r}"
        added = kept - set(pattern.findall(find))
        if added and label in ("number", "url"):
            return f"adds {label} {sorted(added)[0]!r}"
    # A capitalized word that also appears in lowercase in the issue is an
    # ordinary word opening a sentence, not a name ("Beyond that, ...").
    # URLs and link targets are left out of that search: names appear lowercase
    # in domains and paths ("example.com/acme").
    prose = _URL.sub(" ", _LINK.sub(" ", text))
    missing_names = {
        name for name in _names(find) - _names(replace) - set(_NAME.findall(replace))
        if not re.search(rf"(?<![\w./-]){re.escape(name.lower())}(?![\w-])", prose)
    }
    if missing_names:
        return f"drops name {sorted(missing_names)[0]!r}"
    if replace.count("—") > find.count("—"):
        return "adds an em dash"
    if len(replace) > len(find) * 1.5 + 40:
        return "grows the span by more than half"
    new_bans = {h.entry.term for h in word_bank.scan(replace, "newsletter") if h.entry.tier == "ban"}
    old_bans = {h.entry.term for h in word_bank.scan(find, "newsletter") if h.entry.tier == "ban"}
    if new_bans - old_bans:
        return f"adds banned term {sorted(new_bans - old_bans)[0]!r}"
    return None


def apply_edits(text: str, edits: list[dict[str, str]]) -> tuple[str, list[dict], list[dict]]:
    applied, rejected = [], []
    for edit in edits:
        find, replace = edit.get("find", ""), edit.get("replace", "")
        why = check_edit(find, replace, text)
        if why:
            rejected.append({**edit, "why": why})
            continue
        text = text.replace(find, replace, 1)
        applied.append(edit)
    return text, applied, rejected


def build_prompt(text: str, violations: list[str]) -> str:
    listed = "\n".join(f"- {v}" for v in violations) or "- none"
    return (
        "Edit this newsletter for the tells listed in your instructions.\n\n"
        "## Violations the deterministic writing policy found (fix these first)\n"
        f"{listed}\n\n"
        "## The writing policy, as the writer saw it\n"
        f"{word_bank.prompt_block('newsletter')}\n\n"
        "## Newsletter\n"
        f"{text}\n"
    )


def edit_newsletter(text: str, *, runner: Callable[..., Any] = run_claude_process) -> EditOutcome:
    """Run the editor and apply the edits that pass the guard. Never raises."""
    before = word_bank.violations(text, "newsletter")
    outcome = EditOutcome(text=text, violations_before=before, violations_after=before)
    if os.environ.get("MP_DRY_RUN") == "1":
        outcome.skipped = "dry run"
        return outcome
    try:
        route = route_for(TASK)
        if not route.enabled:
            outcome.skipped = "disabled in config/models.json"
            return outcome
        result = call_model(
            CallRequest(task=TASK, prompt=build_prompt(text, before), system_prompt_file=EDITOR_SYSTEM_PROMPT,
                        unit="newsletter", cwd=PROJECT_ROOT, output_schema=contracts.path("editor_edits")),
            route=route, runner=runner,
        )
        if not result.ok:
            outcome.skipped = f"editor call {result.outcome}"
            return outcome
        payload = extract_json(result.text)
        problems = contracts.check("editor_edits", payload)
        if problems:
            outcome.skipped = f"contract: {problems[0]}"
            return outcome
        edited, applied, rejected = apply_edits(text, payload["edits"])
    except Exception as exc:  # the editor must never cost the day's issue
        logger.warning("newsletter editor failed open: %s", exc)
        outcome.skipped = f"error: {exc}"
        return outcome
    outcome.text = edited
    outcome.applied, outcome.rejected = applied, rejected
    outcome.violations_after = word_bank.violations(edited, "newsletter")
    return outcome

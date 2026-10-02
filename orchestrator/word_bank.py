"""Shared word bank for every surface that publishes prose.

Before this module the project kept four ban lists that had drifted apart:

* ``data/ramsay/mindpattern/voice.md`` reached the social writers as prompt text
  and was never checked.
* ``policies/social.json`` checked eleven marketing words on social posts.
* ``orchestrator/site_copy_lint.py`` checked forty words on site stories.
* ``orchestrator/prose_gate.py`` checked em-dashes on the newsletter and nothing
  lexical at all.

So the newsletter used "landed" 27 times across 9 of the 10 August issues and
no gate saw it. The bank fixes the drift by holding every term once, tagging it
with the surfaces it applies to, and rendering the prompt text from the same
rows the gate reads. A ban the writer was never told about is a bug, and
``prompt_block()`` is what keeps that from happening.

Two tiers:

* ``ban`` the term never appears. A regex catches it.
* ``cap`` the term is legitimate but was overused. The ceiling is a rate per
  10,000 words, set at roughly half the measured August rate, so one use in a
  short post is always fine and a habit is not.

Counts in the ``note`` fields were measured over ``reports/ramsay/2026-08-14``
through ``2026-08-23``, 92,096 words of prose with headings, source lines and
the feedback footer stripped.

@know: [[orchestrator/runner#Synthesis]]
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import json
from pathlib import Path
import re

SURFACES = ("newsletter", "social", "engagement", "site")
ALL = SURFACES

VOICE_SECTION_MARKER = "## Word bank (generated, do not hand-edit)"

# Spans whose contents are never our prose: fenced code, inline code, markdown
# link and image targets, bare URLs, and anything inside straight double quotes.
# The quote rule matters most. We police the sentences we write, not the words a
# source used, and the newsletter quotes release notes constantly.
_PROTECTED = re.compile(
    r"```.*?```"
    r"|`[^`\n]*`"
    r"|\[[^\]\n]*\]\([^)\s]*\)"
    r"|<https?://[^>\s]+>"
    r"|https?://\S+"
    r"|\"[^\"\n]{0,400}\""
    r"|“[^”\n]{0,400}”",
    re.DOTALL,
)


@dataclass(frozen=True)
class Entry:
    """One banned or capped term."""

    term: str
    tier: str            # "ban" or "cap"
    pattern: str         # regex source, always compiled case-insensitive
    instead: str         # what to write in its place
    example: str         # a real sentence the pattern must match
    surfaces: tuple[str, ...] = ALL
    family: str = ""
    note: str = ""
    cap_per_10k: float = 0.0
    # How hard the site copy lint should push back. A word the writer must
    # never type is worth rejecting the draft over. A sentence shape is not:
    # rejecting costs a full regeneration, and the critic can fix a frame in
    # place, so frames come back as revision notes instead.
    site_severity: str = "fail"
    # Provenance for rules added from measurement: which models show the tell,
    # when it was measured, when to re-measure, and a sentence it must not match.
    models: tuple[str, ...] = ()
    measured: str = ""
    review_by: str = ""
    counterexample: str = ""


@dataclass(frozen=True)
class Hit:
    entry: Entry
    count: int
    examples: tuple[str, ...] = field(default=())


# ── The bank ────────────────────────────────────────────────────────────────
#
# The rows live in policies/writing.json, so a rule changes by editing a file.
# Family names describe the rhetorical move, because the move is what reads as
# machine-written. Banning one word from a family and leaving its four siblings
# just moves the tic.

POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "writing.json"
_ENTRY_KEYS = {f.name for f in fields(Entry)}


class WritingPolicyError(ValueError):
    """policies/writing.json is malformed or a rule fails its own example."""


def load_bank(path: Path = POLICY_PATH) -> tuple[Entry, ...]:
    """Read and check every lexicon row. A rule that misses its own example fails here."""
    try:
        policy = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise WritingPolicyError(f"cannot read {path}: {exc}") from exc
    entries = []
    for index, raw in enumerate(policy.get("lexicon") or []):
        where = f"{path.name} lexicon[{index}] {raw.get('term', '?')!r}"
        unknown = set(raw) - _ENTRY_KEYS
        if unknown:
            raise WritingPolicyError(f"{where}: unknown keys {sorted(unknown)}")
        try:
            entry = Entry(**{**raw, "surfaces": tuple(raw.get("surfaces", ALL)),
                             "models": tuple(raw.get("models", ()))})
        except TypeError as exc:
            raise WritingPolicyError(f"{where}: {exc}") from exc
        if entry.tier not in ("ban", "cap"):
            raise WritingPolicyError(f"{where}: tier must be ban or cap")
        if entry.tier == "cap" and entry.cap_per_10k <= 0:
            raise WritingPolicyError(f"{where}: a cap needs cap_per_10k above zero")
        if not set(entry.surfaces) <= set(SURFACES):
            raise WritingPolicyError(f"{where}: unknown surfaces {sorted(set(entry.surfaces) - set(SURFACES))}")
        try:
            pattern = re.compile(entry.pattern, re.IGNORECASE)
        except re.error as exc:
            raise WritingPolicyError(f"{where}: pattern does not compile: {exc}") from exc
        if not pattern.search(entry.example):
            raise WritingPolicyError(f"{where}: pattern misses its own example")
        if entry.counterexample and pattern.search(entry.counterexample):
            raise WritingPolicyError(f"{where}: pattern matches its counterexample")
        entries.append(entry)
    return tuple(entries)


def budgets(path: Path = POLICY_PATH) -> dict[str, float]:
    return dict(json.loads(path.read_text()).get("budgets") or {})


BANK: tuple[Entry, ...] = load_bank()


# ── Reading ────────────────────────────────────────────────────────────────


def entries_for(surface: str) -> list[Entry]:
    """Every entry that applies to one surface."""
    return [e for e in BANK if surface in e.surfaces]


def _unprotected(text: str) -> str:
    """Text with code, links, URLs and quotations blanked out.

    Spans become spaces of the same length so offsets stay usable and no two
    words are accidentally joined across a removed span.
    """
    out = list(text)
    for match in _PROTECTED.finditer(text):
        for i in range(match.start(), match.end()):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def _sentence_around(text: str, index: int) -> str:
    """The sentence holding ``index``, whitespace collapsed."""
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index)) + 1
    end = text.find(".", index)
    end = len(text) if end == -1 else end + 1
    return " ".join(text[start:end].split())


def scan(text: str, surface: str) -> list[Hit]:
    """Count every bank term present in one surface's prose.

    Counts only unprotected prose, so a term inside code, a link, a URL or a
    quotation is not a hit.
    """
    prose = _unprotected(text)
    hits: list[Hit] = []
    for entry in entries_for(surface):
        matches = list(re.finditer(entry.pattern, prose, re.IGNORECASE))
        if not matches:
            continue
        # Excerpt from the masked text, not the original: a bare URL blanked
        # for matching still carries dots, and pulling from the raw string put
        # half a changelog slug in front of every log line.
        examples = tuple(
            _sentence_around(prose, m.start()) for m in matches[:3]
        )
        hits.append(Hit(entry=entry, count=len(matches), examples=examples))
    return hits


def violations(text: str, surface: str) -> list[str]:
    """Human-readable failures. Empty list means the copy passes.

    A ``ban`` fails on the first hit. A ``cap`` fails only when the rate clears
    its ceiling, and never on a single use, so a 40-word post is never rejected
    for a limit expressed per 10,000 words.
    """
    words = max(len(text.split()), 1)
    out: list[str] = []
    for hit in scan(text, surface):
        entry = hit.entry
        if entry.tier == "ban":
            out.append(
                f"banned: \"{entry.term}\" x{hit.count} "
                f"({hit.examples[0] if hit.examples else ''}) "
                f"-> {entry.instead}"
            )
            continue
        allowed = max(1, int(entry.cap_per_10k * words / 10_000))
        if hit.count > allowed:
            rate = hit.count * 10_000 / words
            out.append(
                f"over cap: \"{entry.term}\" x{hit.count} in {words} words "
                f"({rate:.1f} per 10k, ceiling {entry.cap_per_10k:.0f}) "
                f"-> {entry.instead}"
            )
    return out


# ── Writing the prompt ──────────────────────────────────────────────────────


def prompt_block(surface: str) -> str:
    """Render the bank as prompt text for one surface.

    Every gate the writers face is stated here first. Rendering both from the
    same rows is the point: a term can never be enforced by a check the prompt
    did not mention.
    """
    entries = entries_for(surface)
    if not entries:
        return ""

    families: dict[str, list[Entry]] = {}
    for entry in entries:
        families.setdefault(entry.family or "other", []).append(entry)

    lines = [
        "### Never write these",
        "",
        "Measured across the last ten published issues. Each line gives the "
        "replacement, because a ban with no replacement makes prose worse.",
        "",
    ]
    for family, rows in families.items():
        lines.append(f"**{family.capitalize()}.**")
        for entry in rows:
            lines.append(f"- \"{entry.term}\". {_rule(entry)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _cap_label(cap: float) -> str:
    """A cap reads as a count, so never round it down to zero."""
    return f"{cap:g}" if cap < 2 else f"{cap:.0f}"


def _rule(entry: Entry) -> str:
    """One line of guidance: the limit, then the replacement."""
    instead = entry.instead[0].upper() + entry.instead[1:] if entry.instead else ""
    if entry.tier == "ban":
        return f"Never. Write instead: {instead}"
    return (
        f"At most {_cap_label(entry.cap_per_10k)} per 10,000 words, so at most "
        f"once in a short post. {instead}"
    )


def voice_section() -> str:
    """The block written into voice.md, marker included.

    One deduped list, not one per surface. voice.md is the human-facing
    reference and gets read end to end; the per-surface detail is injected into
    each writer's prompt by ``prompt_block`` at run time.
    """
    parts = [
        VOICE_SECTION_MARKER,
        "",
        "Rendered from `policies/writing.json`. Edit the file, then run",
        "`python3 -m orchestrator.word_bank --write-voice`. These rows also run as a",
        "deterministic gate on the newsletter, social posts, engagement replies and",
        "site stories, so everything here is measured, not just requested.",
        "",
        "Counts come from the ten issues published 2026-08-14 through 2026-08-23.",
        "",
    ]

    families: dict[str, list[Entry]] = {}
    for entry in BANK:
        families.setdefault(entry.family or "other", []).append(entry)

    for family, rows in families.items():
        parts.append(f"### {family.capitalize()}")
        parts.append("")
        for entry in rows:
            scope = (
                "" if set(entry.surfaces) == set(SURFACES)
                else f" ({', '.join(entry.surfaces)} only)"
            )
            parts.append(f"- **{entry.term}**{scope}. {_rule(entry)}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _write_voice() -> None:
    """Replace the generated section in voice.md, leaving the hand-written rest."""
    path = Path(__file__).resolve().parent.parent / "data" / "ramsay" / \
        "mindpattern" / "voice.md"
    text = path.read_text()
    section = voice_section()

    if VOICE_SECTION_MARKER in text:
        head, _, tail = text.partition(VOICE_SECTION_MARKER)
        # The generated section runs to the next H2 or to end of file.
        rest = re.split(r"\n(?=## )", tail, maxsplit=1)
        remainder = "\n" + rest[1] if len(rest) > 1 else ""
        path.write_text(head + section + remainder)
    else:
        path.write_text(text.rstrip() + "\n\n" + section)
    print(f"wrote word bank section to {path}")


if __name__ == "__main__":
    import sys

    if "--write-voice" in sys.argv:
        _write_voice()
    else:
        for _surface in SURFACES:
            print(f"===== {_surface} =====")
            print(prompt_block(_surface))

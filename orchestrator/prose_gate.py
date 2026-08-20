"""Deterministic prose gate for the newsletter.

Style rules a regex can enforce are enforced here, not asked for in the prompt.

Prompt-only enforcement of a mechanical rule is stochastic. On 2026-07-25, -26
and -27 the same model (claude-opus-5[1m]), the same synthesis prompt and the
same voice.md produced 42, 2 and 52 em-dashes. The voice guide was loaded into
the prompt on all three days. Asking harder does not close that gap; a check at
the choke point does.

The split this module assumes:

* Things code can detect — banned characters, counts, banned phrases. Do not
  ask the model. Sanitize or regenerate.
* Things that need taste — tone, register, whether a sentence earns its length.
  Those stay in the prompt and in a critic, not here.

Scope: this module only does the first kind. It never calls an LLM.

@know: [[orchestrator/runner#Synthesis]]
"""

import logging
import re

logger = logging.getLogger(__name__)

EM_DASH = "—"

# Baseline measured from reports/ramsay/2026-07-17..24 (pre-Opus-5 issues):
# 2 to 4 em-dashes per issue at 6,200-9,000 words. Generic tools are far looser
# — deslop defaults to 14 per 500 words, which today's 2.3 per 500 would pass
# while still reading as machine prose. Calibrate to the corpus, not to a tool.
EM_DASH_BUDGET = 6

# Spans whose contents are never rewritten: fenced code, inline code, markdown
# link/image targets, and bare URLs. An em-dash inside any of these is data.
_PROTECTED = re.compile(
    r"```.*?```"           # fenced code block
    r"|`[^`\n]*`"          # inline code
    r"|\]\([^)\s]*\)"      # markdown link/image target
    r"|<https?://[^>\s]+>" # autolink
    r"|https?://\S+",      # bare URL
    re.DOTALL,
)

# Capturing group: re.split keeps the separators, so rejoining reproduces the
# original whitespace byte for byte. The newsletter is published verbatim, so
# this module must never normalize spacing as a side effect.
_SENTENCE_SPLIT = re.compile(r"((?<=[.!?])\s+)")

# Headings are exempt. The H1 is built by runner.py as
# "# {title} — {date}", where the em-dash is our own formatting rather than
# model output, and section headings are structure rather than prose.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")

# Fenced blocks are tracked line by line rather than by the span regex: both
# scan() and sanitize() walk lines to preserve layout, so a ```...``` span is
# never visible to a single-line match.
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")


def _prose_lines(markdown: str) -> list[str]:
    """Lines that carry prose: no headings, nothing inside a fenced block."""
    out: list[str] = []
    in_fence = False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or _HEADING.match(line):
            continue
        out.append(line)
    return out


def _replace_in_sentence(sentence: str) -> tuple[str, int]:
    """Rewrite em-dashes in one sentence. Returns (sentence, replacements).

    Two em-dashes read as a parenthetical aside, so they become commas. One
    reads as an appositive expansion ("X — which means Y"), so it becomes a
    colon, which keeps the clause attached and grammatical. Three or more is
    past the point where a mechanical rewrite is safe: those are counted and
    left for the critic rather than mangled.
    """
    count = sentence.count(EM_DASH)
    if count == 0:
        return sentence, 0

    if count == 2:
        # Parenthetical: "the fix — three lines — landed" -> commas.
        return re.sub(r"\s*" + EM_DASH + r"\s*", ", ", sentence), 2

    if count == 1:
        # Appositive expansion. A sentence that already carries a colon gets a
        # semicolon instead, so we never emit two colons in one sentence.
        replacement = "; " if ":" in sentence else ": "
        return re.sub(r"\s*" + EM_DASH + r"\s*", replacement, sentence, count=1), 1

    return sentence, 0


def _sanitize_unprotected(text: str) -> tuple[str, int]:
    """Rewrite each sentence, preserving the whitespace between them exactly."""
    parts = _SENTENCE_SPLIT.split(text)
    replaced = 0
    # With a capturing split, odd indices are the separators — leave them alone.
    for i in range(0, len(parts), 2):
        new, n = _replace_in_sentence(parts[i])
        parts[i] = new
        replaced += n
    return "".join(parts), replaced


def _split_protected(markdown: str) -> list[tuple[str, bool]]:
    """Split into (chunk, is_protected) segments preserving order."""
    segments: list[tuple[str, bool]] = []
    pos = 0
    for m in _PROTECTED.finditer(markdown):
        if m.start() > pos:
            segments.append((markdown[pos:m.start()], False))
        segments.append((m.group(0), True))
        pos = m.end()
    if pos < len(markdown):
        segments.append((markdown[pos:], False))
    return segments


# Self-referential length claims: "the next 4,000 words", "these 900 words".
# The model cannot know its own final length while writing, so the number is
# invented — 2026-08-04 promised "the next 4,000 words" above an 8,100-word
# issue, and the site surfaces that lede as the homepage preview. Same rule as
# the em-dash budget: a fact a regex can check is corrected here, not asked for
# in the prompt.
_LENGTH_CLAIM = re.compile(
    r"(?P<lead>\b(?:next|these|this|following|remaining)\s+)"
    r"(?P<count>\d{1,3}(?:,\d{3})+|\d{3,6})"
    r"(?P<tail>[\s-]+words?\b)",
    re.IGNORECASE,
)


def _round_words(count: int) -> str:
    """Round to the nearest 500 so the claim reads as prose, not telemetry."""
    if count < 500:
        return str(max(count, 0))
    return f"{int(round(count / 500.0) * 500):,}"


def correct_length_claims(markdown: str) -> tuple[str, int]:
    """Rewrite self-referential word-count claims to the real length.

    Returns (corrected_markdown, number_of_claims_rewritten). Only claims that
    point at this document ("the next N words") are touched; a story quoting
    someone else's "4,000 words" has no such lead-in and is left alone.
    """
    actual = _round_words(len(markdown.split()))
    corrected = 0

    def _fix(match: re.Match) -> str:
        nonlocal corrected
        if match.group("count").replace(",", "") == actual.replace(",", ""):
            return match.group(0)
        corrected += 1
        return f"{match.group('lead')}{actual}{match.group('tail')}"

    return _LENGTH_CLAIM.sub(_fix, markdown), corrected


def scan(markdown: str) -> dict:
    """Measure prose markers without changing anything.

    Counts only em-dashes in prose — ones inside code, links and URLs are data
    and are excluded, so the number matches what a reader actually sees.
    """
    body = "\n".join(_prose_lines(markdown))
    prose = "".join(c for c, protected in _split_protected(body) if not protected)
    words = len(markdown.split())
    em = prose.count(EM_DASH)
    return {
        "words": words,
        "em_dashes": em,
        "em_dashes_per_500w": round(em * 500 / words, 2) if words else 0.0,
        "over_budget": em > EM_DASH_BUDGET,
        "budget": EM_DASH_BUDGET,
    }


def sanitize(markdown: str) -> tuple[str, dict]:
    """Strip em-dashes from prose. Returns (clean_markdown, report).

    Line structure is preserved: rewriting happens per line, so markdown that
    depends on layout (headings, list items, tables, blank lines) is unchanged.
    Code blocks, inline code, link targets and URLs are never touched.
    """
    before = scan(markdown)

    out_lines: list[str] = []
    replaced = 0
    in_fence = False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence or _HEADING.match(line):
            out_lines.append(line)
            continue
        rebuilt: list[str] = []
        for chunk, protected in _split_protected(line):
            if protected:
                rebuilt.append(chunk)
                continue
            new, n = _sanitize_unprotected(chunk)
            rebuilt.append(new)
            replaced += n
        out_lines.append("".join(rebuilt))

    clean = "\n".join(out_lines)
    clean, length_claims = correct_length_claims(clean)
    after = scan(clean)

    report = {
        "words": before["words"],
        "em_dashes_before": before["em_dashes"],
        "em_dashes_after": after["em_dashes"],
        "replaced": replaced,
        "length_claims_corrected": length_claims,
        "remaining_over_budget": after["em_dashes"] > EM_DASH_BUDGET,
        "budget": EM_DASH_BUDGET,
        "per_500w_before": before["em_dashes_per_500w"],
    }

    if replaced:
        logger.info(
            "Prose gate: replaced %d em-dash(es) in %d words (%.2f per 500w before)",
            replaced, report["words"], report["per_500w_before"],
        )
    if report["remaining_over_budget"]:
        # 3+ in one sentence is deliberately left alone; if enough of those
        # survive to clear the budget, the drift is stylistic, not typographic,
        # and wants the critic rather than another regex.
        logger.warning(
            "Prose gate: %d em-dash(es) remain after sanitizing (budget %d) — "
            "sentences with 3+ are left intact for review",
            report["em_dashes_after"], EM_DASH_BUDGET,
        )

    return clean, report

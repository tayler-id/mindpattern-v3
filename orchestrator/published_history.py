"""Story history from published newsletter issues, for selection-time dedup.

Every other dedup layer in the pipeline (preflight annotation, the sim>0.90
storage gate, cross-agent dedup, duplicate_story_risk) compares research
*findings*. None of them ever looks at what past *issues* published, which is
how the 2026-08-17 audit found 26 stories re-reported as new across 20 issues
while every gate scored green. This module reads the published reports
themselves and gives story selection a memory of them.

Deterministic Python only — no LLM, no embeddings — so the hard check works in
tests and keeps working when the model misbehaves. Similarity uses the same
light-stemmed significant-word Jaccard as duplicate_story_risk so the two
checks agree on what "the same story" means.
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from .evaluator import _jaccard, _story_words

logger = logging.getLogger(__name__)

# Calibrated 2026-08-17 on real duplicate pairs from the 20-issue audit:
# reworded repeats of the same story score 0.50-0.75 on stemmed-word Jaccard,
# while distinct stories about the same product score at most ~0.17. 0.45
# sits in that gap. Fully re-vocabularized repeats score below it and are the
# job of the prompt-side skip-list, which shows the selector the real titles.
REPUBLISH_SIMILARITY = 0.45

_TOP_STORY_RE = re.compile(r"^###\s*\d+\.\s*(.+?)\s*$")
_SECTION_ITEM_RE = re.compile(r"^\*\*(.+?)\*\*")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_DATE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")

# Recurring-by-design sections whose entries repeat legitimately.
_SKIP_SECTIONS = {
    "skills of the day",
    "how this newsletter learns from you",
}


def published_stories(
    report_dir: Path,
    date_str: str,
    days: int = 14,
) -> list[dict]:
    """Extract story headlines from issues published in the days before date_str.

    Reads ``{report_dir}/{YYYY-MM-DD}.md`` files inside the window
    ``[date_str - days, date_str)``. Returns one dict per story:
    ``{"date", "title", "kind"}`` where kind is "top" (a ``### N.`` headline)
    or "item" (a section entry's bold lead sentence). Files that fail to parse
    are skipped with a warning — history is best-effort, never fatal.
    """
    try:
        end = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logger.warning(f"published_stories: bad date_str {date_str!r}")
        return []
    start = end - timedelta(days=days)

    stories: list[dict] = []
    if not report_dir.is_dir():
        return stories

    for path in sorted(report_dir.iterdir()):
        m = _DATE_FILE_RE.match(path.name)
        if not m:
            continue
        try:
            file_date = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if not (start <= file_date < end):
            continue
        try:
            stories.extend(_extract_stories(path.read_text(), m.group(1)))
        except Exception as e:
            logger.warning(f"published_stories: failed to parse {path.name}: {e}")

    return stories


def _extract_stories(markdown: str, date: str) -> list[dict]:
    stories = []
    section = ""
    for line in markdown.splitlines():
        h2 = _H2_RE.match(line)
        if h2:
            section = h2.group(1).strip().lower()
            continue
        if section in _SKIP_SECTIONS:
            continue
        top = _TOP_STORY_RE.match(line)
        if top:
            stories.append({"date": date, "title": top.group(1), "kind": "top"})
            continue
        item = _SECTION_ITEM_RE.match(line)
        if item:
            stories.append({"date": date, "title": item.group(1), "kind": "item"})
    return stories


def format_published_block(stories: list[dict], max_items: int = 500) -> str:
    """Render the skip-list block for the story-selection prompt.

    Returns "" when there is no history, so the prompt gains nothing on the
    first run or after an archive wipe.
    """
    if not stories:
        return ""
    shown = stories[-max_items:]
    lines = [f"- ({s['date']}) {s['title']}" for s in shown]
    return (
        "## Already Published (do not re-select)\n"
        "Every story below already ran in a recent issue. Selecting one again "
        "is only allowed when today's finding contains a genuinely NEW "
        "development (new data, new release, new disclosure) — and then your "
        "\"reason\" field must name that new development and the date it "
        "previously ran. Re-reporting the same event with new wording is "
        "forbidden.\n\n" + "\n".join(lines)
    )


def flag_republished(
    selected_titles: list[str],
    stories: list[dict],
    threshold: float = REPUBLISH_SIMILARITY,
) -> list[dict]:
    """Deterministic tripwire: which selected stories repeat a published one?

    Compares light-stemmed significant-word sets (same method and bar as the
    quality floor's near-title check). Returns one dict per flagged selection
    with the best-matching published story attached.
    """
    published_words = [
        (s, set(_story_words(s["title"]))) for s in stories
    ]
    flagged = []
    for title in selected_titles:
        words = set(_story_words(title))
        best_sim = 0.0
        best_story = None
        for story, story_words in published_words:
            sim = _jaccard(words, story_words)
            if sim > best_sim:
                best_sim = sim
                best_story = story
        if best_story is not None and best_sim >= threshold:
            flagged.append({
                "selected_title": title,
                "published_title": best_story["title"],
                "published_date": best_story["date"],
                "similarity": round(best_sim, 3),
            })
    return flagged

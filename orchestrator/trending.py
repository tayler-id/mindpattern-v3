"""Trending and popularity scoring for the public wire.

Pure math over event rows + corpus signals so it's trivially testable.
score = W_ONSITE * normalized(onsite) + W_CORPUS * normalized(corpus)

onsite: time-decayed weighted events (Hacker News style gravity).
corpus: the research pipeline as an internet-trending sensor — source
recurrence, arc membership, and log of HN points / GitHub stars found in
the primary finding text. A story nobody on the site has read yet can
still trend because the internet is talking about its sources.
"""

from __future__ import annotations

import math
import os
import re
import time
from typing import Any, Iterable

EVENT_WEIGHTS = {
    "story_view": 1.0,
    "related_click": 2.0,
    "entity_click": 1.0,
    "source_click": 1.0,
    "outbound_source_click": 3.0,
    "scroll_depth": 0.02,  # per depth point; 100-depth ≈ 2.0
}
GRAVITY = float(os.environ.get("MP_TRENDING_GRAVITY", "1.4"))
W_ONSITE = float(os.environ.get("MP_TRENDING_W_ONSITE", "0.7"))
W_CORPUS = float(os.environ.get("MP_TRENDING_W_CORPUS", "0.3"))
FLAT_BAND = 0.15

_NUMBER_SIGNAL_RE = re.compile(
    r"(\d[\d,]{2,})\s*(?:points|stars|upvotes)", re.IGNORECASE
)


def onsite_score(events: Iterable[dict[str, Any]], *, now: float | None = None) -> float:
    """Time-decayed weighted sum. events: {type, ts, value}."""
    now = now or time.time()
    score = 0.0
    for event in events:
        weight = EVENT_WEIGHTS.get(str(event.get("type")), 0.0)
        if not weight:
            continue
        if event.get("type") == "scroll_depth":
            weight *= float(event.get("value") or 0)
        age_hours = max(0.0, (now - float(event.get("ts") or now)) / 3600.0)
        score += weight / (age_hours + 2.0) ** GRAVITY
    return score


def corpus_score(story: dict[str, Any], *, domain_recurrence: dict[str, int]) -> float:
    """Internet-side signal from the research corpus itself."""
    score = 0.0
    for domain in story.get("graph_connectors", {}).get("source_domains", []):
        score += min(domain_recurrence.get(str(domain), 0), 20) * 0.3
    score += 2.0 * len(story.get("arc_ids") or [])
    text = f"{story.get('title', '')} {story.get('summary', '')}"
    for match in _NUMBER_SIGNAL_RE.finditer(text):
        try:
            score += math.log10(max(int(match.group(1).replace(",", "")), 10))
        except ValueError:
            continue
    return score


def _normalize(values: dict[str, float]) -> dict[str, float]:
    top = max(values.values(), default=0.0)
    if top <= 0:
        return {key: 0.0 for key in values}
    return {key: value / top for key, value in values.items()}


def blend_scores(
    onsite: dict[str, float],
    corpus: dict[str, float],
) -> dict[str, float]:
    slugs = set(onsite) | set(corpus)
    n_onsite = _normalize({s: onsite.get(s, 0.0) for s in slugs})
    n_corpus = _normalize({s: corpus.get(s, 0.0) for s in slugs})
    return {
        slug: W_ONSITE * n_onsite[slug] + W_CORPUS * n_corpus[slug]
        for slug in slugs
    }


def trend_direction(score_now: float, score_prior: float) -> str:
    if score_prior <= 0 and score_now <= 0:
        return "flat"
    if score_prior <= 0:
        return "up"
    ratio = score_now / score_prior
    if ratio > 1 + FLAT_BAND:
        return "up"
    if ratio < 1 - FLAT_BAND:
        return "down"
    return "flat"

# preflight/run_all.py
"""Orchestrate all preflight sources, dedup-annotate, assign to agents."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import make_entry

logger = logging.getLogger(__name__)

# Agent assignment routing table
SOURCE_ROUTING = {
    "arxiv": ("arxiv-researcher", ["agents-researcher"]),
    "github": ("github-pulse-researcher", ["projects-researcher", "vibe-coding-researcher"]),
    "hn": ("hn-researcher", ["news-researcher"]),
    "reddit": ("reddit-researcher", ["vibe-coding-researcher"]),
    "twitter": ("thought-leaders-researcher", ["news-researcher"]),
    "youtube": ("sources-researcher", ["vibe-coding-researcher"]),
    "exa": (None, []),  # Distributed by topic
}

RSS_ROUTING = {
    "saas": ["Tomasz Tunguz", "SaaStr", "Bessemer", "Crunchbase", "Stripe", "Plaid",
             "a16z", "Sequoia", "Y Combinator", "First Round"],
    "sources": ["Simon Willison", "Latent Space", "The Batch", "Import AI",
                "Nathan Lambert", "Ahead of AI", "Ben's Bites"],
}


DEDUP_SIMILARITY_THRESHOLD = 0.85
DEDUP_LOOKBACK_DAYS = 7


def _dedup_annotate(
    items: list[dict],
    existing_fn=None,
    threshold: float = DEDUP_SIMILARITY_THRESHOLD,
    db=None,
) -> list[dict]:
    """Tag each item as NEW or ALREADY_COVERED via batch embedding comparison.

    Uses batch vectorized approach when db is available, falls back to
    per-item existing_fn when db is None.
    """
    if not items:
        return items

    # Prefer batch approach when db is available
    if db is not None:
        try:
            return _dedup_batch(items, db, threshold)
        except Exception as e:
            logger.warning(f"Batch dedup failed, falling back to per-item: {e}")

    # Fallback: per-item dedup via existing_fn
    if existing_fn is None:
        return items

    for item in items:
        query = f"{item['title']}. {item.get('content_preview', '')}"
        try:
            matches = existing_fn(query)
            if matches and matches[0].get("similarity", 0) >= threshold:
                best = matches[0]
                item["already_covered"] = True
                item["match_info"] = {
                    "matched_finding": best.get("title", ""),
                    "matched_date": best.get("date", ""),
                    "matched_agent": best.get("agent", ""),
                    "similarity": round(best["similarity"], 3),
                }
        except Exception as e:
            logger.debug(f"Dedup check failed for '{item['title'][:50]}': {e}")

    return items


def _dedup_batch(items: list[dict], db, threshold: float) -> list[dict]:
    """Batch dedup: embed all items at once, compare against stored findings vectorized."""
    import numpy as np
    from memory.embeddings import embed_texts, deserialize_f32
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=DEDUP_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    rows = db.execute(
        """SELECT f.title, f.agent, f.run_date, e.embedding
           FROM findings f
           JOIN findings_embeddings e ON e.finding_id = f.id
           WHERE f.run_date >= ?""",
        (cutoff,),
    ).fetchall()

    if not rows:
        return items

    stored_titles = [r["title"] for r in rows]
    stored_agents = [r["agent"] for r in rows]
    stored_dates = [r["run_date"] for r in rows]
    stored_matrix = np.array([deserialize_f32(r["embedding"]) for r in rows], dtype=np.float32)

    texts = [f"{item['title']}. {item.get('content_preview', '')[:200]}" for item in items]
    item_vecs = np.array(embed_texts(texts), dtype=np.float32)

    sim_matrix = item_vecs @ stored_matrix.T

    for i, item in enumerate(items):
        max_idx = int(np.argmax(sim_matrix[i]))
        max_sim = float(sim_matrix[i, max_idx])
        if max_sim >= threshold:
            item["already_covered"] = True
            item["match_info"] = {
                "matched_finding": stored_titles[max_idx],
                "matched_date": stored_dates[max_idx],
                "matched_agent": stored_agents[max_idx],
                "similarity": round(max_sim, 3),
            }

    return items


def _assign_rss_item(item: dict) -> tuple[str, list[str]]:
    """Route an RSS item to the right agent(s) based on source name."""
    name = item.get("source_name", "").lower()

    for agent_key, patterns in RSS_ROUTING.items():
        for pattern in patterns:
            if pattern.lower() in name:
                if agent_key == "saas":
                    return "saas-disruption-researcher", ["news-researcher"]
                elif agent_key == "sources":
                    return "sources-researcher", ["rss-researcher"]

    return "rss-researcher", ["news-researcher"]


def _assign_to_agents(items: list[dict]) -> dict[str, list[dict]]:
    """Route preflight items to agents by source and topic."""
    assignments: dict[str, list[dict]] = {}

    for item in items:
        source = item.get("source", "")

        if source == "rss":
            primary, secondaries = _assign_rss_item(item)
        elif source == "exa":
            primary = "news-researcher"
            secondaries = []
            search_text = item.get("title", "").lower() + " " + item.get("content_preview", "").lower()
            if any(kw in search_text for kw in ["saas", "fintech", "startup", "venture"]):
                secondaries.append("saas-disruption-researcher")
            if any(kw in search_text for kw in ["agent", "mcp", "tool use"]):
                secondaries.append("agents-researcher")
            if any(kw in search_text for kw in ["vibe", "cursor", "copilot", "coding"]):
                secondaries.append("vibe-coding-researcher")
        else:
            route = SOURCE_ROUTING.get(source, (None, []))
            primary, secondaries = route[0], route[1]

        if primary:
            assignments.setdefault(primary, []).append(item)
        for sec in secondaries:
            assignments.setdefault(sec, []).append(item)

    return assignments


def run_all(
    date_str: str,
    db=None,
    feeds_file: Path | None = None,
) -> dict:
    """Run all preflight sources in parallel, dedup-annotate, assign to agents.

    Returns dict with items, assignments, counts, and timing.
    """
    from . import PROJECT_ROOT
    start = time.monotonic()

    if feeds_file is None:
        feeds_file = PROJECT_ROOT / "verticals" / "ai-tech" / "rss-feeds.json"

    from . import rss, arxiv, github, hn, reddit, twitter, exa, youtube

    tasks = {
        "rss": lambda: rss.fetch(feeds_file=feeds_file),
        "arxiv": lambda: arxiv.fetch(),
        "github": lambda: github.fetch(),
        "hn": lambda: hn.fetch(),
        "reddit": lambda: reddit.fetch(),
        "twitter": lambda: twitter.fetch(),
        "exa": lambda: exa.fetch(),
        "youtube": lambda: youtube.fetch(),
    }

    all_items: list[dict] = []
    source_counts: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}

        for future in as_completed(futures):
            source_name = futures[future]
            try:
                items = future.result()
                all_items.extend(items)
                source_counts[source_name] = len(items)
                logger.info(f"Preflight {source_name}: {len(items)} items")
            except Exception as e:
                logger.error(f"Preflight {source_name} failed: {e}")
                source_counts[source_name] = 0

    logger.info(f"Preflight total: {len(all_items)} raw items from {len(source_counts)} sources")

    # Dedup-annotate against recent findings (batch-vectorized when db available)
    all_items = _dedup_annotate(all_items, db=db, threshold=0.85)

    new_items = [i for i in all_items if not i["already_covered"]]
    covered_items = [i for i in all_items if i["already_covered"]]

    assignments = _assign_to_agents(all_items)

    duration_ms = int((time.monotonic() - start) * 1000)

    logger.info(
        f"Preflight complete: {len(all_items)} total, {len(new_items)} new, "
        f"{len(covered_items)} already covered, {duration_ms}ms"
    )

    return {
        "items": all_items,
        "assignments": assignments,
        "already_covered": covered_items,
        "total_items": len(all_items),
        "new_count": len(new_items),
        "covered_count": len(covered_items),
        "source_counts": source_counts,
        "duration_ms": duration_ms,
    }

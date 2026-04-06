"""Deterministic trend detection from preflight data.

Replaces the old Haiku-based trend scanner. Clusters preflight items by
topic similarity, scores by engagement and source diversity. No LLM required.

Usage:
    from preflight.trends import detect_trends, format_trends_for_agents
    trends = detect_trends(preflight_items)
    text = format_trends_for_agents(trends)
"""

import logging
import math

import numpy as np

from memory.embeddings import embed_texts

logger = logging.getLogger(__name__)

# Clustering threshold: items with similarity >= this are in the same cluster
CLUSTER_SIMILARITY = 0.75


def _normalize_engagement(metrics: dict, source: str) -> float:
    """Extract a 0-1 engagement score from source-specific metrics.

    Maps raw engagement numbers (HN points, Reddit upvotes, etc.) to a
    normalized 0-1 scale using log scaling. Different sources have different
    engagement ranges, so each gets its own normalization.
    """
    if not metrics:
        return 0.0

    if source == "hn":
        points = metrics.get("points", 0)
        # HN: 100 points is decent, 500+ is huge
        return min(1.0, math.log1p(points) / math.log1p(500))

    if source == "reddit":
        score = metrics.get("score", 0)
        # Reddit: 200 is decent, 1000+ is huge
        return min(1.0, math.log1p(score) / math.log1p(1000))

    if source == "twitter":
        likes = metrics.get("likes", 0)
        retweets = metrics.get("retweets", 0)
        combined = likes + retweets * 3  # retweets weigh more
        return min(1.0, math.log1p(combined) / math.log1p(10000))

    if source == "github":
        stars = metrics.get("stars", 0)
        return min(1.0, math.log1p(stars) / math.log1p(1000))

    if source == "youtube":
        views = metrics.get("views", 0)
        return min(1.0, math.log1p(views) / math.log1p(100000))

    return 0.0


def _cluster_items(items: list[dict]) -> list[list[dict]]:
    """Group items into topic clusters using embedding similarity.

    Uses greedy single-linkage: for each item, assign to the first cluster
    whose centroid has similarity >= CLUSTER_SIMILARITY. Otherwise create
    a new cluster.
    """
    if not items:
        return []

    texts = [f"{item['title']}. {item.get('content_preview', '')[:200]}" for item in items]
    vecs = np.array(embed_texts(texts), dtype=np.float32)

    clusters: list[list[int]] = []  # list of index lists
    centroids: list[np.ndarray] = []

    for i in range(len(items)):
        assigned = False
        for c_idx, centroid in enumerate(centroids):
            sim = float(np.dot(vecs[i], centroid))
            if sim >= CLUSTER_SIMILARITY:
                clusters[c_idx].append(i)
                # Update centroid as running mean
                members = clusters[c_idx]
                centroid_sum = sum(vecs[j] for j in members)
                centroids[c_idx] = centroid_sum / np.linalg.norm(centroid_sum)
                assigned = True
                break

        if not assigned:
            clusters.append([i])
            centroids.append(vecs[i].copy())

    return [[items[i] for i in cluster] for cluster in clusters]


def _score_cluster(cluster: list[dict]) -> dict:
    """Score a cluster and produce a trend dict.

    Score formula: source_diversity * (1 + engagement_avg) * log(item_count + 1)
    - source_diversity: unique source types / total items (0-1)
    - engagement_avg: mean normalized engagement across items
    - item_count bonus: more items = stronger signal (logarithmic)
    """
    sources = set(item["source"] for item in cluster)
    source_count = len(sources)
    item_count = len(cluster)

    # Source diversity: unique sources / items, but capped at 1.0
    diversity = min(1.0, source_count / max(item_count, 1))

    # Average engagement
    engagements = [
        _normalize_engagement(item.get("metrics", {}), item["source"])
        for item in cluster
    ]
    engagement_avg = sum(engagements) / len(engagements) if engagements else 0.0

    # Combined score
    score = diversity * (1.0 + engagement_avg) * math.log1p(item_count)

    # Pick the highest-engagement item's title as the topic label
    best_idx = max(range(len(engagements)), key=lambda i: engagements[i]) if engagements else 0
    topic = cluster[best_idx]["title"]

    # Build evidence string from real data
    evidence_parts = []
    for item in cluster:
        source_label = item.get("source_name", item["source"])
        metrics = item.get("metrics", {})
        metric_str = ""
        if "points" in metrics:
            metric_str = f" ({metrics['points']} points)"
        elif "score" in metrics:
            metric_str = f" ({metrics['score']} upvotes)"
        elif "likes" in metrics:
            metric_str = f" ({metrics['likes']} likes)"
        elif "stars" in metrics:
            metric_str = f" ({metrics['stars']} stars)"
        evidence_parts.append(f"{source_label}{metric_str}")

    evidence = "; ".join(evidence_parts)

    return {
        "topic": topic,
        "evidence": evidence,
        "score": round(score, 4),
        "source_count": source_count,
        "item_count": item_count,
        "sources": sorted(sources),
        "items": cluster,
    }


def detect_trends(
    preflight_items: list[dict],
    max_trends: int = 8,
) -> list[dict]:
    """Detect trends from preflight data by clustering and scoring.

    Args:
        preflight_items: Items from preflight.run_all() output.
        max_trends: Maximum number of trends to return.

    Returns:
        List of trend dicts sorted by score descending. Each dict:
        {topic, evidence, score, source_count, item_count, sources, items}
    """
    if not preflight_items:
        return []

    # Filter out already-covered items
    new_items = [item for item in preflight_items if not item.get("already_covered")]
    if not new_items:
        return []

    # Cluster by topic similarity
    clusters = _cluster_items(new_items)

    # Score each cluster
    trends = [_score_cluster(cluster) for cluster in clusters]

    # Sort by score descending
    trends.sort(key=lambda t: t["score"], reverse=True)

    return trends[:max_trends]


def format_trends_for_agents(trends: list[dict]) -> str:
    """Format trends as a markdown section for agent prompts.

    Produces richer context than the old comma-separated list:
    includes evidence, source count, and engagement metrics.
    """
    if not trends:
        return ""

    lines = ["## Today's Trending Topics\n"]
    for i, t in enumerate(trends, 1):
        # Support both new format (from detect_trends) and legacy format
        item_count = t.get("item_count", 1)
        source_count = t.get("source_count", 1)
        score = t.get("score", 0)
        evidence = t.get("evidence", "")
        topic = t.get("topic", "")

        lines.append(
            f"{i}. **{topic}** "
            f"({item_count} items from {source_count} sources, "
            f"score: {score:.2f})"
        )
        if evidence:
            lines.append(f"   Evidence: {evidence}")
        lines.append("")

    return "\n".join(lines)

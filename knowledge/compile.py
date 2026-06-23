"""Knowledge compiler: reads daily research findings and synthesizes persistent concept pages.

Standalone script, NOT a pipeline phase. Runs after the daily pipeline completes.
If it crashes, the pipeline already succeeded and the newsletter already sent.

Usage:
    python3 -m knowledge.compile [--date 2026-04-06] [--lookback 7] [--dry-run]
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from memory.embeddings import embed_texts
from memory.vault import atomic_write, read_source_file
from orchestrator.agents import run_claude_prompt

logger = logging.getLogger(__name__)

CLUSTER_SIMILARITY = 0.75
CONCEPT_MATCH_THRESHOLD = 0.80
DEFAULT_LOOKBACK_DAYS = 7
KNOWLEDGE_SUBDIR = "knowledge"
CONCEPTS_SUBDIR = "concepts"
CONNECTIONS_SUBDIR = "connections"


# ---------------------------------------------------------------------------
# Step 1: Fetch findings from SQLite
# ---------------------------------------------------------------------------

def fetch_recent_findings(
    db: sqlite3.Connection,
    date_str: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[dict]:
    """Fetch findings from the last N days.

    Returns list of dicts with keys: title, summary, importance, agent,
    run_date, source_name, source_url, category.
    """
    end_date = datetime.strptime(date_str, "%Y-%m-%d")
    start_date = end_date - timedelta(days=lookback_days - 1)
    start_str = start_date.strftime("%Y-%m-%d")

    rows = db.execute(
        """SELECT title, summary, importance, agent, run_date,
                  source_name, source_url, category
           FROM findings
           WHERE run_date >= ? AND run_date <= ?
           ORDER BY run_date DESC, importance DESC""",
        (start_str, date_str),
    ).fetchall()

    return [dict(row) if hasattr(row, "keys") else {
        "title": row[0], "summary": row[1], "importance": row[2],
        "agent": row[3], "run_date": row[4], "source_name": row[5],
        "source_url": row[6], "category": row[7],
    } for row in rows]


# ---------------------------------------------------------------------------
# Step 2: Cluster findings by embedding similarity
# ---------------------------------------------------------------------------

def cluster_findings(
    findings: list[dict],
    threshold: float = CLUSTER_SIMILARITY,
) -> list[list[dict]]:
    """Group findings into topic clusters using embedding similarity.

    Reuses the greedy single-linkage approach from preflight/trends.py.
    """
    if not findings:
        return []

    texts = [f"{f['title']}. {f['summary'][:200]}" for f in findings]
    vecs = np.array(embed_texts(texts), dtype=np.float32)

    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []

    for i in range(len(findings)):
        assigned = False
        for c_idx, centroid in enumerate(centroids):
            sim = float(np.dot(vecs[i], centroid))
            if sim >= threshold:
                clusters[c_idx].append(i)
                members = clusters[c_idx]
                centroid_sum = sum(vecs[j] for j in members)
                centroids[c_idx] = centroid_sum / np.linalg.norm(centroid_sum)
                assigned = True
                break

        if not assigned:
            clusters.append([i])
            centroids.append(vecs[i].copy())

    return [[findings[i] for i in cluster] for cluster in clusters]


# ---------------------------------------------------------------------------
# Step 3: Match clusters to existing concept pages
# ---------------------------------------------------------------------------

def _extract_concept_title(path: Path) -> str | None:
    """Read the title from a concept page's frontmatter."""
    content = read_source_file(path)
    if not content:
        return None
    match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def _cluster_label(cluster: list[dict]) -> str:
    """Pick a representative label for a cluster (highest importance finding title)."""
    importance_rank = {"high": 3, "medium": 2, "low": 1}
    best = max(cluster, key=lambda f: importance_rank.get(f.get("importance", "low"), 0))
    return best["title"]


def match_clusters_to_concepts(
    clusters: list[list[dict]],
    concepts_dir: Path,
    threshold: float = CONCEPT_MATCH_THRESHOLD,
) -> list[dict]:
    """For each cluster, find the best matching existing concept page (or None).

    Returns list of dicts with keys: cluster, label, existing_path, existing_title.
    """
    # Load existing concept titles and paths
    existing = []
    if concepts_dir.exists():
        for path in sorted(concepts_dir.glob("*.md")):
            title = _extract_concept_title(path)
            if title:
                existing.append({"path": path, "title": title})

    # Embed existing concept titles
    existing_vecs = []
    if existing:
        existing_vecs = embed_texts([c["title"] for c in existing])

    # Embed cluster labels
    labels = [_cluster_label(c) for c in clusters]
    if not labels:
        return []
    label_vecs = embed_texts(labels)

    results = []
    for c_idx, cluster in enumerate(clusters):
        best_match = None
        best_sim = 0.0

        if existing_vecs:
            label_vec = np.array(label_vecs[c_idx], dtype=np.float32)
            for e_idx, e_vec in enumerate(existing_vecs):
                sim = float(np.dot(label_vec, np.array(e_vec, dtype=np.float32)))
                if sim >= threshold and sim > best_sim:
                    best_sim = sim
                    best_match = existing[e_idx]

        results.append({
            "cluster": cluster,
            "label": labels[c_idx],
            "existing_path": best_match["path"] if best_match else None,
            "existing_title": best_match["title"] if best_match else None,
        })

    return results


# ---------------------------------------------------------------------------
# Step 4: Synthesize via LLM
# ---------------------------------------------------------------------------

SYNTHESIS_PROMPT_NEW = """\
You are a knowledge compiler for a research pipeline. Given these related research findings,
synthesize them into a single concept article.

## Findings

{findings_text}

## Instructions

Produce a JSON object with these fields:
- "title": A concise concept name (2-5 words, e.g. "MCP Security Vulnerabilities")
- "summary": A 2-3 paragraph synthesis that captures the key narrative across all findings.
  Write in present tense. Connect the dots between findings. Be specific with names, numbers, dates.
- "key_insights": A list of 3-5 bullet-point insights derived from the findings.
- "related_concepts": A list of 0-3 related concept slugs (lowercase-hyphenated, e.g. "supply-chain-attacks")
- "tags": A list of 3-6 lowercase tags

Output ONLY the JSON object, no markdown fences, no explanation.
"""

SYNTHESIS_PROMPT_UPDATE = """\
You are a knowledge compiler for a research pipeline. An existing concept page needs
updating with new findings.

## Existing Concept

{existing_content}

## New Findings

{findings_text}

## Instructions

Produce an UPDATED JSON object. Merge the new findings into the existing knowledge.
Keep prior insights that are still relevant, add new ones, update the summary to
reflect the fuller picture. Don't just append; synthesize.

Fields:
- "title": Keep the existing title unless the new findings reveal a better name
- "summary": Updated 2-3 paragraph synthesis incorporating old + new knowledge
- "key_insights": Updated list of 3-5 insights (keep relevant old ones, add new)
- "related_concepts": Updated list of 0-3 related concept slugs
- "tags": Updated list of 3-6 lowercase tags

Output ONLY the JSON object, no markdown fences, no explanation.
"""


def _format_findings_for_prompt(findings: list[dict]) -> str:
    """Format findings as readable text for the LLM prompt."""
    lines = []
    for f in findings:
        importance = f.get("importance", "medium")
        source = f.get("source_name", "unknown")
        date = f.get("run_date", "unknown")
        lines.append(f"### {f['title']} [{importance}]")
        lines.append(f"Source: {source} | Date: {date}")
        lines.append(f"{f['summary']}")
        lines.append("")
    return "\n".join(lines)


def _synthesize_concept(
    findings: list[dict],
    existing_content: str | None = None,
) -> dict | None:
    """Call Claude to synthesize findings into a concept. Returns parsed JSON or None."""
    findings_text = _format_findings_for_prompt(findings)

    if existing_content:
        prompt = SYNTHESIS_PROMPT_UPDATE.format(
            existing_content=existing_content,
            findings_text=findings_text,
        )
    else:
        prompt = SYNTHESIS_PROMPT_NEW.format(findings_text=findings_text)

    output, exit_code = run_claude_prompt(prompt, task_type="synthesis")

    if exit_code != 0:
        logger.warning("Claude synthesis failed with exit code %d", exit_code)
        return None

    # Strip markdown fences if present
    cleaned = output.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Claude synthesis output: %s", e)
        return None


# ---------------------------------------------------------------------------
# Step 5: Write concept pages
# ---------------------------------------------------------------------------

def _slugify(title: str) -> str:
    """Convert a title to a URL-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def write_concept_page(concepts_dir: Path, concept_data: dict) -> Path:
    """Write or overwrite a concept page from structured data.

    concept_data keys: title, slug, summary, key_insights, evidence,
    related_concepts, tags, first_seen, finding_count.
    """
    slug = concept_data.get("slug") or _slugify(concept_data["title"])
    path = concepts_dir / f"{slug}.md"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    first_seen = concept_data.get("first_seen", today)
    finding_count = concept_data.get("finding_count", 0)
    tags = concept_data.get("tags", [])

    # Build YAML tags as a proper list
    tag_lines = "tags:"
    if tags:
        tag_lines = "tags:\n" + "\n".join(f"  - {t}" for t in tags)

    lines = [
        "---",
        "type: concept",
        f"title: \"{concept_data['title']}\"",
        f"first_seen: {first_seen}",
        f"last_updated: {today}",
        f"finding_count: {finding_count}",
        tag_lines,
        "---",
        "",
        f"# {concept_data['title']}",
        "",
        "## Summary",
        "",
        concept_data.get("summary", ""),
        "",
        "## Key Points",
        "",
    ]

    for insight in concept_data.get("key_insights", []):
        lines.append(f"- {insight}")

    lines.append("")
    lines.append("## Evidence")
    lines.append("")

    # Use full path from project root so Obsidian resolves links
    for ev in concept_data.get("evidence", []):
        date = ev.get("date", today)
        title = ev.get("title", "Finding")
        lines.append(f"- [[data/ramsay/mindpattern/daily/{date}|{title}]]")

    lines.append("")
    lines.append("## Related")
    lines.append("")

    for rc in concept_data.get("related_concepts", []):
        lines.append(f"- [[data/ramsay/mindpattern/knowledge/concepts/{rc}]]")

    lines.append("")
    content = "\n".join(lines)

    atomic_write(path, content)
    return path


# ---------------------------------------------------------------------------
# Step 6: Generate index
# ---------------------------------------------------------------------------

def generate_index(knowledge_dir: Path) -> Path:
    """Regenerate knowledge/index.md listing all concepts."""
    concepts_dir = knowledge_dir / CONCEPTS_SUBDIR
    concepts = []

    if concepts_dir.exists():
        for path in sorted(concepts_dir.glob("*.md")):
            title = _extract_concept_title(path)
            if title:
                slug = path.stem
                # Extract finding_count from frontmatter
                content = read_source_file(path)
                count_match = re.search(r"^finding_count:\s*(\d+)", content, re.MULTILINE)
                count = int(count_match.group(1)) if count_match else 0
                concepts.append({"slug": slug, "title": title, "count": count})

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "---",
        "type: index",
        f"last_updated: {today}",
        f"concept_count: {len(concepts)}",
        "---",
        "",
        "# Knowledge Base",
        "",
        f"Compiled from {sum(c['count'] for c in concepts)} research findings "
        f"across {len(concepts)} concepts.",
        "",
        "## Concepts",
        "",
    ]

    if concepts:
        # Sort by finding count descending
        concepts.sort(key=lambda c: c["count"], reverse=True)
        for c in concepts:
            lines.append(f"- [[data/ramsay/mindpattern/knowledge/concepts/{c['slug']}|{c['title']}]] ({c['count']} findings)")
    else:
        lines.append("No concepts compiled yet. Run the compiler after a pipeline run.")

    lines.append("")

    index_path = knowledge_dir / "index.md"
    atomic_write(index_path, "\n".join(lines))
    return index_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compile_knowledge(
    db: sqlite3.Connection,
    vault_dir: str | Path,
    date_str: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    dry_run: bool = False,
) -> dict:
    """Main compiler entry point.

    Reads findings, clusters, synthesizes via Claude, writes concept pages.

    Returns dict with stats: findings_processed, concepts_created,
    concepts_updated, errors.
    """
    vault_dir = Path(vault_dir)
    knowledge_dir = vault_dir / KNOWLEDGE_SUBDIR
    concepts_dir = knowledge_dir / CONCEPTS_SUBDIR
    concepts_dir.mkdir(parents=True, exist_ok=True)
    (knowledge_dir / CONNECTIONS_SUBDIR).mkdir(parents=True, exist_ok=True)

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    stats = {
        "findings_processed": 0,
        "concepts_created": 0,
        "concepts_updated": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    # Step 1: Fetch findings
    findings = fetch_recent_findings(db, date_str, lookback_days)
    stats["findings_processed"] = len(findings)

    if not findings:
        logger.info("No findings in lookback window, nothing to compile")
        if not dry_run:
            generate_index(knowledge_dir)
        return stats

    logger.info("Compiling %d findings from last %d days", len(findings), lookback_days)

    # Step 2: Cluster
    clusters = cluster_findings(findings)
    logger.info("Formed %d clusters from %d findings", len(clusters), len(findings))

    # Step 3: Match to existing concepts
    matches = match_clusters_to_concepts(clusters, concepts_dir)

    if dry_run:
        stats["clusters"] = len(clusters)
        stats["concepts_created"] = sum(1 for match in matches if not match["existing_path"])
        stats["concepts_updated"] = sum(1 for match in matches if match["existing_path"])
        logger.info(
            "Dry run: %d findings, %d clusters, %d creates, %d updates",
            stats["findings_processed"], stats["clusters"],
            stats["concepts_created"], stats["concepts_updated"],
        )
        return stats

    # Step 4 + 5: Synthesize and write each cluster
    for match in matches:
        cluster = match["cluster"]
        existing_path = match["existing_path"]

        existing_content = None
        if existing_path:
            existing_content = read_source_file(existing_path)

        concept_json = _synthesize_concept(cluster, existing_content)
        if concept_json is None:
            stats["errors"] += 1
            logger.warning("Skipping cluster '%s': synthesis failed", match["label"])
            continue

        # Build concept_data for write
        title = concept_json.get("title", match["label"])
        slug = _slugify(title)

        # Preserve first_seen from existing page
        first_seen = date_str
        if existing_content:
            fs_match = re.search(r"^first_seen:\s*(.+)$", existing_content, re.MULTILINE)
            if fs_match:
                first_seen = fs_match.group(1).strip()

        # Count total findings (existing + new)
        existing_count = 0
        if existing_content:
            fc_match = re.search(r"^finding_count:\s*(\d+)", existing_content, re.MULTILINE)
            if fc_match:
                existing_count = int(fc_match.group(1))

        concept_data = {
            "title": title,
            "slug": slug,
            "summary": concept_json.get("summary", ""),
            "key_insights": concept_json.get("key_insights", []),
            "evidence": [
                {"date": f["run_date"], "title": f["title"]}
                for f in cluster
            ],
            "related_concepts": concept_json.get("related_concepts", []),
            "tags": concept_json.get("tags", []),
            "first_seen": first_seen,
            "finding_count": existing_count + len(cluster),
        }

        write_concept_page(concepts_dir, concept_data)

        if existing_path:
            stats["concepts_updated"] += 1
            logger.info("Updated concept: %s (+%d findings)", title, len(cluster))
        else:
            stats["concepts_created"] += 1
            logger.info("Created concept: %s (%d findings)", title, len(cluster))

    # Step 6: Regenerate index
    generate_index(knowledge_dir)

    logger.info(
        "Compile complete: %d processed, %d created, %d updated, %d errors",
        stats["findings_processed"], stats["concepts_created"],
        stats["concepts_updated"], stats["errors"],
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Compile research findings into knowledge base")
    parser.add_argument("--date", default=None, help="Date to compile (YYYY-MM-DD, default: today)")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_DAYS, help="Days to look back")
    parser.add_argument("--db", default="data/ramsay/memory.db", help="Path to memory.db")
    parser.add_argument("--vault", default="data/ramsay/mindpattern", help="Path to vault directory")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing files")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row

    try:
        result = compile_knowledge(
            db=db,
            vault_dir=args.vault,
            date_str=args.date,
            lookback_days=args.lookback,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
    finally:
        db.close()

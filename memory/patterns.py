"""Pattern tracking, consolidation, promotion, pruning, and agent self-improvement notes.

All functions take a `db` (sqlite3.Connection) parameter and return data structures.
No argparse, no print, no CLI.

FIX from v2: prune() batches deletes in chunks of 500 for the IN-clause.
v2 had unbounded IN-clause that could crash at >999 items (SQLite's SQLITE_MAX_VARIABLE_NUMBER).
"""

import hashlib
import re
import sqlite3
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np

from .embeddings import (
    cosine_similarity,
    deserialize_f32,
    embed_text,
    embed_texts,
    serialize_f32,
)


# ── Pattern recording ───────────────────────────────────────────────────


def record_pattern(
    db: sqlite3.Connection,
    run_date: str,
    theme: str,
    description: str | None = None,
) -> dict:
    """Record a recurring pattern/theme with semantic dedup (threshold 0.75).

    If a semantically similar pattern already exists, merge into it by
    incrementing recurrence_count. Otherwise create a new pattern.

    Returns {theme, recurrence_count, merged}.
    """
    SIMILARITY_THRESHOLD = 0.75

    # Generate embedding for the incoming theme
    new_vec = embed_text(theme)

    # Load all existing pattern embeddings and find the closest match
    rows = db.execute(
        """SELECT p.id, p.recurrence_count, p.theme, e.embedding
           FROM patterns p JOIN patterns_embeddings e ON e.pattern_id = p.id"""
    ).fetchall()

    best_id = None
    best_theme = None
    best_count = 0
    best_sim = 0.0

    for row in rows:
        emb = deserialize_f32(row["embedding"])
        sim = cosine_similarity(new_vec, emb)
        if sim > best_sim:
            best_sim = sim
            best_id = row["id"]
            best_theme = row["theme"]
            best_count = row["recurrence_count"]

    if best_id and best_sim >= SIMILARITY_THRESHOLD:
        # Semantically similar pattern exists -- merge into it
        db.execute(
            """UPDATE patterns SET recurrence_count = recurrence_count + 1,
                      last_seen = ?, description = COALESCE(?, description)
               WHERE id = ?""",
            (run_date, description, best_id),
        )
        db.commit()
        return {
            "theme": best_theme,
            "recurrence_count": best_count + 1,
            "merged": True,
        }

    # No similar pattern -- insert new and embed
    cur = db.execute(
        """INSERT INTO patterns (run_date, theme, description, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?)""",
        (run_date, theme, description, run_date, run_date),
    )
    pattern_id = cur.lastrowid
    db.execute(
        "INSERT INTO patterns_embeddings (pattern_id, embedding) VALUES (?, ?)",
        (pattern_id, serialize_f32(new_vec)),
    )
    db.commit()
    return {
        "theme": theme,
        "recurrence_count": 1,
        "merged": False,
    }


# ── Recurring patterns ──────────────────────────────────────────────────


def get_recurring(db: sqlite3.Connection, min_count: int = 2) -> list[dict]:
    """Return recurring patterns above a threshold.

    Returns list of {theme, description, count, first_seen, last_seen}.
    """
    rows = db.execute(
        """SELECT theme, description, recurrence_count, first_seen, last_seen
           FROM patterns WHERE recurrence_count >= ?
           ORDER BY recurrence_count DESC""",
        (min_count,),
    ).fetchall()

    return [
        {
            "theme": r["theme"],
            "description": r["description"],
            "count": r["recurrence_count"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
        }
        for r in rows
    ]


# ── Consolidation ───────────────────────────────────────────────────────


def consolidate(db: sqlite3.Connection, days: int = 30) -> dict:
    """Cluster agent notes into validated patterns using semantic similarity.

    Uses greedy clustering with cosine similarity threshold of 0.80.
    Matches clusters against existing validated_patterns: updates existing ones
    if similar, creates new ones if a cluster has 3+ notes.

    Returns {clusters, created, updated}.
    """
    CLUSTER_THRESHOLD = 0.80
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Load recent notes with embeddings
    rows = db.execute(
        """SELECT n.id, n.agent, n.note_type, n.content, n.run_date, e.embedding
           FROM agent_notes n
           JOIN agent_notes_embeddings e ON e.note_id = n.id
           WHERE n.run_date >= ?
           ORDER BY n.run_date DESC""",
        (cutoff,),
    ).fetchall()

    if not rows:
        return {
            "clusters": 0,
            "created": 0,
            "updated": 0,
        }

    # Build note list with deserialized embeddings
    notes = []
    for r in rows:
        emb = np.array(deserialize_f32(r["embedding"]), dtype=np.float32)
        notes.append({
            "id": r["id"],
            "agent": r["agent"],
            "note_type": r["note_type"],
            "content": r["content"],
            "date": r["run_date"],
            "embedding": emb,
        })

    # Greedy clustering by cosine similarity > threshold
    used: set[int] = set()
    clusters: list[list[dict]] = []

    for i, note in enumerate(notes):
        if i in used:
            continue
        cluster = [note]
        used.add(i)
        for j in range(i + 1, len(notes)):
            if j in used:
                continue
            sim = float(np.dot(note["embedding"], notes[j]["embedding"]))
            if sim >= CLUSTER_THRESHOLD:
                cluster.append(notes[j])
                used.add(j)
        clusters.append(cluster)

    # Load existing validated pattern embeddings
    vp_rows = db.execute(
        """SELECT vp.id, vp.pattern_key, vp.source_agents, vp.observation_count,
                  e.embedding
           FROM validated_patterns vp
           JOIN validated_patterns_embeddings e ON e.pattern_id = vp.id
           WHERE vp.status = 'active'"""
    ).fetchall()

    vp_list = []
    for r in vp_rows:
        vp_list.append({
            "id": r["id"],
            "key": r["pattern_key"],
            "agents": r["source_agents"],
            "count": r["observation_count"],
            "embedding": np.array(deserialize_f32(r["embedding"]), dtype=np.float32),
        })

    created = 0
    updated = 0
    now = datetime.now().isoformat()

    for cluster in clusters:
        # Compute cluster centroid (normalized)
        centroid = np.mean([n["embedding"] for n in cluster], axis=0).astype(np.float32)
        centroid = centroid / (np.linalg.norm(centroid) + 1e-9)

        # Find best matching validated pattern
        best_vp = None
        best_sim = 0.0
        for vp in vp_list:
            sim = float(np.dot(centroid, vp["embedding"]))
            if sim > best_sim:
                best_sim = sim
                best_vp = vp

        cluster_agents = list(set(n["agent"] for n in cluster))
        cluster_dates = [n["date"] for n in cluster]

        if best_vp and best_sim >= CLUSTER_THRESHOLD:
            # Update existing validated pattern
            existing_agents = set(best_vp["agents"].split(","))
            merged_agents = ",".join(sorted(existing_agents | set(cluster_agents)))
            db.execute(
                """UPDATE validated_patterns
                   SET observation_count = observation_count + ?,
                       last_seen = ?, source_agents = ?
                   WHERE id = ?""",
                (len(cluster), max(cluster_dates), merged_agents, best_vp["id"]),
            )
            updated += 1
        elif len(cluster) >= 3:
            # Create new validated pattern from cluster
            representative = max(cluster, key=lambda n: len(n["content"]))
            note_type = representative["note_type"]
            words = representative["content"].lower().split()[:5]
            base_slug = re.sub(r'[^a-z0-9-]', '', '-'.join([note_type] + words))[:72]
            content_hash = hashlib.md5(representative["content"].encode()).hexdigest()[:6]
            slug = f"{base_slug}-{content_hash}"

            cur = db.execute(
                """INSERT OR IGNORE INTO validated_patterns
                   (pattern_key, distilled_rule, source_agents, observation_count,
                    first_seen, last_seen, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
                (slug, representative["content"],
                 ",".join(sorted(cluster_agents)), len(cluster),
                 min(cluster_dates), max(cluster_dates), now),
            )
            pid = cur.lastrowid
            if pid:
                db.execute(
                    "INSERT OR IGNORE INTO validated_patterns_embeddings (pattern_id, embedding) VALUES (?, ?)",
                    (pid, serialize_f32(centroid.tolist())),
                )
                created += 1

    db.commit()
    return {"clusters": len(clusters), "created": created, "updated": updated}


# ── Promotion ───────────────────────────────────────────────────────────


def promote(db: sqlite3.Connection) -> dict:
    """Promote validated patterns that meet observation thresholds.

    Promotion criteria:
    - 2+ distinct agents AND 3+ observations, OR
    - 5+ observations from a single agent.

    Returns {promoted, total_promoted, patterns}.
    """
    candidates = db.execute(
        """SELECT id, pattern_key, distilled_rule, source_agents, observation_count
           FROM validated_patterns WHERE status = 'active'"""
    ).fetchall()

    promoted = 0
    for c in candidates:
        agents = c["source_agents"].split(",")
        distinct_agents = len(set(agents))

        if (distinct_agents >= 2 and c["observation_count"] >= 3) or c["observation_count"] >= 5:
            db.execute(
                "UPDATE validated_patterns SET status = 'promoted' WHERE id = ?",
                (c["id"],),
            )
            promoted += 1

    db.commit()

    results = db.execute(
        """SELECT pattern_key, distilled_rule, source_agents, observation_count
           FROM validated_patterns WHERE status = 'promoted'"""
    ).fetchall()

    return {
        "promoted": promoted,
        "total_promoted": len(results),
        "patterns": [dict(r) for r in results],
    }


# ── Pruning ─────────────────────────────────────────────────────────────


def prune(
    db: sqlite3.Connection,
    notes_days: int = 30,
    patterns_days: int = 60,
) -> dict:
    """Archive stale notes and patterns.

    FIX from v2: Batch deletes in chunks of 500 for the IN-clause.
    SQLite's SQLITE_MAX_VARIABLE_NUMBER defaults to 999, so an unbounded
    IN-clause could crash with >999 items.

    Returns {notes_pruned, patterns_archived}.
    """
    BATCH_SIZE = 500
    now = datetime.now()

    notes_cutoff = (now - timedelta(days=notes_days)).strftime("%Y-%m-%d")
    patterns_cutoff = (now - timedelta(days=patterns_days)).strftime("%Y-%m-%d")

    # Collect old note IDs
    old_note_ids = db.execute(
        "SELECT id FROM agent_notes WHERE run_date < ?", (notes_cutoff,)
    ).fetchall()
    note_ids = [r["id"] for r in old_note_ids]

    # Delete in batches of BATCH_SIZE to avoid exceeding SQLite variable limit
    for i in range(0, len(note_ids), BATCH_SIZE):
        batch = note_ids[i : i + BATCH_SIZE]
        placeholders = ",".join("?" * len(batch))
        db.execute(
            f"DELETE FROM agent_notes_embeddings WHERE note_id IN ({placeholders})",
            batch,
        )
        db.execute(
            f"DELETE FROM agent_notes WHERE id IN ({placeholders})",
            batch,
        )

    # Archive stale validated patterns
    archived = db.execute(
        """UPDATE validated_patterns SET status = 'archived'
           WHERE status = 'active' AND last_seen < ?""",
        (patterns_cutoff,),
    ).rowcount

    db.commit()
    return {"notes_pruned": len(note_ids), "patterns_archived": archived}


# ── Agent notes ─────────────────────────────────────────────────────────


def store_note(
    db: sqlite3.Connection,
    run_date: str,
    agent: str,
    note_type: str,
    content: str,
) -> int:
    """Store an agent self-improvement note with embedding.

    Returns the note ID.
    """
    now = datetime.now().isoformat()

    cur = db.execute(
        """INSERT INTO agent_notes (run_date, agent, note_type, content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (run_date, agent, note_type, content, now),
    )
    note_id = cur.lastrowid

    # Generate and store embedding for semantic clustering
    vec = embed_text(f"{note_type}: {content}")
    db.execute(
        "INSERT INTO agent_notes_embeddings (note_id, embedding) VALUES (?, ?)",
        (note_id, serialize_f32(vec)),
    )

    db.commit()
    return note_id


def get_recent_notes(
    db: sqlite3.Connection,
    agent: str,
    limit: int = 30,
) -> list[dict]:
    """Recent notes grouped by type.

    Returns list of {note_type, content, run_date}.
    """
    notes = db.execute(
        """SELECT note_type, content, run_date FROM agent_notes
           WHERE agent = ? ORDER BY run_date DESC LIMIT ?""",
        (agent, limit),
    ).fetchall()

    return [dict(n) for n in notes]


# ── Backfill ────────────────────────────────────────────────────────────


def backfill_note_embeddings(db: sqlite3.Connection) -> dict:
    """Backfill embeddings for agent_notes that are missing them.

    Returns {backfilled}.
    """
    rows = db.execute(
        """SELECT n.id, n.note_type, n.content FROM agent_notes n
           LEFT JOIN agent_notes_embeddings e ON e.note_id = n.id
           WHERE e.note_id IS NULL"""
    ).fetchall()

    if not rows:
        return {"backfilled": 0}

    texts = [f"{r['note_type']}: {r['content']}" for r in rows]
    vectors = embed_texts(texts)

    for row, vec in zip(rows, vectors):
        db.execute(
            "INSERT OR IGNORE INTO agent_notes_embeddings (note_id, embedding) VALUES (?, ?)",
            (row["id"], serialize_f32(vec)),
        )

    db.commit()
    return {"backfilled": len(rows)}

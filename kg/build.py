"""Resumable knowledge-graph builder over the findings corpus.

Purely additive: writes only ``kg_*`` tables (plus its own ``kg_build_log``
progress ledger) inside memory.db. Never modifies findings, entity_graph, or
any existing table. Every batch is independent and fails open — a bad batch
marks its findings ``failed`` (retryable via ``--retry-failed``) and the build
moves on.

Usage:
    python -m kg.build --db-path data/ramsay/memory.db --limit 500
    python -m kg.build --db-path ... --since 2026-06-01 --workers 4
    python -m kg.build --db-path ... --consolidate-only
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.claude_cli import ClaudeProcessResult, run_claude_process
from kg.extract import (
    build_extraction_prompt,
    extraction_command,
    parse_extraction_output,
    validate_extraction,
)
from kg.resolve import resolve_entity
from kg.schema import init_kg_schema

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 25
DEFAULT_TIMEOUT = 300

_BUILD_LOG_SCHEMA = """
    CREATE TABLE IF NOT EXISTS kg_build_log (
        finding_id INTEGER PRIMARY KEY,
        status TEXT NOT NULL,            -- extracted | empty | failed
        edges_added INTEGER DEFAULT 0,
        processed_at TEXT DEFAULT (datetime('now'))
    );
"""


@dataclass
class BuildStats:
    findings_processed: int = 0
    findings_failed: int = 0
    entities_created: int = 0
    edges_added: int = 0
    batches: int = 0
    batches_failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "findings_processed": self.findings_processed,
            "findings_failed": self.findings_failed,
            "entities_created": self.entities_created,
            "edges_added": self.edges_added,
            "batches": self.batches,
            "batches_failed": self.batches_failed,
            "errors": self.errors[:10],
        }


def init_build_schema(conn: sqlite3.Connection) -> None:
    init_kg_schema(conn)
    conn.executescript(_BUILD_LOG_SCHEMA)
    conn.commit()


def select_unprocessed_findings(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    limit: int | None = None,
    retry_failed: bool = False,
) -> list[sqlite3.Row]:
    """Newest-first findings that have no kg_build_log entry yet."""
    status_clause = "" if not retry_failed else " OR log.status = 'failed'"
    query = f"""
        SELECT f.id, f.run_date, f.title, f.summary
        FROM findings f
        LEFT JOIN kg_build_log log ON log.finding_id = f.id
        WHERE (log.finding_id IS NULL{status_clause})
    """
    params: list[Any] = []
    if since:
        query += " AND f.run_date >= ?"
        params.append(since)
    query += " ORDER BY f.run_date DESC, f.id DESC"
    if limit is not None:
        # limit=0 means "select nothing" (a spend cap), never "no limit"
        query += " LIMIT ?"
        params.append(int(limit))
    return conn.execute(query, params).fetchall()


def _edge_exists(
    conn: sqlite3.Connection,
    subject_id: int,
    predicate: str,
    object_id: int,
    finding_id: int,
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM kg_edges
        WHERE subject_id = ? AND predicate = ? AND object_id = ? AND finding_id = ?
        LIMIT 1
        """,
        (subject_id, predicate, object_id, finding_id),
    ).fetchone()
    return row is not None


def apply_batch_result(
    conn: sqlite3.Connection,
    batch: list[sqlite3.Row],
    validated: dict[int, dict[str, Any]],
    stats: BuildStats,
) -> None:
    """Write one batch's entities/edges + progress markers in one transaction."""
    by_id = {int(row["id"]): row for row in batch}
    entities_before = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    # accumulate locally; fold into stats only after the commit, so a
    # mid-batch rollback can't leave counters claiming rows that don't exist
    processed = failed = batch_edges = 0
    try:
        for finding_id, row in by_id.items():
            item = validated.get(finding_id)
            run_date = str(row["run_date"] or "") or None
            if item is None:
                conn.execute(
                    "INSERT OR REPLACE INTO kg_build_log (finding_id, status) VALUES (?, 'failed')",
                    (finding_id,),
                )
                failed += 1
                continue

            id_by_name: dict[str, int] = {}
            for entity in item["entities"]:
                entity_id = resolve_entity(
                    conn, entity["name"], entity["type"], seen_date=run_date
                )
                if entity_id is not None:
                    id_by_name[entity["name"].casefold()] = entity_id

            edges_added = 0
            for edge in item["edges"]:
                subject_id = id_by_name.get(edge["subject"].casefold())
                object_id = id_by_name.get(edge["object"].casefold())
                if subject_id is None or object_id is None or subject_id == object_id:
                    continue
                if _edge_exists(conn, subject_id, edge["predicate"], object_id, finding_id):
                    continue
                conn.execute(
                    """
                    INSERT INTO kg_edges
                        (subject_id, predicate, object_id, fact_text, fact_type,
                         confidence, finding_id, valid_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        subject_id,
                        edge["predicate"],
                        object_id,
                        edge["fact_text"],
                        edge["fact_type"],
                        edge["confidence"],
                        finding_id,
                        run_date,
                    ),
                )
                edges_added += 1

            status = "extracted" if (id_by_name or edges_added) else "empty"
            conn.execute(
                "INSERT OR REPLACE INTO kg_build_log (finding_id, status, edges_added) VALUES (?, ?, ?)",
                (finding_id, status, edges_added),
            )
            processed += 1
            batch_edges += edges_added
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    stats.findings_processed += processed
    stats.findings_failed += failed
    stats.edges_added += batch_edges
    entities_after = conn.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
    stats.entities_created += int(entities_after) - int(entities_before)


def _run_one_batch(
    batch: list[sqlite3.Row],
    *,
    model: str | None,
    timeout: int,
    runner: Callable[..., ClaudeProcessResult],
) -> dict[int, dict[str, Any]]:
    """Subprocess + parse + validate for one batch. No DB access (thread-safe)."""
    findings = [dict(row) for row in batch]
    allowed_ids = {int(f["id"]) for f in findings}
    prompt = build_extraction_prompt(findings)
    process = runner(extraction_command(prompt, model=model), timeout=timeout)
    if process.returncode != 0 or process.timed_out:
        logger.warning(
            "kg batch failed rc=%s timed_out=%s err=%s",
            process.returncode, process.timed_out, (process.error or process.stderr or "")[:200],
        )
        return {}
    validated: dict[int, dict[str, Any]] = {}
    for item in parse_extraction_output(process.stdout):
        clean = validate_extraction(item, allowed_ids=allowed_ids)
        if clean is not None:
            validated[clean["id"]] = clean
    return validated


def build_kg(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    limit: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    workers: int = 1,
    model: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    retry_failed: bool = False,
    runner: Callable[..., ClaudeProcessResult] = run_claude_process,
    progress: Callable[[str], None] | None = None,
) -> BuildStats:
    """Extract entities/edges for unprocessed findings. Resumable; fails open."""
    init_build_schema(conn)
    stats = BuildStats()
    rows = select_unprocessed_findings(
        conn, since=since, limit=limit, retry_failed=retry_failed
    )
    if not rows:
        return stats
    batches = [rows[i: i + batch_size] for i in range(0, len(rows), batch_size)]

    def note(message: str) -> None:
        if progress:
            progress(message)

    note(f"{len(rows)} findings in {len(batches)} batches (size {batch_size})")

    def run(batch: list[sqlite3.Row]) -> dict[int, dict[str, Any]]:
        try:
            return _run_one_batch(batch, model=model, timeout=timeout, runner=runner)
        except Exception as e:  # extraction is fail-open too, not just apply
            logger.warning("kg batch extraction failed open: %s", e)
            return {}

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, batches))
    else:
        results = [run(batch) for batch in batches]

    for index, (batch, validated) in enumerate(zip(batches, results), start=1):
        stats.batches += 1
        if not validated:
            stats.batches_failed += 1
        try:
            apply_batch_result(conn, batch, validated, stats)
        except Exception as e:  # never abort the whole build on one batch
            conn.rollback()
            stats.batches_failed += 1
            stats.errors.append(f"batch {index}: {type(e).__name__}: {e}")
            logger.warning("kg batch %d apply failed open: %s", index, e)
        note(
            f"batch {index}/{len(batches)}: "
            f"{stats.edges_added} edges, {stats.entities_created} entities so far"
        )
    return stats


# ── Consolidation ─────────────────────────────────────────────────────


def _connected_components(adjacency: dict[int, set[int]]) -> list[set[int]]:
    seen: set[int] = set()
    components: list[set[int]] = []
    for start in adjacency:
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency.get(node, ()) - component)
        seen |= component
        components.append(component)
    return components


def consolidate(conn: sqlite3.Connection, *, run_date: str) -> dict[str, Any]:
    """Recompute mention counts, importance, and communities. Idempotent."""
    init_build_schema(conn)

    # heal rows created before the slug column existed — collision-aware:
    # two legacy names can render the same slug ("GPT-5.2" / "GPT 5.2"), and
    # a blind UPDATE would either violate the UNIQUE index or merge two
    # entities onto one public page. Suffix the newcomer with its id instead.
    from kg.resolve import public_slug

    for row in conn.execute(
        "SELECT id, canonical_name FROM kg_entities WHERE slug IS NULL OR slug = ''"
    ).fetchall():
        entity_id = int(row["id"])
        slug = public_slug(str(row["canonical_name"]))
        if not slug:
            continue  # unslugifiable name stays NULL (allowed by the index)
        taken = conn.execute(
            "SELECT 1 FROM kg_entities WHERE slug = ? AND id != ? LIMIT 1",
            (slug, entity_id),
        ).fetchone()
        if taken:
            slug = f"{slug}-{entity_id}"
        conn.execute(
            "UPDATE kg_entities SET slug = ? WHERE id = ?", (slug, entity_id)
        )

    # one pass over kg_edges instead of a correlated OR subquery per entity
    # (the OR defeats both single-column indexes → O(entities × edges))
    mention_rows = conn.execute(
        """
        SELECT entity_id, COUNT(DISTINCT finding_id) AS mentions FROM (
            SELECT subject_id AS entity_id, finding_id FROM kg_edges
            UNION ALL
            SELECT object_id AS entity_id, finding_id FROM kg_edges
        ) GROUP BY entity_id
        """
    ).fetchall()
    conn.execute("UPDATE kg_entities SET mention_count = 0")
    conn.executemany(
        "UPDATE kg_entities SET mention_count = ? WHERE id = ?",
        [(int(r["mentions"]), int(r["entity_id"])) for r in mention_rows],
    )

    rows = conn.execute(
        "SELECT id, mention_count, last_seen FROM kg_entities"
    ).fetchall()
    degree_rows = conn.execute(
        """
        SELECT entity_id, COUNT(*) AS degree FROM (
            SELECT subject_id AS entity_id FROM kg_edges WHERE invalid_at IS NULL
            UNION ALL
            SELECT object_id AS entity_id FROM kg_edges WHERE invalid_at IS NULL
        ) GROUP BY entity_id
        """
    ).fetchall()
    degree = {int(r["entity_id"]): int(r["degree"]) for r in degree_rows}
    max_mentions = max((int(r["mention_count"] or 0) for r in rows), default=0)
    max_degree = max(degree.values(), default=0)
    latest = max((str(r["last_seen"] or "") for r in rows), default="")

    def recency_score(last_seen: str) -> float:
        if not last_seen or not latest:
            return 0.0
        # both are ISO dates; compare lexically at day granularity
        return 1.0 if last_seen >= latest[:10] else (0.5 if last_seen >= latest[:7] else 0.1)

    for row in rows:
        entity_id = int(row["id"])
        mentions = int(row["mention_count"] or 0)
        mention_score = (
            math.log1p(mentions) / math.log1p(max_mentions) if max_mentions else 0.0
        )
        degree_score = (degree.get(entity_id, 0) / max_degree) if max_degree else 0.0
        importance = round(
            0.5 * mention_score + 0.3 * degree_score + 0.2 * recency_score(str(row["last_seen"] or "")),
            4,
        )
        conn.execute(
            "UPDATE kg_entities SET importance = ? WHERE id = ?", (importance, entity_id)
        )

    adjacency: dict[int, set[int]] = {}
    for row in conn.execute(
        "SELECT subject_id, object_id FROM kg_edges WHERE invalid_at IS NULL"
    ):
        a, b = int(row["subject_id"]), int(row["object_id"])
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    components = [c for c in _connected_components(adjacency) if len(c) >= 3]

    conn.execute("DELETE FROM kg_communities WHERE run_date = ?", (run_date,))
    names = {
        int(r["id"]): str(r["canonical_name"])
        for r in conn.execute("SELECT id, canonical_name FROM kg_entities")
    }
    for component in sorted(components, key=len, reverse=True)[:200]:
        top = sorted(component, key=lambda i: -degree.get(i, 0))[:3]
        label = " / ".join(names.get(i, "?") for i in top)
        conn.execute(
            """
            INSERT INTO kg_communities (run_date, label, member_ids_json, algorithm)
            VALUES (?, ?, ?, 'connected-components-v1')
            """,
            (run_date, label, json.dumps(sorted(component))),
        )
    conn.commit()
    return {"entities": len(rows), "communities": len(components)}


# ── CLI ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the MindPattern knowledge graph")
    parser.add_argument("--db-path", required=True, help="Path to memory.db (explicit, always)")
    parser.add_argument("--since", default=None, help="Only findings with run_date >= this")
    parser.add_argument("--limit", type=int, default=None, help="Max findings this run")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--consolidate-only", action="store_true")
    parser.add_argument("--run-date", default=None, help="Consolidation run date (YYYY-MM-DD)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    db_path = Path(args.db_path)
    if not db_path.exists():
        parser.error(f"db not found: {db_path}")

    from memory.db import get_db

    conn = get_db(db_path)
    init_build_schema(conn)

    run_date = args.run_date
    if not run_date:
        row = conn.execute("SELECT MAX(run_date) FROM findings").fetchone()
        run_date = str(row[0] or "1970-01-01")

    if not args.consolidate_only:
        stats = build_kg(
            conn,
            since=args.since,
            limit=args.limit,
            batch_size=args.batch_size,
            workers=args.workers,
            model=args.model,
            timeout=args.timeout,
            retry_failed=args.retry_failed,
            progress=lambda m: print(f"  {m}", flush=True),
        )
        print(json.dumps({"build": stats.as_dict()}, indent=2))

    summary = consolidate(conn, run_date=run_date)
    print(json.dumps({"consolidate": summary}, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

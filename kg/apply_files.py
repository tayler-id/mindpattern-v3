"""Apply file-based extraction results to the knowledge graph — single writer.

Companion to the multi-agent fan-out: many read-only workers each write a
``result-NNNN.json`` for a ``chunk-NNNN.json`` of findings; this module is the
ONE process that touches the database, pushing every result through the same
``validate_extraction`` → ``resolve_entity`` → ``apply_batch_result`` path the
in-process builder uses. Parallel extraction, serialized writes — never the
other way around (SQLite single-writer + order-dependent entity resolution).

Usage:
    python -m kg.apply_files --db-path data/ramsay/memory.db \
        --chunks-dir /path/kg-chunks --results-dir /path/kg-results
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from kg.build import BuildStats, apply_batch_result, consolidate, init_build_schema
from kg.extract import validate_extraction

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("skipping unreadable %s: %s", path.name, e)
        return None


def apply_result_files(
    conn: sqlite3.Connection,
    *,
    chunks_dir: Path,
    results_dir: Path,
) -> BuildStats:
    """Validate and apply every chunk/result pair. Idempotent: findings already
    in kg_build_log are skipped, and duplicate edges never double-insert."""
    init_build_schema(conn)
    stats = BuildStats()
    processed = {
        int(row[0])
        for row in conn.execute("SELECT finding_id FROM kg_build_log").fetchall()
    }

    for chunk_path in sorted(chunks_dir.glob("chunk-*.json")):
        result_path = results_dir / chunk_path.name.replace("chunk-", "result-")
        chunk = _load_json(chunk_path)
        if not isinstance(chunk, list) or not chunk:
            continue
        batch = [row for row in chunk if int(row.get("id", -1)) not in processed]
        if not batch:
            continue
        # chunk rows carry {id, date, title, summary}; the applier needs run_date
        for row in batch:
            row.setdefault("run_date", row.get("date"))

        stats.batches += 1
        allowed_ids = {int(row["id"]) for row in batch}
        validated: dict[int, dict[str, Any]] = {}
        payload = _load_json(result_path) if result_path.exists() else None
        items = payload.get("findings") if isinstance(payload, dict) else None
        for item in items or []:
            clean = validate_extraction(item, allowed_ids=allowed_ids)
            if clean is not None:
                validated[clean["id"]] = clean
        if not validated:
            stats.batches_failed += 1

        try:
            apply_batch_result(conn, batch, validated, stats)
        except Exception as e:  # one bad pair never aborts the apply run
            conn.rollback()
            stats.batches_failed += 1
            stats.errors.append(f"{chunk_path.name}: {type(e).__name__}: {e}")
            logger.warning("apply failed open for %s: %s", chunk_path.name, e)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply extraction result files to the KG")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--chunks-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--run-date", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from memory.db import get_db

    conn = get_db(Path(args.db_path))
    stats = apply_result_files(
        conn,
        chunks_dir=Path(args.chunks_dir),
        results_dir=Path(args.results_dir),
    )
    run_date = args.run_date
    if not run_date:
        row = conn.execute("SELECT MAX(run_date) FROM findings").fetchone()
        run_date = str(row[0] or "1970-01-01")
    summary = consolidate(conn, run_date=run_date)
    print(json.dumps({"apply": stats.as_dict(), "consolidate": summary}, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

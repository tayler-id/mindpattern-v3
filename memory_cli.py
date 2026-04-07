#!/usr/bin/env python3
"""Lightweight CLI for agent memory access.

Agents call this via the Bash tool to query the memory database.
Each command prints JSON to stdout.

Usage:
    python3 memory_cli.py search-findings --days 7 --min-importance high --limit 10
    python3 memory_cli.py recent-posts --days 14 --limit 20
    python3 memory_cli.py get-exemplars --platform twitter --limit 5
    python3 memory_cli.py recent-corrections --platform twitter --limit 10
    python3 memory_cli.py check-duplicate --anchor "AI agents are..." --days 14 --threshold 0.8
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import memory.social as social
import memory.corrections as corrections

DB_DIR = Path(__file__).parent / "data"


def _get_db(user: str = "ramsay") -> sqlite3.Connection:
    """Open the memory database with WAL mode and foreign keys."""
    db_path = DB_DIR / user / "memory.db"
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Commands ──────────────────────────────────────────────────────────────


def cmd_search_findings(args: argparse.Namespace) -> None:
    """Search findings by recency and importance."""
    db = _get_db()
    try:
        cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

        rows = db.execute(
            """SELECT id, run_date, agent, title, summary, importance,
                      category, source_url, source_name
               FROM findings
               WHERE run_date >= ?
                 AND CASE importance
                       WHEN 'high' THEN 0
                       WHEN 'medium' THEN 1
                       ELSE 2
                     END <= CASE ?
                               WHEN 'high' THEN 0
                               WHEN 'medium' THEN 1
                               ELSE 2
                             END
               ORDER BY CASE importance
                          WHEN 'high' THEN 0
                          WHEN 'medium' THEN 1
                          ELSE 2
                        END,
                        run_date DESC
               LIMIT ?""",
            (cutoff, args.min_importance, args.limit),
        ).fetchall()

        print(json.dumps([dict(r) for r in rows], indent=2))
    finally:
        db.close()


def cmd_recent_posts(args: argparse.Namespace) -> None:
    """List recent social posts."""
    db = _get_db()
    try:
        result = social.recent_posts(db, days=args.days, limit=args.limit)
        print(json.dumps(result, indent=2))
    finally:
        db.close()


def cmd_get_exemplars(args: argparse.Namespace) -> None:
    """Retrieve voice exemplars for a platform."""
    db = _get_db()
    try:
        result = social.get_exemplars(db, platform=args.platform, limit=args.limit)
        print(json.dumps(result, indent=2))
    finally:
        db.close()


def cmd_recent_corrections(args: argparse.Namespace) -> None:
    """Get recent editorial corrections."""
    db = _get_db()
    try:
        result = corrections.recent_corrections(
            db, platform=args.platform, limit=args.limit,
        )
        print(json.dumps(result, indent=2))
    finally:
        db.close()


def cmd_check_duplicate(args: argparse.Namespace) -> None:
    """Check if anchor text is too similar to recent posts."""
    db = _get_db()
    try:
        result = social.check_duplicate(
            db, anchor_text=args.anchor, days=args.days, threshold=args.threshold,
        )
        print(json.dumps(result, indent=2))
    finally:
        db.close()


# ── Parser ────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_cli",
        description="Agent memory access CLI — prints JSON to stdout.",
    )
    sub = parser.add_subparsers(dest="command")

    # search-findings
    sf = sub.add_parser("search-findings", help="Search findings by recency/importance")
    sf.add_argument("--days", type=int, default=7, help="Look back N days (default: 7)")
    sf.add_argument(
        "--min-importance",
        choices=["high", "medium", "low"],
        default="medium",
        help="Minimum importance level (default: medium)",
    )
    sf.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    sf.set_defaults(func=cmd_search_findings)

    # recent-posts
    rp = sub.add_parser("recent-posts", help="List recent social posts")
    rp.add_argument("--days", type=int, default=14, help="Look back N days (default: 14)")
    rp.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    rp.set_defaults(func=cmd_recent_posts)

    # get-exemplars
    ge = sub.add_parser("get-exemplars", help="Retrieve voice exemplars")
    ge.add_argument("--platform", type=str, default=None, help="Platform filter")
    ge.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
    ge.set_defaults(func=cmd_get_exemplars)

    # recent-corrections
    rc = sub.add_parser("recent-corrections", help="Get recent editorial corrections")
    rc.add_argument("--platform", type=str, default=None, help="Platform filter")
    rc.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    rc.set_defaults(func=cmd_recent_corrections)

    # check-duplicate
    cd = sub.add_parser("check-duplicate", help="Check anchor text for duplicates")
    cd.add_argument("--anchor", type=str, required=True, help="Anchor text to check")
    cd.add_argument("--days", type=int, default=14, help="Look back N days (default: 14)")
    cd.add_argument(
        "--threshold", type=float, default=0.80, help="Similarity threshold (default: 0.80)",
    )
    cd.set_defaults(func=cmd_check_duplicate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(2)

    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

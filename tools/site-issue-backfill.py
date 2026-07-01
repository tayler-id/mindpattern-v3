#!/usr/bin/env python3
"""Backfill canonical newsletters into Rabbit Hole site-issue artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.site_content import run_site_issue_backfill
from orchestrator.site_content_engine import run_historical_site_seed_generation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Backfill audit run date in YYYY-MM-DD format")
    parser.add_argument("--user", default="ramsay", help="Safe user id")
    parser.add_argument(
        "--reports-root",
        default=str(PROJECT_ROOT / "reports"),
        help="Reports root containing <user>/*.md newsletters",
    )
    parser.add_argument(
        "--source-date",
        action="append",
        default=[],
        help="Optional source newsletter date to backfill; repeatable",
    )
    parser.add_argument("--max-reports", type=int, default=None, help="Optional cap for parsed reports")
    parser.add_argument("--seed", action="store_true", help="Generate high-confidence historical seed stories")
    parser.add_argument("--max-stories", type=int, default=5, help="Max historical stories to publish when --seed is set")
    args = parser.parse_args()

    reports_root = Path(args.reports_root)
    audit = run_site_issue_backfill(
        date=args.date,
        user=args.user,
        reports_root=reports_root,
        source_dates=args.source_date or None,
        max_reports=args.max_reports,
    )
    result = {
        "backfill": {
            "status": audit["status"],
            "date": audit["date"],
            "user": audit["user"],
            "counts": audit["counts"],
        }
    }
    if args.seed:
        seed = run_historical_site_seed_generation(
            date=args.date,
            user=args.user,
            reports_root=reports_root,
            source_dates=args.source_date or None,
            max_stories=args.max_stories,
        )
        result["seed"] = {
            "status": seed["status"],
            "date": seed["date"],
            "user": seed["user"],
            "counts": seed["counts"],
            "degraded_reasons": seed.get("degraded_reasons", []),
        }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

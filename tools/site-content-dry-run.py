#!/usr/bin/env python3
"""Run the Rabbit Hole site content machine in deterministic fixture mode."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestrator.site_content_engine import run_site_content_dry_run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Run date in YYYY-MM-DD format")
    parser.add_argument("--user", default="ramsay", help="Safe user id")
    parser.add_argument(
        "--reports-root",
        default=str(PROJECT_ROOT / "reports"),
        help="Reports root to write site-* artifacts under",
    )
    parser.add_argument(
        "--fixture",
        default=str(PROJECT_ROOT / "tests" / "fixtures" / "site_content" / "graph_pack_cases.json"),
        help="Public-safe fixture cases JSON",
    )
    args = parser.parse_args()

    ledger = run_site_content_dry_run(
        date=args.date,
        user=args.user,
        reports_root=Path(args.reports_root),
        fixture_path=Path(args.fixture),
    )
    print(
        json.dumps(
            {
                "status": ledger["status"],
                "date": ledger["date"],
                "user": ledger["user"],
                "generated_story_count": ledger["generated_story_count"],
                "degraded_story_count": ledger["degraded_story_count"],
                "artifacts_written": ledger["artifacts_written"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Write the site stories that past issues should have had, through the live writer and critic.

    .venv/bin/python3 devtools/site_backfill.py --dates 2026-10-03,2026-10-04
    .venv/bin/python3 devtools/site_backfill.py --dates 2026-10-03 --claude-critic

Runs write_issue_stories_for_date for each date with the production
copywriter, up to policies/editorial.json's issue_stories_per_day counting
the stories a date already has. --claude-critic sends the critic to its
Claude fallback route, so a large backfill does not spend the Codex plan.
Writes into reports/<user>/site-stories/; the next sync publishes them.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sys
from typing import Callable, Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@contextmanager
def claude_critic() -> Iterator[None]:
    """Route the site critic to its Claude fallback for the duration."""
    from core.config import route_for
    from orchestrator import site_critic

    fallback = route_for("site_story_critic").fallback
    if fallback is None or fallback.provider != "claude":
        raise SystemExit("site_story_critic has no Claude fallback route in config/models.json")
    original = site_critic.route_for
    site_critic.route_for = lambda task, *a, **k: fallback if task == "site_story_critic" else original(task, *a, **k)
    try:
        yield
    finally:
        site_critic.route_for = original


def backfill(dates: list[str], *, user: str, reports_root: Path, copywriter: Callable, cap: int) -> list[dict]:
    from core.trace_store import set_run_context
    from orchestrator.site_content_engine import write_issue_stories_for_date

    outcomes = []
    for day in dates:
        set_run_context(run_id=f"site-backfill-{day}", run_date=day, phase="site_content", user_id=user)
        outcomes.append(write_issue_stories_for_date(date=day, user=user, reports_root=reports_root,
                                                     story_copywriter=copywriter, max_written=cap))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dates", required=True, help="comma-separated YYYY-MM-DD")
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--claude-critic", action="store_true", help="critic on its Claude fallback, no Codex")
    args = parser.parse_args(argv)

    from orchestrator import editorial, site_critic

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    os.environ.setdefault("MP_SITE_STORY_WRITER", "claude")
    copywriter = site_critic.reviewed_copywriter_from_env()
    if copywriter is None:
        raise SystemExit("the site writer is off (MP_SITE_STORY_WRITER)")
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    cap = editorial.load().issue_stories_per_day
    run = lambda: backfill(dates, user=args.user, reports_root=PROJECT_ROOT / "reports",
                           copywriter=copywriter, cap=cap)
    if args.claude_critic:
        with claude_critic():
            outcomes = run()
    else:
        outcomes = run()
    for outcome in outcomes:
        print(json.dumps(outcome))
    return 0


if __name__ == "__main__":
    sys.exit(main())

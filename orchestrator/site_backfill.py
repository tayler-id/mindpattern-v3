"""Backfill the historical story archive through the writer+critic harness.

Rewrites dynamic (newsletter-excerpt) stories as reviewed, voice-clean site
story artifacts, in bounded batches so a run is cheap to stop and resume:

    python -m orchestrator.site_backfill --limit 25            # newest first
    python -m orchestrator.site_backfill --since 2026-06-01
    python -m orchestrator.site_backfill --dry-run             # list targets

Resumable by construction: a story that already has a writer-authored
site-stories artifact is skipped, so re-running continues where the last
batch stopped. Never touches the newsletter or the canonical briefings.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from orchestrator.site_content import (
    sanitize_site_artifact,
    site_artifact_path,
    write_site_artifact,
)
from orchestrator.site_content_engine import evaluate_site_story_confidence
from orchestrator.site_critic import write_story_with_review
from orchestrator.site_writer import apply_story_copy

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_REPORTS_ROOT = PROJECT_ROOT / "reports"


def _graph_pack_from_story(story: dict[str, Any]) -> dict[str, Any]:
    """Adapt a public story dict into the writer's evidence-pack shape."""
    return {
        "candidate_id": story.get("slug"),
        "date": story.get("issue_date", ""),
        "why_now": story.get("why_now") or f"Covered in the {story.get('issue_date')} briefing.",
        "primary_evidence": [
            {
                "title": story.get("title", ""),
                "summary": story.get("body_markdown") or story.get("summary", ""),
            }
        ],
        "source_refs": story.get("source_refs") or [],
        "entity_refs": story.get("entity_refs") or [],
        "related_paths": story.get("related_paths") or [],
    }


def _already_backfilled(slug: str, date: str, *, user: str, reports_root: Path) -> bool:
    try:
        path = site_artifact_path(
            kind="site_story", user=user, date=date, slug=slug, reports_root=reports_root
        )
    except ValueError:
        return True
    return path.exists()


def backfill_targets(
    *,
    user: str,
    since: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Newest-first dynamic stories that still lack a written artifact."""
    from dashboard.routes import api as api_routes

    stories = api_routes._build_all_public_stories(user)
    targets = []
    for story in stories:
        if story.get("provenance", {}).get("ai_generated"):
            continue
        if since and str(story.get("issue_date", "")) < since:
            continue
        targets.append(story)
        if len(targets) >= limit:
            break
    return targets


def backfill_story(
    story: dict[str, Any],
    *,
    user: str,
    reports_root: Path,
) -> str:
    """Rewrite one story through the harness. Returns an outcome label."""
    slug = str(story.get("slug") or "")
    date = str(story.get("issue_date") or "")
    if not slug or not date:
        return "skipped:no_slug"
    if _already_backfilled(slug, date, user=user, reports_root=reports_root):
        return "skipped:exists"

    pack = _graph_pack_from_story(story)
    copy = write_story_with_review(pack, [])
    if copy is None:
        return "failed:writer"

    artifact = apply_story_copy(dict(story), copy)
    artifact["kind"] = "site_story"
    provenance = dict(artifact.get("provenance") or {})
    provenance["generated_by"] = "mindpattern.site_backfill.writer_harness"
    artifact["provenance"] = provenance
    gate = evaluate_site_story_confidence(
        {**artifact, "claim_evidence": artifact.get("claim_evidence") or [{"claim": artifact.get("title")}]}
    )
    if not gate["publishable"] and gate["reasons"] not in ([], ["missing_claim_evidence"]):
        return f"failed:gate:{'+'.join(gate['reasons'])}"

    write_site_artifact(
        kind="site_story",
        user=user,
        reports_root=reports_root,
        date=date,
        slug=slug,
        artifact=sanitize_site_artifact(artifact),
    )
    return "written"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--since", default=None, help="Only stories from this date on (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=25, help="Max stories this run")
    parser.add_argument("--workers", type=int, default=4, help="Parallel writer pipelines")
    parser.add_argument("--dry-run", action="store_true", help="List targets, write nothing")
    parser.add_argument("--reports-root", default=str(DEFAULT_REPORTS_ROOT))
    args = parser.parse_args(argv)

    reports_root = Path(args.reports_root)
    targets = backfill_targets(user=args.user, since=args.since, limit=args.limit)
    print(f"targets: {len(targets)}")
    if args.dry_run:
        for story in targets:
            print(f"  {story.get('issue_date')} {story.get('slug')}")
        return 0

    outcomes: dict[str, int] = {}
    workers = max(1, args.workers)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(backfill_story, story, user=args.user, reports_root=reports_root): story
            for story in targets
        }
        for future in as_completed(futures):
            story = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:
                outcome = f"failed:exception:{type(exc).__name__}"
            done += 1
            outcomes[outcome.split(":")[0]] = outcomes.get(outcome.split(":")[0], 0) + 1
            print(f"[{done}/{len(targets)}] {outcome}  {story.get('slug')}", flush=True)

    print(json.dumps(outcomes))
    return 0 if outcomes.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

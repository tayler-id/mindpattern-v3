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
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from orchestrator.site_content import (
    sanitize_site_artifact,
    site_artifact_path,
    write_site_artifact,
)
from orchestrator.site_content_engine import evaluate_site_story_confidence
from orchestrator.site_critic import write_story_with_review
from orchestrator.site_writer import UsageLimitReached, apply_story_copy

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
    if not path.exists():
        return False
    # Evidence-only fallback artifacts (daily coverage with no accepted copy)
    # stay eligible for rewrite; only writer-authored artifacts are done.
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool((payload.get("provenance") or {}).get("writer"))


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


CLAIM_TTL_HOURS = 3


def _notebook_path(user: str, reports_root: Path) -> Path:
    return reports_root / user / "site-backfill-notebook.md"


def notebook_append(user: str, reports_root: Path, line: str) -> None:
    """Append one line to the run notebook, safe under concurrent writers."""
    import fcntl

    path = _notebook_path(user, reports_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "# Rabbit Hole backfill notebook\n\n"
            "Append-only ledger of every batch and story. Source of truth for\n"
            "done-ness is the artifact files; this is the human-readable trail.\n\n"
        )
    with open(path, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(line.rstrip("\n") + "\n")
        fcntl.flock(handle, fcntl.LOCK_UN)


def _ts() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%SZ")


def _claims_dir(user: str, reports_root: Path) -> Path:
    return reports_root / user / "site-backfill-claims"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def reap_expired_claims(user: str, reports_root: Path) -> int:
    """Delete expired claim files. Returns how many were reaped."""
    reaped = 0
    claims = _claims_dir(user, reports_root)
    if not claims.is_dir():
        return 0
    for path in claims.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
            if _parse_ts(payload["expires_at"]) < _now():
                path.unlink(missing_ok=True)
                reaped += 1
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            reaped += 1
    return reaped


def _active_claims(user: str, reports_root: Path) -> dict[str, dict]:
    """slug -> claim payload for unexpired claims."""
    claims = _claims_dir(user, reports_root)
    active: dict[str, dict] = {}
    if not claims.is_dir():
        return active
    now = _now()
    for path in claims.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
            if _parse_ts(payload["expires_at"]) >= now:
                active[path.stem] = payload
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue
    return active


def claim_batch(
    *,
    user: str,
    reports_root: Path,
    size: int,
    agent: str,
    ttl_hours: float = CLAIM_TTL_HOURS,
) -> dict:
    """Atomically claim up to ``size`` unwritten, unclaimed stories."""
    reap_expired_claims(user, reports_root)
    claims = _claims_dir(user, reports_root)
    claims.mkdir(parents=True, exist_ok=True)
    claim_id = f"c-{_now().strftime('%Y%m%d-%H%M%S')}-{agent}"
    expires_at = (_now() + timedelta(hours=ttl_hours)).isoformat()

    claimed: list[str] = []
    for story in backfill_targets(user=user, since=None, limit=size * 3):
        if len(claimed) >= size:
            break
        slug = str(story.get("slug") or "")
        if not slug:
            continue
        payload = json.dumps({
            "claim_id": claim_id,
            "agent": agent,
            "claimed_at": _now().isoformat(),
            "expires_at": expires_at,
        })
        try:
            # O_EXCL create is the atomicity: whoever creates the file owns it.
            fd = os.open(claims / f"{slug}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
        claimed.append(slug)
    if claimed:
        notebook_append(
            user, reports_root,
            f"\n## {claim_id}\n- agent: {agent}\n- claimed: {len(claimed)} stories at {_ts()}\n"
            + "\n".join(f"- [ ] {slug}" for slug in claimed),
        )
    return {"claim_id": claim_id, "agent": agent, "slugs": claimed}


def release_claim(*, user: str, reports_root: Path, claim_id: str) -> int:
    """Delete every claim file belonging to ``claim_id``."""
    released = 0
    for slug, payload in list(_active_claims(user, reports_root).items()):
        if payload.get("claim_id") == claim_id:
            (_claims_dir(user, reports_root) / f"{slug}.json").unlink(missing_ok=True)
            released += 1
    return released


def run_claim(
    *,
    user: str,
    reports_root: Path,
    claim_id: str,
    workers: int = 2,
) -> dict:
    """Process exactly the stories owned by ``claim_id``."""
    owned = {
        slug for slug, payload in _active_claims(user, reports_root).items()
        if payload.get("claim_id") == claim_id
    }
    if not owned:
        return {"error": "no active claims for that id (expired or released?)", "outcomes": {}}

    stories = [
        story for story in backfill_targets(user=user, since=None, limit=100000)
        if str(story.get("slug") or "") in owned
    ]
    outcomes: dict[str, int] = {}
    aborted = ""
    claims = _claims_dir(user, reports_root)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(backfill_story, story, user=user, reports_root=reports_root): story
            for story in stories
        }
        done = 0
        consecutive = 0
        for future in as_completed(futures):
            story = futures[future]
            slug = str(story.get("slug") or "")
            try:
                outcome = future.result()
            except UsageLimitReached as exc:
                aborted = f"usage_limit: {exc}"
                break
            except Exception as exc:
                outcome = f"failed:exception:{type(exc).__name__}"
            done += 1
            kind = outcome.split(":")[0]
            outcomes[kind] = outcomes.get(kind, 0) + 1
            consecutive = consecutive + 1 if kind == "failed" else 0
            # Completion releases the claim whatever the outcome; failures
            # become claimable again for a later batch.
            (claims / f"{slug}.json").unlink(missing_ok=True)
            mark = "x" if kind in {"written", "skipped"} else "!"
            notebook_append(
                user, reports_root,
                f"- [{mark}] {slug} — {outcome} at {_ts()} ({claim_id})",
            )
            print(f"[{done}/{len(stories)}] {outcome}  {slug}", flush=True)
            if consecutive >= 10:
                aborted = "10 consecutive failures"
                break
        if aborted:
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"ABORTED: {aborted}. Remaining claims expire on their own.")
    notebook_append(
        user, reports_root,
        f"- batch {claim_id} finished at {_ts()}: {json.dumps(outcomes)}"
        + (f" ABORTED: {aborted}" if aborted else ""),
    )
    return {"claim_id": claim_id, "outcomes": outcomes, "aborted": aborted}


def backfill_status(*, user: str, reports_root: Path) -> dict:
    """Done / in-progress / remaining across the story pool."""
    reap_expired_claims(user, reports_root)
    stories_dir = reports_root / user / "site-stories"
    written = 0
    fallback = 0
    for path in list(stories_dir.rglob("*.json")) if stories_dir.is_dir() else []:
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (payload.get("provenance") or {}).get("writer"):
            written += 1
        else:
            fallback += 1
    active = _active_claims(user, reports_root)
    by_agent: dict[str, int] = {}
    for payload in active.values():
        by_agent[payload.get("agent", "?")] = by_agent.get(payload.get("agent", "?"), 0) + 1
    remaining = len(backfill_targets(user=user, since=None, limit=100000)) - len(active)
    return {
        "notebook": str(_notebook_path(user, reports_root)),
        "written": written,
        "fallback_artifacts": fallback,
        "in_progress": len(active),
        "in_progress_by_agent": by_agent,
        "remaining_unclaimed": max(0, remaining),
    }


def main(argv: list[str] | None = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    if args_in and args_in[0] in {"status", "claim", "run", "release"}:
        return _main_subcommand(args_in)
    return _main_legacy(args_in)


def _main_subcommand(args_in: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "claim", "run", "release"])
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--reports-root", default=str(DEFAULT_REPORTS_ROOT))
    parser.add_argument("--size", type=int, default=50, help="claim: batch size")
    parser.add_argument("--agent", default="agent", help="claim: who is claiming")
    parser.add_argument("--claim", dest="claim_id", default="", help="run/release: claim id")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(args_in)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    reports_root = Path(args.reports_root)

    if args.command == "status":
        print(json.dumps(backfill_status(user=args.user, reports_root=reports_root), indent=2))
        return 0
    if args.command == "claim":
        result = claim_batch(
            user=args.user, reports_root=reports_root,
            size=max(1, min(args.size, 150)), agent=args.agent,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["slugs"] else 3
    if args.command == "release":
        if not args.claim_id:
            print("--claim is required"); return 2
        released = release_claim(user=args.user, reports_root=reports_root, claim_id=args.claim_id)
        print(json.dumps({"released": released}))
        return 0
    # run
    if not args.claim_id:
        print("--claim is required"); return 2
    result = run_claim(
        user=args.user, reports_root=reports_root,
        claim_id=args.claim_id, workers=min(args.workers, 2),
    )
    print(json.dumps(result))
    if result.get("error"):
        return 2
    return 2 if result.get("aborted") else 0


def _main_legacy(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--since", default=None, help="Only stories from this date on (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=25, help="Max stories this run")
    parser.add_argument("--workers", type=int, default=4, help="Parallel writer pipelines")
    parser.add_argument("--dry-run", action="store_true", help="List targets, write nothing")
    parser.add_argument("--reports-root", default=str(DEFAULT_REPORTS_ROOT))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    # Legacy mode respects claims too: skip stories another agent owns.

    reports_root = Path(args.reports_root)
    claimed_now = set(_active_claims(args.user, reports_root))
    targets = [
        story for story in backfill_targets(user=args.user, since=args.since, limit=args.limit)
        if str(story.get("slug") or "") not in claimed_now
    ]
    print(f"targets: {len(targets)}")
    if args.dry_run:
        for story in targets:
            print(f"  {story.get('issue_date')} {story.get('slug')}")
        return 0

    outcomes: dict[str, int] = {}
    workers = max(1, args.workers)
    done = 0
    consecutive_failures = 0
    aborted = ""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(backfill_story, story, user=args.user, reports_root=reports_root): story
            for story in targets
        }
        for future in as_completed(futures):
            story = futures[future]
            try:
                outcome = future.result()
            except UsageLimitReached as exc:
                aborted = f"usage_limit: {exc}"
                break
            except Exception as exc:
                outcome = f"failed:exception:{type(exc).__name__}"
            done += 1
            kind = outcome.split(":")[0]
            outcomes[kind] = outcomes.get(kind, 0) + 1
            consecutive_failures = consecutive_failures + 1 if kind == "failed" else 0
            print(f"[{done}/{len(targets)}] {outcome}  {story.get('slug')}", flush=True)
            if consecutive_failures >= 10:
                aborted = "10 consecutive failures"
                break
        if aborted:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            print(f"ABORTED: {aborted}. Nothing lost; re-run resumes where this stopped.")

    print(json.dumps(outcomes))
    if aborted:
        return 2
    return 0 if outcomes.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

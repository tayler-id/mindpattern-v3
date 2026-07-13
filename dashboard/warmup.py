"""Post-restart warm-up for the public API caches.

Every public cache in dashboard/routes/api.py is an in-memory dict, and the
nightly pipeline restarts this machine immediately after fresh data lands
(orchestrator/runner.py _phase_sync) — so the first readers of the day used
to pay every cold compute themselves (/api/issues/{date}/structured measured
at 18-75s cold). This module rebuilds the hot caches in the background after
every boot, newest content first, so a visitor click never triggers one.

Deliberately sequential: every call funnels through the same bounded
semaphores as organic traffic, and warming one item at a time leaves the
remaining slots free for real readers while the loop runs.
"""

import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)

WARM_USER = "ramsay"
# Let uvicorn bind and /healthz go green before doing any work.
STARTUP_DELAY_SECONDS = 5.0
# The public site requests entities and sources with limit=40 (src/lib/api.ts
# in vercel-mindpattern); the response cache keys include the limit, so any
# other value would warm nothing the site actually reads.
SITE_ENTITY_LIMIT = 40
SITE_SOURCE_LIMIT = 40
# The wire's top fold + archive-rail head; older stories stay lazy but are
# cheap once the shared corpus caches (list, embeddings, KG edges) are hot.
RECENT_STORY_DETAILS = 80

_status: dict = {
    "phase": "idle",
    "started_at": None,
    "finished_at": None,
    "duration_seconds": None,
    "warmed": {},
    "errors": 0,
}


def warmup_status() -> dict:
    """Snapshot for /api/warmup/status (polled by the pipeline's site warm-up)."""
    return dict(_status)


async def startup_warmup() -> None:
    """Lifespan entry point — never raises into the app."""
    try:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        await warm_public_caches()
    except asyncio.CancelledError:
        _status["phase"] = "cancelled"
        raise
    except Exception:
        logger.exception("Cache warm-up crashed (non-fatal)")
        _status["phase"] = "failed"
        _status["finished_at"] = time.time()


async def warm_public_caches(user: str = WARM_USER) -> dict:
    from dashboard.routes import api

    started = time.monotonic()
    warmed: dict[str, int] = {}
    _status.update(
        phase="running",
        started_at=time.time(),
        finished_at=None,
        duration_seconds=None,
        warmed=warmed,
        errors=0,
    )

    async def step(name: str, calls) -> None:
        warmed[name] = 0
        for call in calls:
            try:
                await call()
            except Exception:
                _status["errors"] += 1
                logger.warning("warm-up call failed in step %s", name, exc_info=True)
            else:
                warmed[name] += 1

    # Corpus-wide singletons first: the story list also builds the section
    # maps, and the first story detail builds the embedding + KG edge caches.
    await step("story_list", [lambda: api._all_public_stories(user)])
    await step("stats", [lambda: api.get_stats(user=user)])
    await step("reports_list", [lambda: api.list_reports(user=user)])
    await step("sitemap", [lambda: api.get_site_sitemap(user=user)])

    # Briefing pages: one structured issue per date, newest first.
    dates = api._structured_issue_dates(user=user)
    await step(
        "structured_issues",
        [(lambda d=d: api.get_structured_issue(d, user=user)) for d in dates],
    )

    # Story pages: the newest slice — the wire, top-5, and archive-rail head.
    stories = await api._all_public_stories(user)
    slugs = [s.get("slug") for s in stories[:RECENT_STORY_DETAILS] if s.get("slug")]
    await step(
        "story_details",
        [(lambda s=s: api.get_public_story(s, user=user)) for s in slugs],
    )

    # Entity + source pages, dossier-backed only (what the sitemap exposes).
    entity_slugs: list[str] = []
    entities_dir = api.REPORTS_DIR / user / "site-dossiers" / "entities"
    if entities_dir.is_dir():
        entity_slugs = sorted(
            path.stem
            for path in entities_dir.glob("*.json")
            if api._is_public_entity_slug(path.stem)
        )
    await step(
        "entities",
        [
            (lambda s=s: api.get_entity(s, user=user, limit=SITE_ENTITY_LIMIT))
            for s in entity_slugs
        ],
    )

    source_domains: list[str] = []
    sources_dir = api.REPORTS_DIR / user / "site-dossiers" / "sources"
    if sources_dir.is_dir():
        for path in sorted(sources_dir.glob("*.json")):
            try:
                domain = str(json.loads(path.read_text()).get("domain") or "")
            except (OSError, ValueError):
                continue
            if domain:
                source_domains.append(domain)
    await step(
        "sources",
        [
            (lambda d=d: api.get_source_detail(d, user=user, limit=SITE_SOURCE_LIMIT))
            for d in source_domains
        ],
    )

    _status.update(
        phase="done",
        finished_at=time.time(),
        duration_seconds=round(time.monotonic() - started, 1),
    )
    logger.info(
        "Cache warm-up done in %ss: %s (%d errors)",
        _status["duration_seconds"],
        warmed,
        _status["errors"],
    )
    return warmup_status()

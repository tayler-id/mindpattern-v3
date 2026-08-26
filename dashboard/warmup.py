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

Two rules this module learned on 2026-08-26, when the operator read
`{"phase": "running", "warmed": {..., "entities": 0}}` as "the entity dossier
directory is empty" and went looking for a missing directory that was there
all along:

1. **Bound every call.** /api/entities/{slug} had gone superlinear. The
   warm-up sat on the first of 84 entity slugs for over twenty minutes with
   `errors: 0`, and its compute thread starved the event loop hard enough
   that /healthz stopped answering inside 15s. One unbounded page can no
   longer hold the whole warm-up, or the machine's health check, hostage.
   A step gives up after the first timeout, because a cancelled
   `asyncio.to_thread` cancels the coroutine and not the work: the worker
   thread keeps running, and it also releases its slot on
   `api._PUBLIC_OFFLOAD_SEMAPHORE` on the way out. So a second attempt is
   admitted while the first is still computing, blocks on the same
   `api._ENTITY_ISSUE_INDEX_LOCK` the first one holds, and is guaranteed to
   time out too. Three attempts cost three threads out of a default
   `to_thread` pool of six and buy nothing.

2. **Say which of the two zeros this is.** A count of 0 has to be readable as
   "found nothing to warm" or "found N and warmed none of them" without
   guessing, so every step records its candidate count, its state, and the
   directory it looked in, and a step that warms nothing logs a WARNING
   naming that directory.

Step order is by reader value per second spent. The four corpus singletons
come first because everything downstream reuses them. Structured issues come
next, then the entity issue index they feed: measured on the real corpus,
parsing all 185 issue dates takes 2.89s and building the index on top of the warm
parses takes 0.03s, against 2.94s if the index is built first. Entity pages
then cost 23-62ms each. They come before story details because they are the
pages the sitemap advertises, every story links to them, and story details
already answer in 0.2-3.4s cold while an entity page is the one that times
out.
"""

import asyncio
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

WARM_USER = "ramsay"
# Let uvicorn bind and /healthz go green before doing any work.
STARTUP_DELAY_SECONDS = 5.0
# The public site requests entities and sources with limit=40 (getEntity and
# getSourceByDomain in src/lib/api.ts, vercel-mindpattern); the response cache
# keys include the limit, so any other value would warm nothing the site
# actually reads.
SITE_ENTITY_LIMIT = 40
SITE_SOURCE_LIMIT = 40
# The wire's top fold + archive-rail head; older stories stay lazy but are
# cheap once the shared corpus caches (list, embeddings, KG edges) are hot.
RECENT_STORY_DETAILS = 80

# A page slower than this is broken, not cold. No reader waits it out, and
# the site's own fetch gives up at 10s.
CALL_TIMEOUT_SECONDS = 90.0
# One timed-out sample ends the step. See rule 1 in the module docstring: the
# orphaned worker thread still holds api._ENTITY_ISSUE_INDEX_LOCK (a plain
# blocking threading.Lock), while the cancelled coroutine has already given
# its offload-semaphore slot back, so attempts 2 and 3 are admitted, park on
# that lock, and time out deterministically. Retrying costs 180s and two more
# threads on a 2-core box for zero chance of warming anything.
MAX_STEP_TIMEOUTS = 1
# Wall clock per step. Bounds the slow-but-not-timing-out case: 84 entities at
# 80s each would otherwise run past the next morning's restart.
STEP_BUDGET_SECONDS = 900.0
# Wall clock for the whole run.
TOTAL_BUDGET_SECONDS = 2700.0

# Every step this run intends to attempt, in execution order. Pre-seeding the
# status with all of them is what makes "not reached yet" legible: the deploy
# script and orchestrator/sync.py poll mid-flight, and a step that has not
# started reads `state: pending`, never a bare 0.
_STEP_NAMES = (
    "story_list",
    "stats",
    "reports_list",
    "sitemap",
    "structured_issues",
    "entity_index",
    "entities",
    "sources",
    "story_details",
)

_status: dict = {
    "phase": "idle",
    "started_at": None,
    "finished_at": None,
    "duration_seconds": None,
    "current_step": None,
    "warmed": {},
    "steps": {},
    "incomplete": [],
    "errors": 0,
}


def warmup_status() -> dict:
    """Snapshot for /api/warmup/status (polled by the pipeline's site warm-up).

    `phase` keeps its original vocabulary (idle / running / done / failed /
    cancelled) because deploy/deploy.sh branches on those exact strings.
    """
    snapshot = dict(_status)
    snapshot["warmed"] = dict(_status["warmed"])
    snapshot["steps"] = {name: dict(rec) for name, rec in _status["steps"].items()}
    snapshot["incomplete"] = list(_status["incomplete"])
    return snapshot


async def startup_warmup() -> None:
    """Lifespan entry point — never raises into the app."""
    try:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        await warm_public_caches()
    except asyncio.CancelledError:
        _status["phase"] = "cancelled"
        _close_out_running_step()
        raise
    except Exception:
        logger.exception("Cache warm-up crashed (non-fatal)")
        _status["phase"] = "failed"
        _status["finished_at"] = time.time()
        _close_out_running_step()


def _close_out_running_step() -> None:
    """Stop a step reading `running` under a phase that says the run is over.

    Rule 2 again, one level up: a poller that sees phase 'failed' and
    current_step 'entities' with state 'running' cannot tell whether entities
    is still working.
    """
    for record in _status["steps"].values():
        if record.get("state") == "running":
            record["state"] = "abandoned"
    _status["current_step"] = None


async def _bounded(call):
    """Rule 1 for the calls that build a step's candidate list.

    These sit outside `step`, so without this they are the two places a hang
    could still park the whole run at phase 'running' forever, which is the
    exact failure this module exists to prevent.
    """
    return await asyncio.wait_for(call(), timeout=CALL_TIMEOUT_SECONDS)


def _fmt_seconds(seconds: float) -> str:
    return f"{seconds:g}s"


def _describe_dir(directory: Path) -> str:
    """Directory plus what is actually in it, for the warm-nothing WARNING.

    The whole point of the log line is to end the argument about whether the
    files are there, so it has to answer that on its own.
    """
    try:
        if not directory.is_dir():
            return f"{directory} (no such directory)"
        return f"{directory} ({len(list(directory.glob('*.json')))} json files)"
    except OSError as exc:
        return f"{directory} (unreadable: {exc})"


async def warm_public_caches(user: str = WARM_USER) -> dict:
    from dashboard.routes import api

    started = time.monotonic()
    run_deadline = started + TOTAL_BUDGET_SECONDS
    warmed: dict[str, int] = {}
    steps: dict[str, dict] = {
        name: {
            "state": "pending",
            "candidates": None,
            "warmed": 0,
            "failed": 0,
            "timed_out": 0,
            "skipped": 0,
            "seconds": 0.0,
            "source": None,
        }
        for name in _STEP_NAMES
    }
    incomplete: list[str] = []
    _status.update(
        phase="running",
        started_at=time.time(),
        finished_at=None,
        duration_seconds=None,
        current_step=None,
        warmed=warmed,
        steps=steps,
        incomplete=incomplete,
        errors=0,
    )

    async def step(name: str, calls, source: str | None = None) -> None:
        calls = list(calls)
        record = steps[name]
        record.update(state="running", candidates=len(calls), source=source)
        warmed[name] = 0
        _status["current_step"] = name
        step_started = time.monotonic()
        step_deadline = min(step_started + STEP_BUDGET_SECONDS, run_deadline)
        abandoned = ""

        for index, call in enumerate(calls):
            if time.monotonic() >= step_deadline:
                abandoned = "budget"
                record["skipped"] = len(calls) - index
                break
            if record["timed_out"] >= MAX_STEP_TIMEOUTS:
                abandoned = "timeouts"
                record["skipped"] = len(calls) - index
                break
            try:
                await asyncio.wait_for(call(), timeout=CALL_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                record["timed_out"] += 1
                _status["errors"] += 1
                logger.warning(
                    "warm-up call %d/%d in step %s exceeded %.0fs and was abandoned "
                    "(its compute thread keeps running)",
                    index + 1,
                    len(calls),
                    name,
                    CALL_TIMEOUT_SECONDS,
                )
            except Exception:
                record["failed"] += 1
                _status["errors"] += 1
                logger.warning("warm-up call failed in step %s", name, exc_info=True)
            else:
                warmed[name] += 1
                record["warmed"] += 1

        record["seconds"] = round(time.monotonic() - step_started, 1)
        record["state"] = "abandoned" if abandoned else "done"
        if abandoned:
            incomplete.append(name)
            logger.warning(
                "warm-up step %s abandoned after %s (%s): %d warmed, %d timed out, "
                "%d failed, %d never attempted, source %s",
                name,
                _fmt_seconds(record["seconds"]),
                "step budget spent" if abandoned == "budget" else "too many timeouts",
                record["warmed"],
                record["timed_out"],
                record["failed"],
                record["skipped"],
                source or "n/a",
            )
        elif not calls:
            incomplete.append(name)
            logger.warning(
                "warm-up step %s had nothing to warm; looked in %s",
                name,
                source or "n/a",
            )
        elif record["warmed"] == 0:
            incomplete.append(name)
            logger.warning(
                "warm-up step %s warmed 0 of %d candidates from %s "
                "(%d timed out, %d failed)",
                name,
                len(calls),
                source or "n/a",
                record["timed_out"],
                record["failed"],
            )

    def _skip_remaining(reason: str) -> None:
        for name, record in steps.items():
            if record["state"] == "pending":
                record["state"] = "skipped"
                warmed.setdefault(name, 0)
                incomplete.append(name)
        logger.warning("warm-up stopped early: %s", reason)

    # Corpus-wide singletons first: the story list also builds the section
    # maps, and everything below reuses both.
    await step("story_list", [lambda: api._all_public_stories(user)], "corpus story list")
    await step("stats", [lambda: api.get_stats(user=user)], "memory.db stats")
    await step("reports_list", [lambda: api.list_reports(user=user)], "report files")
    await step("sitemap", [lambda: api.get_site_sitemap(user=user)], "site sitemap")

    # Briefing pages: one structured issue per date, newest first. This also
    # fills api._STRUCTURED_ISSUE_CACHE, which the entity issue index below
    # reads, so issues first is the cheap ordering and not just the historical
    # one.
    issue_source = f"structured issue dates for {user}"
    try:
        dates = await _bounded(lambda: asyncio.to_thread(api._structured_issue_dates, user=user))
    except Exception:
        logger.warning("warm-up could not list structured issue dates", exc_info=True)
        _status["errors"] += 1
        dates = []
        # Never let the step below report "nothing to warm" for a listing that
        # crashed. Two different zeros, again.
        issue_source = f"{issue_source} (listing failed, see the warning above)"
    await step(
        "structured_issues",
        [(lambda d=d: api.get_structured_issue(d, user=user)) for d in dates],
        issue_source,
    )

    # slug -> the issues that name it. Every entity page reads it, and the
    # first one to arrive builds it under a plain blocking lock, so it gets a
    # step of its own rather than being charged to whichever slug is first.
    await step(
        "entity_index",
        [lambda: asyncio.to_thread(api._entity_issue_index, user)],
        "entity issue index over the parsed issues above",
    )

    # Entity + source pages, dossier-backed only (what the sitemap exposes).
    # Every story links to its entities and the sitemap advertises all of
    # them, so these outrank story details for warm-up order.
    dossiers_dir = api.REPORTS_DIR / user / "site-dossiers"
    entities_dir = dossiers_dir / "entities"
    entity_slugs: list[str] = []
    entity_files = 0
    if entities_dir.is_dir():
        stems = sorted(path.stem for path in entities_dir.glob("*.json"))
        entity_files = len(stems)
        entity_slugs = [stem for stem in stems if api._is_public_entity_slug(stem)]
    if entity_files and not entity_slugs:
        logger.warning(
            "warm-up found %d entity dossiers in %s but api._is_public_entity_slug "
            "rejected every filename",
            entity_files,
            entities_dir,
        )
    await step(
        "entities",
        [
            (lambda s=s: api.get_entity(s, user=user, limit=SITE_ENTITY_LIMIT))
            for s in entity_slugs
        ],
        _describe_dir(entities_dir),
    )

    sources_dir = dossiers_dir / "sources"
    source_domains: list[str] = []
    source_files = 0
    if sources_dir.is_dir():
        for path in sorted(sources_dir.glob("*.json")):
            source_files += 1
            try:
                domain = str(json.loads(path.read_text()).get("domain") or "")
            except (OSError, ValueError):
                logger.warning("warm-up could not read source dossier %s", path)
                continue
            if domain:
                source_domains.append(domain)
    if source_files and not source_domains:
        logger.warning(
            "warm-up found %d source dossiers in %s but none carried a domain field",
            source_files,
            sources_dir,
        )
    # Handlers are called as plain functions here, so every Query param must
    # be passed explicitly — an omitted one stays a Query object, not a value.
    await step(
        "sources",
        [
            (lambda d=d: api.get_source_detail(d, user=user, limit=SITE_SOURCE_LIMIT, offset=0))
            for d in source_domains
        ],
        _describe_dir(sources_dir),
    )

    # Story pages last: already 0.2-3.4s cold once the corpus caches above are
    # hot, so they are the cheapest thing to leave lazy if the budget runs out.
    if time.monotonic() >= run_deadline:
        _skip_remaining("total warm-up budget spent before story details")
    else:
        story_source = f"newest {RECENT_STORY_DETAILS} public stories"
        try:
            # Bounded like every other call. _STORY_LIST_CACHE_TTL_SECONDS is
            # 300 and the four steps above take longer than that, so this is
            # routinely the real rebuild rather than a cache read.
            stories = await _bounded(lambda: api._all_public_stories(user))
        except Exception:
            logger.warning("warm-up could not list public stories", exc_info=True)
            _status["errors"] += 1
            stories = []
            story_source = f"{story_source} (listing failed, see the warning above)"
        slugs = [s.get("slug") for s in stories[:RECENT_STORY_DETAILS] if s.get("slug")]
        await step(
            "story_details",
            [(lambda s=s: api.get_public_story(s, user=user)) for s in slugs],
            story_source,
        )

    _status.update(
        phase="done",
        current_step=None,
        finished_at=time.time(),
        duration_seconds=round(time.monotonic() - started, 1),
    )
    if incomplete:
        # ERROR, not WARNING. `phase` stays "done" because deploy/deploy.sh and
        # orchestrator/sync.py branch on that exact vocabulary, so this line is
        # the only thing in the Fly log that says the site came back with holes
        # in it. deploy/deploy.sh prints the same list from `incomplete`.
        logger.error(
            "Cache warm-up done in %ss with gaps in %s: %s (%d errors)",
            _status["duration_seconds"],
            ", ".join(incomplete),
            warmed,
            _status["errors"],
        )
    else:
        logger.info(
            "Cache warm-up done in %ss: %s (%d errors)",
            _status["duration_seconds"],
            warmed,
            _status["errors"],
        )
    return warmup_status()

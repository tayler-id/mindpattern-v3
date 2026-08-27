"""Warm-up loop guards (dashboard/warmup.py).

Written after the 2026-08-26 incident: /api/entities/{slug} had gone
superlinear, the warm-up sat on the first of 84 entity slugs for over twenty
minutes, and its status snapshot read `{"phase": "running", "warmed":
{..., "entities": 0}}`. That was taken to mean the entity dossier directory
was empty, and an hour went into looking for a directory that held 86 files
the whole time.

So these tests pin four things: a populated dossier directory warms every
entity in it, one hanging page cannot eat the run, a zero says which zero it
is, and entity pages warm before story details.
"""

import asyncio
import json
import logging
import threading
import time

import pytest

from dashboard import warmup
from dashboard.routes import api

USER = "ramsay"


@pytest.fixture(autouse=True)
def _no_disk_layer(monkeypatch):
    """Pin these tests to the in-memory warm path.

    The real loader finds dashboard/site_cache.py and would run the disk
    backfill against whatever these stubs return. The disk path has its own
    tests in test_warmup_backfill.py; these tests are about the warm loop.
    """
    monkeypatch.setattr(warmup, "_load_disk_layer", lambda: None)


def _write_dossiers(tmp_path, *, entity_slugs=(), source_domains=()):
    """Build reports/<user>/site-dossiers/{entities,sources} under tmp_path."""
    root = tmp_path / USER / "site-dossiers"
    if entity_slugs:
        entities = root / "entities"
        entities.mkdir(parents=True)
        for slug in entity_slugs:
            (entities / f"{slug}.json").write_text(
                json.dumps({"kind": "entity_dossier", "slug": slug})
            )
    if source_domains:
        sources = root / "sources"
        sources.mkdir(parents=True)
        for domain in source_domains:
            (sources / f"{domain.replace('.', '-')}.json").write_text(
                json.dumps({"kind": "source_dossier", "domain": domain})
            )
    return tmp_path


def _stub_api(monkeypatch, tmp_path, *, order=None, entity_call=None, issue_dates=("2026-08-25",)):
    """Replace every handler the warm loop calls with a fast fake.

    Returns the list that records which entity slugs and story slugs were
    warmed, in call order.
    """
    seen: list[str] = []
    order = order if order is not None else []

    async def _stories(user):
        return [{"slug": "story-one"}, {"slug": "story-two"}]

    async def _noop(*args, **kwargs):
        return {}

    async def _issue(date, **kwargs):
        order.append("structured_issues")
        return {"date": date}

    def _entity_index(user, **kwargs):
        order.append("entity_index")
        return {}

    async def _entity(slug, **kwargs):
        order.append("entities")
        seen.append(slug)
        return {"slug": slug}

    async def _source(domain, **kwargs):
        order.append("sources")
        seen.append(domain)
        return {"domain": domain}

    async def _story(slug, **kwargs):
        order.append("story_details")
        seen.append(slug)
        return {"slug": slug}

    monkeypatch.setattr(api, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(api, "_all_public_stories", _stories)
    monkeypatch.setattr(api, "get_stats", _noop)
    monkeypatch.setattr(api, "list_reports", _noop)
    monkeypatch.setattr(api, "get_site_sitemap", _noop)
    monkeypatch.setattr(api, "_structured_issue_dates", lambda **kwargs: list(issue_dates))
    monkeypatch.setattr(api, "get_structured_issue", _issue)
    # Stubbed like every other call the loop makes: the real one caches under
    # a module-level dict keyed on the live corpus fingerprint, so letting it
    # run here would leave an empty index behind for whatever test runs next.
    monkeypatch.setattr(api, "_entity_issue_index", _entity_index)
    monkeypatch.setattr(api, "get_entity", entity_call or _entity)
    monkeypatch.setattr(api, "get_source_detail", _source)
    monkeypatch.setattr(api, "get_public_story", _story)
    return seen


def _run(coro, timeout=10.0):
    """Run the warm-up under a hard ceiling so a hang fails instead of hanging."""

    async def _bounded():
        return await asyncio.wait_for(coro, timeout=timeout)

    return asyncio.run(_bounded())


def test_every_dossier_on_disk_becomes_one_warm_call_in_filename_order(monkeypatch, tmp_path):
    """Discovery and ordering, not the hang.

    Discovery was never the bug — the old loop found the same files. What this
    pins is that each one becomes exactly one call, in a stable order, and that
    the step record carries the candidate count the operator was missing. The
    hang itself is test_one_hanging_entity_cannot_eat_the_whole_run.
    """
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs", "beta-corp", "gamma-ai"])
    seen = _stub_api(monkeypatch, tmp_path)

    status = _run(warmup.warm_public_caches(USER))

    assert status["warmed"]["entities"] == 3, (
        "3 entity dossiers on disk warmed "
        f"{status['warmed']['entities']}; step record: {status['steps']['entities']}"
    )
    assert seen[:3] == ["alpha-labs", "beta-corp", "gamma-ai"]
    assert status["steps"]["entities"]["state"] == "done"
    assert status["steps"]["entities"]["candidates"] == 3


def test_junk_slugs_are_filtered_but_real_ones_still_warm(monkeypatch, tmp_path):
    """api._is_public_entity_slug drops short junk; it must not drop the rest."""
    _write_dossiers(tmp_path, entity_slugs=["top", "alpha-labs"])
    seen = _stub_api(monkeypatch, tmp_path)

    status = _run(warmup.warm_public_caches(USER))

    assert status["warmed"]["entities"] == 1
    assert seen[0] == "alpha-labs"


def test_one_hanging_entity_cannot_eat_the_whole_run(monkeypatch, tmp_path):
    """A page that never returns is bounded, counted, and does not block sources."""
    _write_dossiers(
        tmp_path,
        entity_slugs=["alpha-labs", "beta-corp", "gamma-ai", "delta-systems"],
        source_domains=["example.com"],
    )

    async def _hangs(slug, **kwargs):
        await asyncio.sleep(30)
        return {"slug": slug}

    _stub_api(monkeypatch, tmp_path, entity_call=_hangs)
    monkeypatch.setattr(warmup, "CALL_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(warmup, "MAX_STEP_TIMEOUTS", 2)

    status = _run(warmup.warm_public_caches(USER), timeout=5.0)

    entities = status["steps"]["entities"]
    assert entities["warmed"] == 0
    assert entities["timed_out"] == 2
    assert entities["skipped"] == 2
    assert entities["state"] == "abandoned"
    assert "entities" in status["incomplete"]
    # The whole point: later steps still run.
    assert status["warmed"]["sources"] == 1
    assert status["warmed"]["story_details"] == 2
    assert status["phase"] == "done"


def test_zero_candidates_logs_a_warning_naming_the_directory(monkeypatch, tmp_path, caplog):
    """A warmed-nothing zero must not read the same as a nothing-to-warm zero."""
    _stub_api(monkeypatch, tmp_path)  # no dossier directories written at all
    entities_dir = tmp_path / USER / "site-dossiers" / "entities"

    with caplog.at_level(logging.WARNING, logger="dashboard.warmup"):
        status = _run(warmup.warm_public_caches(USER))

    assert status["warmed"]["entities"] == 0
    assert status["steps"]["entities"]["candidates"] == 0
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(str(entities_dir) in message for message in warnings), (
        f"no WARNING named {entities_dir}; got {warnings}"
    )


def test_every_candidate_failing_logs_the_count_it_started_with(monkeypatch, tmp_path, caplog):
    """The other zero: candidates found, none warmed."""
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs", "beta-corp"])

    async def _explodes(slug, **kwargs):
        raise RuntimeError("entity graph unavailable")

    _stub_api(monkeypatch, tmp_path, entity_call=_explodes)

    with caplog.at_level(logging.WARNING, logger="dashboard.warmup"):
        status = _run(warmup.warm_public_caches(USER))

    assert status["warmed"]["entities"] == 0
    assert status["steps"]["entities"]["candidates"] == 2
    assert status["steps"]["entities"]["failed"] == 2
    warnings = [r.getMessage() for r in caplog.records]
    assert any("warmed 0 of 2 candidates" in message for message in warnings), warnings


def test_entities_warm_before_story_details(monkeypatch, tmp_path):
    """Every story links to its entities, and /e/ is what the sitemap advertises."""
    _write_dossiers(
        tmp_path, entity_slugs=["alpha-labs"], source_domains=["example.com"]
    )
    order: list[str] = []
    _stub_api(monkeypatch, tmp_path, order=order)

    _run(warmup.warm_public_caches(USER))

    first_seen = []
    for name in order:
        if name not in first_seen:
            first_seen.append(name)
    assert first_seen == [
        "structured_issues",
        "entity_index",
        "entities",
        "sources",
        "story_details",
    ]


def test_status_mid_run_says_a_step_has_not_started_yet(monkeypatch, tmp_path):
    """The misread that started this: `entities: 0` on a still-running warm-up."""
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    snapshots: list[dict] = []

    async def _issue(date, **kwargs):
        snapshots.append(warmup.warmup_status())
        return {"date": date}

    _stub_api(monkeypatch, tmp_path)
    monkeypatch.setattr(api, "get_structured_issue", _issue)

    _run(warmup.warm_public_caches(USER))

    assert snapshots, "structured_issues step never ran"
    mid = snapshots[0]
    assert mid["phase"] == "running"
    assert mid["current_step"] == "structured_issues"
    assert mid["steps"]["entities"]["state"] == "pending"
    assert "entities" not in mid["warmed"]


def test_status_snapshot_does_not_alias_live_state(monkeypatch, tmp_path):
    """A snapshot handed to the HTTP route must not keep mutating under it."""
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    snapshots: list[dict] = []

    async def _issue(date, **kwargs):
        snapshots.append(warmup.warmup_status())
        return {"date": date}

    _stub_api(monkeypatch, tmp_path)
    monkeypatch.setattr(api, "get_structured_issue", _issue)

    final = _run(warmup.warm_public_caches(USER))

    assert snapshots[0]["warmed"] != final["warmed"]
    assert snapshots[0]["steps"]["entities"]["state"] == "pending"


def test_a_timed_out_offload_orphans_exactly_one_thread(monkeypatch, tmp_path):
    """MAX_STEP_TIMEOUTS is sized against this, so pin the real mechanism.

    Production shape: the handler offloads to `asyncio.to_thread` and the work
    takes a plain blocking lock (api._ENTITY_ISSUE_INDEX_LOCK). Cancelling
    `wait_for` cancels the coroutine, not the thread, AND hands back the
    offload-semaphore slot — so with MAX_STEP_TIMEOUTS above 1 the next
    attempt is admitted, parks on the lock the orphan still holds, and times
    out for certain. One is the only value that does not buy guaranteed
    failures with live threads.
    """
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs", "beta-corp", "gamma-ai"])

    # asyncio.run() waits on the default executor at shutdown, so the orphan
    # has to outlive the timeout without outliving the test.
    release = threading.Event()
    live: list[threading.Thread] = []

    def _blocks():
        live.append(threading.current_thread())
        release.wait(2.0)

    async def _entity(slug, **kwargs):
        return await asyncio.to_thread(_blocks)

    _stub_api(monkeypatch, tmp_path, entity_call=_entity)
    monkeypatch.setattr(warmup, "CALL_TIMEOUT_SECONDS", 0.2)

    assert warmup.MAX_STEP_TIMEOUTS == 1, "the accounting below is what sizes this"
    try:
        status = _run(warmup.warm_public_caches(USER), timeout=15.0)
    finally:
        release.set()

    assert len(live) == 1, f"one timeout must orphan one thread, got {len(live)}"
    entities = status["steps"]["entities"]
    assert entities["timed_out"] == 1
    assert entities["skipped"] == 2, "the other two are never attempted"
    assert entities["state"] == "abandoned"
    # The run keeps going: later steps are not charged for the orphan.
    assert status["warmed"]["story_details"] == 2
    assert status["phase"] == "done"


def test_a_hanging_issue_listing_cannot_park_the_run_at_running(monkeypatch, tmp_path):
    """Rule 1 covers the calls that build a step's list, not just the steps.

    _structured_issue_dates and _all_public_stories sit outside `step`. An
    unbounded hang in either leaves phase 'running' forever, which is exactly
    the failure this module was written to end.
    """
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    _stub_api(monkeypatch, tmp_path)

    def _hangs(**kwargs):
        # Longer than the timeout, short enough that the executor shutdown
        # asyncio.run() performs at the end does not stall the suite.
        time.sleep(2.0)
        return []

    monkeypatch.setattr(api, "_structured_issue_dates", _hangs)
    monkeypatch.setattr(warmup, "CALL_TIMEOUT_SECONDS", 0.2)

    status = _run(warmup.warm_public_caches(USER), timeout=15.0)

    assert status["phase"] == "done"
    assert status["steps"]["structured_issues"]["candidates"] == 0
    assert "listing failed" in status["steps"]["structured_issues"]["source"]
    # And the rest of the run still happened.
    assert status["warmed"]["entities"] == 1


def test_a_crash_does_not_leave_a_step_reading_running(monkeypatch):
    """phase 'failed' with a step still 'running' is unreadable.

    A poller cannot tell whether entities is still working or died mid-step,
    which is the same two-readings-of-one-value problem rule 2 exists to kill.
    """

    async def _boom():
        # The state the loop would really be in: mid-step, mid-run.
        warmup._status.update(
            phase="running",
            current_step="entities",
            steps={"entities": {"state": "running", "warmed": 0}},
            incomplete=[],
        )
        raise RuntimeError("corpus exploded")

    monkeypatch.setattr(warmup, "STARTUP_DELAY_SECONDS", 0.0)
    # step() swallows call failures, so crash the loop itself.
    monkeypatch.setattr(warmup, "warm_public_caches", _boom)

    asyncio.run(asyncio.wait_for(warmup.startup_warmup(), timeout=10.0))

    status = warmup.warmup_status()
    assert status["phase"] == "failed"
    assert status["current_step"] is None
    assert status["steps"]["entities"]["state"] != "running"


@pytest.mark.parametrize("limit_name", ["SITE_ENTITY_LIMIT", "SITE_SOURCE_LIMIT"])
def test_limits_match_what_the_site_requests(limit_name):
    """Response caches key on the limit, so a mismatch warms nothing readable.

    src/lib/api.ts (vercel-mindpattern) sends limit=40 for both getEntity and
    getSourceByDomain.
    """
    assert getattr(warmup, limit_name) == 40

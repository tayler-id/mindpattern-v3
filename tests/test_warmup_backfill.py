"""Story disk backfill (dashboard/warmup.py + dashboard/site_cache.py).

The warm-up's story_details step covers only the newest RECENT_STORY_DETAILS
stories, so a restart used to leave the archive behind them with nothing on
disk. The backfill walks the rest of the corpus after the reader-critical
steps and relies on the handlers' own write-through (dashboard/site_cache.py)
to land each response on the volume.

These tests pin its contract: the budget ends the walk between items, a valid
disk entry is never recomputed, a second run writes near zero, the walk never
starts before the entity issue index is built, and a missing disk module
degrades the warm-up to its old in-memory behavior instead of breaking it.
"""

import asyncio
import json
import sys

import pytest

from dashboard import site_cache, warmup
from dashboard.routes import api

USER = "ramsay"

# The real loader, captured before any test monkeypatches the module attribute.
_REAL_LOADER = warmup._load_disk_layer


@pytest.fixture(autouse=True)
def _no_disk_layer(monkeypatch):
    """Default every test to 'module absent' so nothing touches a real store.

    Tests that exercise the disk path override this with the real module
    pointed at a tmp tree.
    """
    monkeypatch.setattr(warmup, "_load_disk_layer", lambda: None)


def _write_dossiers(tmp_path, *, entity_slugs=()):
    root = tmp_path / USER / "site-dossiers" / "entities"
    root.mkdir(parents=True)
    for slug in entity_slugs:
        (root / f"{slug}.json").write_text(
            json.dumps({"kind": "entity_dossier", "slug": slug})
        )
    return tmp_path


class _SiteEnv:
    """A tmp story corpus plus the real site_cache pointed at a tmp root."""

    def __init__(self, tmp_path, story_slugs, *, no_file=()):
        self.slugs = list(story_slugs)
        self.cache_root = tmp_path / "site-cache"
        self.sources = tmp_path / "story-sources"
        self.sources.mkdir()
        self.files: dict[str, object] = {}
        for slug in self.slugs:
            if slug in no_file:
                continue
            path = self.sources / f"{slug}.json"
            path.write_text(json.dumps({"slug": slug}))
            self.files[slug] = path
        self.recomputed: list[str] = []

    def cache_path(self, kind, slug):
        return self.cache_root / kind / f"{slug}.json"

    def persist(self, slug):
        """What api._resolve_story_response does for a story with a file."""
        source = self.files.get(slug)
        if source is None:
            return
        key = site_cache.file_key(source)
        site_cache.write_body(self.cache_path("stories", slug), key, {"slug": slug})


def _stub_api(monkeypatch, tmp_path, env: _SiteEnv, *, order=None, story_call=None):
    """Replace every handler the warm loop calls with a fast fake.

    The story fake mirrors the real handler's write-through: computing a
    story that has a source file persists it via the real site_cache.
    `env.slugs` is newest-first, the order api._all_public_stories keeps.
    """
    order = order if order is not None else []

    async def _stories(user):
        return [{"slug": slug} for slug in env.slugs]

    async def _noop(*args, **kwargs):
        return {}

    async def _issue(date, **kwargs):
        return {"date": date}

    def _entity_index(user, **kwargs):
        order.append("entity_index")
        return {}

    async def _entity(slug, **kwargs):
        order.append("entities")
        return {"slug": slug}

    async def _story(slug, **kwargs):
        order.append("story_details")
        env.recomputed.append(slug)
        env.persist(slug)
        return {"slug": slug}

    def _story_file_for_slug(user, slug):
        return env.files.get(slug)

    def _site_cache_path(user, kind, slug):
        # The backfill asks about "stories"; keep the real layout shape.
        return env.cache_path(kind, slug)

    monkeypatch.setattr(api, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(api, "_all_public_stories", _stories)
    monkeypatch.setattr(api, "get_stats", _noop)
    monkeypatch.setattr(api, "list_reports", _noop)
    monkeypatch.setattr(api, "get_site_sitemap", _noop)
    monkeypatch.setattr(api, "_structured_issue_dates", lambda **kwargs: ["2026-08-25"])
    monkeypatch.setattr(api, "get_structured_issue", _issue)
    monkeypatch.setattr(api, "_entity_issue_index", _entity_index)
    monkeypatch.setattr(api, "get_entity", _entity)
    monkeypatch.setattr(api, "get_source_detail", _noop)
    monkeypatch.setattr(api, "get_public_story", story_call or _story)
    monkeypatch.setattr(api, "_story_file_for_slug", _story_file_for_slug)
    monkeypatch.setattr(api, "_site_cache_path", _site_cache_path)
    return order


def _use_real_disk(monkeypatch):
    monkeypatch.setattr(warmup, "_load_disk_layer", lambda: site_cache)


def _run(coro, timeout=15.0):
    async def _bounded():
        return await asyncio.wait_for(coro, timeout=timeout)

    return asyncio.run(_bounded())


def test_backfill_stops_at_the_deadline_between_items(monkeypatch, tmp_path):
    """The budget is checked between items, so a run never blows far past it."""
    slugs = [f"story-{n:03d}" for n in range(50)]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs)

    async def _slow_story(slug, **kwargs):
        await asyncio.sleep(0.02)
        env.recomputed.append(slug)
        env.persist(slug)
        return {"slug": slug}

    _stub_api(monkeypatch, tmp_path, env, story_call=_slow_story)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 2)
    monkeypatch.setenv(warmup.BACKFILL_MINUTES_ENV, "0.003")  # 0.18 seconds
    _use_real_disk(monkeypatch)

    status = _run(warmup.warm_public_caches(USER))

    backfill = status["backfill"]
    assert backfill["state"] == "abandoned"
    assert backfill["reason"] == "budget"
    assert backfill["candidates"] == 50
    assert 1 <= backfill["written"] < 48
    assert backfill["remaining"] > 0
    assert (
        backfill["written"] + backfill["skipped"] + backfill["remaining"] == 50
    )


def test_backfill_skips_entries_already_valid_on_disk(monkeypatch, tmp_path):
    slugs = [f"story-{n:03d}" for n in range(10)]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs)
    # Five entries already on disk from a previous boot.
    for slug in slugs[3:8]:
        env.persist(slug)
    _stub_api(monkeypatch, tmp_path, env)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 2)
    _use_real_disk(monkeypatch)

    status = _run(warmup.warm_public_caches(USER))

    backfill = status["backfill"]
    assert backfill["state"] == "done"
    # The recent window (2) was persisted by story_details, so the backfill
    # finds those valid too and skips 2 + 5 of the 10.
    assert backfill["skipped"] == 7
    assert backfill["written"] == 3
    assert backfill["remaining"] == 0
    # Every story now has a cache file, and the pre-seeded five got there
    # without a recompute.
    for slug in slugs:
        assert env.cache_path("stories", slug).exists()
    assert not set(slugs[3:8]) & set(env.recomputed)


def test_a_second_run_writes_near_zero(monkeypatch, tmp_path):
    """Incremental by design: the first run does the work, later runs skip it."""
    slugs = [f"story-{n:03d}" for n in range(12)]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs)
    _stub_api(monkeypatch, tmp_path, env)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 2)
    _use_real_disk(monkeypatch)

    first = _run(warmup.warm_public_caches(USER))
    assert first["backfill"]["written"] == 10  # 12 minus the recent window of 2

    second = _run(warmup.warm_public_caches(USER))
    backfill = second["backfill"]
    assert backfill["state"] == "done"
    assert backfill["written"] == 0
    assert backfill["skipped"] == 12


def test_memory_only_stories_are_left_alone(monkeypatch, tmp_path):
    """A structured-issue fallback story has no source file, so the disk layer
    cannot key an entry for it. Recomputing one every boot would burn the
    budget for nothing durable, so the backfill counts it and moves on."""
    slugs = ["story-a", "story-b", "story-c"]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs, no_file=("story-b",))
    _stub_api(monkeypatch, tmp_path, env)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 1)
    _use_real_disk(monkeypatch)

    status = _run(warmup.warm_public_caches(USER))

    backfill = status["backfill"]
    assert backfill["state"] == "done"
    assert backfill["no_file"] == 1
    # story_details warmed story-a; the backfill recomputed only story-c.
    assert env.recomputed == ["story-a", "story-c"]


def test_backfill_never_runs_before_the_entity_index_step(monkeypatch, tmp_path):
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, ["story-a", "story-b"])
    order = _stub_api(monkeypatch, tmp_path, env)
    _use_real_disk(monkeypatch)

    # Only the backfill asks for a story's source file, so this marks its
    # first activity on the shared order list.
    original = api._story_file_for_slug
    monkeypatch.setattr(
        api,
        "_story_file_for_slug",
        lambda user, slug: (order.append("backfill"), original(user, slug))[1],
    )

    _run(warmup.warm_public_caches(USER))

    assert "backfill" in order, "the backfill never checked the disk"
    assert "entity_index" in order
    assert order.index("entity_index") < order.index("backfill")
    # And it stays behind every reader-critical step, not just the index.
    assert max(i for i, name in enumerate(order) if name == "story_details") < (
        order.index("backfill")
    )


def test_backfill_evicts_its_stories_from_the_memory_cache(monkeypatch, tmp_path):
    """The archive does not fit in RAM; the volume holds its serving copy.

    Thousands of enriched responses in api._STORY_RESPONSE_CACHE would be a
    slow OOM on the shared-cpu box, so a story the backfill recomputes is
    dropped from the memory dict once the handler has persisted it. The
    recent window stays: its disk entry is already valid, so the backfill
    never touches it.
    """
    slugs = ["story-new", "story-old"]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs)
    _stub_api(monkeypatch, tmp_path, env)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 1)
    _use_real_disk(monkeypatch)
    monkeypatch.setattr(api, "_STORY_RESPONSE_CACHE", {
        (USER, "story-new"): (1.0, {"slug": "story-new"}),
        (USER, "story-old"): (1.0, {"slug": "story-old"}),
    })

    _run(warmup.warm_public_caches(USER))

    assert (USER, "story-new") in api._STORY_RESPONSE_CACHE
    assert (USER, "story-old") not in api._STORY_RESPONSE_CACHE


def test_a_refused_disk_write_keeps_the_memory_entry_and_counts_failed(monkeypatch, tmp_path):
    """A compute whose disk write was refused must not lose its memory copy.

    site_cache.write_body refuses a body over the 2MB guard and returns False
    on a full disk. The handler still returns a dict, so counting that as
    written and evicting the memory entry throws away the only warm copy and
    repeats the wasted compute every boot. Only a VALID disk entry makes the
    memory copy safe to drop.
    """
    slugs = ["story-new", "story-huge", "story-old"]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs)

    async def _story(slug, **kwargs):
        env.recomputed.append(slug)
        if slug != "story-huge":  # the write-through refused this one
            env.persist(slug)
        return {"slug": slug}

    _stub_api(monkeypatch, tmp_path, env, story_call=_story)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 1)
    _use_real_disk(monkeypatch)
    monkeypatch.setattr(api, "_STORY_RESPONSE_CACHE", {
        (USER, "story-huge"): (1.0, {"slug": "story-huge"}),
        (USER, "story-old"): (1.0, {"slug": "story-old"}),
    })

    status = _run(warmup.warm_public_caches(USER))

    backfill = status["backfill"]
    assert backfill["state"] == "done"
    assert backfill["written"] == 1, "only story-old actually landed on disk"
    assert backfill["failed"] == 1
    assert (USER, "story-huge") in api._STORY_RESPONSE_CACHE, (
        "the memory entry is the only copy a refused write leaves; evicting "
        "it repeats the compute every boot for nothing durable"
    )
    assert (USER, "story-old") not in api._STORY_RESPONSE_CACHE


def test_a_timed_out_story_does_not_end_the_backfill(monkeypatch, tmp_path):
    """One pathological story must cost itself, not the rest of the archive.

    The walk is newest-first and skip-valid fast-forwards to the same story
    next boot, so ending the walk on the first timeout blocked disk coverage
    for everything older, permanently. A story compute holds no shared
    blocking lock and its orphaned thread finishes its own write-through, so
    walking on is safe.
    """
    slugs = ["story-a", "story-hung", "story-c", "story-d"]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, slugs)

    async def _story(slug, **kwargs):
        if slug == "story-hung":
            await asyncio.sleep(3600)
        env.recomputed.append(slug)
        env.persist(slug)
        return {"slug": slug}

    _stub_api(monkeypatch, tmp_path, env, story_call=_story)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 1)
    monkeypatch.setattr(warmup, "CALL_TIMEOUT_SECONDS", 0.1)
    _use_real_disk(monkeypatch)

    status = _run(warmup.warm_public_caches(USER))

    backfill = status["backfill"]
    assert backfill["state"] == "done"
    assert backfill["timed_out"] == 1
    assert backfill["written"] == 2, "the stories behind the hung one still landed"
    assert env.cache_path("stories", "story-c").exists()
    assert env.cache_path("stories", "story-d").exists()


def test_repeated_timeouts_still_abandon_the_backfill(monkeypatch, tmp_path):
    """The allowance is a cap, not unlimited: every timeout orphans a worker
    thread on the 2-core box, so a systemically hung backend ends the walk."""
    hung = [f"story-hung-{n:02d}" for n in range(10)]
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, ["story-warm"] + hung)

    async def _story(slug, **kwargs):
        if slug.startswith("story-hung"):
            await asyncio.sleep(3600)
        env.recomputed.append(slug)
        env.persist(slug)
        return {"slug": slug}

    _stub_api(monkeypatch, tmp_path, env, story_call=_story)
    monkeypatch.setattr(warmup, "RECENT_STORY_DETAILS", 1)
    monkeypatch.setattr(warmup, "CALL_TIMEOUT_SECONDS", 0.05)
    _use_real_disk(monkeypatch)

    status = _run(warmup.warm_public_caches(USER))

    backfill = status["backfill"]
    assert backfill["state"] == "abandoned"
    assert backfill["reason"] == "timeouts"
    assert backfill["timed_out"] == warmup.BACKFILL_MAX_TIMEOUTS
    assert backfill["timed_out"] < len(hung), "the cap ended the walk early"


def test_warmup_without_the_disk_module_still_completes(monkeypatch, tmp_path):
    """Import guard: the disk layer lands alongside this module, so its
    absence must mean 'warm exactly as today', not a crash."""
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, ["story-a", "story-b"])
    _stub_api(monkeypatch, tmp_path, env)
    # Simulate the module being absent from this build, then let the real
    # loader hit that absence.
    monkeypatch.setitem(sys.modules, "dashboard.site_cache", None)
    monkeypatch.setattr(warmup, "_load_disk_layer", _REAL_LOADER)

    status = _run(warmup.warm_public_caches(USER))

    assert status["phase"] == "done"
    assert status["warmed"]["entities"] == 1
    assert status["warmed"]["story_details"] == 2
    assert status["backfill"]["state"] == "skipped"
    assert "disk" in status["backfill"]["reason"]
    assert status["disk"]["module"] is None


def test_the_loader_finds_the_real_module():
    assert _REAL_LOADER() is site_cache


def test_env_var_disables_the_backfill(monkeypatch, tmp_path):
    _write_dossiers(tmp_path, entity_slugs=["alpha-labs"])
    env = _SiteEnv(tmp_path, ["story-a"])
    order = _stub_api(monkeypatch, tmp_path, env)
    _use_real_disk(monkeypatch)
    monkeypatch.setenv(warmup.BACKFILL_MINUTES_ENV, "0")

    status = _run(warmup.warm_public_caches(USER))

    assert status["phase"] == "done"
    assert status["backfill"]["state"] == "skipped"
    assert warmup.BACKFILL_MINUTES_ENV in status["backfill"]["reason"]
    assert status["backfill"]["candidates"] is None  # never listed anything
    # The write-through in the story_details step is the handler's own, not
    # the backfill's; it still ran.
    assert env.cache_path("stories", "story-a").exists()

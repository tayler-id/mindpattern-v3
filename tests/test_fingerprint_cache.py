"""The public cache fingerprint must not stat the world on every request.

_data_fingerprint runs before the cache lookup on every public endpoint, on
the event loop. It calls _story_sources_fingerprint, which iterdir()s
reports/<user>/site-stories and stats every date directory, then stats
memory.db. That is 50+ syscalls per request against a network-backed Fly
volume, serialized on the loop.

Measured 2026-08-26: /api/reports 8.3s, /healthz 37s and a 503. The site calls
getStats() and getReports() through contentVersion() before every detail
fetch, so an 8.3s /api/reports blew the site's 10s abort and 70% of cold story
pages returned 500 with no share card.

The fingerprint only decides when to invalidate a response cache, and the
thing that moves it is a daily sync. A couple of seconds of staleness costs
nothing; recomputing it per request costs the whole box.
"""

import time

import pytest

from dashboard.routes import api as api_mod


@pytest.fixture
def story_tree(tmp_path, monkeypatch):
    user = tmp_path / "ramsay"
    stories = user / "site-stories"
    for day in range(40):
        (stories / f"2026-07-{day % 28 + 1:02d}-{day}").mkdir(parents=True)
    (user / "memory.db").write_bytes(b"x")
    monkeypatch.setattr(api_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path)
    api_mod._reset_fingerprint_cache()
    return user


class TestFingerprintIsCached:
    def test_repeat_calls_do_not_re_stat_the_tree(self, story_tree, monkeypatch):
        calls = {"n": 0}
        real = api_mod._story_sources_fingerprint

        def counting(user):
            calls["n"] += 1
            return real(user)

        monkeypatch.setattr(api_mod, "_story_sources_fingerprint", counting)

        for _ in range(50):
            api_mod._data_fingerprint("ramsay")

        assert calls["n"] == 1, (
            f"50 requests caused {calls['n']} filesystem sweeps; it should be 1"
        )

    def test_the_value_is_stable_within_the_window(self, story_tree):
        first = api_mod._data_fingerprint("ramsay")
        second = api_mod._data_fingerprint("ramsay")
        assert first == second

    def test_the_cache_expires_so_a_sync_is_picked_up(self, story_tree, monkeypatch):
        clock = {"t": 1000.0}
        monkeypatch.setattr(api_mod.time, "monotonic", lambda: clock["t"])
        api_mod._reset_fingerprint_cache()

        calls = {"n": 0}
        real = api_mod._story_sources_fingerprint
        monkeypatch.setattr(
            api_mod, "_story_sources_fingerprint",
            lambda u: (calls.__setitem__("n", calls["n"] + 1), real(u))[1],
        )

        api_mod._data_fingerprint("ramsay")
        clock["t"] += api_mod._FINGERPRINT_TTL + 0.1
        api_mod._data_fingerprint("ramsay")
        assert calls["n"] == 2, "the fingerprint never refreshes, so a sync is invisible"

    def test_the_ttl_is_short_enough_to_stay_honest(self):
        assert 0 < api_mod._FINGERPRINT_TTL <= 30

    def test_each_user_is_cached_separately(self, story_tree, monkeypatch):
        seen = []
        monkeypatch.setattr(
            api_mod, "_story_sources_fingerprint",
            lambda u: (seen.append(u), 1.0)[1],
        )
        api_mod._data_fingerprint("ramsay")
        api_mod._data_fingerprint("ramsay")
        assert seen == ["ramsay"]


class TestSourcesFingerprintIsCachedToo:
    """The story detail endpoint calls the primitive directly, not
    _data_fingerprint. Six handlers do. Memoizing only the wrapper left a
    second door onto the same 53-directory sweep, which is why a warm story
    detail still measured 7.7s after the first fix."""

    def test_the_primitive_is_memoized(self, story_tree, monkeypatch):
        import pathlib as _pl

        calls = {"n": 0}
        api_mod._reset_fingerprint_cache()
        real = _pl.Path.iterdir

        def counting(self):
            if "site-stories" in str(self):
                calls["n"] += 1
            return real(self)

        monkeypatch.setattr(_pl.Path, "iterdir", counting)
        for _ in range(30):
            api_mod._story_sources_fingerprint("ramsay")
        assert calls["n"] == 1, f"30 calls swept the tree {calls['n']} times"

    def test_both_memos_clear_together(self, story_tree):
        api_mod._data_fingerprint("ramsay")
        api_mod._story_sources_fingerprint("ramsay")
        assert api_mod._FINGERPRINT_CACHE and api_mod._SOURCES_FINGERPRINT_CACHE
        api_mod._reset_fingerprint_cache()
        assert not api_mod._FINGERPRINT_CACHE
        assert not api_mod._SOURCES_FINGERPRINT_CACHE


class TestStillCorrect:
    def test_a_fresh_process_computes_a_real_value(self, story_tree):
        api_mod._reset_fingerprint_cache()
        assert api_mod._data_fingerprint("ramsay") > 0

    def test_an_unknown_user_is_not_cached_as_a_real_value(self, story_tree):
        api_mod._reset_fingerprint_cache()
        assert api_mod._data_fingerprint("../etc") == 0.0

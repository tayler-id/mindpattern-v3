"""The disk layer behind the public story and entity response caches.

Every backend cache in dashboard/routes/api.py is an in-memory dict, so a
restart or deploy used to cost the first reader the full corpus rebuild.
_all_public_stories reads every story JSON on the volume, measured 5,471ms
cold against 1ms warm. dashboard/site_cache.py keeps the finished response
bodies on disk under DATA_DIR/<user>/site-cache so a restart costs one small
file read instead.

Failure modes pinned here because they have shipped before. A truncated cache
file must never be served and never 500 (zero-byte artifacts shipped
2026-07-27 and 2026-08-04), and a path built from a slug must never leave the
cache root.
"""

import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from dashboard.routes import api as api_mod

STORY_SLUG = "openai-agent-runtime"
ISSUE_DATE = "2026-07-01"
USER = "ramsay"


def _story_payload(title: str = "OpenAI agent runtime reliability becomes a public benchmark") -> dict:
    return {
        "kind": "site_story",
        "id": STORY_SLUG,
        "slug": STORY_SLUG,
        "status": "published",
        "confidence": "high",
        "issue_date": ISSUE_DATE,
        "title": title,
        "dek": "A source-backed Rabbit Hole story artifact.",
        "summary": "OpenAI made agent runtime reliability a buyer-visible benchmark.",
        "take": "Runtime reliability is moving to public buying criteria.",
        "why_now": "The July 1 corpus connected product updates and graph recurrence.",
        "body_markdown": "OpenAI made agent runtime reliability a buyer-visible benchmark.",
        "source_refs": [
            {
                "url": "https://openai.com/news/agents",
                "domain": "openai.com",
                "title": "OpenAI agent update",
            }
        ],
        "entity_refs": [
            {"id": "openai", "slug": "openai", "name": "OpenAI", "kind": "company"}
        ],
        "primary_finding_ids": [101],
        "supporting_finding_ids": [102],
        "arc_ids": ["agent-runtime-reliability"],
        "graph_edges": [
            {
                "kind": "entity",
                "relationship": "same_entity",
                "id": "openai",
                "label": "OpenAI",
                "target_url": "/e/openai",
                "evidence": "finding:101",
            }
        ],
        "related_paths": [],
        "claim_evidence": [
            {
                "claim": "OpenAI made runtime reliability a buyer-visible benchmark.",
                "source_url": "https://openai.com/news/agents",
                "finding_id": 101,
            }
        ],
        "provenance": {
            "generated_by": "mindpattern.site_content.story_engine",
            "generated_at": "2026-07-01T12:00:00+00:00",
            "input_artifacts": ["reports/ramsay/site-graph-packs/2026-07-01/openai-agent-runtime.json"],
            "source_finding_ids": [101, 102],
            "source_issue_dates": [ISSUE_DATE],
            "redaction_status": "passed",
            "ai_generated": True,
            "human_approved": False,
        },
        "json_ld_ready": True,
    }


def _report_markdown(date: str) -> str:
    """A report the issue splitter turns into story units with entity refs."""
    return (
        f"# Rabbit Hole briefing {date}\n\n"
        "## Agent Platforms\n\n"
        f"**OpenAI shipped agent runtime changes on {date}.** "
        "OpenAI and Anthropic both moved runtime reliability into buying criteria. "
        + "Full dynamic story body sentence. " * 40
        + "Source: [OpenAI](https://openai.com/news/agents).\n"
    )


def _restart(api) -> None:
    """Empty every in-memory cache, the way a deploy or reboot does."""
    api._reset_fingerprint_cache()
    api._reset_story_file_index()
    for name in (
        "_STORY_RESPONSE_CACHE",
        "_STORY_LIST_CACHE",
        "_PUBLIC_RESPONSE_CACHE",
        "_ENTITY_ISSUE_INDEX_CACHE",
        "_ENTITY_LIST_INDEX_CACHE",
        "_FINDING_ID_INDEX_CACHE",
        "_STRUCTURED_ISSUE_CACHE",
        "_SECTION_MAP_CACHE",
        "_STORY_EMBEDDING_CACHE",
        "_KG_PAIR_EDGE_CACHE",
    ):
        getattr(api, name).clear()


def _count_calls(monkeypatch, target, name) -> list:
    calls: list = []
    original = getattr(target, name)

    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, counted)
    return calls


@pytest.fixture
def site_env(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    data = tmp_path / "data"
    cache_root = data / USER / "site-cache"
    story_dir = reports / USER / "site-stories" / ISSUE_DATE
    story_dir.mkdir(parents=True)
    (data / USER).mkdir(parents=True)
    story_file = story_dir / f"{STORY_SLUG}.json"
    story_file.write_text(json.dumps(_story_payload()))
    (reports / USER / f"{ISSUE_DATE}.md").write_text(_report_markdown(ISSUE_DATE))

    monkeypatch.setattr(api_mod, "REPORTS_DIR", reports)
    monkeypatch.setattr(api_mod, "DATA_DIR", data)

    _restart(api_mod)
    yield SimpleNamespace(
        reports=reports,
        data=data,
        cache_root=cache_root,
        story_file=story_file,
    )
    _restart(api_mod)


class TestRestartServesFromDisk:
    def test_a_story_survives_a_restart_without_a_corpus_rebuild(self, site_env, monkeypatch):
        with TestClient(app) as client:
            first = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")
        assert first.status_code == 200

        _restart(api_mod)
        rebuilds = _count_calls(monkeypatch, api_mod, "_build_all_public_stories")
        with TestClient(app) as client:
            second = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")

        assert second.status_code == 200
        assert second.json() == first.json()
        assert rebuilds == [], "a disk hit must not rebuild the story corpus"

    def test_an_entity_page_survives_a_restart_without_recompute(self, site_env, monkeypatch):
        with TestClient(app) as client:
            first = client.get(f"/api/entities/openai?user={USER}&limit=20")
        assert first.status_code == 200

        _restart(api_mod)
        computes = _count_calls(monkeypatch, api_mod, "_entity_impl")
        with TestClient(app) as client:
            second = client.get(f"/api/entities/openai?user={USER}&limit=20")

        assert second.status_code == 200
        assert second.json() == first.json()
        assert computes == [], "a disk hit must not recompute the entity page"


class TestInvalidation:
    def test_a_corrupt_story_cache_file_falls_through_and_heals(self, site_env):
        with TestClient(app) as client:
            first = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")
        assert first.status_code == 200

        cache_file = site_env.cache_root / "stories" / f"{STORY_SLUG}.json"
        assert cache_file.exists(), "the computed response must land on disk"
        cache_file.write_bytes(b'{"v": 1, "key"')

        _restart(api_mod)
        with TestClient(app) as client:
            second = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")

        assert second.status_code == 200
        assert second.json() == first.json()
        healed = json.loads(cache_file.read_text())
        assert healed["body"]["slug"] == STORY_SLUG

    def test_a_zero_byte_cache_file_is_never_served(self, site_env):
        with TestClient(app) as client:
            first = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")
        assert first.status_code == 200

        cache_file = site_env.cache_root / "stories" / f"{STORY_SLUG}.json"
        cache_file.write_bytes(b"")

        _restart(api_mod)
        with TestClient(app) as client:
            second = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")
        assert second.status_code == 200
        assert second.json()["slug"] == STORY_SLUG

    def test_a_changed_source_file_recomputes_instead_of_serving_stale(self, site_env):
        with TestClient(app) as client:
            first = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")
        assert first.status_code == 200

        new_title = "OpenAI runtime reliability, revised edition with a longer headline"
        site_env.story_file.write_text(json.dumps(_story_payload(title=new_title)))

        _restart(api_mod)
        with TestClient(app) as client:
            second = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")

        assert second.status_code == 200
        assert second.json()["title"] == new_title

    def test_a_replace_landing_mid_request_never_pins_the_old_body(self, site_env, monkeypatch):
        """The disk key must be the source file's stat from BEFORE the read.

        Story JSONs are rewritten in place on the live box (sync.py uploads a
        tar the server extracts onto the volume). A request in flight across
        that replace reads the old body but, if it stats the file afterwards,
        writes the envelope under the new file's key. That entry then reads as
        fresh forever and the stale body survives every restart. Keyed by the
        pre-read stat, the same interleaving leaves a key the next stat
        mismatches, so it costs one recompute and heals.
        """
        new_title = "OpenAI runtime reliability, revised edition with a much longer headline"
        original_enrich = api_mod._story_with_graph_related
        replaced = []

        def replace_mid_request(story, stories, **kwargs):
            # Runs between _load_public_story_file and the envelope write,
            # exactly where the nightly sync can land.
            if not replaced:
                replaced.append(True)
                site_env.story_file.write_text(json.dumps(_story_payload(title=new_title)))
            return original_enrich(story, stories, **kwargs)

        monkeypatch.setattr(api_mod, "_story_with_graph_related", replace_mid_request)
        with TestClient(app) as client:
            first = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")
        assert first.status_code == 200
        monkeypatch.setattr(api_mod, "_story_with_graph_related", original_enrich)

        _restart(api_mod)
        with TestClient(app) as client:
            second = client.get(f"/api/stories/{STORY_SLUG}?user={USER}")

        assert second.status_code == 200
        assert second.json()["title"] == new_title, (
            "the disk cache served the pre-replace body as fresh"
        )

    def test_a_moved_data_fingerprint_recomputes_the_entity_page(self, site_env, monkeypatch):
        with TestClient(app) as client:
            assert client.get(f"/api/entities/openai?user={USER}&limit=20").status_code == 200

        report = site_env.reports / USER / f"{ISSUE_DATE}.md"
        report.write_text(report.read_text() + "\nAppended line moves the tree mtime.\n")
        os.utime(site_env.reports / USER)

        _restart(api_mod)
        computes = _count_calls(monkeypatch, api_mod, "_entity_impl")
        with TestClient(app) as client:
            assert client.get(f"/api/entities/openai?user={USER}&limit=20").status_code == 200
        assert len(computes) == 1, "a moved fingerprint must invalidate the disk entry"


class TestSiteCacheModule:
    def test_a_killed_replace_leaves_the_old_file_intact(self, tmp_path, monkeypatch):
        from dashboard import site_cache

        path = tmp_path / "stories" / "some-story.json"
        assert site_cache.write_body(path, "key-1", {"slug": "some-story", "n": 1})
        assert site_cache.read_body(path, "key-1") == {"slug": "some-story", "n": 1}

        def killed(src, dst):
            raise OSError("simulated kill between tmp write and replace")

        monkeypatch.setattr(os, "replace", killed)
        assert site_cache.write_body(path, "key-2", {"slug": "some-story", "n": 2}) is False
        monkeypatch.undo()

        assert site_cache.read_body(path, "key-1") == {"slug": "some-story", "n": 1}
        assert [p.name for p in path.parent.iterdir()] == [path.name], "no tmp litter"

    def test_a_successful_write_leaves_only_the_final_file(self, tmp_path):
        from dashboard import site_cache

        path = tmp_path / "entities" / "openai.json"
        assert site_cache.write_body(path, "key", {"slug": "openai"})
        assert [p.name for p in path.parent.iterdir()] == [path.name]

    def test_version_or_key_mismatch_reads_as_a_miss(self, tmp_path):
        from dashboard import site_cache

        path = tmp_path / "stories" / "s.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"v": 0, "key": "k", "body": {"slug": "s"}}))
        assert site_cache.read_body(path, "k") is None

        assert site_cache.write_body(path, "k", {"slug": "s"})
        assert site_cache.read_body(path, "other-key") is None
        assert site_cache.read_body(path, "k") == {"slug": "s"}

    def test_garbage_and_non_dict_bodies_read_as_a_miss(self, tmp_path):
        from dashboard import site_cache

        path = tmp_path / "stories" / "s.json"
        path.parent.mkdir(parents=True)
        for blob in (b"", b"not json", b'"a string"', b'{"v": 1, "key": "k", "body": [1]}'):
            path.write_bytes(blob)
            assert site_cache.read_body(path, "k") is None, blob

    def test_a_traversal_slug_gets_no_path(self, tmp_path):
        from dashboard import site_cache

        for slug in ("../evil", "..", "a/b", "a\\b", ""):
            assert site_cache.cache_path(tmp_path, "stories", slug) is None, slug
        assert site_cache.cache_path(tmp_path, "not-a-kind", "openai") is None

        good = site_cache.cache_path(tmp_path, "stories", "openai-agent-runtime")
        assert good is not None
        assert good.name == "openai-agent-runtime.json"
        assert str(good).startswith(str(tmp_path.resolve()))

    def test_a_body_over_the_size_guard_is_refused_with_a_warning(self, tmp_path, caplog):
        import logging

        from dashboard import site_cache

        path = tmp_path / "stories" / "giant-story.json"
        body = {"slug": "giant-story", "body_markdown": "x" * (site_cache.MAX_BODY_BYTES + 1)}
        with caplog.at_level(logging.WARNING):
            assert site_cache.write_body(path, "k", body) is False
        assert not path.exists()
        assert any("giant-story" in record.message for record in caplog.records)

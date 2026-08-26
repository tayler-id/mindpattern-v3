"""Purge-on-publish and the deploy warm path (orchestrator/sync.py).

Covers what the site's hour-long ISR TTL used to hide: which paths a publish
changed, the authenticated POST that drops them from the Next.js cache, and
the exit code the deploy wrapper reads.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator import sync


def _write_story(story_dir: Path, slug: str, entities: list[str]) -> None:
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / f"{slug}.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "entity_refs": [{"slug": name, "name": name} for name in entities],
            }
        )
    )


@pytest.fixture
def reports_root(tmp_path: Path) -> Path:
    root = tmp_path / "reports" / "ramsay"
    story_dir = root / "site-stories" / "2026-08-25"
    _write_story(story_dir, "2026-08-25-first-story", ["anthropic", "nvidia", "ai"])
    _write_story(story_dir, "2026-08-25-second-story", ["anthropic", "unpublished-entity"])
    dossiers = root / "site-dossiers" / "entities"
    dossiers.mkdir(parents=True)
    for slug in ("anthropic", "nvidia", "ai"):
        (dossiers / f"{slug}.json").write_text("{}")
    return root


class TestChangedSitePaths:
    def test_entry_points_come_first(self, reports_root):
        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        assert paths[:4] == ["/", "/briefings", "/briefings/2026-08-25", "/blog/2026-08-25"]

    def test_includes_every_story_published_today(self, reports_root):
        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        assert "/s/2026-08-25-first-story" in paths
        assert "/s/2026-08-25-second-story" in paths

    def test_entity_pages_ranked_by_mentions_and_limited_to_published(self, reports_root):
        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        entity_paths = [p for p in paths if p.startswith("/e/")]
        # anthropic is named by both stories, so it leads. "ai" is under the
        # four-character floor and "unpublished-entity" has no dossier.
        assert entity_paths == ["/e/anthropic", "/e/nvidia"]

    def test_entity_cap_is_honoured(self, reports_root):
        paths = sync.changed_site_paths(
            "2026-08-25", reports_root=reports_root, max_entities=1
        )

        assert [p for p in paths if p.startswith("/e/")] == ["/e/anthropic"]

    def test_missing_story_directory_still_returns_entry_points(self, tmp_path):
        paths = sync.changed_site_paths("2026-08-25", reports_root=tmp_path)

        assert paths == ["/", "/briefings", "/briefings/2026-08-25", "/blog/2026-08-25"]

    def test_unreadable_story_is_skipped_not_fatal(self, reports_root):
        broken = reports_root / "site-stories" / "2026-08-25" / "broken.json"
        broken.write_text("{ not json")

        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        assert "/s/broken" not in paths
        assert "/s/2026-08-25-first-story" in paths

    def test_story_json_that_is_not_an_object_is_skipped(self, reports_root):
        story_dir = reports_root / "site-stories" / "2026-08-25"
        (story_dir / "list.json").write_text("[1, 2, 3]")

        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        assert "/s/list" not in paths
        assert "/s/2026-08-25-first-story" in paths

    def test_malformed_entity_refs_are_ignored(self, reports_root):
        story_dir = reports_root / "site-stories" / "2026-08-25"
        (story_dir / "odd.json").write_text(
            json.dumps({"slug": "2026-08-25-odd", "entity_refs": ["anthropic", None, {}]})
        )

        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        assert "/s/2026-08-25-odd" in paths

    def test_paths_are_unique(self, reports_root):
        paths = sync.changed_site_paths("2026-08-25", reports_root=reports_root)

        assert len(paths) == len(set(paths))


class TestRevalidateSitePaths:
    def test_posts_the_secret_in_a_header_and_never_in_the_body(self, monkeypatch):
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.data)
            captured["method"] = request.get_method()
            response = MagicMock()
            response.read.return_value = json.dumps(
                {"ok": True, "revalidated": ["/", "/s/one"], "rejected": []}
            ).encode()
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = sync.revalidate_site_paths(["/", "/s/one"], site_url="https://site.test")

        assert captured["url"] == "https://site.test/api/revalidate"
        assert captured["method"] == "POST"
        assert captured["headers"]["X-revalidate-secret"] == "s3cret"
        assert captured["body"] == {"paths": ["/", "/s/one"]}
        assert "s3cret" not in json.dumps(captured["body"])
        assert result["ok"] is True
        assert result["revalidated"] == 2
        assert result["batches"] == 1

    def test_splits_into_batches_under_the_route_cap(self, monkeypatch):
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")
        paths = [f"/s/story-{i}" for i in range(120)]
        sizes = []

        def fake_urlopen(request, timeout=None):
            sizes.append(len(json.loads(request.data)["paths"]))
            response = MagicMock()
            response.read.return_value = b'{"ok": true, "revalidated": [], "rejected": []}'
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = sync.revalidate_site_paths(paths, batch_size=50)

        assert sizes == [50, 50, 20]
        assert result["batches"] == 3
        assert result["sent"] == 120
        assert max(sizes) <= sync.REVALIDATE_BATCH

    def test_skips_when_no_secret_is_configured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MP_REVALIDATE_SECRET", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        with patch("urllib.request.urlopen") as urlopen:
            result = sync.revalidate_site_paths(["/"])

        urlopen.assert_not_called()
        assert result["skipped"] is True
        assert result["ok"] is False

    def test_reads_the_secret_from_the_local_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MP_REVALIDATE_SECRET", raising=False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        (tmp_path / ".mindpattern-revalidate-secret").write_text("file-secret\n")

        assert sync._revalidate_secret() == "file-secret"

    def test_transport_failure_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")

        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            result = sync.revalidate_site_paths(["/"])

        assert result["ok"] is False
        assert "connection refused" in result["error"]

    def test_error_text_never_carries_the_secret(self, monkeypatch):
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")

        with patch("urllib.request.urlopen", side_effect=OSError("bad token s3cret")):
            result = sync.revalidate_site_paths(["/"])

        assert "s3cret" not in result["error"]
        assert "[redacted]" in result["error"]

    def test_rejected_paths_make_the_call_not_ok(self, monkeypatch):
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"ok": False, "revalidated": ["/"], "rejected": ["/nope"]}
        ).encode()
        response.__enter__ = lambda self: self
        response.__exit__ = lambda self, *args: False

        with patch("urllib.request.urlopen", return_value=response):
            result = sync.revalidate_site_paths(["/", "/nope"])

        assert result["ok"] is False
        assert result["rejected"] == 1

    def test_empty_path_list_does_not_call_the_site(self, monkeypatch):
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")

        with patch("urllib.request.urlopen") as urlopen:
            result = sync.revalidate_site_paths(["not-a-path"])

        urlopen.assert_not_called()
        assert result["ok"] is False

    def test_sandbox_refuses_to_purge_the_live_site(self, monkeypatch):
        """Every other production-mutating call in sync.py refuses. So does this.

        A purge drops entries from the real mindpattern.ai CDN cache, and
        warm_public_site is reachable from runner.py and from the CLI without
        going through deploy/deploy.sh, which is where the MP_SANDBOX check
        used to be.
        """
        monkeypatch.setenv("MP_SANDBOX", "1")
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")

        with patch("urllib.request.urlopen") as urlopen:
            result = sync.revalidate_site_paths(["/", "/e/anthropic"])

        urlopen.assert_not_called()
        assert result["skipped"] is True
        assert result["error"] == "MP_SANDBOX=1"

    @pytest.mark.parametrize("junk", [None, 123, ["/nested"], {"a": 1}])
    def test_non_string_paths_never_raise(self, monkeypatch, junk):
        """The docstring says "never raises" without qualification.

        `dict.fromkeys` raises TypeError on an unhashable element and
        `.startswith` raises AttributeError on a non-string one, so the filter
        has to check the type before it does either.
        """
        monkeypatch.setenv("MP_REVALIDATE_SECRET", "s3cret")
        sent: list[list[str]] = []

        def fake_urlopen(request, timeout=None):
            sent.append(json.loads(request.data.decode())["paths"])
            response = MagicMock()
            response.read.return_value = json.dumps(
                {"ok": True, "revalidated": ["/"], "rejected": []}
            ).encode()
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = sync.revalidate_site_paths([junk, "/"])

        assert sent == [["/"]], "the junk element must be dropped, not sent"
        assert result["ok"] is True


class TestSitemapSitePaths:
    """scope="site" after a Vercel deploy, which drops the whole ISR cache."""

    # The path set comes from the backend graph, not the site's sitemap.xml.
    # That route carries revalidate=3600 behind Vercel's CDN, and on 2026-08-26
    # the crawler got a HIT on the previous 187-URL version and warmed 36 blog
    # dates over a site that was entirely cold.
    GRAPH = {
        "stories": [
            {"slug": "old", "issue_date": "2026-01-01"},
            {"slug": "new", "issue_date": "2026-08-25"},
            {"slug": "mid", "issue_date": "2026-05-01"},
        ],
        "entities": ["anthropic", "nvidia"],
        "sources": ["openai.com"],
        "briefings": ["2026-01-01", "2026-08-25"],
    }

    def _paths(self, **kwargs):
        with patch.object(sync, "_backend_sitemap_graph", return_value=self.GRAPH):
            return sync.sitemap_site_paths("https://site.test", **kwargs)

    def test_entry_points_and_every_entity_come_first(self):
        paths = self._paths()

        entity_positions = [i for i, p in enumerate(paths) if p.startswith("/e/")]
        story_positions = [i for i, p in enumerate(paths) if p.startswith("/s/")]
        assert paths[0] == "/"
        assert len(entity_positions) == 2, "the sitemap advertises them, so warm all of them"
        assert max(entity_positions) < min(story_positions)

    def test_the_long_tail_is_capped_newest_first(self):
        paths = self._paths(story_limit=2, archive_limit=1)

        assert [p for p in paths if p.startswith("/s/")] == ["/s/new", "/s/mid"]
        assert [p for p in paths if p.startswith("/briefings/")] == ["/briefings/2026-08-25"]

    def test_an_empty_graph_raises_rather_than_warming_nothing(self):
        with patch.object(sync, "_backend_sitemap_graph", return_value={"stories": []}):
            with pytest.raises(RuntimeError):
                sync.sitemap_site_paths("https://site.test")

    def test_the_cdn_copy_of_the_sitemap_is_never_read(self):
        """The bug this replaces: warming targets read through a CDN cache."""
        with patch.object(sync, "_backend_sitemap_graph", return_value=self.GRAPH), \
             patch("urllib.request.urlopen") as urlopen:
            sync.sitemap_site_paths("https://site.test")
        assert not urlopen.called


class TestWarmPublicSiteScopes:
    """The 2026-08-26 blocker: --warm-only reported success over a cold site."""

    def _run(self, *, scope, reports_root, sitemap_paths=None, **kwargs):
        crawled: list[str] = []

        def fake_urlopen(url, timeout=None):
            target = url if isinstance(url, str) else url.full_url
            response = MagicMock()
            if target.endswith("/api/warmup/status"):
                response.read.return_value = b'{"phase": "done"}'
            elif "/api/stories" in target:
                response.read.return_value = json.dumps({"items": []}).encode()
            else:
                crawled.append(target)
                response.read.return_value = b"<html></html>"
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch.object(
            sync, "sitemap_site_paths", return_value=list(sitemap_paths or [])
        ), patch.object(
            sync,
            "revalidate_site_paths",
            return_value={"ok": True, "revalidated": 0, "skipped": False, "error": None},
        ) as purge:
            result = sync.warm_public_site(
                date="2026-08-25",
                site_url="https://site.test",
                backend_url="https://backend.test",
                reports_root=reports_root,
                scope=scope,
                **kwargs,
            )
        return result, crawled, purge

    def test_a_day_with_no_publish_warms_the_whole_site_not_four_paths(self, tmp_path):
        """The exact failure: no site-stories directory for today.

        changed_site_paths then yields ["/", "/briefings", "/briefings/<date>",
        "/blog/<date>"], all four answer 200, and the old check reported
        "purged and warm" while ~780 story pages and 86 entity pages were cold.
        """
        empty = tmp_path / "reports" / "ramsay"
        empty.mkdir(parents=True)

        changed, _, _ = self._run(scope="changed", reports_root=empty)
        assert changed["requested"] == 4

        site_paths = ["/", "/e/anthropic", "/e/nvidia", "/s/new"]
        wide, crawled, _ = self._run(
            scope="site", reports_root=empty, sitemap_paths=site_paths
        )
        assert wide["requested"] == len(site_paths)
        assert crawled == [f"https://site.test{p}" for p in site_paths]

    def test_the_site_scope_never_purges(self, tmp_path):
        """A Vercel deploy already dropped every entry a purge would drop."""
        empty = tmp_path / "reports" / "ramsay"
        empty.mkdir(parents=True)

        result, _, purge = self._run(
            scope="site", reports_root=empty, sitemap_paths=["/", "/e/anthropic"]
        )

        purge.assert_not_called()
        assert "revalidate" not in result

    def test_an_unreadable_sitemap_is_a_failure_not_an_empty_warm(self, tmp_path):
        empty = tmp_path / "reports" / "ramsay"
        empty.mkdir(parents=True)

        with patch("urllib.request.urlopen") as urlopen, patch.object(
            sync, "sitemap_site_paths", side_effect=OSError("502")
        ):
            response = MagicMock()
            response.read.return_value = b'{"phase": "done"}'
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            urlopen.return_value = response
            result = sync.warm_public_site(
                date="2026-08-25",
                site_url="https://site.test",
                backend_url="https://backend.test",
                reports_root=empty,
                scope="site",
            )

        assert result["error"].startswith("sitemap unavailable")
        assert result["crawled"] == 0
        assert result["requested"] == 0


class TestWarmPublicSiteBudget:
    def test_the_crawl_stops_at_its_deadline_and_says_what_it_skipped(self, tmp_path):
        """_get allows 45s per request; an unbounded loop blocks SYNC for an hour."""
        empty = tmp_path / "reports" / "ramsay"
        empty.mkdir(parents=True)
        paths = [f"/s/story-{i}" for i in range(40)]

        def fake_urlopen(url, timeout=None):
            target = url if isinstance(url, str) else url.full_url
            response = MagicMock()
            if target.endswith("/api/warmup/status"):
                response.read.return_value = b'{"phase": "done"}'
            else:
                response.read.return_value = b"<html></html>"
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            return response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch.object(
            sync, "sitemap_site_paths", return_value=paths
        ):
            result = sync.warm_public_site(
                date="2026-08-25",
                site_url="https://site.test",
                backend_url="https://backend.test",
                reports_root=empty,
                scope="site",
                crawl_budget_minutes=0.0,
            )

        assert result["crawled"] == 0
        assert result["skipped_pages"] == 40
        assert result["requested"] == 40


class TestWarmPublicSitePurges:
    """warm_public_site must purge before it crawls, or it re-caches yesterday."""

    def _run(self, reports_root, *, crawl_error=None):
        order: list[str] = []

        def fake_get(url, timeout=45.0):
            order.append(f"GET {url}")
            if url.endswith("/api/warmup/status"):
                return b'{"phase": "done"}'
            if "/api/stories" in url:
                return json.dumps({"items": []}).encode()
            if crawl_error and crawl_error in url:
                raise OSError("boom")
            return b"<html></html>"

        def fake_urlopen(url, timeout=None):
            response = MagicMock()
            response.read.return_value = fake_get(
                url if isinstance(url, str) else url.full_url, timeout
            )
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            return response

        def fake_revalidate(paths, **kwargs):
            order.append("PURGE")
            return {"ok": True, "revalidated": len(paths), "skipped": False, "error": None}

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch.object(
            sync, "revalidate_site_paths", side_effect=fake_revalidate
        ) as purge:
            result = sync.warm_public_site(
                date="2026-08-25",
                site_url="https://site.test",
                backend_url="https://backend.test",
                reports_root=reports_root,
            )
        return result, order, purge

    def test_purge_happens_before_the_crawl(self, reports_root):
        _, order, _ = self._run(reports_root)

        first_page_crawl = next(
            i for i, entry in enumerate(order) if entry.startswith("GET https://site.test/")
        )
        assert order.index("PURGE") < first_page_crawl

    def test_purge_covers_stories_home_briefing_and_entities(self, reports_root):
        _, _, purge = self._run(reports_root)

        paths = purge.call_args.args[0]
        assert "/" in paths
        assert "/briefings/2026-08-25" in paths
        assert "/s/2026-08-25-first-story" in paths
        assert "/e/anthropic" in paths

    def test_every_purged_path_is_crawled_back_warm(self, reports_root):
        _, order, purge = self._run(reports_root)

        crawled = {
            entry[len("GET https://site.test") :]
            for entry in order
            if entry.startswith("GET https://site.test")
        }
        for path in purge.call_args.args[0]:
            assert path in crawled, f"purged but never re-crawled: {path}"

    def test_result_reports_the_purge(self, reports_root):
        result, _, _ = self._run(reports_root)

        assert result["revalidate"]["ok"] is True
        assert result["failed"] == 0
        assert result["crawled"] > 0

    def test_revalidate_can_be_turned_off(self, reports_root):
        with patch("urllib.request.urlopen") as urlopen, patch.object(
            sync, "revalidate_site_paths"
        ) as purge:
            response = MagicMock()
            response.read.return_value = b'{"phase": "done"}'
            response.__enter__ = lambda self: self
            response.__exit__ = lambda self, *args: False
            urlopen.return_value = response

            result = sync.warm_public_site(
                date="2026-08-25",
                reports_root=reports_root,
                revalidate=False,
            )

        purge.assert_not_called()
        assert "revalidate" not in result


class TestWarmCli:
    """deploy/deploy.sh reads this exit code. A cold site must not look green."""

    def test_returns_zero_when_everything_warmed(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={
                "requested": 12,
                "crawled": 12,
                "failed": 0,
                "skipped_pages": 0,
                "revalidate": {"ok": True},
            },
        ):
            assert sync.warm_cli(["--date", "2026-08-25"]) == 0

    def test_returns_nonzero_when_a_page_failed(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={
                "requested": 12,
                "crawled": 11,
                "failed": 1,
                "skipped_pages": 0,
                "revalidate": {"ok": True},
            },
        ):
            assert sync.warm_cli(["--date", "2026-08-25"]) == 1

    def test_returns_nonzero_when_nothing_was_crawled(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={"requested": 12, "crawled": 0, "failed": 0, "skipped_pages": 12},
        ):
            assert sync.warm_cli(["--date", "2026-08-25"]) == 1

    def test_returns_nonzero_when_the_budget_cut_the_crawl_short(self):
        """Coverage, not liveness. Half a warm site is not a warm site."""
        with patch.object(
            sync,
            "warm_public_site",
            return_value={
                "requested": 368,
                "crawled": 40,
                "failed": 0,
                "skipped_pages": 328,
                "revalidate": {"ok": True},
            },
        ):
            assert sync.warm_cli(["--date", "2026-08-25"]) == 1

    def test_returns_nonzero_when_there_was_nothing_to_warm(self):
        """The 2026-08-26 bug: "4 warmed, 0 failed" over a fully cold site.

        A run that asks for nothing and crawls nothing has not warmed the
        site, and the deploy wrapper must not read it as success.
        """
        with patch.object(
            sync,
            "warm_public_site",
            return_value={"requested": 0, "crawled": 0, "failed": 0, "skipped_pages": 0},
        ):
            assert sync.warm_cli(["--date", "2026-08-25", "--scope", "site"]) == 1

    def test_returns_nonzero_when_the_path_set_could_not_be_built(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={
                "requested": 0,
                "crawled": 0,
                "failed": 0,
                "error": "sitemap unavailable: HTTPError: 500",
            },
        ):
            assert sync.warm_cli(["--scope", "site"]) == 1

    def test_returns_nonzero_when_the_purge_failed(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={
                "requested": 12,
                "crawled": 12,
                "failed": 0,
                "skipped_pages": 0,
                "revalidate": {"ok": False, "skipped": False, "error": "401"},
            },
        ):
            assert sync.warm_cli(["--date", "2026-08-25"]) == 1

    def test_an_unconfigured_purge_is_not_a_deploy_failure(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={
                "requested": 12,
                "crawled": 12,
                "failed": 0,
                "skipped_pages": 0,
                "revalidate": {"ok": False, "skipped": True, "error": "no secret"},
            },
        ):
            assert sync.warm_cli(["--date", "2026-08-25"]) == 0

    def test_passes_its_flags_through(self):
        with patch.object(
            sync,
            "warm_public_site",
            return_value={"requested": 1, "crawled": 1, "failed": 0, "skipped_pages": 0},
        ) as warm:
            sync.warm_cli(
                [
                    "--date",
                    "2026-08-25",
                    "--site-url",
                    "https://site.test",
                    "--backend-wait-minutes",
                    "2",
                    "--scope",
                    "site",
                    "--crawl-budget-minutes",
                    "3",
                    "--no-revalidate",
                ]
            )

        kwargs = warm.call_args.kwargs
        assert kwargs["date"] == "2026-08-25"
        assert kwargs["site_url"] == "https://site.test"
        assert kwargs["backend_wait_minutes"] == 2
        assert kwargs["revalidate"] is False
        assert kwargs["scope"] == "site"
        assert kwargs["crawl_budget_minutes"] == 3

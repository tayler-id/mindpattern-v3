"""The reader path survives a restart. "Always up, every link quick," as tests.

Every public cache in dashboard/routes/api.py is an in-memory dict. A deploy
or a crash empties all of them at once, and the first request after boot then
pays the full computes itself: _build_all_public_stories reads every story
JSON on the volume (6,897 files, measured 5,471ms cold and 1ms warm) and
_build_entity_issue_index walks all 185 issue dates (2.9s cold).
dashboard/warmup.py refills the dicts after boot, but it takes minutes, and
until it finishes real readers pay the cold costs.

The Fly machine mounts a persistent volume at /data, and the Dockerfile
symlinks /app/data and /app/reports onto it, so anything the backend writes
under DATA_DIR survives a restart. dashboard/site_cache.py keeps finished
story and entity responses there, under DATA_DIR/<user>/site-cache. These
tests reroot that store by patching api.DATA_DIR at a tmp tree, the same
mechanism the conftest guard relies on, and they are the executable contract
for the disk store, end to end through the real handlers:

1. A process that has served a story and an entity page once must, after a
   restart that keeps the disk, serve them again without replaying the
   full-corpus computes. The computes are monkeypatched to fail loudly, so a
   regression names the compute that ran instead of just running slow.
2. With no disk store at all and memory empty, the handlers still answer
   correctly. The slow path is the fallback and it has to stay whole.
3. A corrupt or zero-byte disk entry is served around, and the entry is
   rewritten. Truncated artifacts have shipped twice (2026-07-27, 2026-08-04),
   so no *.json under either tree may ever be left at zero bytes.

Real FastAPI app, real TestClient, real fixture trees. The handlers
themselves are never mocked.
"""

import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from kg.schema import init_kg_schema

ISSUE_DATES = ["2026-06-10", "2026-06-11", "2026-06-12"]
STORY_SLUG = "openai-agent-runtime"
STORY_URL = f"/api/stories/{STORY_SLUG}?user=ramsay"
ENTITY_URL = "/api/entities/openai?user=ramsay&limit=40"


def _report_markdown(date: str, index: int) -> str:
    """A report the issue splitter turns into story units with entity refs."""
    return (
        f"# Rabbit Hole briefing {date}\n\n"
        "## Agent Platforms\n\n"
        f"**OpenAI shipped agent runtime changes on {date}.** "
        "OpenAI and Anthropic both moved runtime reliability into buying criteria. "
        + "Full dynamic story body sentence. " * 40
        + "Source: [OpenAI](https://openai.com/news/agents).\n\n"
        "## Tooling\n\n"
        f"**Vercel Platform shipped build tooling on {date}.** "
        f"Vercel Platform changed how deploy caches behave for run {index}. "
        + "Second story body sentence. " * 40
        + "Source: [Vercel](https://vercel.com/changelog).\n"
    )


def _create_memory_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    # Production databases are WAL already. Creating the fixture in WAL keeps
    # the serving layer's own "PRAGMA journal_mode=WAL" a no-op, so the file's
    # mtime, which feeds the cache invalidation key, never moves at serve time.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            agent TEXT,
            title TEXT,
            summary TEXT,
            importance TEXT,
            category TEXT,
            source_url TEXT,
            source_name TEXT,
            created_at TEXT
        );
        CREATE TABLE findings_embeddings (
            finding_id INTEGER PRIMARY KEY,
            embedding BLOB
        );
        CREATE TABLE entity_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a TEXT NOT NULL,
            entity_a_type TEXT,
            relationship TEXT NOT NULL,
            entity_b TEXT NOT NULL,
            entity_b_type TEXT,
            finding_id INTEGER,
            created_at TEXT
        );
        """
    )
    init_kg_schema(conn)
    conn.executemany(
        """INSERT INTO findings
           (id, run_date, agent, title, summary, importance, category,
            source_url, source_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                100 + index,
                date,
                "fixture-agent",
                f"OpenAI runtime reliability update {index}",
                f"OpenAI moved runtime reliability into buying criteria on {date}.",
                "high",
                "agents",
                "https://openai.com/news/agents",
                "OpenAI",
                f"{date}T12:00:00",
            )
            for index, date in enumerate(ISSUE_DATES)
        ],
    )
    conn.executemany(
        """INSERT INTO entity_graph
           (entity_a, entity_a_type, relationship, entity_b, entity_b_type,
            finding_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                "OpenAI",
                "company",
                "mentions",
                "Vercel Platform",
                "company",
                100 + index,
                f"{date}T12:00:00",
            )
            for index, date in enumerate(ISSUE_DATES)
        ],
    )
    openai_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("OpenAI", "Company", 12, 0.94, ISSUE_DATES[0], ISSUE_DATES[-1]),
    ).lastrowid
    vercel_id = conn.execute(
        """INSERT INTO kg_entities
           (canonical_name, entity_type, mention_count, importance, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("Vercel Platform", "Company", 6, 0.61, ISSUE_DATES[0], ISSUE_DATES[-1]),
    ).lastrowid
    conn.executemany(
        "INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (?, ?)",
        [(openai_id, "OpenAI"), (vercel_id, "Vercel Platform")],
    )
    conn.execute(
        """INSERT INTO kg_edges
           (subject_id, predicate, object_id, fact_text, fact_type, confidence,
            finding_id, valid_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            openai_id,
            "RELEASED",
            vercel_id,
            "OpenAI released runtime reliability updates.",
            "Fact",
            0.94,
            100,
            ISSUE_DATES[-1],
        ),
    )
    conn.commit()
    conn.close()


def _story_artifact() -> dict:
    """A publishable site-story artifact, the shape the pipeline writes."""
    return {
        "kind": "site_story",
        "id": STORY_SLUG,
        "slug": STORY_SLUG,
        "status": "published",
        "confidence": "high",
        "issue_date": "2026-06-12",
        "title": "OpenAI agent runtime reliability becomes a public benchmark",
        "dek": "A source-backed Rabbit Hole story artifact.",
        "summary": "OpenAI made agent runtime reliability a buyer-visible benchmark.",
        "take": "Runtime reliability is moving from plumbing to buying criteria.",
        "why_now": "The corpus connected product updates, sources, and recurrence.",
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
            "generated_at": "2026-06-12T12:00:00+00:00",
            "input_artifacts": [],
            "source_finding_ids": [101, 102],
            "source_issue_dates": ["2026-06-12"],
            "redaction_status": "passed",
            "ai_generated": True,
            "human_approved": False,
        },
        "json_ld_ready": True,
    }


def _simulate_restart(api_routes) -> None:
    """What a deploy does to the process: every module-level dict goes away.

    Clears by name pattern rather than a hand-kept list so a cache added
    tomorrow is covered the day it lands.
    """
    for name, value in list(vars(api_routes).items()):
        if name.endswith(("_CACHE", "_INDEX", "_LOCKS")) and isinstance(value, dict):
            value.clear()


def _forbid(monkeypatch, target, name: str) -> None:
    """The named compute must not run. If it does, say so by name."""

    def tripped(*args, **kwargs):
        raise AssertionError(
            f"{name} ran on the post-restart read path. With the disk store "
            "intact, a restarted process must serve story and entity pages "
            "from disk, not replay the full-corpus build the first reader "
            "of the day cannot afford."
        )

    monkeypatch.setattr(target, name, tripped)


def _json_files(*roots: Path) -> dict[str, int]:
    """Relative path -> size for every file under the given roots."""
    inventory: dict[str, int] = {}
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file():
                inventory[str(path.relative_to(root.parent))] = path.stat().st_size
    return inventory


def _written_since(before: dict[str, int], *roots: Path) -> list[Path]:
    """Files the serving layer created since the snapshot.

    Sqlite sidecars of the fixture databases are journal noise, not entries.
    Roots may nest (the site-cache root sits inside the data root), so each
    file is reported once.
    """
    written: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            if str(path.relative_to(root.parent)) in before:
                continue
            if "memory.db" in path.name or "traces.db" in path.name:
                continue
            written.append(path)
    return written


def _assert_no_zero_byte_json(*roots: Path) -> None:
    """A killed process must never leave a truncated file a reader is served."""
    empty = [
        str(path)
        for root in roots
        for path in root.rglob("*.json")
        if path.is_file() and path.stat().st_size == 0
    ]
    assert not empty, f"zero-byte artifacts on the serving path: {empty}"


MISSING_DISK_STORE = (
    "The warm pass persisted nothing to the site cache. Every in-memory "
    "response cache empties on a deploy or crash, so without the disk store "
    "the first reader of the day pays the 5.4s full-corpus rebuild. The "
    "handlers must write their finished payloads through "
    "dashboard/site_cache.py (atomically: tmp file, then os.replace) so a "
    "restart reads files instead of recomputing."
)


@pytest.fixture
def reader_site(tmp_path, monkeypatch):
    from dashboard import warmup
    from dashboard.routes import api as api_routes

    # The background warm-up task belongs to production boot, not to these
    # tests. It would race the restart simulation below.
    async def _no_warmup():
        return None

    monkeypatch.setattr(warmup, "startup_warmup", _no_warmup)

    data_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"
    user_data = data_dir / "ramsay"
    user_reports = reports_dir / "ramsay"
    user_data.mkdir(parents=True)
    user_reports.mkdir(parents=True)

    _create_memory_db(user_data / "memory.db")
    for index, date in enumerate(ISSUE_DATES):
        (user_reports / f"{date}.md").write_text(_report_markdown(date, index))
    story_dir = user_reports / "site-stories" / "2026-06-12"
    story_dir.mkdir(parents=True)
    (story_dir / f"{STORY_SLUG}.json").write_text(json.dumps(_story_artifact()))

    # The disk store lands under the patched DATA_DIR at
    # DATA_DIR/<user>/site-cache; nothing reads an env var for it. The
    # conftest guard reroots only tests that leave DATA_DIR at the repo tree,
    # so patching DATA_DIR below is the whole isolation mechanism, and this
    # path is where the tests inspect what the serving layer writes.
    cache_dir = user_data / "site-cache"
    cache_dir.mkdir()

    monkeypatch.setattr(api_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_routes, "REPORTS_DIR", reports_dir)
    api_routes._reset_fingerprint_cache()
    _simulate_restart(api_routes)

    from dashboard.app import app

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            api=api_routes,
            data_dir=data_dir,
            reports_dir=reports_dir,
            cache_dir=cache_dir,
        )

    _simulate_restart(api_routes)
    api_routes._reset_fingerprint_cache()


def test_with_no_disk_store_and_no_memory_the_slow_path_still_answers(reader_site):
    """The fallback compute path is the floor. It has to stay whole.

    Archive gaps are real: most of the 6,897 stories predate any precompute,
    so a slug with no disk entry must still come back correct, just slower.
    """
    story = reader_site.client.get(STORY_URL)
    assert story.status_code == 200
    body = story.json()
    assert body["slug"] == STORY_SLUG
    assert body["title"] == "OpenAI agent runtime reliability becomes a public benchmark"
    assert body["source_refs"], "a public story must carry its source trail"
    assert body["claim_evidence"], "a public story must carry claim evidence"
    assert "related_paths" in body

    entity = reader_site.client.get(ENTITY_URL)
    assert entity.status_code == 200
    page = entity.json()
    assert page["name"] == "OpenAI"
    assert page["story_units"], "the issue archive names this entity"
    assert "newsletter_issues" in page["graph_sources"]
    assert page["counts"]["story_units"] == len(page["story_units"])


def test_a_restart_with_the_disk_store_intact_never_replays_the_full_corpus_build(
    reader_site, monkeypatch
):
    """Warm once, restart, answer from disk. The expensive computes stay cold.

    _build_all_public_stories and _build_entity_issue_index are patched to
    fail by name, so the assertion that trips reads "this compute ran" rather
    than a wall-clock number that only reproduces on the Fly volume.
    """
    api = reader_site.api
    roots = (reader_site.data_dir, reader_site.reports_dir, reader_site.cache_dir)

    before = _json_files(*roots)
    warm_story = reader_site.client.get(STORY_URL)
    warm_entity = reader_site.client.get(ENTITY_URL)
    assert warm_story.status_code == 200
    assert warm_entity.status_code == 200

    assert _written_since(before, *roots), MISSING_DISK_STORE

    _simulate_restart(api)
    _forbid(monkeypatch, api, "_build_all_public_stories")
    _forbid(monkeypatch, api, "_build_entity_issue_index")

    started = time.perf_counter()
    cold_story = reader_site.client.get(STORY_URL)
    cold_entity = reader_site.client.get(ENTITY_URL)
    elapsed = time.perf_counter() - started

    assert cold_story.status_code == 200
    assert cold_entity.status_code == 200
    # A restart changes nothing a reader can see.
    assert cold_story.json() == warm_story.json()
    assert cold_entity.json() == warm_entity.json()
    # Generous for CI noise. On fixture-sized data the disk path is
    # milliseconds; the patched computes above carry the real budget.
    assert elapsed < 2.0, f"post-restart reads took {elapsed:.2f}s on tiny fixtures"

    _assert_no_zero_byte_json(*roots)


def test_a_corrupt_disk_entry_is_served_around_and_rewritten(reader_site):
    """Disk rot must cost one recompute, never a wrong or broken page.

    Zero-byte artifacts have shipped twice (2026-07-27, 2026-08-04). One
    corrupted entry here is truncated JSON and one is empty, the two shapes a
    killed writer actually leaves behind.
    """
    api = reader_site.api
    roots = (reader_site.data_dir, reader_site.reports_dir, reader_site.cache_dir)

    before = _json_files(*roots)
    warm_story = reader_site.client.get(STORY_URL)
    warm_entity = reader_site.client.get(ENTITY_URL)
    assert warm_story.status_code == 200
    assert warm_entity.status_code == 200

    entries = _written_since(before, *roots)
    assert entries, MISSING_DISK_STORE

    garbage = b'{"truncated'
    for index, path in enumerate(entries):
        path.write_bytes(b"" if index == 0 else garbage)

    _simulate_restart(api)

    cold_story = reader_site.client.get(STORY_URL)
    cold_entity = reader_site.client.get(ENTITY_URL)
    assert cold_story.status_code == 200
    assert cold_entity.status_code == 200
    assert cold_story.json() == warm_story.json()
    assert cold_entity.json() == warm_entity.json()

    # The read that hit the rot repairs it: every corrupted entry is either
    # rewritten whole or removed, never left for the next reader to trip on.
    for path in entries:
        if not path.exists():
            continue
        content = path.read_bytes()
        assert content != garbage and content != b"", (
            f"{path} still holds the corrupt bytes after being served around"
        )
        if path.suffix == ".json":
            json.loads(content)

    _assert_no_zero_byte_json(*roots)

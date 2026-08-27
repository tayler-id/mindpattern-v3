"""Internal analytics dash: private, summarizes reader behavior."""

import time

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_EVENTS_DB", str(tmp_path / "site_events.db"))
    return TestClient(app)


def test_summary_requires_auth(client):
    assert client.get("/api/site-analytics/summary").status_code == 401
    assert client.get("/site-analytics").status_code == 401


def test_summary_shape_with_bearer(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "reader01"})
    client.post("/api/event", json={"type": "subscribe_submitted", "target": "band"})
    client.post("/api/event", json={"type": "subscribe_success", "target": "band"})

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["top_stories"][0]["target"] == "hot-story"
    assert payload["subscribe"]["conversion"] == 1.0
    assert payload["totals"]["events"] == 3

    page = client.get("/site-analytics", headers=headers)
    assert page.status_code == 200
    assert "hot-story" in page.text


def test_summary_splits_crawlers_from_humans(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "agent_hit", "target": "GPTBot", "path": "/s/hot-story"})
    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "reader01"})
    client.post("/api/event", json={"type": "scroll_depth", "target": "hot-story", "value": 50})
    client.post("/api/event", json={"type": "related_click", "target": "next-story"})

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["totals"]["events"] == 4
    assert payload["totals"]["crawler_hits"] == 1
    assert payload["totals"]["human_events"] == 3
    assert payload["totals"]["reader_events"] == 3
    assert payload["totals"]["owner_events"] == 0
    assert payload["totals"]["crawler_share"] == 25.0
    assert payload["totals"]["story_views"] == 1
    assert payload["agents"]["by_bot"][0]["target"] == "GPTBot"
    # daily series covers today with the bot/reader/owner split
    assert payload["daily"][-1]["bots"] == 1
    assert payload["daily"][-1]["readers"] == 3
    assert payload["daily"][-1]["owner"] == 0
    assert payload["daily"][-1]["views"] == 1
    # human event mix excludes crawler hits
    assert {m["type"] for m in payload["mix"]} == {"story_view", "scroll_depth", "related_click"}
    assert payload["scroll"] == [{"value": 50, "n": 1}]


def test_page_view_counts_reader_and_has_human_label(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={
        "type": "page_view",
        "target": "home",
        "path": "/",
        "anon_id": "reader01",
    })

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["totals"]["readers"] == 1
    assert payload["totals"]["reader_events"] == 1
    assert payload["totals"]["story_views"] == 0
    page_views = next(item for item in payload["mix"] if item["type"] == "page_view")
    assert page_views == {
        "type": "page_view",
        "label": "Page views",
        "count": 1,
        "owner_count": 0,
    }


def test_referrers_deduplicate_identified_non_owner_page_view_readers(
    client, monkeypatch
):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    for payload in (
        {"type": "page_view", "path": "/", "anon_id": "reader01",
         "ref_domain": "linkedin.com"},
        {"type": "page_view", "path": "/topics/agents", "anon_id": "reader01",
         "ref_domain": "linkedin.com"},
        {"type": "page_view", "path": "/", "anon_id": "reader02",
         "ref_domain": "linkedin.com"},
        {"type": "page_view", "path": "/", "anon_id": "reader03",
         "ref_domain": "news.ycombinator.com"},
        {"type": "story_view", "target": "story", "anon_id": "reader04",
         "ref_domain": "linkedin.com"},
        {"type": "related_click", "target": "story", "anon_id": "reader05",
         "ref_domain": "linkedin.com"},
        {"type": "page_view", "path": "/", "anon_id": "reader06",
         "ref_domain": "linkedin.com", "owner": 1},
        {"type": "page_view", "path": "/", "anon_id": "short",
         "ref_domain": "linkedin.com"},
    ):
        client.post("/api/event", json=payload)

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["referrers"] == [
        {"ref_domain": "linkedin.com", "count": 2,
         "new_count": 2, "returning_count": 0},
        {"ref_domain": "news.ycombinator.com", "count": 1,
         "new_count": 1, "returning_count": 0},
    ]
    page = client.get("/site-analytics?window=7d", headers=headers)
    assert 'unit: "unique readers"' in page.text
    assert 'unit: "visits"' not in page.text


def test_owner_events_marked_not_counted_as_readers(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "visitor1"})
    client.post("/api/event", json={"type": "story_view", "target": "hot-story", "anon_id": "tayler01", "owner": 1})
    client.post("/api/event", json={"type": "story_view", "target": "own-story", "anon_id": "tayler01", "owner": 1})
    client.post("/api/event", json={"type": "search_query", "target": "agents", "anon_id": "tayler01", "owner": 1})

    payload = client.get("/api/site-analytics/summary?window=7d", headers=headers).json()
    assert payload["totals"]["owner_events"] == 3
    assert payload["totals"]["reader_events"] == 1
    assert payload["totals"]["readers"] == 1  # tayler01 is not a reader
    assert payload["totals"]["story_views"] == 1  # owner views not reader views
    hot = next(s for s in payload["top_stories"] if s["target"] == "hot-story")
    assert hot["views"] == 1 and hot["owner_views"] == 1
    own = next(s for s in payload["top_stories"] if s["target"] == "own-story")
    assert own["views"] == 0 and own["owner_views"] == 1
    assert payload["daily"][-1]["owner"] == 3
    assert payload["search_terms"][0]["count"] == 0
    assert payload["search_terms"][0]["owner_count"] == 1


def test_page_escapes_user_supplied_targets(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    headers = {"Authorization": "Bearer test-token"}

    client.post("/api/event", json={"type": "search_query", "target": "<script>alert(1)</script>"})

    page = client.get("/site-analytics", headers=headers)
    assert page.status_code == 200
    assert "<script>alert" not in page.text  # injected JSON escapes all '<'


def test_dash_query_token(client, monkeypatch):
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "browser-token")
    assert client.get("/site-analytics?token=wrong").status_code == 401
    ok = client.get("/site-analytics?token=browser-token")
    assert ok.status_code == 200
    assert "token=browser-token" in ok.text  # window links stay authed
    # query token must NOT unlock other private routes
    assert client.get("/api/site-analytics/summary?token=browser-token").status_code == 401


# --- New vs returning readers -------------------------------------------------
#
# COUNT(DISTINCT anon_id) inside a window answers "unique in window", not
# "new". These pin the difference. Seeding goes straight to the store because
# /api/event always stamps ts=now and the whole question is about timestamps
# either side of the window boundary.


def _seed(db_path, rows):
    """Insert (anon_id, ts_offset_seconds, [type], [ref_domain], [owner],
    [durable]) tuples."""
    from memory.events_db import open_events_db

    now = int(time.time())
    conn = open_events_db(db_path)
    try:
        for row in rows:
            anon, offset = row[0], row[1]
            event_type = row[2] if len(row) > 2 else "page_view"
            ref = row[3] if len(row) > 3 else ""
            owner = row[4] if len(row) > 4 else 0
            durable = row[5] if len(row) > 5 else 0
            conn.execute(
                "INSERT INTO events (ts, type, target, path, ref_domain,"
                " anon_id, value, owner, durable) VALUES (?,?,?,?,?,?,0,?,?)",
                (now + offset, event_type, "", "/", ref, anon, owner, durable),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def authed(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_EVENTS_DB", str(tmp_path / "site_events.db"))
    import dashboard.auth as auth
    monkeypatch.setattr(auth, "_token_valid", lambda token: token == "test-token")
    http = TestClient(app)
    db_path = tmp_path / "site_events.db"

    def summary(window="7d"):
        return http.get(
            f"/api/site-analytics/summary?window={window}",
            headers={"Authorization": "Bearer test-token"},
        ).json()

    return http, db_path, summary


def test_new_vs_returning_split_separates_first_timers_from_regulars(authed):
    _, db_path, summary = authed
    _seed(db_path, [
        ("regular01", -30 * 86400),   # first seen a month ago
        ("regular01", -2 * 86400),    # back this week
        ("firsttime1", -2 * 86400),   # never seen before
        ("firsttime2", -1 * 86400),
    ])

    totals = summary("7d")["totals"]
    assert totals["readers"] == 3          # unique in window
    assert totals["new_readers"] == 2
    assert totals["returning_readers"] == 1
    assert totals["new_readers"] + totals["returning_readers"] == totals["readers"]


def test_reader_whose_first_ever_event_is_inside_the_window_is_new(authed):
    """Boundary: 'new' is decided by the window start, not by the row order."""
    _, db_path, summary = authed
    _seed(db_path, [
        # first event lands just INSIDE the window and nothing precedes it
        ("insider01", -7 * 86400 + 120),
        # identical shape, except one event sits just OUTSIDE the window start
        ("straddler", -7 * 86400 - 120),
        ("straddler", -7 * 86400 + 120),
    ])

    totals = summary("7d")["totals"]
    assert totals["readers"] == 2
    assert totals["new_readers"] == 1, "the event before the cutoff decides it"
    assert totals["returning_readers"] == 1


def test_a_readers_only_event_in_the_window_still_counts_as_new(authed):
    """A reader active only inside the window must never read as returning."""
    _, db_path, summary = authed
    _seed(db_path, [("solo0001", -3600)])

    totals = summary("7d")["totals"]
    assert totals["readers"] == 1
    assert totals["new_readers"] == 1
    assert totals["returning_readers"] == 0


def test_crawler_history_cannot_flip_a_reader_to_returning(authed):
    """Crawler hits carry no anon_id, so they cannot supply prior history."""
    _, db_path, summary = authed
    _seed(db_path, [
        ("reader001", -2 * 86400),
        ("", -30 * 86400, "agent_hit"),
    ])

    totals = summary("7d")["totals"]
    assert totals["readers"] == 1
    assert totals["new_readers"] == 1
    assert totals["returning_readers"] == 0


def test_owner_history_does_flip_that_browser_to_returning(authed):
    """The one design call most likely to be argued with later, pinned.

    _SEEN_BEFORE deliberately does not filter on owner. If this browser was
    here a month ago with ?mp_owner=1 set and comes back today without it, the
    same browser was here before, whoever was driving it, so today's visit is
    not a first visit. The owner filter belongs on the reader counts, which is
    where it is, not on the history probe.
    """
    _, db_path, summary = authed
    _seed(db_path, [
        ("ownerbrowser", -30 * 86400, "page_view", "", 1),  # owner=1, out of window
        ("ownerbrowser", -86400),                            # owner=0, in window
    ])

    totals = summary("7d")["totals"]
    assert totals["readers"] == 1
    assert totals["new_readers"] == 0
    assert totals["returning_readers"] == 1


def test_the_all_time_window_reports_no_split_rather_than_a_false_one(authed):
    """Nothing precedes all-time, so "every reader is new" is not a finding.

    A consumer of /api/site-analytics/summary would read a number as fact, so
    the payload says null and new_split says why.
    """
    _, db_path, summary = authed
    _seed(db_path, [("reader001", -30 * 86400), ("reader001", -86400)])

    body = summary("all")
    assert body["new_split"] is False
    assert body["totals"]["readers"] == 1
    assert body["totals"]["new_readers"] is None
    assert body["totals"]["returning_readers"] is None


def test_referrers_report_new_and_returning_per_domain(authed):
    """'Google sent me N, M of them new' has to be one row, not a subtraction."""
    _, db_path, summary = authed
    _seed(db_path, [
        ("googlenew", -86400, "page_view", "google.com"),
        ("googleold", -30 * 86400, "page_view", "google.com"),
        ("googleold", -86400, "page_view", "google.com"),
        ("linkedin1", -86400, "page_view", "linkedin.com"),
    ])

    referrers = {r["ref_domain"]: r for r in summary("7d")["referrers"]}
    assert referrers["google.com"] == {
        "ref_domain": "google.com", "count": 2,
        "new_count": 1, "returning_count": 1,
    }
    assert referrers["linkedin.com"] == {
        "ref_domain": "linkedin.com", "count": 1,
        "new_count": 1, "returning_count": 0,
    }


def test_a_reader_arriving_from_two_domains_is_new_under_both(authed):
    """The split is a property of the anon_id, not of the referrer."""
    _, db_path, summary = authed
    _seed(db_path, [
        ("twoways1", -86400, "page_view", "google.com"),
        ("twoways1", -3600, "page_view", "news.ycombinator.com"),
    ])

    referrers = {r["ref_domain"]: r for r in summary("7d")["referrers"]}
    assert referrers["google.com"]["new_count"] == 1
    assert referrers["news.ycombinator.com"]["new_count"] == 1
    assert summary("7d")["totals"]["new_readers"] == 1  # one person, counted once


def test_all_time_window_declares_the_split_meaningless(authed):
    """Nothing precedes the all-time window, so every reader would read as new."""
    _, db_path, summary = authed
    _seed(db_path, [
        ("regular01", -30 * 86400),
        ("regular01", -86400),
    ])

    assert summary("7d")["new_split"] is True
    assert summary("all")["new_split"] is False


def test_page_shows_the_split_and_explains_the_vercel_gap(authed):
    http, db_path, _ = authed
    _seed(db_path, [
        ("regular01", -30 * 86400, "page_view", "google.com"),
        ("regular01", -86400, "page_view", "google.com"),
        ("firsttime", -86400, "page_view", "google.com"),
    ])
    headers = {"Authorization": "Bearer test-token"}

    page = http.get("/site-analytics?window=7d", headers=headers).text
    assert "New readers" in page
    assert "Returning" in page
    assert '"new_count": 1' in page or '"new_count":1' in page

    # The counting note has to name a mechanism that actually operates. Owner
    # tagging is the real, code-verifiable reason Vercel counts more visitors:
    # isOwner() stamps owner=1 and every reader query here filters owner=0.
    # Crawler filing is not a reason — src/middleware.ts only POSTs an extra
    # agent_hit row and suppresses nothing, and a crawler running no JS was
    # never in either total. An earlier version of this note said it was.
    # The note is written by the page's own script, so read the source of that
    # block rather than the empty div it fills.
    note_start = page.index('getElementById("countingBody")')
    note = page[note_start : note_start + 2500]
    assert "mp_owner=1" in note
    assert "Vercel" in note
    assert "blocks site storage" in note, "the id-lifetime case that inflates 'new' hardest"

    all_time = http.get("/site-analytics?window=all", headers=headers).text
    assert '"new_split": false' in all_time or '"new_split":false' in all_time


# --- Durable readers vs churned loads -----------------------------------------
#
# 2026-08-26: 757 "unique readers" at 1.02 page views each, zero non-owner
# scroll events. An id minted per page load inflates the reader count; the
# durable flag says whether the client could persist its id. Every row from
# before the site shipped the flag carries the column default 0, which means
# "unlabeled", not "churned", so the split only starts at the first flagged
# event and pre-flag history is never presented as churn.


def test_durable_split_counts_readers_it_can_stand_behind(authed):
    _, db_path, summary = authed
    _seed(db_path, [
        ("keeper01x", -2 * 86400, "page_view", "", 0, 1),
        ("keeper01x", -86400, "page_view", "", 0, 1),
        ("keeper02x", -86400, "story_view", "", 0, 1),
        # a storage-blocked client: every load mints a new id
        ("mintedid1", -3600, "page_view", "", 0, 0),
        ("mintedid2", -3500, "page_view", "", 0, 0),
    ])

    d = summary("7d")["durable"]
    assert d["active"] is True
    assert d["durable_readers"] == 2
    assert d["churned_loads"] == 2


def test_pre_flag_history_is_not_presented_as_churn(authed):
    _, db_path, summary = authed
    _seed(db_path, [
        # history from before the site shipped the flag, unlabeled rather
        # than churned
        ("oldreader1", -6 * 86400, "page_view", "", 0, 0),
        ("oldreader2", -5 * 86400, "page_view", "", 0, 0),
        # the first flagged event, which is the moment the flag shipped
        ("keeper01x", -86400, "page_view", "", 0, 1),
        # one genuinely churning load after that
        ("mintedid1", -3600, "page_view", "", 0, 0),
    ])

    d = summary("7d")["durable"]
    assert d["durable_readers"] == 1
    assert d["churned_loads"] == 1, "the two pre-flag loads must not count"
    assert d["partial"] is True
    assert d["since_label"]


def test_no_flagged_events_means_no_durable_numbers_at_all(authed):
    """Before the site ships the flag, zeros would be a lie, so say nothing."""
    _, db_path, summary = authed
    _seed(db_path, [("oldreader1", -86400)])

    d = summary("7d")["durable"]
    assert d["active"] is False
    assert d["durable_readers"] is None
    assert d["churned_loads"] is None


def test_owner_and_crawler_events_stay_out_of_the_durable_split(authed):
    _, db_path, summary = authed
    _seed(db_path, [
        ("reader001", -86400, "page_view", "", 0, 1),
        ("tayler01x", -3600, "page_view", "", 1, 1),  # owner browsing, durable
        ("", -3600, "agent_hit"),                     # crawler, no anon_id
        ("tayler01x", -3000, "page_view", "", 1, 0),  # owner, id not persisted
    ])

    d = summary("7d")["durable"]
    assert d["durable_readers"] == 1
    assert d["churned_loads"] == 0


def test_the_flag_posted_by_the_site_reaches_the_split(authed):
    """End to end over HTTP: the body the site posts decides the split."""
    http, _, summary = authed
    http.post("/api/event", json={
        "type": "page_view", "path": "/", "anon_id": "keeper0001", "durable": 1,
    })
    http.post("/api/event", json={
        "type": "page_view", "path": "/", "anon_id": "mintedid01", "durable": 0,
    })

    d = summary("7d")["durable"]
    assert d["active"] is True
    assert d["durable_readers"] == 1
    assert d["churned_loads"] == 1


def test_page_carries_the_durable_copy_and_signs_of_reading(authed):
    http, db_path, _ = authed
    _seed(db_path, [("keeper01x", -3600, "page_view", "", 0, 1)])

    page = http.get("/site-analytics?window=7d",
                    headers={"Authorization": "Bearer test-token"})
    assert page.status_code == 200
    assert "Durable readers" in page.text
    assert "Churned loads" in page.text
    assert "can mint a new id" in page.text
    assert "Signs of reading" in page.text

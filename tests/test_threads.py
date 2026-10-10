"""Lead stories built from several of today's findings, and their earlier coverage (orchestrator/threads.py)."""
import json

import pytest

from core.claude_cli import ClaudeProcessResult
from orchestrator import threads

TODAY = "2026-10-10"
POLICY = threads.ThreadPolicy(leads=4, candidates=10, window_days=30, min_earlier_days=2,
                              similarity=0.9, max_entity_findings=3)


@pytest.fixture
def conn(tmp_path):
    """Findings with 3-d embeddings and knowledge-graph edges for the earlier ones."""
    from kg.schema import init_kg_schema
    from memory.db import get_db
    from memory.embeddings import serialize_f32

    db = get_db(db_path=tmp_path / "memory.db")
    init_kg_schema(db)
    entities = {"Deno": 1, "Anthropic": 2, "Lean": 3}
    for name, eid in entities.items():
        db.execute("INSERT INTO kg_entities (id, canonical_name, entity_type) VALUES (?, ?, 'Product')", (eid, name))
    db.execute("INSERT INTO kg_entity_aliases (entity_id, alias) VALUES (1, 'Deno Deploy')")
    deno, anthropic, lean = [1, 0, 0], [0, 1, 0], [0, 0, 1]
    rows = [
        # id, date, agent, title, vector, entity ids (earlier findings only)
        (1, "2026-10-01", "news", "Deno ships 3.0", deno, [1]),
        (2, "2026-10-05", "hn", "Deno Deploy changes pricing", deno, [1]),
        (3, TODAY, "news", "Cloudflare acquires the Deno team and ends Deno Deploy", [0.95, 0.3122, 0.0], []),
        (4, "2026-10-02", "news", "Anthropic news one", anthropic, [2]),
        (5, "2026-10-06", "news", "Anthropic news two", anthropic, [2]),
        (6, "2026-10-07", "news", "Anthropic news three", anthropic, [2]),
        (7, "2026-10-08", "news", "Anthropic news four", anthropic, [2]),
        (8, TODAY, "rss", "Anthropic changes its eval policy", anthropic, []),
        (9, "2026-10-08", "arxiv", "Lean proof checking rules", lean, [3]),
        (10, TODAY, "arxiv", "A new Lean proof dispute", lean, []),
    ]
    for fid, run_date, agent, title, vector, eids in rows:
        db.execute("INSERT INTO findings (id, run_date, agent, title, summary, importance, source_url, source_name) "
                   "VALUES (?, ?, ?, ?, 'summary', 'medium', ?, 'Source')", (fid, run_date, agent, title,
                                                                           f"https://x.example/{fid}"))
        db.execute("INSERT INTO findings_embeddings (finding_id, embedding) VALUES (?, ?)", (fid, serialize_f32(vector)))
        for eid in eids:
            db.execute("INSERT INTO kg_edges (subject_id, predicate, object_id, fact_text, finding_id) "
                       "VALUES (?, 'about', ?, 'fact', ?)", (eid, eid, fid))
    db.commit()
    return db


def test_a_story_that_continues_on_earlier_days_becomes_a_candidate(conn):
    candidates = threads.find_candidates(conn, TODAY, POLICY)
    assert [[e.finding_id for e in c.today] for c in candidates] == [[3]]
    deno = candidates[0]
    assert ([e.finding_id for e in deno.earlier], deno.earlier_days, deno.entities) == (
        [1, 2], ["2026-10-01", "2026-10-05"], ["Deno"])


def test_a_generic_entity_or_a_single_earlier_day_is_not_a_thread(conn):
    """Anthropic appears in more findings than max_entity_findings; Lean has one earlier day."""
    candidates = threads.find_candidates(conn, TODAY, POLICY)
    titles = {e.title for c in candidates for e in c.today}
    assert "Anthropic changes its eval policy" not in titles and "A new Lean proof dispute" not in titles
    loose = threads.ThreadPolicy(**{**POLICY.__dict__, "min_earlier_days": 1})
    assert "A new Lean proof dispute" in {e.title for c in threads.find_candidates(conn, TODAY, loose) for e in c.today}


def test_unrelated_stories_that_share_an_earlier_finding_do_not_chain(conn):
    from memory.embeddings import serialize_f32

    conn.execute("INSERT INTO findings (id, run_date, agent, title, summary, importance, source_url, source_name) "
                 "VALUES (11, ?, 'hn', 'Deno Deploy outage, unrelated angle', 's', 'low', 'https://x.example/11', 'S')",
                 (TODAY,))
    conn.execute("INSERT INTO findings_embeddings (finding_id, embedding) VALUES (11, ?)",
                 (serialize_f32([0.95, 0.0, 0.3122]),))  # 0.95 from the earlier Deno story, 0.90 from finding 3
    conn.commit()
    candidates = threads.find_candidates(conn, TODAY, threads.ThreadPolicy(**{**POLICY.__dict__, "similarity": 0.92}))
    assert sorted(len(c.today) for c in candidates) == [1, 1]


def _finder(answer):
    def runner(argv, **kwargs):
        return ClaudeProcessResult(json.dumps(answer), "", 0)
    return runner


THREE = [3, 8, 10]  # today's findings from news, rss and arxiv


def _row(ids, strength=4, title="Agents get fenced in", angle="Three findings show the same shift today."):
    return {"title": title, "angle": angle, "finding_ids": ids, "strength": strength}


def _add_today(conn, fid, agent):
    conn.execute("INSERT INTO findings (id, run_date, agent, title, summary, importance, source_url, source_name) "
                 "VALUES (?, ?, ?, ?, 'summary', 'medium', ?, 'Source')",
                 (fid, TODAY, agent, f"Finding {fid}", f"https://x.example/{fid}"))


def _leads(conn, answer, policy=POLICY, **kwargs):
    found = threads.find_threads(conn, TODAY, policy=policy, runner=_finder(answer), **kwargs)
    return [(t.title, [m.finding_id for m in t.members]) for t in found]


def test_a_lead_story_built_from_three_findings_by_two_agents_is_kept(conn):
    assert _leads(conn, {"threads": [_row(THREE)]}) == [("Agents get fenced in", THREE)]


@pytest.mark.parametrize("ids", [[3, 8], [3, 8, 999], [3, 3, 8]], ids=["too few", "unknown id", "repeats one"])
def test_a_lead_story_without_three_real_findings_is_dropped(conn, ids):
    assert _leads(conn, {"threads": [_row(ids)]}) == []


def test_findings_an_earlier_issue_used_do_not_count(conn):
    assert _leads(conn, {"threads": [_row(THREE)]}, covered={10}) == []


def test_one_agent_is_not_enough(conn):
    for fid in (12, 13):
        _add_today(conn, fid, "news")
    assert _leads(conn, {"threads": [_row([3, 12, 13])]}) == []


def test_a_finding_serves_one_lead_story_and_the_stronger_story_keeps_it(conn):
    for fid, agent in ((12, "hn"), (13, "news"), (14, "rss")):
        _add_today(conn, fid, agent)
    answer = {"threads": [_row([3, 8, 12], strength=3, title="Weakest"),
                          _row([10, 12, 13, 14], strength=4, title="Second"),
                          _row(THREE, strength=5, title="Strongest")]}
    assert _leads(conn, answer) == [("Strongest", THREE), ("Second", [12, 13, 14])]


def test_no_more_lead_stories_than_top_slots(conn):
    for fid, agent in ((12, "hn"), (13, "news"), (14, "rss")):
        _add_today(conn, fid, agent)
    answer = {"threads": [_row([12, 13, 14], strength=4, title="Second"), _row(THREE, strength=5, title="First")]}
    policy = threads.ThreadPolicy(**{**POLICY.__dict__, "leads": 1})
    assert _leads(conn, answer, policy) == [("First", THREE)]


def test_one_bad_row_costs_only_itself_and_the_strongest_fill_the_slots(conn):
    answer = {"threads": [_row(THREE, strength=2, title="Weaker"), _row(THREE, strength=4, title="Stronger"),
                          _row(THREE, strength=5, angle="x" * 1300, title="Too long")]}
    policy = threads.ThreadPolicy(**{**POLICY.__dict__, "leads": 1})
    assert _leads(conn, answer, policy) == [("Stronger", THREE)]


def test_earlier_coverage_is_attached_to_a_lead_storys_findings(conn):
    found = threads.find_threads(conn, TODAY, policy=POLICY, runner=_finder({"threads": [_row(THREE)]}))
    assert [e.finding_id for e in found[0].earlier] == [1, 2]


@pytest.mark.parametrize("stdout", ["not json", json.dumps({"threads": "nope"})])
def test_a_bad_answer_gives_no_lead_stories(conn, stdout):
    runner = lambda argv, **kwargs: ClaudeProcessResult(stdout, "", 0)
    assert threads.find_threads(conn, TODAY, policy=POLICY, runner=runner) == []


def test_the_prompt_carries_every_finding_its_notes_and_the_published_list(conn):
    prompt = threads.build_prompt(threads.today_episodes(conn, TODAY), policy=POLICY,
                                  notes={8: "Also found by: hn"}, published="## Already Published\n- Old story")
    assert prompt.startswith("Propose up to 7 lead stories. The 4 strongest")
    assert "## Already Published\n- Old story" in prompt and "## Today's findings (3)" in prompt
    assert "#8 [rss] Anthropic changes its eval policy (Source)\n  Also found by: hn\n  summary" in prompt
    assert "#3 [news] Cloudflare acquires the Deno team and ends Deno Deploy (Source)\n  summary" in prompt


def test_the_writer_and_the_deep_dives_get_the_angle_and_every_finding(conn, tmp_path):
    from orchestrator import deep_dive

    found = threads.find_threads(conn, TODAY, policy=POLICY, runner=_finder({"threads": [_row(THREE)]}))
    block = threads.lead_block(found)
    assert block.startswith("## Lead stories\nThe Top stories open with these 1, in this order.")
    assert ("### Lead story 1\nWorking title: Agents get fenced in\nAngle: Three findings show the same shift "
            "today.\nFindings:\n- [Source](https://x.example/3) Cloudflare acquires the Deno team") in block
    assert "Earlier coverage:\n- 2026-10-01: [Source](https://x.example/1) Deno ships 3.0" in block
    assert threads.lead_block([]) == "" and threads.lead_positions(found) == {3: 1, 8: 1, 10: 1}
    prompt = deep_dive.build_prompt(threads.deep_dives(found)[0])
    assert prompt.startswith("Story id: agents-get-fenced-in\nStory: Agents get fenced in\n"
                             "Angle: Three findings show the same shift today.\nBuilt from these findings:\n"
                             "- Cloudflare acquires the Deno team and ends Deno Deploy (Source, https://x.example/3).")
    saved = json.loads(threads.save(found, date_str=TODAY, user="ramsay", reports_root=tmp_path).read_text())
    assert [m["finding_id"] for m in saved["threads"][0]["members"]] == THREE


def test_the_policy_loads_and_rejects_out_of_range_values(tmp_path):
    from orchestrator.editorial import EditorialPolicyError

    policy = threads.load_policy()
    assert (policy.leads, policy.proposals, policy.similarity) == (5, 7, 0.72)
    path = tmp_path / "editorial.json"
    path.write_text(json.dumps({"threads": {"similarity": 1.5}}))
    with pytest.raises(EditorialPolicyError, match="threads.similarity"):
        threads.load_policy(path)

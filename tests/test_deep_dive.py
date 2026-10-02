"""orchestrator.deep_dive researches the selector's picks and hands the writer an evidence pack per story."""
import json

from core.claude_cli import ClaudeProcessResult
from orchestrator import deep_dive

FINDINGS = [
    {"agent": "agents-researcher", "title": "Acme ships Runtime 2.0 with a retrying planner",
     "summary": "Acme released Runtime 2.0.", "source_url": "https://acme.example.com/r2", "source_name": "Acme"},
    {"agent": "news-researcher", "title": "[Security Research] Beta patches a sandbox escape",
     "summary": "Beta fixed CVE-2026-1.", "source_url": "https://beta.example.com/cve", "source_name": "Beta"},
]
PASS1 = json.dumps([
    {"story_title": "Acme ships Runtime 2.0 with a retrying planner", "agent": "agents-researcher",
     "section": "agents", "reason": "r"},
    {"story_title": "Beta patches a sandbox escape", "agent": "news-researcher", "section": "security", "reason": "r"},
    {"story_title": "A story nobody found", "agent": "rss-researcher", "section": "x", "reason": "r"},
])


def test_picks_are_matched_to_the_findings_they_came_from():
    stories = deep_dive.stories_from_selection(PASS1, FINDINGS, limit=5)
    assert [(s.story_id, s.finding["source_url"] if s.finding else None) for s in stories] == [
        ("acme-ships-runtime-2-0-with-a-retrying-planner", "https://acme.example.com/r2"),
        ("beta-patches-a-sandbox-escape", "https://beta.example.com/cve"),
        ("a-story-nobody-found", None),
    ]
    assert len(deep_dive.stories_from_selection(PASS1, FINDINGS, limit=1)) == 1
    assert deep_dive.stories_from_selection("not json at all", FINDINGS, limit=5) == []


def test_each_story_gets_an_agent_and_its_stored_evidence(tmp_path):
    stories = deep_dive.stories_from_selection(PASS1, FINDINGS, limit=2)
    seen = []

    def runner(argv, **kwargs):
        env = kwargs["env"]
        seen.append((env["MINDPATTERN_TASK"], env["MINDPATTERN_AGENT"], env["PATH"].split(":")[0].endswith("/bin")))
        story = argv[2].split("Story id: ", 1)[1].split("\n", 1)[0]
        if story.startswith("acme"):
            with open(env["MP_EVIDENCE_FILE"], "a") as handle:
                handle.write(json.dumps({"kind": "number", "claim": "Failed tasks fell from 12% to 6%.",
                                         "source_url": "https://acme.example.com/r2", "source_name": "Acme",
                                         "story": story}) + "\n")
        return ClaudeProcessResult('{"type": "result", "subtype": "success", "is_error": false, '
                                   '"result": "stored 1 item", "num_turns": 3}', "", 0)

    (tmp_path / "ev").mkdir()
    done = deep_dive.run_deep_dives(stories, evidence_dir=tmp_path / "ev", runner=runner)
    assert sorted(seen) == [("story_deep_dive", "deep-dive-acme-ships-runtime-2-0-with-a-retrying-planner", True),
                            ("story_deep_dive", "deep-dive-beta-patches-a-sandbox-escape", True)]
    assert deep_dive.summary(done) == {
        "stories": 2, "with_evidence": 1, "items": 1,
        "outcomes": {"acme-ships-runtime-2-0-with-a-retrying-planner": "success",
                     "beta-patches-a-sandbox-escape": "success"}}
    block = deep_dive.evidence_block(done)
    assert block.startswith("## Evidence packs (deep dives on today's picks)")
    assert "### Acme ships Runtime 2.0 with a retrying planner" in block
    assert "- [number] Failed tasks fell from 12% to 6%. (Acme, https://acme.example.com/r2)." in block
    assert "Beta patches" not in block


def test_a_failing_agent_leaves_its_story_without_a_pack(tmp_path):
    stories = deep_dive.stories_from_selection(PASS1, FINDINGS, limit=1)
    done = deep_dive.run_deep_dives(stories, evidence_dir=tmp_path,
                                    runner=lambda argv, **kw: ClaudeProcessResult("", "", 1, timed_out=True))
    assert done[0].outcome == "timeout" and done[0].evidence == []
    assert deep_dive.evidence_block(done) == ""

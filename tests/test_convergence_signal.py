"""Several agents finding one story reaches the story selector as "Also found by"."""
from core import findings_store
from orchestrator.agents import AgentResult, dedup_cross_agent_findings
from orchestrator.runner import _candidate_summary

STORY = {"title": "Deno's team joins Cloudflare and Deno Deploy shuts down", "summary": "s",
         "source_url": "https://blog.cloudflare.com/deno", "source_name": "Cloudflare blog",
         "importance": "high", "agent": "news-researcher"}


def test_matching_finds_other_agents_by_url_or_close_title():
    rows = [
        {"agent": "hn-researcher", "source_name": "Hacker News", "corroborates_url": "https://www.blog.cloudflare.com/deno/",
         "corroborates_title": "x"},
        {"agent": "projects-researcher", "source_name": "GitHub", "corroborates_url": "https://other.example/a",
         "corroborates_title": "Deno team joins Cloudflare; Deno Deploy shuts down"},
        {"agent": "rss-researcher", "source_name": "RSS", "corroborates_url": "https://other.example/b",
         "corroborates_title": "Qwen ships an image model"},
        {"agent": "news-researcher", "source_name": "Self", "corroborates_url": STORY["source_url"],
         "corroborates_title": STORY["title"]},
    ]
    assert findings_store.corroborators(STORY, rows) == ["hn-researcher (Hacker News)", "projects-researcher (GitHub)"]


def test_the_selector_candidate_names_the_other_agents():
    text = _candidate_summary(STORY, "", ["hn-researcher (Hacker News)"])
    assert text == ("[news-researcher] (high) Deno's team joins Cloudflare and Deno Deploy shuts down\n"
                    "  Source: [Cloudflare blog](https://blog.cloudflare.com/deno)\n"
                    "  Also found by: hn-researcher (Hacker News)\n  s")
    assert "Also found by" not in _candidate_summary(STORY, "", [])


def test_the_dedupe_records_what_it_removes(offline_embeddings):
    a = AgentResult(agent_name="news-researcher", findings=[dict(STORY)], raw_output="", exit_code=0, duration_ms=1)
    b = AgentResult(agent_name="hn-researcher", findings=[{**STORY, "agent": "hn-researcher",
                                                          "source_name": "Hacker News"}], raw_output="", exit_code=0,
                    duration_ms=1)
    rows: list[dict] = []
    _, summary = dedup_cross_agent_findings([a, b], corroborations=rows)
    assert summary["removed"] == 1
    assert len(rows) == 1 and {rows[0]["agent"], rows[0]["corroborates_agent"]} == {"news-researcher", "hn-researcher"}

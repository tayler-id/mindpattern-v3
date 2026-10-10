"""devtools/health.py turns what the pipeline records into one row per day and a list of problems."""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("health_tool", ROOT / "devtools" / "health.py")
health = importlib.util.module_from_spec(SPEC)
sys.modules["health_tool"] = health
SPEC.loader.exec_module(health)


def _state(tmp_path):
    from memory.db import get_db
    from orchestrator.traces_db import init_db

    data = tmp_path / "data" / "ramsay"
    data.mkdir(parents=True)
    traces = init_db(data / "traces.db")
    run = "research-2026-10-09-abc123"
    traces.execute("INSERT INTO pipeline_runs (id, pipeline_type, status, started_at, completed_at) VALUES "
                   "(?, 'research', 'completed', '2026-10-09T12:00:00+00:00', '2026-10-09T12:50:00+00:00')", (run,))
    events = [
        ("phase_research_complete", {"duration_ms": 1, "result": str({"agents_succeeded": 12, "findings_stored": 46})}),
        ("cross_agent_dedup", {"total": 70, "removed": 24, "kept": 46}),
        ("newsletter_evaluation", {"overall": 0.83}),
        ("newsletter_sent", {"success": True}),
    ]
    for kind, payload in events:
        traces.execute("INSERT INTO events (pipeline_run_id, event_type, payload) VALUES (?, ?, ?)",
                       (run, kind, json.dumps(payload)))
    calls = [("a", "claude", "success", 0, 1.25), ("b", "claude", "timeout", 0, 0.5),
             ("c", "codex", "success", 0, None), ("d", "claude", "success", 1, 0.25)]
    for cid, provider, outcome, fell_back, cost in calls:
        traces.execute("INSERT INTO model_calls (id, run_id, run_date, task, provider, model, outcome, fell_back, cost_usd) "
                       "VALUES (?, ?, '2026-10-09', 't', ?, 'm', ?, ?, ?)", (cid, run, provider, outcome, fell_back, cost))
    traces.commit()
    traces.close()
    memory = get_db(db_path=data / "memory.db")
    for run_date, agent, n in (("2026-10-09", "hn-researcher", 2), ("2026-10-02", "hn-researcher", 8)):
        for i in range(n):
            memory.execute("INSERT INTO findings (run_date, agent, title, summary, importance, source_url, source_name) "
                           "VALUES (?, ?, ?, 's', 'low', ?, 'x')", (run_date, agent, f"{agent} {run_date} {i}",
                                                                      f"https://x.example/{run_date}/{i}"))
    memory.commit()
    memory.close()
    day = tmp_path / "reports" / "ramsay" / "site-stories" / "2026-10-09"
    day.mkdir(parents=True)
    for name in ("foo.json", "2026-10-09-foo.json", "bar.json"):
        (day / name).write_text("{}")
    return tmp_path


def test_a_day_is_summarized_and_its_problems_named(tmp_path):
    root = _state(tmp_path)
    data = health.report(root, "ramsay", 7, date(2026, 10, 9))
    today = data["days"][-1]
    assert {k: today[k] for k in ("date", "status", "minutes", "sent", "agents_ok", "findings", "duplicates_removed",
                                  "eval_overall", "site_stories", "claude_usd", "codex_calls", "failed_calls",
                                  "fallbacks")} == {
        "date": "2026-10-09", "status": "completed", "minutes": 50, "sent": True, "agents_ok": 12, "findings": 46,
        "duplicates_removed": 24, "eval_overall": 0.83, "site_stories": 3, "claude_usd": 2.0, "codex_calls": 1,
        "failed_calls": 1, "fallbacks": 1}
    assert today["flags"] == ["46 findings, floor 70", "3 site stories, target 20", "1 failed model calls",
                              "1 calls fell back"]
    assert data["days"][0]["flags"] == ["no pipeline run"]
    assert data["agents"] == [{"agent": "hn-researcher", "per_day_now": 2.0, "per_day_before": 8.0}]
    assert data["ambiguous_story_slugs"] == 1


def test_the_cli_prints_the_table_and_exits_1_on_problems(tmp_path, capsys):
    root = _state(tmp_path)
    assert health.main(["--root", str(root), "--today", "2026-10-09", "--since", "1"]) == 1
    out = capsys.readouterr().out
    assert "2026-10-09 completed    50  yes     12       46    24  0.83    3     2.00     1      1        1" in out
    assert "  2026-10-09  46 findings, floor 70" in out
    assert "Ambiguous story slugs (404 on the site): 1" in out


def test_a_sync_only_retry_does_not_hide_the_days_run(tmp_path):
    import sqlite3

    root = _state(tmp_path)
    conn = sqlite3.connect(root / "data" / "ramsay" / "traces.db")
    conn.execute("INSERT INTO pipeline_runs (id, pipeline_type, status, started_at) VALUES "
                 "('research-2026-10-09-zzz999', 'research', 'running', '2026-10-09T19:00:00+00:00')")
    conn.commit()
    conn.close()
    today = health.report(root, "ramsay", 1, date(2026, 10, 9))["days"][-1]
    assert (today["run_id"], today["status"], today["findings"]) == ("research-2026-10-09-abc123", "completed", 46)

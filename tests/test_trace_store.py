"""core.trace_store files every model call under its run: rows, steps, subagents, raw stream."""
import gzip
import sqlite3
from datetime import date
from pathlib import Path

from core.claude_cli import ClaudeProcessResult
from core.config import Route
from core.model_cli import CallRequest, call_model
from core.trace_store import RunContext, prune_raw_traces, record_call

FIXTURES = Path(__file__).parent / "fixtures" / "cli"
ROUTE = Route("research_agent", "claude", "claude-sonnet-5-5", 1800, effort="medium", max_turns=4)
CTX = RunContext(run_id="research-2026-10-02-abc123", run_date="2026-10-02", phase="research", user_id="ramsay")


def _call(stream: str):
    def runner(argv, *, timeout, input_text=None, cwd=None, env=None):
        return ClaudeProcessResult(stream, "", 0)
    return call_model(CallRequest(task="research_agent", prompt="Find one thing.", unit="news-researcher"),
                      route=ROUTE, runner=runner, recorder=None)


def test_a_call_with_a_subagent_becomes_two_linked_rows_with_their_own_steps(tmp_path):
    stream = (FIXTURES / "claude_subagent.ndjson").read_text()
    result = _call(stream)
    db = tmp_path / "traces.db"

    record_call(CallRequest(task="research_agent", prompt="Find one thing.", unit="news-researcher"),
                ROUTE, result, stream, ctx=CTX, db_path=db, root=tmp_path / "traces")

    conn = sqlite3.connect(db)
    calls = conn.execute(
        "SELECT id, parent_call_id, run_id, phase, task, unit, model, outcome, output_tokens, step_count, cost_usd "
        "FROM model_calls ORDER BY parent_call_id IS NOT NULL").fetchall()
    assert calls == [
        (result.call_id, None, "research-2026-10-02-abc123", "research", "research_agent", "news-researcher",
         "claude-sonnet-5-5", "success", 143, 1, 0.1647092),
        (f"{result.call_id}.1", result.call_id, "research-2026-10-02-abc123", "research",
         "research_agent:subagent", "Reply pong", "claude-sonnet-5-5", "completed", 24, 1, None),
    ]
    steps = conn.execute("SELECT call_id, seq, tool, ok FROM model_call_steps ORDER BY call_id").fetchall()
    assert steps == [(result.call_id, 1, "Agent", 1), (f"{result.call_id}.1", 1, "SubagentHandback", 1)]

    folder = tmp_path / "traces" / "2026-10-02" / "research-2026-10-02-abc123"
    with gzip.open(folder / f"{result.call_id}.events.jsonl.gz", "rt") as handle:
        assert handle.read() == stream
    with gzip.open(folder / f"{result.call_id}.prompt.md.gz", "rt") as handle:
        assert handle.read() == "Find one thing."


def test_a_call_outside_a_run_is_filed_as_adhoc(tmp_path):
    stream = (FIXTURES / "claude_success.ndjson").read_text()
    result = _call(stream)
    record_call(CallRequest(task="writer", prompt="draft"), ROUTE, result, stream,
                ctx=RunContext(run_date="2026-10-02"), db_path=tmp_path / "t.db", root=tmp_path / "traces")
    row = sqlite3.connect(tmp_path / "t.db").execute("SELECT run_id, phase FROM model_calls").fetchone()
    assert row == ("adhoc", None)
    assert (tmp_path / "traces" / "2026-10-02" / "adhoc" / f"{result.call_id}.events.jsonl.gz").exists()


def test_pruning_removes_only_day_folders_past_the_cutoff(tmp_path):
    root = tmp_path / "traces"
    for name in ("2026-06-01", "2026-07-03", "2026-07-04", "2026-10-02", "notes"):
        (root / name).mkdir(parents=True)
    removed = prune_raw_traces(90, root=root, today=date(2026, 10, 2))
    assert removed == ["2026-06-01", "2026-07-03"]
    assert sorted(p.name for p in root.iterdir()) == ["2026-07-04", "2026-10-02", "notes"]


def test_the_observability_policy_and_run_totals(tmp_path):
    from core.trace_store import load_observability_policy, over_budget, run_totals

    policy = load_observability_policy()
    assert (policy.raw_trace_days, policy.budget_output_tokens, policy.budget_api_price_usd) == (90, 3_000_000, 120.0)

    stream = (FIXTURES / "claude_subagent.ndjson").read_text()
    result = _call(stream)
    db = tmp_path / "traces.db"
    record_call(CallRequest(task="research_agent", prompt="p"), ROUTE, result, stream, ctx=CTX, db_path=db,
                root=tmp_path / "traces")
    totals = run_totals(CTX.run_id, db_path=db)
    assert totals == {"calls": 1, "output_tokens": 143, "api_price_usd": 0.16}
    assert over_budget(totals, policy) == []
    assert over_budget({"calls": 900, "output_tokens": 4_000_000, "api_price_usd": 130.0}, policy) == [
        "4,000,000 output tokens (soft budget 3,000,000)", "$130.0 at API prices (soft budget $120)"]
    assert run_totals("no-such-run", db_path=tmp_path / "absent.db")["calls"] == 0

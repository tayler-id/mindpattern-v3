"""`python -m orchestrator.trace` shows a recorded run down to each tool call and subagent."""
from datetime import date
from pathlib import Path

import pytest

from core.claude_cli import ClaudeProcessResult
from core.config import Route
from core.model_cli import CallRequest, call_model
from core.trace_store import RunContext, record_call
from orchestrator import trace

FIXTURES = Path(__file__).parent / "fixtures" / "cli"
RUN = "research-2026-10-02-abc123"


@pytest.fixture
def recorded(tmp_path):
    db = tmp_path / "traces.db"
    ids = {}
    for name, route, request, phase in (
        ("claude_subagent.ndjson", Route("research_agent", "claude", "claude-sonnet-5-5", 1800, max_turns=4),
         CallRequest(task="research_agent", prompt="Research agents.", unit="agents-researcher"), "research"),
        ("codex_command.ndjson", Route("site_story_critic", "codex", "gpt-6.1-sol", 300),
         CallRequest(task="site_story_critic", prompt="Judge the draft.", unit="story-slug"), "site_content"),
    ):
        stream = (FIXTURES / name).read_text()
        result = call_model(request, route=route, recorder=None,
                            runner=lambda argv, **kw: ClaudeProcessResult(stream, "", 0))
        record_call(request, route, result, stream, db_path=db, root=tmp_path / "traces",
                    ctx=RunContext(run_id=RUN, run_date="2026-10-02", phase=phase, user_id="ramsay"))
        ids[name] = result.call_id
    return tmp_path, db, ids


def run_cli(capsys, tmp_path, db, *args) -> str:
    assert trace.main(["--db", str(db), "--root", str(tmp_path), *args]) == 0
    return capsys.readouterr().out


def test_runs_lists_the_run_with_its_totals(recorded, capsys):
    tmp_path, db, _ = recorded
    out = run_cli(capsys, tmp_path, db, "runs")
    assert f"{RUN:38} 2026-10-02     2      0        254" in out


def test_show_renders_phases_calls_subagents_and_steps(recorded, capsys):
    tmp_path, db, ids = recorded
    out = run_cli(capsys, tmp_path, db, "show", RUN, "--steps")
    research = ids["claude_subagent.ndjson"]
    assert "  phase research" in out and "  phase site_content" in out
    assert f"    {research}  research_agent" in out and "agents-researcher" in out
    assert f"      subagent {research}.1  Reply pong  claude-sonnet-5-5  completed  out 24  steps 1" in out
    assert "  1. Agent              ok" in out
    assert "  1. SubagentHandback   ok" in out
    assert "codex:gpt-6.1-sol  success" in out


def test_call_full_prints_the_prompt_and_the_conversation(recorded, capsys):
    tmp_path, db, ids = recorded
    out = run_cli(capsys, tmp_path, db, "call", ids["claude_subagent.ndjson"], "--full")
    assert "task research_agent  unit agents-researcher  claude:claude-sonnet-5-5  outcome success" in out
    assert "  Research agents." in out
    assert '  -> Agent {"description": "Reply pong"' in out
    assert "    [subagent] -> SubagentHandback" in out
    assert "  assistant: pong" in out

    codex = run_cli(capsys, tmp_path, db, "call", ids["codex_command.ndjson"], "--full")
    assert "  -> $ /bin/zsh -lc 'echo hello-from-codex' (exit 0)" in codex
    assert "  assistant: hello-from-codex" in codex


def test_grep_finds_text_inside_any_call_of_the_run(recorded, capsys):
    tmp_path, db, ids = recorded
    out = run_cli(capsys, tmp_path, db, "grep", RUN, "hello-from-codex")
    assert out.startswith(f"{ids['codex_command.ndjson']}  site_story_critic  story-slug: ...")
    assert "no match" in run_cli(capsys, tmp_path, db, "grep", RUN, "zebra-unicorn")


def test_usage_totals_parent_calls_by_task_and_model(recorded):
    _, db, _ = recorded
    conn = trace._connect(db)
    lines = trace.cmd_usage(conn, 7, ["provider"], today=date(2026, 10, 3))
    assert lines[2].split() == ["claude", "1", "143", "14,600", "69,991", "$0.165"]
    assert lines[3].split() == ["codex", "1", "111", "10,126", "54,016", "-"]


def test_a_missing_database_is_reported(tmp_path):
    with pytest.raises(SystemExit, match="no traces database"):
        trace.main(["--db", str(tmp_path / "absent.db"), "runs"])

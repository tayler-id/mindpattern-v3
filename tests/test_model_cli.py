"""core.model_cli builds each CLI's argv, reads its event stream, and records the call.

Fixtures in tests/fixtures/cli/ are real `claude -p --output-format stream-json
--verbose` and `codex exec --json` output captured on 2026-10-02 (paths and
plugin lists removed). A CLI update that changes the format fails here.
"""
from pathlib import Path

from core.claude_cli import ClaudeProcessResult
from core.config import Route
from core.model_cli import (
    CallRequest,
    ToolPolicy,
    Usage,
    build_argv,
    call_model,
    parse_claude_stream,
    parse_codex_stream,
    run_task_process,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cli"
CLAUDE = Route("research_agent", "claude", "claude-sonnet-5-5", 1800, effort="medium", max_turns=35)
CODEX = Route("site_story_critic", "codex", "gpt-6.1-sol", 300, effort="low")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_claude_argv_streams_events_and_skips_the_users_own_settings():
    request = CallRequest(task="research_agent", prompt="find things",
                          system_prompt_file=Path("prompts/research-agent-system.md"),
                          tools=ToolPolicy(allowed=("WebSearch", "Bash(twitter *)"), disallowed=("Agent", "Skill")))
    argv, stdin = build_argv(CLAUDE, request)
    assert argv == [
        "claude", "-p", "find things",
        "--model", "claude-sonnet-5-5", "--output-format", "stream-json", "--verbose",
        "--effort", "medium", "--max-turns", "35",
        "--append-system-prompt-file", "prompts/research-agent-system.md",
        "--allowedTools", "WebSearch", "--allowedTools", "Bash(twitter *)",
        "--disallowedTools", "Agent,Skill",
        "--setting-sources", "project,local", "--strict-mcp-config",
    ]
    assert stdin is None


def test_a_long_claude_prompt_goes_through_stdin_with_no_dash_argument():
    prompt = "x" * 100_001
    argv, stdin = build_argv(CLAUDE, CallRequest(task="synthesis_pass2", prompt=prompt))
    assert argv[:3] == ["claude", "-p", "--model"]
    assert "-" not in argv
    assert stdin == prompt


def test_codex_argv_pins_model_and_effort_and_reads_no_stdin(tmp_path):
    system = tmp_path / "critic.md"
    system.write_text("You are the desk editor.\n")
    argv, stdin = build_argv(CODEX, CallRequest(task="site_story_critic", prompt="Judge this.",
                                                system_prompt_file=system))
    assert argv == [
        "codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
        "-m", "gpt-6.1-sol", "--ignore-rules",
        "-c", "features.plugins=false", "-c", "features.skill_search=false", "-c", "features.hooks=false",
        "-c", "features.apps=false", "-c", "features.browser_use=false", "-c", "features.computer_use=false",
        "-c", 'model_reasoning_effort="low"',
        "You are the desk editor.\n\n---\n\nJudge this.",
    ]
    assert stdin == ""


def test_claude_success_stream():
    parsed = parse_claude_stream(fixture("claude_success.ndjson"), max_turns=1)
    assert (parsed.text, parsed.outcome, parsed.turns, parsed.model) == ("ok", "success", 1, "claude-sonnet-5-5")
    assert parsed.usage == Usage(2, 18116, 10341, 4, 0, 0.0745762)
    assert parsed.steps == ()


def test_claude_turn_cap_reads_like_the_old_text_output():
    parsed = parse_claude_stream(fixture("claude_max_turns.ndjson"), max_turns=1)
    assert (parsed.text, parsed.outcome) == ("Error: Reached max turns (1)", "max_turns")
    assert [(s.tool, s.ok, s.result_chars) for s in parsed.steps] == [("ToolSearch", True, 54)]


def test_claude_tool_steps_record_name_input_and_result_size():
    parsed = parse_claude_stream(fixture("claude_web_search.ndjson"), max_turns=3)
    assert parsed.outcome == "success"
    assert parsed.text.startswith("Today's top Hacker News story is \"Pi 1.0\"")
    assert [(s.seq, s.tool, s.input_summary, s.ok, s.result_chars) for s in parsed.steps] == [
        (1, "WebSearch", '{"query": "Hacker News top story today October 2 2026"}', True, 614),
    ]


def test_claude_subagent_is_linked_to_the_agent_call_that_started_it():
    parsed = parse_claude_stream(fixture("claude_subagent.ndjson"), max_turns=4)
    assert parsed.text == "pong"
    agent_call = "toolu_012W2fehySGywcXxK1kRsp3A"
    assert [(s.tool, s.parent_tool_use_id) for s in parsed.steps] == [
        ("Agent", None), ("SubagentHandback", agent_call),
    ]
    assert len(parsed.subagents) == 1
    sub = parsed.subagents[0]
    assert (sub.tool_use_id, sub.description, sub.model, sub.status) == (
        agent_call, "Reply pong", "claude-sonnet-5-5", "completed")
    assert (sub.usage.output_tokens, sub.usage.cache_write_tokens) == (24, 36146)
    assert parsed.usage.cost_usd == 0.1647092


def test_codex_streams():
    success = parse_codex_stream(fixture("codex_success.ndjson"))
    assert (success.text, success.outcome) == ("ok", "success")
    assert success.usage == Usage(17377, 0, 24576, 78, 18, None)

    command = parse_codex_stream(fixture("codex_command.ndjson"))
    assert command.text == "hello-from-codex"
    assert [(s.tool, s.input_summary, s.ok, s.result_chars) for s in command.steps][1] == (
        "command_execution", "/bin/zsh -lc 'echo hello-from-codex'", True, 17)


def test_a_stream_without_a_result_event_is_an_error():
    parsed = parse_claude_stream('{"type": "system", "subtype": "init", "model": "m"}\n')
    assert (parsed.outcome, parsed.error) == ("error", "no result event in the stream")


class FakeRunner:
    """Stands in for run_claude_process: replays fixture output per call."""

    def __init__(self, *outputs: ClaudeProcessResult):
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def __call__(self, argv, *, timeout, input_text=None, cwd=None, env=None):
        self.calls.append({"argv": argv, "timeout": timeout, "env": env})
        return self.outputs.pop(0)


def test_call_model_returns_text_and_records_it():
    runner = FakeRunner(ClaudeProcessResult(fixture("claude_success.ndjson"), "", 0))
    recorded = []
    result = call_model(CallRequest(task="research_agent", prompt="hi", env={"MINDPATTERN_AGENT": "news"}),
                        route=CLAUDE, runner=runner, recorder=lambda *args: recorded.append(args))
    assert (result.text, result.outcome, result.ok, result.provider) == ("ok", "success", True, "claude")
    assert runner.calls[0]["timeout"] == 1800
    env = runner.calls[0]["env"]
    assert (env["CLAUDE_INVOKED_BY"], env["MINDPATTERN_TASK"], env["MINDPATTERN_AGENT"]) == (
        "mindpattern", "research_agent", "news")
    assert len(recorded) == 1 and recorded[0][2] is result


def test_a_timeout_falls_back_once_and_both_attempts_are_recorded():
    route = Route("site_story_critic", "codex", "gpt-6.1-sol", 300,
                  fallback=Route("site_story_critic", "claude", "claude-sonnet-5-5", 300, max_turns=5))
    runner = FakeRunner(
        ClaudeProcessResult("", "", 1, timed_out=True, error="Timed out after 300s"),
        ClaudeProcessResult(fixture("claude_success.ndjson"), "", 0),
    )
    recorded = []
    result = call_model(CallRequest(task="site_story_critic", prompt="judge"), route=route, runner=runner,
                        recorder=lambda *args: recorded.append(args[2]))
    assert [r.outcome for r in recorded] == ["timeout", "success"]
    assert (result.provider, result.text, result.fell_back) == ("claude", "ok", True)
    assert runner.calls[0]["argv"][0] == "codex" and runner.calls[1]["argv"][0] == "claude"


def test_a_successful_text_about_rate_limits_is_still_a_success():
    stream = fixture("claude_success.ndjson").replace('"result": "ok"', '"result": "Anthropic raised its rate limit"')
    result = call_model(CallRequest(task="synthesis_pass2", prompt="write"), route=CLAUDE,
                        runner=FakeRunner(ClaudeProcessResult(stream, "", 0)), recorder=None)
    assert (result.outcome, result.text) == ("success", "Anthropic raised its rate limit")


def test_run_task_process_hands_old_callers_the_text_output_they_parse():
    process = run_task_process("research_agent", prompt="go",
                               runner=FakeRunner(ClaudeProcessResult(fixture("claude_max_turns.ndjson"), "", 1)),
                               recorder=None)
    assert (process.stdout, process.returncode, process.timed_out) == ("Error: Reached max turns (35)", 1, False)


def test_plain_text_stdout_passes_through_as_text_mode_output():
    parsed = parse_claude_stream("API Error: Connection closed mid-response.\n")
    assert (parsed.text, parsed.outcome) == ("API Error: Connection closed mid-response.\n", "text")
    result = call_model(CallRequest(task="writer", prompt="x"), route=CLAUDE, recorder=None,
                        runner=FakeRunner(ClaudeProcessResult('{"findings": []}', "", 0)))
    assert (result.text, result.outcome) == ('{"findings": []}', "success")


def test_tests_record_model_calls_into_a_temp_folder(tmp_path):
    import os
    from core.trace_store import traces_db_path, traces_root
    assert os.environ["MP_TRACE_ROOT"].startswith(str(tmp_path))
    assert traces_root("ramsay") == tmp_path / "model-traces"
    assert traces_db_path("ramsay") == tmp_path / "model-traces" / "traces.db"


def test_a_trace_that_cannot_be_written_never_fails_the_call():
    """Fly's Slack handlers call models too; a read-only disk there must not cost a draft."""
    stream = fixture("claude_success.ndjson")

    def recorder(*args):
        raise OSError("read-only file system")

    result = call_model(CallRequest(task="writer", prompt="draft"), route=CLAUDE, recorder=recorder,
                        runner=lambda argv, **kw: ClaudeProcessResult(stream, "", 0))
    assert (result.outcome, result.ok) == ("success", True)
    assert result.text == parse_claude_stream(stream).text

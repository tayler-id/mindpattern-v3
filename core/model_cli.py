"""One way to call a model: the claude or codex CLI, headless, with every call traced.

Python decides which task runs. config/models.json decides which provider and
model run it. This module builds the argv, runs the process, reads the CLI's
event stream, and hands back a ModelResult whose `.text` is exactly what the
old `--output-format text` call printed, so callers keep their parsing.

Every call runs in a clean context. Claude skips the user's own settings,
plugins, hooks and MCP servers (--setting-sources project,local and
--strict-mcp-config): on 2026-10-02 a one-word call cost $0.075 with them and
$0.017 without, and the user's pstack hook was injecting engineering
instructions into every research agent. CLAUDE_INVOKED_BY tells the project's
own SessionStart/SessionEnd hooks to skip pipeline sessions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import json
import logging
import os
from pathlib import Path
import time
import uuid

from core.claude_cli import ClaudeProcessResult, run_claude_process
from core.config import Route, route_for

logger = logging.getLogger(__name__)

PIPELINE_MARKER = "mindpattern"
CLAUDE_CLEAN_CONTEXT = ("--setting-sources", "project,local", "--strict-mcp-config")
# Codex reads its login from the user's config, so that file has to load. These
# switch off what it would otherwise pull in: on 2026-10-02 a one-word call read
# the user's unslop skill first (42K input tokens); with these, 18K and no reads.
# ~/.codex/AGENTS.md still loads; no flag skips it without dropping the login.
CODEX_CLEAN_CONTEXT = (
    "--ignore-rules",
    "-c", "features.plugins=false", "-c", "features.skill_search=false", "-c", "features.hooks=false",
    "-c", "features.apps=false", "-c", "features.browser_use=false", "-c", "features.computer_use=false",
)
# Past this size a prompt goes through stdin: the OS argument limit truncates silently.
STDIN_THRESHOLD_CHARS = 100_000
# Outcomes that are worth one try on a route's fallback provider.
FALLBACK_OUTCOMES = ("timeout", "rate_limit", "error", "start_failed")
_RATE_LIMIT_MARKERS = ("rate limit", "usage limit", "hit your session limit", "429", "overloaded")


@dataclass(frozen=True)
class ToolPolicy:
    allowed: tuple[str, ...] = ()
    disallowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class CallRequest:
    task: str
    prompt: str
    system_prompt_file: Path | None = None
    tools: ToolPolicy = ToolPolicy()
    unit: str | None = None
    cwd: Path | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    # A contracts/*.schema.json file. Codex enforces it (--output-schema); for
    # Claude the caller checks the parsed answer with core.contracts.
    output_schema: Path | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None


@dataclass(frozen=True)
class Step:
    """One tool call. parent_tool_use_id is set when a subagent made it."""

    seq: int
    tool: str
    tool_use_id: str | None
    input_summary: str
    ok: bool | None = None
    result_chars: int = 0
    parent_tool_use_id: str | None = None


@dataclass(frozen=True)
class Subagent:
    tool_use_id: str
    description: str
    model: str | None
    status: str | None
    usage: Usage


@dataclass(frozen=True)
class ParsedStream:
    text: str
    outcome: str
    turns: int | None
    model: str | None
    session_id: str | None
    usage: Usage
    steps: tuple[Step, ...]
    subagents: tuple[Subagent, ...]
    error: str | None = None


@dataclass(frozen=True)
class ModelResult:
    call_id: str
    task: str
    provider: str
    model: str
    text: str
    exit_code: int
    stderr: str
    timed_out: bool
    outcome: str
    usage: Usage
    turns: int | None
    duration_ms: int
    parsed: ParsedStream | None = None
    fell_back: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "success" and self.exit_code == 0


# ---------------------------------------------------------------------------
# argv
# ---------------------------------------------------------------------------


def claude_argv(route: Route, request: CallRequest, *, via_stdin: bool) -> list[str]:
    # With stdin, pass no prompt argument: `claude -p -` makes "-" the prompt's
    # first line, which every stdin newsletter prompt carried until 2026-10-02.
    argv = ["claude", "-p"] if via_stdin else ["claude", "-p", request.prompt]
    argv += ["--model", route.model, "--output-format", "stream-json", "--verbose"]
    if route.effort:
        argv += ["--effort", route.effort]
    if route.max_turns:
        argv += ["--max-turns", str(route.max_turns)]
    if request.system_prompt_file:
        argv += ["--append-system-prompt-file", str(request.system_prompt_file)]
    for tool in request.tools.allowed:
        argv += ["--allowedTools", tool]
    if request.tools.disallowed:
        argv += ["--disallowedTools", ",".join(request.tools.disallowed)]
    argv += list(CLAUDE_CLEAN_CONTEXT)
    return argv


def codex_argv(route: Route, request: CallRequest, *, via_stdin: bool) -> list[str]:
    argv = ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check",
            "--sandbox", "read-only", "-m", route.model, *CODEX_CLEAN_CONTEXT]
    if route.effort:
        argv += ["-c", f'model_reasoning_effort="{route.effort}"']
    if request.output_schema:
        argv += ["--output-schema", str(request.output_schema)]
    argv.append("-" if via_stdin else _codex_prompt(request))
    return argv


def _codex_prompt(request: CallRequest) -> str:
    """Codex has no system-prompt flag, so the system file leads the prompt."""
    if not request.system_prompt_file:
        return request.prompt
    system = Path(request.system_prompt_file).read_text()
    return f"{system.rstrip()}\n\n---\n\n{request.prompt}"


def build_argv(route: Route, request: CallRequest) -> tuple[list[str], str | None]:
    """(argv, stdin text) for one call."""
    if route.provider == "codex":
        prompt = _codex_prompt(request)
        via_stdin = len(prompt) > STDIN_THRESHOLD_CHARS
        # Always hand codex a closed stdin: given an open one it waits to read more input.
        return codex_argv(route, request, via_stdin=via_stdin), (prompt if via_stdin else "")
    via_stdin = len(request.prompt) > STDIN_THRESHOLD_CHARS
    return claude_argv(route, request, via_stdin=via_stdin), (request.prompt if via_stdin else None)


def call_env(request: CallRequest) -> dict[str, str]:
    env = {**os.environ, **request.env}
    env["CLAUDE_INVOKED_BY"] = PIPELINE_MARKER
    env["MINDPATTERN_TASK"] = request.task
    return env


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------


def _events(stdout: str) -> list[dict]:
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and "type" in event:
            events.append(event)
    return events


def _summary(value: object, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + "..."


def _usage_from_claude(raw: Mapping | None, cost: float | None = None) -> Usage:
    raw = raw or {}
    details = raw.get("output_tokens_details") or {}
    return Usage(
        input_tokens=int(raw.get("input_tokens") or 0),
        cache_write_tokens=int(raw.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(raw.get("cache_read_input_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
        reasoning_tokens=int(details.get("thinking_tokens") or 0),
        cost_usd=cost,
    )


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(
        a.input_tokens + b.input_tokens,
        a.cache_write_tokens + b.cache_write_tokens,
        a.cache_read_tokens + b.cache_read_tokens,
        a.output_tokens + b.output_tokens,
        a.reasoning_tokens + b.reasoning_tokens,
        None,
    )


def parse_claude_stream(stdout: str, *, max_turns: int | None = None) -> ParsedStream:
    """Read `claude -p --output-format stream-json --verbose` output."""
    steps: list[Step] = []
    by_tool_use: dict[str, int] = {}
    subagent_usage: dict[str, Usage] = {}
    subagent_model: dict[str, str] = {}
    subagent_meta: dict[str, dict] = {}
    seen_messages: set[str] = set()
    model = session_id = None
    result: dict | None = None

    for event in _events(stdout):
        kind = event.get("type")
        parent = event.get("parent_tool_use_id")
        if kind == "system":
            if event.get("subtype") == "init":
                model = event.get("model") or model
                session_id = event.get("session_id") or session_id
            tool_use_id = event.get("tool_use_id")
            if tool_use_id and event.get("subtype", "").startswith("task_"):
                meta = subagent_meta.setdefault(tool_use_id, {})
                meta["description"] = event.get("description") or meta.get("description", "")
                if event.get("status"):
                    meta["status"] = event["status"]
        elif kind == "assistant":
            message = event.get("message") or {}
            message_id = message.get("id")
            if parent and message_id and message_id not in seen_messages:
                subagent_usage[parent] = _add(subagent_usage.get(parent, Usage()),
                                              _usage_from_claude(message.get("usage")))
                subagent_model[parent] = message.get("model") or subagent_model.get(parent, "")
            if message_id:
                seen_messages.add(message_id)
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    by_tool_use[block.get("id")] = len(steps)
                    steps.append(Step(
                        seq=len(steps) + 1,
                        tool=str(block.get("name")),
                        tool_use_id=block.get("id"),
                        input_summary=_summary(block.get("input")),
                        parent_tool_use_id=parent,
                    ))
        elif kind == "user":
            message = event.get("message") or {}
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                index = by_tool_use.get(block.get("tool_use_id"))
                if index is None:
                    continue
                body = block.get("content")
                chars = len(body) if isinstance(body, str) else len(json.dumps(body or ""))
                steps[index] = replace(steps[index], ok=not block.get("is_error"), result_chars=chars)
        elif kind == "result":
            result = event
            session_id = event.get("session_id") or session_id

    subagents = tuple(
        Subagent(
            tool_use_id=tool_use_id,
            description=subagent_meta.get(tool_use_id, {}).get("description", ""),
            model=subagent_model.get(tool_use_id),
            status=subagent_meta.get(tool_use_id, {}).get("status"),
            usage=subagent_usage.get(tool_use_id, Usage()),
        )
        for tool_use_id in dict.fromkeys(
            [s.parent_tool_use_id for s in steps if s.parent_tool_use_id]
            + list(subagent_usage) + list(subagent_meta)
        )
    )

    if result is None:
        if not _events(stdout) and stdout.strip():
            # Plain text, not an event stream: pass it through as text-mode
            # output so the caller's own checks (API errors, refusals) see it.
            return ParsedStream(stdout, "text", None, model, session_id, Usage(), (), ())
        return ParsedStream("", "error", None, model, session_id, Usage(), tuple(steps), subagents,
                            error="no result event in the stream")
    usage = _usage_from_claude(result.get("usage"), result.get("total_cost_usd"))
    turns = result.get("num_turns")
    if result.get("terminal_reason") == "max_turns" or result.get("subtype") == "error_max_turns":
        cap = max_turns if max_turns is not None else turns
        return ParsedStream(f"Error: Reached max turns ({cap})", "max_turns", turns, model, session_id,
                            usage, tuple(steps), subagents, error="max_turns")
    text = result.get("result") or ""
    if result.get("is_error"):
        return ParsedStream(text, "error", turns, model, session_id, usage, tuple(steps), subagents,
                            error=text[:300] or str(result.get("subtype")))
    return ParsedStream(text, "success", turns, model, session_id, usage, tuple(steps), subagents)


def parse_codex_stream(stdout: str) -> ParsedStream:
    """Read `codex exec --json` output."""
    steps: list[Step] = []
    messages: list[str] = []
    usage = Usage()
    session_id = error = None
    turns = 0
    for event in _events(stdout):
        kind = event.get("type")
        if kind == "thread.started":
            session_id = event.get("thread_id")
        elif kind == "turn.completed":
            turns += 1
            raw = event.get("usage") or {}
            usage = _add(usage, Usage(
                input_tokens=int(raw.get("input_tokens") or 0) - int(raw.get("cached_input_tokens") or 0),
                cache_write_tokens=int(raw.get("cache_write_input_tokens") or 0),
                cache_read_tokens=int(raw.get("cached_input_tokens") or 0),
                output_tokens=int(raw.get("output_tokens") or 0),
                reasoning_tokens=int(raw.get("reasoning_output_tokens") or 0),
            ))
        elif kind in ("turn.failed", "error"):
            detail = event.get("error") or event.get("message") or event
            error = _summary(detail.get("message") if isinstance(detail, dict) else detail)
        elif kind == "item.completed":
            item = event.get("item") or {}
            item_type = item.get("type")
            if item_type == "agent_message":
                messages.append(item.get("text") or "")
            elif item_type and item_type not in ("reasoning", "todo_list"):
                tool_input = item.get("command") or item.get("query") or item.get("tool") or item.get("changes")
                output = item.get("aggregated_output") or item.get("result") or ""
                exit_code = item.get("exit_code")
                ok = None if exit_code is None and item.get("status") is None else (
                    exit_code == 0 if exit_code is not None else item.get("status") == "completed")
                steps.append(Step(
                    seq=len(steps) + 1,
                    tool=str(item_type),
                    tool_use_id=item.get("id"),
                    input_summary=_summary(tool_input or ""),
                    ok=ok,
                    result_chars=len(output) if isinstance(output, str) else len(json.dumps(output)),
                ))
    if not _events(stdout) and stdout.strip():
        # Plain text, not an event stream: pass it through, as for Claude.
        return ParsedStream(stdout, "text", None, None, None, Usage(), (), ())
    text = messages[-1] if messages else ""
    outcome = "error" if error or not messages else "success"
    return ParsedStream(text, outcome, turns or None, None, session_id, usage, tuple(steps), (), error=error)


# ---------------------------------------------------------------------------
# Calling
# ---------------------------------------------------------------------------

Runner = Callable[..., ClaudeProcessResult]
Recorder = Callable[[CallRequest, Route, ModelResult, str, str | None], None]


def _classify_failure(process: ClaudeProcessResult, parsed: ParsedStream) -> str:
    if process.timed_out:
        return "timeout"
    if process.error and not process.stdout:
        return "start_failed"
    if parsed.outcome in ("success", "text") and process.returncode == 0:
        # The text is the deliverable. A story about rate limits is not a rate limit.
        return "success"
    text = f"{parsed.text} {parsed.error or ''} {process.stderr}".lower()
    if any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return "rate_limit"
    return parsed.outcome if parsed.outcome not in ("success", "text") else "error"


def _run_once(request: CallRequest, route: Route, runner: Runner) -> tuple[ModelResult, str, str | None]:
    argv, stdin_text = build_argv(route, request)
    call_id = uuid.uuid4().hex[:16]
    started = time.monotonic()
    try:
        process = runner(argv, timeout=route.timeout_s, input_text=stdin_text,
                         cwd=request.cwd, env=call_env(request))
    except Exception as exc:  # the runner itself failed, not the model
        process = ClaudeProcessResult("", "", 1, error=str(exc))
    # Read the process through getattr: injected test runners return light objects.
    process = ClaudeProcessResult(
        stdout=getattr(process, "stdout", "") or "",
        stderr=getattr(process, "stderr", "") or "",
        returncode=getattr(process, "returncode", 1),
        timed_out=bool(getattr(process, "timed_out", False)),
        error=getattr(process, "error", None),
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    if route.provider == "codex":
        parsed = parse_codex_stream(process.stdout)
    else:
        parsed = parse_claude_stream(process.stdout, max_turns=route.max_turns)
    outcome = _classify_failure(process, parsed)
    result = ModelResult(
        call_id=call_id,
        task=request.task,
        provider=route.provider,
        model=parsed.model or route.model,
        text="" if process.timed_out else parsed.text,
        exit_code=process.returncode,
        stderr=process.stderr,
        timed_out=process.timed_out,
        outcome=outcome,
        usage=parsed.usage,
        turns=parsed.turns,
        duration_ms=duration_ms,
        parsed=parsed,
        error=process.error or parsed.error,
    )
    return result, process.stdout, stdin_text


def _default_recorder(request: CallRequest, route: Route, result: ModelResult,
                      raw_stdout: str, stdin_text: str | None) -> None:
    from core.trace_store import record_call

    record_call(request, route, result, raw_stdout)


def call_model(
    request: CallRequest,
    *,
    route: Route | None = None,
    runner: Runner = run_claude_process,
    recorder: Recorder | None = _default_recorder,
) -> ModelResult:
    """Run one model call for `request.task` and record it.

    A failure on a route with a fallback gets one try on the fallback. A
    recorder failure is logged and never fails the call.
    """
    route = route or route_for(request.task)
    attempts = [route] + ([route.fallback] if route.fallback else [])
    result: ModelResult | None = None
    for index, attempt in enumerate(attempts):
        result, raw_stdout, stdin_text = _run_once(request, attempt, runner)
        if index:
            result = replace(result, fell_back=True)
        if recorder is not None:
            try:
                recorder(request, attempt, result, raw_stdout, stdin_text)
            except Exception as exc:
                logger.warning("model call %s not recorded: %s", result.call_id, exc)
        if result.outcome not in FALLBACK_OUTCOMES:
            break
        if index + 1 < len(attempts):
            logger.warning("task %s: %s on %s:%s, trying fallback %s:%s", request.task, result.outcome,
                           attempt.provider, attempt.model, attempts[index + 1].provider,
                           attempts[index + 1].model)
    assert result is not None
    return result


def text_process(result: ModelResult) -> ClaudeProcessResult:
    """The ClaudeProcessResult an `--output-format text` call would have returned."""
    return ClaudeProcessResult(
        stdout=result.text,
        stderr=result.stderr,
        returncode=result.exit_code,
        timed_out=result.timed_out,
        error=result.error if result.timed_out or result.outcome == "start_failed" else None,
    )


def run_task_process(task: str, *, prompt: str, system_prompt_file: Path | None = None,
                     tools: ToolPolicy = ToolPolicy(), unit: str | None = None, cwd: Path | None = None,
                     env: Mapping[str, str] | None = None, route: Route | None = None,
                     output_schema: Path | None = None, runner: Runner = run_claude_process,
                     recorder: Recorder | None = _default_recorder) -> ClaudeProcessResult:
    """call_model for code that still reads a ClaudeProcessResult."""
    request = CallRequest(task=task, prompt=prompt, system_prompt_file=system_prompt_file, tools=tools,
                          unit=unit, cwd=cwd, env=dict(env or {}), output_schema=output_schema)
    return text_process(call_model(request, route=route, runner=runner, recorder=recorder))


def disallowed(tools: str | Sequence[str] | None) -> tuple[str, ...]:
    if not tools:
        return ()
    if isinstance(tools, str):
        return tuple(t.strip() for t in tools.split(",") if t.strip())
    return tuple(tools)

"""Record every model call: a traces.db row, its tool steps, its subagents, and the raw stream.

The runner sets the run context (run id, date, phase) as it moves through the
pipeline. core.model_cli calls record_call() after each call. A call made
outside a run (Slack bot, a tool script) is filed under run "adhoc".

Raw files: data/<user>/traces/<date>/<run_id>/<call_id>.events.jsonl.gz holds
the CLI's complete event stream, and <call_id>.prompt.md.gz holds the exact
prompt. They stay on this machine: they contain fetched pages and the identity
files.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import gzip
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Route
    from core.model_cli import CallRequest, ModelResult

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADHOC_RUN = "adhoc"

# One row per model call (core.model_cli) and one per subagent inside a call,
# linked by parent_call_id. Tool calls go in model_call_steps. The full event
# stream and prompt of each call sit in gzipped files named by events_path and
# prompt_path. The runner opens traces.db with get_db(), not init_db(), so the
# recorder creates these tables itself.
MODEL_CALL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS model_calls (
        id TEXT PRIMARY KEY,
        parent_call_id TEXT,
        run_id TEXT,
        run_date TEXT,
        phase TEXT,
        task TEXT NOT NULL,
        unit TEXT,
        provider TEXT NOT NULL,
        model TEXT,
        route_model TEXT,
        effort TEXT,
        outcome TEXT NOT NULL,
        exit_code INTEGER,
        timed_out INTEGER NOT NULL DEFAULT 0,
        fell_back INTEGER NOT NULL DEFAULT 0,
        turns INTEGER,
        duration_ms INTEGER,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        cache_write_tokens INTEGER NOT NULL DEFAULT 0,
        cache_read_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        reasoning_tokens INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL,
        session_id TEXT,
        error TEXT,
        prompt_chars INTEGER,
        text_chars INTEGER,
        step_count INTEGER NOT NULL DEFAULT 0,
        events_path TEXT,
        prompt_path TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_model_calls_run ON model_calls(run_id);
    CREATE INDEX IF NOT EXISTS idx_model_calls_date ON model_calls(run_date);
    CREATE INDEX IF NOT EXISTS idx_model_calls_parent ON model_calls(parent_call_id);

    CREATE TABLE IF NOT EXISTS model_call_steps (
        call_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        tool TEXT NOT NULL,
        tool_use_id TEXT,
        input_summary TEXT,
        ok INTEGER,
        result_chars INTEGER,
        PRIMARY KEY (call_id, seq)
    );
"""


def ensure_model_call_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(MODEL_CALL_SCHEMA)



@dataclass(frozen=True)
class RunContext:
    run_id: str | None = None
    run_date: str | None = None
    phase: str | None = None
    user_id: str | None = None


_context = RunContext()
_context_lock = threading.Lock()


def set_run_context(**fields: str | None) -> None:
    """Update the run id, date, phase, or user that later calls are filed under."""
    global _context
    with _context_lock:
        _context = replace(_context, **fields)


def clear_run_context() -> None:
    global _context
    with _context_lock:
        _context = RunContext()


def run_context() -> RunContext:
    with _context_lock:
        return _context


def _user(ctx: RunContext) -> str:
    return ctx.user_id or os.environ.get("MP_USER_ID") or os.environ.get("DASHBOARD_USER") or "ramsay"


def _override() -> Path | None:
    """MP_TRACE_ROOT sends every record to one folder: tests and replays use it."""
    value = os.environ.get("MP_TRACE_ROOT")
    return Path(value) if value else None


def traces_root(user_id: str) -> Path:
    override = _override()
    return override if override else PROJECT_ROOT / "data" / user_id / "traces"


def traces_db_path(user_id: str) -> Path:
    override = _override()
    if override:
        return override / "traces.db"
    # Same file orchestrator.traces_db resolves; core may not import orchestrator (layers.toml).
    return PROJECT_ROOT / "data" / user_id / "traces.db"


def _write_gz(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as handle:
        handle.write(text)
    tmp.replace(path)


def _relative(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def record_call(
    request: CallRequest,
    route: Route,
    result: ModelResult,
    raw_stdout: str,
    *,
    ctx: RunContext | None = None,
    db_path: Path | None = None,
    root: Path | None = None,
) -> None:
    """Write the raw files, then the call row, its subagent rows, and their steps."""
    ctx = ctx or run_context()
    user_id = _user(ctx)
    run_date = ctx.run_date or date.today().isoformat()
    run_id = ctx.run_id or ADHOC_RUN
    directory = (root or traces_root(user_id)) / run_date / run_id
    directory.mkdir(parents=True, exist_ok=True)
    events_path = directory / f"{result.call_id}.events.jsonl.gz"
    prompt_path = directory / f"{result.call_id}.prompt.md.gz"
    _write_gz(events_path, raw_stdout)
    system = f"[system prompt file: {request.system_prompt_file}]\n\n" if request.system_prompt_file else ""
    _write_gz(prompt_path, system + request.prompt)

    parsed = result.parsed
    steps = parsed.steps if parsed else ()
    subagents = parsed.subagents if parsed else ()
    child_ids = {sub.tool_use_id: f"{result.call_id}.{index}" for index, sub in enumerate(subagents, 1)}
    usage = result.usage

    rows = [(
        result.call_id, None, run_id, run_date, ctx.phase, request.task, request.unit, result.provider,
        result.model, route.model, route.effort, result.outcome, result.exit_code, int(result.timed_out),
        int(result.fell_back), result.turns, result.duration_ms, usage.input_tokens, usage.cache_write_tokens,
        usage.cache_read_tokens, usage.output_tokens, usage.reasoning_tokens, usage.cost_usd,
        parsed.session_id if parsed else None, result.error, len(request.prompt), len(result.text),
        sum(1 for s in steps if not s.parent_tool_use_id), _relative(events_path), _relative(prompt_path),
    )]
    for sub in subagents:
        sub_usage = sub.usage
        rows.append((
            child_ids[sub.tool_use_id], result.call_id, run_id, run_date, ctx.phase, f"{request.task}:subagent",
            sub.description or request.unit, result.provider, sub.model, None, None, sub.status or "unknown",
            None, 0, 0, None, None, sub_usage.input_tokens, sub_usage.cache_write_tokens,
            sub_usage.cache_read_tokens, sub_usage.output_tokens, sub_usage.reasoning_tokens, None, None, None,
            None, None, sum(1 for s in steps if s.parent_tool_use_id == sub.tool_use_id),
            _relative(events_path), None,
        ))

    step_rows = []
    sequence: dict[str, int] = {}
    for step in steps:
        owner = child_ids.get(step.parent_tool_use_id, result.call_id)
        sequence[owner] = sequence.get(owner, 0) + 1
        step_rows.append((owner, sequence[owner], step.tool, step.tool_use_id, step.input_summary,
                          None if step.ok is None else int(step.ok), step.result_chars))

    db = db_path or traces_db_path(user_id)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        ensure_model_call_tables(conn)
        conn.executemany(
            "INSERT OR REPLACE INTO model_calls (id, parent_call_id, run_id, run_date, phase, task, unit, "
            "provider, model, route_model, effort, outcome, exit_code, timed_out, fell_back, turns, "
            "duration_ms, input_tokens, cache_write_tokens, cache_read_tokens, output_tokens, "
            "reasoning_tokens, cost_usd, session_id, error, prompt_chars, text_chars, step_count, "
            "events_path, prompt_path) VALUES (" + ",".join("?" * 30) + ")",
            rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO model_call_steps (call_id, seq, tool, tool_use_id, input_summary, ok, "
            "result_chars) VALUES (?, ?, ?, ?, ?, ?, ?)",
            step_rows,
        )
        conn.commit()
    finally:
        conn.close()


def prune_raw_traces(keep_days: int, *, user_id: str = "ramsay", root: Path | None = None,
                     today: date | None = None) -> list[str]:
    """Delete raw trace folders older than keep_days. traces.db rows are kept."""
    base = root or traces_root(user_id)
    if not base.is_dir():
        return []
    cutoff = (today or date.today()) - timedelta(days=keep_days)
    removed = []
    for folder in sorted(base.iterdir()):
        try:
            folder_day = datetime.strptime(folder.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if folder.is_dir() and folder_day < cutoff:
            shutil.rmtree(folder)
            removed.append(folder.name)
    return removed


OBSERVABILITY_POLICY = PROJECT_ROOT / "policies" / "observability.json"


@dataclass(frozen=True)
class ObservabilityPolicy:
    raw_trace_days: int
    budget_output_tokens: int
    budget_api_price_usd: float


def load_observability_policy(path: Path = OBSERVABILITY_POLICY) -> ObservabilityPolicy:
    data = json.loads(path.read_text())
    budget = data.get("soft_budget_per_run") or {}
    values = (data.get("raw_trace_days"), budget.get("output_tokens"), budget.get("api_price_usd"))
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in values):
        raise ValueError(f"{path.name}: raw_trace_days and both soft_budget_per_run values must be positive numbers")
    return ObservabilityPolicy(int(values[0]), int(values[1]), float(values[2]))


def run_totals(run_id: str, *, db_path: Path | None = None, user_id: str = "ramsay") -> dict:
    """Calls, output tokens, and CLI-reported cost for one run (parent calls only)."""
    db = db_path or traces_db_path(user_id)
    if not db.exists():
        return {"calls": 0, "output_tokens": 0, "api_price_usd": 0.0}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        ensure = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_calls'").fetchone()
        if not ensure:
            return {"calls": 0, "output_tokens": 0, "api_price_usd": 0.0}
        calls, output, cost = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(output_tokens), 0), COALESCE(SUM(cost_usd), 0) FROM model_calls "
            "WHERE run_id = ? AND parent_call_id IS NULL", (run_id,)).fetchone()
    finally:
        conn.close()
    return {"calls": calls, "output_tokens": output, "api_price_usd": round(cost, 2)}


def over_budget(totals: dict, policy: ObservabilityPolicy) -> list[str]:
    reasons = []
    if totals["output_tokens"] > policy.budget_output_tokens:
        reasons.append(f"{totals['output_tokens']:,} output tokens (soft budget {policy.budget_output_tokens:,})")
    if totals["api_price_usd"] > policy.budget_api_price_usd:
        reasons.append(f"${totals['api_price_usd']} at API prices (soft budget ${policy.budget_api_price_usd:g})")
    return reasons

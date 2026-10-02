"""See what every agent did in any run.

    .venv/bin/python3 -m orchestrator.trace runs --last 7
    .venv/bin/python3 -m orchestrator.trace show <run_id> [--steps]
    .venv/bin/python3 -m orchestrator.trace call <call_id> [--full]
    .venv/bin/python3 -m orchestrator.trace grep <run_id> "<text>"
    .venv/bin/python3 -m orchestrator.trace usage --since 7 [--by task,model]
    .venv/bin/python3 -m orchestrator.trace prune --keep-days 90

Reads the model_calls and model_call_steps tables that core.trace_store writes,
and the gzipped event stream kept for each call.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import gzip
import json
from pathlib import Path
import sqlite3
import sys

from core.trace_store import PROJECT_ROOT, prune_raw_traces, traces_db_path, traces_root

_CALL_COLUMNS = ("id, parent_call_id, run_id, run_date, phase, task, unit, provider, model, outcome, turns, "
                 "duration_ms, input_tokens, cache_write_tokens, cache_read_tokens, output_tokens, cost_usd, "
                 "step_count, error, events_path, prompt_path, fell_back")


def _connect(db: Path) -> sqlite3.Connection:
    if not db.exists():
        raise SystemExit(f"no traces database at {db}")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _raw(path: str | None, root: Path) -> str:
    if not path:
        return ""
    full = Path(path) if Path(path).is_absolute() else root / path
    if not full.exists():
        return ""
    with gzip.open(full, "rt", encoding="utf-8") as handle:
        return handle.read()


def _money(value: float | None) -> str:
    return "-" if value is None else f"${value:.3f}"


def _tokens(row: sqlite3.Row) -> str:
    return f"out {row['output_tokens']:,} in {row['input_tokens'] + row['cache_write_tokens']:,} cached {row['cache_read_tokens']:,}"


def cmd_runs(conn: sqlite3.Connection, last: int) -> list[str]:
    rows = conn.execute(
        "SELECT run_id, run_date, COUNT(*) AS calls, SUM(outcome NOT IN ('success','completed')) AS failed, "
        "SUM(output_tokens) AS output_tokens, SUM(cost_usd) AS cost, MIN(created_at) AS started "
        "FROM model_calls WHERE parent_call_id IS NULL GROUP BY run_id ORDER BY started DESC LIMIT ?",
        (last,),
    ).fetchall()
    lines = [f"{'run':38} {'date':10} {'calls':>5} {'failed':>6} {'output':>10} {'cost':>9}"]
    for row in rows:
        lines.append(f"{row['run_id']:38} {row['run_date']:10} {row['calls']:>5} {row['failed']:>6} "
                     f"{row['output_tokens']:>10,} {_money(row['cost']):>9}")
    return lines


def cmd_show(conn: sqlite3.Connection, run_id: str, with_steps: bool) -> list[str]:
    calls = conn.execute(f"SELECT {_CALL_COLUMNS} FROM model_calls WHERE run_id = ? ORDER BY created_at, id",
                         (run_id,)).fetchall()
    if not calls:
        return [f"no calls recorded for run {run_id}"]
    children: dict[str, list[sqlite3.Row]] = {}
    for row in calls:
        if row["parent_call_id"]:
            children.setdefault(row["parent_call_id"], []).append(row)
    lines = [f"run {run_id} ({calls[0]['run_date']})"]
    phase = object()
    for row in calls:
        if row["parent_call_id"]:
            continue
        if row["phase"] != phase:
            phase = row["phase"]
            lines.append(f"  phase {phase or '-'}")
        fallback = " [fallback]" if row["fell_back"] else ""
        lines.append(f"    {row['id']}  {row['task']:<18} {row['unit'] or '':<28} {row['provider']}:{row['model']}"
                     f"  {row['outcome']}{fallback}  turns {row['turns'] or '-'}  {_tokens(row)}  "
                     f"{_money(row['cost_usd'])}  steps {row['step_count']}")
        if row["error"] and row["outcome"] != "success":
            lines.append(f"      error: {row['error'][:160]}")
        if with_steps:
            lines.extend(_step_lines(conn, row["id"], indent="      "))
        for child in children.get(row["id"], []):
            lines.append(f"      subagent {child['id']}  {child['unit'] or ''}  {child['model'] or ''}  "
                         f"{child['outcome']}  out {child['output_tokens']:,}  steps {child['step_count']}")
            if with_steps:
                lines.extend(_step_lines(conn, child["id"], indent="        "))
    return lines


def _step_lines(conn: sqlite3.Connection, call_id: str, *, indent: str) -> list[str]:
    rows = conn.execute("SELECT seq, tool, input_summary, ok, result_chars FROM model_call_steps "
                        "WHERE call_id = ? ORDER BY seq", (call_id,)).fetchall()
    marks = {1: "ok", 0: "ERR", None: "?"}
    return [f"{indent}{row['seq']:>3}. {row['tool']:<18} {marks[row['ok']]:<3} {row['result_chars']:>7} chars  "
            f"{(row['input_summary'] or '')[:110]}" for row in rows]


def _conversation(stream: str, provider: str) -> list[str]:
    lines = []
    for raw in stream.splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if provider == "codex":
            item = event.get("item") or {}
            if kind == "item.completed" and item.get("type") == "agent_message":
                lines.append(f"assistant: {item.get('text', '')}")
            elif kind == "item.completed" and item.get("type") == "command_execution":
                lines.append(f"-> $ {item.get('command')} (exit {item.get('exit_code')})")
                lines.append(f"<- {str(item.get('aggregated_output', ''))[:400]}")
            elif kind == "turn.completed":
                lines.append(f"[turn usage {json.dumps(event.get('usage'))}]")
            continue
        prefix = "  [subagent] " if event.get("parent_tool_use_id") else ""
        if kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "text":
                    lines.append(f"{prefix}assistant: {block.get('text', '')}")
                elif block.get("type") == "tool_use":
                    lines.append(f"{prefix}-> {block.get('name')} {json.dumps(block.get('input'), ensure_ascii=False)[:400]}")
        elif kind == "user":
            content = (event.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    body = block.get("content")
                    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
                    flag = " ERROR" if block.get("is_error") else ""
                    lines.append(f"{prefix}<-{flag} {text[:400]}")
        elif kind == "result":
            lines.append(f"[result {event.get('subtype')} turns {event.get('num_turns')} "
                         f"cost {event.get('total_cost_usd')}]")
    return lines


def cmd_call(conn: sqlite3.Connection, call_id: str, full: bool, root: Path) -> list[str]:
    row = conn.execute(f"SELECT {_CALL_COLUMNS} FROM model_calls WHERE id = ?", (call_id,)).fetchone()
    if row is None:
        return [f"no call {call_id}"]
    lines = [
        f"call {row['id']}  run {row['run_id']}  phase {row['phase'] or '-'}",
        f"task {row['task']}  unit {row['unit'] or '-'}  {row['provider']}:{row['model']}  outcome {row['outcome']}",
        f"turns {row['turns'] or '-'}  {_tokens(row)}  cost {_money(row['cost_usd'])}  "
        f"duration {row['duration_ms'] or 0} ms",
    ]
    if row["error"]:
        lines.append(f"error: {row['error']}")
    lines.append("steps:")
    lines.extend(_step_lines(conn, call_id, indent="  "))
    if full:
        lines.append("prompt:")
        lines.extend("  " + line for line in _raw(row["prompt_path"], root).splitlines())
        lines.append("conversation:")
        lines.extend("  " + line for line in _conversation(_raw(row["events_path"], root), row["provider"]))
    return lines


def cmd_grep(conn: sqlite3.Connection, run_id: str, needle: str, root: Path) -> list[str]:
    rows = conn.execute("SELECT id, task, unit, events_path FROM model_calls WHERE run_id = ? AND "
                        "parent_call_id IS NULL ORDER BY created_at", (run_id,)).fetchall()
    lowered = needle.lower()
    lines = []
    for row in rows:
        for raw in _raw(row["events_path"], root).splitlines():
            position = raw.lower().find(lowered)
            if position >= 0:
                snippet = raw[max(0, position - 80): position + 120].replace("\\n", " ")
                lines.append(f"{row['id']}  {row['task']}  {row['unit'] or ''}: ...{snippet}...")
    return lines or [f"no match for {needle!r} in run {run_id}"]


def cmd_usage(conn: sqlite3.Connection, since_days: int, by: list[str], today: date | None = None) -> list[str]:
    allowed = {"task", "model", "provider", "phase", "run_date"}
    columns = [c for c in by if c in allowed] or ["task", "model"]
    start = ((today or date.today()) - timedelta(days=since_days)).isoformat()
    group = ", ".join(columns)
    rows = conn.execute(
        f"SELECT {group}, COUNT(*) AS calls, SUM(output_tokens) AS output_tokens, "
        "SUM(input_tokens + cache_write_tokens) AS new_input, SUM(cache_read_tokens) AS cached, "
        "SUM(cost_usd) AS cost FROM model_calls WHERE parent_call_id IS NULL AND run_date >= ? "
        f"GROUP BY {group} ORDER BY cost DESC", (start,),
    ).fetchall()
    header = " ".join(f"{c:22}" for c in columns)
    lines = [f"since {start}", f"{header} {'calls':>6} {'output':>11} {'new input':>12} {'cached':>13} {'cost':>9}"]
    for row in rows:
        keys = " ".join(f"{str(row[c]):22}" for c in columns)
        lines.append(f"{keys} {row['calls']:>6} {row['output_tokens']:>11,} {row['new_input']:>12,} "
                     f"{row['cached']:>13,} {_money(row['cost']):>9}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m orchestrator.trace", description=__doc__.splitlines()[0])
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--db", type=Path, help="traces.db path (default: data/<user>/traces.db)")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT,
                        help="directory that events_path and prompt_path are relative to")
    commands = parser.add_subparsers(dest="command", required=True)
    runs = commands.add_parser("runs")
    runs.add_argument("--last", type=int, default=10)
    show = commands.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--steps", action="store_true")
    call = commands.add_parser("call")
    call.add_argument("call_id")
    call.add_argument("--full", action="store_true")
    grep = commands.add_parser("grep")
    grep.add_argument("run_id")
    grep.add_argument("text")
    usage = commands.add_parser("usage")
    usage.add_argument("--since", type=int, default=7, help="days back")
    usage.add_argument("--by", default="task,model")
    prune = commands.add_parser("prune")
    prune.add_argument("--keep-days", type=int, required=True)
    args = parser.parse_args(argv)

    if args.command == "prune":
        removed = prune_raw_traces(args.keep_days, user_id=args.user, root=traces_root(args.user))
        print(f"removed {len(removed)} day folders" + (f": {', '.join(removed)}" if removed else ""))
        return 0
    conn = _connect(args.db or traces_db_path(args.user))
    try:
        if args.command == "runs":
            lines = cmd_runs(conn, args.last)
        elif args.command == "show":
            lines = cmd_show(conn, args.run_id, args.steps)
        elif args.command == "call":
            lines = cmd_call(conn, args.call_id, args.full, args.root)
        elif args.command == "grep":
            lines = cmd_grep(conn, args.run_id, args.text, args.root)
        else:
            lines = cmd_usage(conn, args.since, args.by.split(","))
    finally:
        conn.close()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

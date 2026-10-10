#!/usr/bin/env python3
"""How the daily pipeline has been running: one row per day, per-agent output, and problems.

    .venv/bin/python3 devtools/health.py                # last 7 days
    .venv/bin/python3 devtools/health.py --since 14 --json

Reads only what the pipeline records: traces.db (runs, events, model calls),
memory.db (findings per agent), and the site story folders. Opens every
database read-only. Exits 1 when any day has a problem, so a scheduler can
alert on it.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_RUN_ID = re.compile(r"^research-(\d{4}-\d{2}-\d{2})-")


@dataclass
class Day:
    date: str
    run_id: str | None = None
    status: str | None = None
    minutes: int | None = None
    sent: bool | None = None
    agents_ok: int | None = None
    findings: int | None = None
    duplicates_removed: int | None = None
    eval_overall: float | None = None
    site_stories: int = 0
    claude_usd: float = 0.0
    codex_calls: int = 0
    failed_calls: int = 0
    fallbacks: int = 0
    flags: list[str] = field(default_factory=list)


def _ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _research_result(payload: dict) -> dict:
    """phase_research_complete stores its result as a Python repr string."""
    raw = payload.get("result")
    if isinstance(raw, dict):
        return raw
    try:
        value = ast.literal_eval(raw) if isinstance(raw, str) else {}
    except (ValueError, SyntaxError):
        return {}
    return value if isinstance(value, dict) else {}


def _minutes(started: str | None, completed: str | None) -> int | None:
    try:
        return round((datetime.fromisoformat(completed) - datetime.fromisoformat(started)).total_seconds() / 60)
    except (TypeError, ValueError):
        return None


def collect_days(root: Path, user: str, dates: list[str]) -> list[Day]:
    traces = _ro(root / "data" / user / "traces.db")
    stories = root / "reports" / user / "site-stories"
    days = {d: Day(date=d) for d in dates}
    if traces is not None:
        with traces:
            # A day can hold more than one run record: a sync-only retry opens
            # its own with no events. The day's run is the one that recorded the most.
            runs = traces.execute(
                "SELECT r.id, r.status, r.started_at, r.completed_at, "
                "(SELECT count(*) FROM events e WHERE e.pipeline_run_id = r.id) AS n_events "
                "FROM pipeline_runs r WHERE r.pipeline_type='research' "
                "ORDER BY n_events, r.started_at").fetchall()
            for run in runs:
                match = _RUN_ID.match(run["id"] or "")
                if not match or match.group(1) not in days:
                    continue
                day = days[match.group(1)]
                day.run_id, day.status = run["id"], run["status"]
                day.minutes = _minutes(run["started_at"], run["completed_at"])
            for day in days.values():
                if day.run_id is None:
                    continue
                for row in traces.execute(
                        "SELECT event_type, payload FROM events WHERE pipeline_run_id=? ORDER BY id",
                        (day.run_id,)):
                    try:
                        payload = json.loads(row["payload"] or "{}")
                    except json.JSONDecodeError:
                        continue
                    kind = row["event_type"]
                    if kind == "newsletter_sent":
                        day.sent = bool(payload.get("success"))
                    elif kind == "cross_agent_dedup":
                        day.duplicates_removed = payload.get("removed")
                    elif kind == "newsletter_evaluation":
                        day.eval_overall = payload.get("overall")
                    elif kind == "phase_research_complete":
                        result = _research_result(payload)
                        day.findings = result.get("findings_stored", day.findings)
                        day.agents_ok = result.get("agents_succeeded", day.agents_ok)
                calls = traces.execute(
                    "SELECT coalesce(sum(CASE WHEN provider='claude' THEN cost_usd END), 0), "
                    "sum(provider='codex'), sum(outcome!='success'), sum(fell_back) "
                    "FROM model_calls WHERE run_id=? AND parent_call_id IS NULL", (day.run_id,)).fetchone()
                day.claude_usd = round(calls[0] or 0.0, 2)
                day.codex_calls, day.failed_calls, day.fallbacks = (calls[1] or 0, calls[2] or 0, calls[3] or 0)
    for day in days.values():
        folder = stories / day.date
        day.site_stories = sum(1 for _ in folder.glob("*.json")) if folder.is_dir() else 0
    return [days[d] for d in dates]


def flag_days(days: list[Day], *, min_findings: int, min_agents: int, min_eval: float,
              site_target: int) -> None:
    for day in days:
        if day.run_id is None:
            day.flags.append("no pipeline run")
            continue
        if day.status != "completed":
            day.flags.append(f"run {day.status}")
        if day.sent is False:
            day.flags.append("newsletter not sent")
        if day.findings is not None and day.findings < min_findings:
            day.flags.append(f"{day.findings} findings, floor {min_findings}")
        if day.agents_ok is not None and day.agents_ok < min_agents:
            day.flags.append(f"{day.agents_ok} agents succeeded, floor {min_agents}")
        if day.eval_overall is not None and day.eval_overall < min_eval:
            day.flags.append(f"eval {day.eval_overall}, floor {min_eval}")
        if day.site_stories < site_target:
            day.flags.append(f"{day.site_stories} site stories, target {site_target}")
        if day.failed_calls:
            day.flags.append(f"{day.failed_calls} failed model calls")
        if day.fallbacks:
            day.flags.append(f"{day.fallbacks} calls fell back")


def agent_output(root: Path, user: str, window: list[str], previous: list[str]) -> list[dict]:
    """Average findings per run day for each agent, this window against the one before."""
    memory = _ro(root / "data" / user / "memory.db")
    if memory is None:
        return []
    with memory:
        rows = memory.execute(
            "SELECT agent, run_date, count(*) n FROM findings WHERE run_date BETWEEN ? AND ? GROUP BY agent, run_date",
            (min(previous + window), max(previous + window))).fetchall()
    totals: dict[str, dict[str, list[int]]] = {}
    days_with = {"now": {r["run_date"] for r in rows if r["run_date"] in window},
                 "before": {r["run_date"] for r in rows if r["run_date"] in previous}}
    for r in rows:
        bucket = "now" if r["run_date"] in window else "before"
        totals.setdefault(r["agent"], {"now": [], "before": []})[bucket].append(r["n"])
    out = []
    for agent, buckets in totals.items():
        avg = {k: round(sum(v) / len(days_with[k]), 1) if days_with[k] else None for k, v in buckets.items()}
        out.append({"agent": agent, "per_day_now": avg["now"], "per_day_before": avg["before"]})
    return sorted(out, key=lambda a: -(a["per_day_now"] or 0))


def ambiguous_story_slugs(root: Path, user: str) -> int:
    """Story slugs two files claim. The story route refuses them, so each is a 404."""
    from dashboard.routes.api import _story_file_identity

    base = (root / "reports" / user / "site-stories").resolve()
    if not base.is_dir():
        return 0
    seen: dict[str, int] = {}
    for path in base.rglob("*.json"):
        identity = _story_file_identity(path, base)
        if identity is not None:
            seen[identity] = seen.get(identity, 0) + 1
    return sum(1 for n in seen.values() if n > 1)


def report(root: Path, user: str, since: int, today: date) -> dict:
    from orchestrator import editorial
    from orchestrator.evaluator import QUALITY_FLOOR_THRESHOLDS as floors

    window = [(today - timedelta(days=i)).isoformat() for i in range(since - 1, -1, -1)]
    previous = [(today - timedelta(days=i)).isoformat() for i in range(2 * since - 1, since - 1, -1)]
    days = collect_days(root, user, window)
    flag_days(days, min_findings=floors["min_finding_count"], min_agents=floors["min_agent_count"],
              min_eval=floors["min_overall"], site_target=editorial.load().issue_stories_per_day)
    return {"window": [window[0], window[-1]], "days": [asdict(d) for d in days],
            "agents": agent_output(root, user, window, previous),
            "ambiguous_story_slugs": ambiguous_story_slugs(root, user)}


def render(data: dict) -> str:
    def cell(value, fmt="{}"):
        return "-" if value is None else fmt.format(value)

    lines = [f"Pipeline health {data['window'][0]} to {data['window'][1]}", "",
             f"{'date':10} {'status':10} {'min':>4} {'sent':>4} {'agents':>6} {'findings':>8} {'dupes':>5} "
             f"{'eval':>5} {'site':>4} {'claude$':>8} {'codex':>5} {'failed':>6} {'fellback':>8}"]
    for d in data["days"]:
        lines.append(
            f"{d['date']:10} {cell(d['status']):10} {cell(d['minutes']):>4} "
            f"{cell(None if d['sent'] is None else ('yes' if d['sent'] else 'NO')):>4} {cell(d['agents_ok']):>6} "
            f"{cell(d['findings']):>8} {cell(d['duplicates_removed']):>5} {cell(d['eval_overall'], '{:.2f}'):>5} "
            f"{d['site_stories']:>4} {d['claude_usd']:>8.2f} {d['codex_calls']:>5} {d['failed_calls']:>6} "
            f"{d['fallbacks']:>8}")
    lines += ["", f"{'agent':28} {'per day now':>11} {'before':>7}"]
    for a in data["agents"]:
        lines.append(f"{a['agent']:28} {cell(a['per_day_now']):>11} {cell(a['per_day_before']):>7}")
    lines += ["", f"Ambiguous story slugs (404 on the site): {data['ambiguous_story_slugs']}"]
    problems = [(d["date"], f) for d in data["days"] for f in d["flags"]]
    lines += ["", "Problems:" if problems or data["ambiguous_story_slugs"] else "Problems: none"]
    lines += [f"  {when}  {flag}" for when, flag in problems]
    if data["ambiguous_story_slugs"]:
        lines.append(f"  site  {data['ambiguous_story_slugs']} story slugs are claimed by two files")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", type=int, default=7, help="days back, today included")
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="checkout whose data/ and reports/ to read")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = report(args.root, args.user, args.since, args.today)
    print(json.dumps(data, indent=2) if args.json else render(data))
    unhealthy = any(d["flags"] for d in data["days"]) or data["ambiguous_story_slugs"]
    return 1 if unhealthy else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Rerun a pipeline stage for a past day in a scratch copy, so a model or prompt
change can be judged on real data without touching live state.

    # synthesis (lead stories, selection, deep dives, newsletter) for Sep 30 with this checkout's code
    # and the live checkout's data, into a fresh output folder:
    .venv/bin/python3 tools/replay_day.py --date 2026-09-30 --stage synthesis \\
        --state-root ~/Projects/mindpattern-v3 --out /private/tmp/mp-replay/2026-09-30-a

    # the same day with another model table, for a bakeoff:
    ... --models /private/tmp/models-opus55.json --out /private/tmp/mp-replay/2026-09-30-b

How it stays isolated: the pipeline resolves every path from the location of its
own code, so the replay copies the code into a temporary workspace and snapshots
the state it needs (memory.db, traces.db, identity files, earlier issues) into it.
Everything the stage writes lands in that workspace. MP_DISABLE_OUTBOUND=1 blocks
email, sync, and alerts. Model calls are real unless --dry-run, and they are
traced into <out>/traces.

The output folder holds newsletter.md (the replay), original.md (what was
published that day), replay.json (routes, eval scores, usage), replay.log, and
traces/ for `python -m orchestrator.trace --db <out>/traces/traces.db ...`.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STAGES = ("synthesis", "research")
EXCLUDED_DIRS = {
    ".git", ".venv", ".claude", ".agents", "data", "reports", "tests", "__pycache__", ".pytest_cache",
    ".mypy_cache", "graphify-out", "node_modules", "research", "verification",
}
EXCLUDED_FILES = {"users.json", "social-config.json"}
ISSUE_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")

# Runs inside the workspace with the workspace's own code on PYTHONPATH.
DRIVER = r'''
import json, logging, sys
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(levelname)s %(message)s")
from core.trace_store import set_run_context
from orchestrator.pipeline import Phase
from orchestrator.runner import ResearchPipeline

user, day, stage = sys.argv[1], sys.argv[2], sys.argv[3]
only = set(sys.argv[4].split(",")) if len(sys.argv) > 4 and sys.argv[4] else None
trend_scan = len(sys.argv) <= 5 or sys.argv[5] != "no-trend-scan"
pipeline = ResearchPipeline(user, date_str=day)
import orchestrator.runner as runner_module
if stage == "research":
    # Research runs on today's sources: preflight fetches what is live now.
    import memory
    from core import findings_store
    from orchestrator import agents as agent_dispatch
    if trend_scan:
        set_run_context(phase="trend_scan")
        pipeline._phase_trend_scan()
    set_run_context(phase="research")
    results = agent_dispatch.dispatch_research_agents(
        user_id=user, date_str=day, context_fn=lambda agent, d: memory.get_context(pipeline.db, agent, d),
        trends=pipeline.trends, max_workers=3, preflight_data=pipeline.preflight_data, only=only)
    agents_out = {}
    for r in results:
        stored = findings_store.read_rows(findings_store.path_for(user, pipeline.traces_run_id, r.agent_name))
        agents_out[r.agent_name] = {"findings": len(r.findings), "stored_with_mp": len(stored),
                                    "classification": r.classification, "duration_ms": r.duration_ms}
    print("REPLAY_RESULT " + json.dumps({"project_root": str(runner_module.PROJECT_ROOT),
                                         "run_id": pipeline.traces_run_id, "trends": len(pipeline.trends),
                                         "agents": agents_out}, default=str))
    sys.exit(0)
# The day's trends come from the original run's TREND_SCAN checkpoint.
rows = pipeline.traces_conn.execute(
    "SELECT id FROM pipeline_runs WHERE id LIKE ? AND id != ? ORDER BY started_at DESC",
    (f"research-{day}-%", pipeline.traces_run_id),
).fetchall()
for row in rows:
    state = pipeline.checkpoint.load_phase(row[0], Phase.TREND_SCAN)
    if state and state.get("trends"):
        pipeline.trends = state["trends"]
        break
set_run_context(phase="synthesis")
result = pipeline._phase_synthesis()
print("REPLAY_RESULT " + json.dumps({
    "project_root": str(runner_module.PROJECT_ROOT),
    "run_id": pipeline.traces_run_id,
    "trends": len(pipeline.trends),
    "words": len(pipeline.newsletter_text.split()),
    "eval": pipeline.newsletter_eval,
    "result": result,
}, default=str))
'''


class ReplayError(RuntimeError):
    """The replay could not be set up or did not finish."""


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def copy_code(code_root: Path, workspace: Path) -> int:
    count = 0
    for directory, subdirectories, filenames in os.walk(code_root):
        base = Path(directory)
        subdirectories[:] = [name for name in subdirectories
                             if name not in EXCLUDED_DIRS and not (base / name).is_symlink()]
        for name in filenames:
            source = base / name
            if name in EXCLUDED_FILES or name.startswith(".env") or source.is_symlink() or name.endswith(".db"):
                continue
            target = workspace / source.relative_to(code_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            count += 1
    return count


def snapshot_db(source: Path, target: Path) -> None:
    """A consistent copy of a live SQLite file, WAL included."""
    if not source.exists():
        raise ReplayError(f"missing database {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def build_workspace(code_root: Path, state_root: Path, workspace: Path, *, user: str, day: date,
                    models: Path | None) -> dict:
    users = state_root / "users.json"
    if not users.exists():
        raise ReplayError(f"no users.json in the state root {state_root}")
    files = copy_code(code_root, workspace)
    shutil.copy2(users, workspace / "users.json")
    data_src, data_dst = state_root / "data" / user, workspace / "data" / user
    snapshot_db(data_src / "memory.db", data_dst / "memory.db")
    snapshot_db(data_src / "traces.db", data_dst / "traces.db")
    for pattern in ("*.md", "mindpattern/*.md"):
        for source in data_src.glob(pattern):
            target = data_dst / source.relative_to(data_src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    issues = 0
    reports_dst = workspace / "reports" / user
    reports_dst.mkdir(parents=True, exist_ok=True)
    for source in sorted((state_root / "reports" / user).glob("*.md")):
        match = ISSUE_NAME.match(source.name)
        if match and match.group(1) < day.isoformat():
            shutil.copy2(source, reports_dst / source.name)
            issues += 1
    if models:
        shutil.copy2(models, workspace / "config" / "models.json")
    return {"code_files": files, "earlier_issues": issues}


def _routes(workspace: Path, tasks: tuple[str, ...]) -> dict:
    done = subprocess.run(
        [sys.executable, "-c", "import json,sys\nfrom dataclasses import asdict\nfrom core.config import route_for\n"
         "print(json.dumps({t: asdict(route_for(t)) for t in sys.argv[1:]}))", *tasks],
        cwd=workspace, env={**os.environ, "PYTHONPATH": str(workspace)}, capture_output=True, text=True,
    )
    if done.returncode != 0:
        raise ReplayError(f"invalid config/models.json in the replay: {done.stderr.strip()[-300:]}")
    return json.loads(done.stdout)


def _usage(traces_db: Path) -> dict:
    if not traces_db.exists():
        return {"calls": 0}
    conn = sqlite3.connect(traces_db)
    try:
        rows = conn.execute(
            "SELECT task, provider, model, COUNT(*), SUM(output_tokens), SUM(input_tokens + cache_write_tokens), "
            "SUM(cache_read_tokens), SUM(cost_usd), SUM(outcome != 'success') FROM model_calls "
            "WHERE parent_call_id IS NULL GROUP BY task, provider, model ORDER BY task").fetchall()
    finally:
        conn.close()
    tasks = [{"task": r[0], "provider": r[1], "model": r[2], "calls": r[3], "output_tokens": r[4],
              "new_input_tokens": r[5], "cache_read_tokens": r[6], "cost_usd": r[7], "failed": r[8]} for r in rows]
    return {"calls": sum(t["calls"] for t in tasks), "tasks": tasks,
            "cost_usd": round(sum(t["cost_usd"] or 0 for t in tasks), 4)}


def _revision(code_root: Path) -> dict:
    def git(*args: str) -> str:
        done = subprocess.run(["git", *args], cwd=code_root, capture_output=True, text=True)
        return done.stdout.strip()
    return {"commit": git("rev-parse", "HEAD") or None, "branch": git("branch", "--show-current") or None,
            "dirty": bool(git("status", "--porcelain"))}


def replay(*, day: date, stage: str, out: Path, state_root: Path, code_root: Path = PROJECT_ROOT,
           user: str = "ramsay", models: Path | None = None, dry_run: bool = False,
           timeout: int = 3600, keep_workspace: bool = False, agents: list[str] | None = None,
           trend_scan: bool = True) -> dict:
    if stage not in STAGES:
        raise ReplayError(f"unknown stage {stage}; supported: {', '.join(STAGES)}")
    if out.exists() and any(out.iterdir()):
        raise ReplayError(f"output folder {out} is not empty; use a new one per replay")
    out.mkdir(parents=True, exist_ok=True)
    live_issue = state_root / "reports" / user / f"{day.isoformat()}.md"
    live_issue_before = _sha256(live_issue)

    workspace = Path(tempfile.mkdtemp(prefix="mp-replay-"))
    started = time.monotonic()
    try:
        built = build_workspace(code_root, state_root, workspace, user=user, day=day, models=models)
        routes = _routes(workspace, ("research_agent",) if stage == "research" else
                         ("thread_finder", "synthesis_pass1", "story_deep_dive", "synthesis_pass2",
                          "newsletter_editor"))
        # MP_PYTHON: the workspace has no .venv for bin/mp to find.
        env = {**os.environ, "PYTHONPATH": str(workspace), "MP_DISABLE_OUTBOUND": "1",
               "MP_TRACE_ROOT": str(out / "traces"), "MP_USER_ID": user, "MP_PYTHON": sys.executable}
        env.pop("MP_DRY_RUN", None)
        if dry_run:
            env["MP_DRY_RUN"] = "1"
        try:
            done = subprocess.run([sys.executable, "-c", DRIVER, user, day.isoformat(), stage, ",".join(agents or []),
                                   "trend-scan" if trend_scan else "no-trend-scan"],
                                  cwd=workspace, env=env,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ReplayError(f"stage {stage} did not finish in {timeout}s") from exc
        (out / "replay.log").write_text(f"--- stdout ---\n{done.stdout}\n--- stderr ---\n{done.stderr}\n")
        marker = [line for line in done.stdout.splitlines() if line.startswith("REPLAY_RESULT ")]
        if done.returncode != 0 or not marker:
            raise ReplayError(f"stage {stage} failed (exit {done.returncode}); see {out / 'replay.log'}")
        result = json.loads(marker[-1][len("REPLAY_RESULT "):])
        if Path(result["project_root"]).resolve() != workspace.resolve():
            raise ReplayError(f"the stage ran code from {result['project_root']}, not the scratch copy")
        written = workspace / "reports" / user / f"{day.isoformat()}.md"
        if written.exists():
            shutil.copy2(written, out / "newsletter.md")
        if live_issue.exists():
            shutil.copy2(live_issue, out / "original.md")
    finally:
        if keep_workspace:
            print(f"workspace kept at {workspace}", file=sys.stderr)
        else:
            shutil.rmtree(workspace, ignore_errors=True)

    summary = {
        "date": day.isoformat(),
        "stage": stage,
        "dry_run": dry_run,
        "replayed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_s": round(time.monotonic() - started, 1),
        "code": {"root": str(code_root), **_revision(code_root)},
        "state_root": str(state_root),
        "models_file": str(models) if models else None,
        "routes": routes,
        "workspace": built,
        "result": result,
        "usage": _usage(out / "traces" / "traces.db"),
        "live_issue_unchanged": _sha256(live_issue) == live_issue_before,
    }
    (out / "replay.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--stage", default="synthesis", choices=STAGES)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--state-root", type=Path, default=PROJECT_ROOT,
                        help="checkout whose data/, reports/ and users.json are replayed (read-only)")
    parser.add_argument("--user", default="ramsay")
    parser.add_argument("--models", type=Path, help="a models.json to use instead of config/models.json")
    parser.add_argument("--dry-run", action="store_true", help="no model calls (MP_DRY_RUN=1)")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--agents", help="research stage: comma-separated agent names (default: all thirteen)")
    parser.add_argument("--no-trend-scan", action="store_true",
                        help="research stage: skip preflight and trends (research without pre-fetched items)")
    parser.add_argument("--keep-workspace", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = replay(day=args.date, stage=args.stage, out=args.out, state_root=args.state_root.expanduser(),
                         user=args.user, models=args.models, dry_run=args.dry_run, timeout=args.timeout,
                         keep_workspace=args.keep_workspace,
                         agents=[a for a in (args.agents or "").split(",") if a],
                         trend_scan=not args.no_trend_scan)
    except ReplayError as exc:
        print(f"replay failed: {exc}", file=sys.stderr)
        return 1
    usage = summary["usage"]
    detail = (f"{summary['result'].get('words')} words" if summary["stage"] == "synthesis" else
              ", ".join(f"{a}: {r['findings']} findings ({r['stored_with_mp']} stored with mp, {r['classification']})"
                        for a, r in summary["result"].get("agents", {}).items()))
    print(f"replayed {summary['stage']} for {summary['date']} in {summary['duration_s']}s: {detail}; "
          f"{usage.get('calls', 0)} model calls, ${usage.get('cost_usd', 0)} at API prices. Output in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

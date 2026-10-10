#!/usr/bin/env python3
"""Rerun one traced model call with a different system prompt, on exactly the same input.

    .venv/bin/python3 devtools/rerun_call.py --traces data/ramsay/replays/DAY/traces --call ID \\
        --system-prompt agents/synthesis-writer.md --out /tmp/rerun/new-writer --runs 2

Reads call ID's saved prompt and task from TRACES/traces.db and runs it through the
pipeline's own call path (orchestrator.agents.run_claude_prompt) with the given
system prompt. Each run is traced under OUT/traces, its answer saved as
OUT/run-N.md, and its layout printed (orchestrator/issue_format.py). Outbound
actions are disabled. Real model calls.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import os
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def saved_call(traces: Path, call_id: str) -> tuple[str, str]:
    """(task, prompt) of a recorded call."""
    with sqlite3.connect(traces / "traces.db") as db:
        row = db.execute("SELECT task, prompt_path FROM model_calls WHERE id = ?", (call_id,)).fetchone()
    if not row or not row[1]:
        raise SystemExit(f"call {call_id} has no saved prompt in {traces / 'traces.db'}")
    path = Path(row[1])
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        return row[0], handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--traces", type=Path, required=True, help="folder holding traces.db")
    parser.add_argument("--call", required=True, help="model_calls.id to rerun")
    parser.add_argument("--system-prompt", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args(argv)

    task, prompt = saved_call(args.traces, args.call)
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["MP_TRACE_ROOT"] = str(args.out / "traces")
    os.environ["MP_DISABLE_OUTBOUND"] = "1"
    from orchestrator import agents
    from orchestrator.issue_format import report

    system_prompt = str(args.system_prompt.resolve())

    def run(n: int) -> str:
        text, code = agents.run_claude_prompt(prompt, task, system_prompt_file=system_prompt)
        path = args.out / f"run-{n}.md"
        path.write_text(text)
        return f"== {path} (exit {code})\n{report(text)}"

    with ThreadPoolExecutor(max_workers=args.runs) as pool:
        for block in pool.map(run, range(1, args.runs + 1)):
            print(block, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

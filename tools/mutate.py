#!/usr/bin/env python3
"""Break a guard on purpose, watch its tests fail, and put the file back byte for byte.

    .venv/bin/python3 tools/mutate.py --file orchestrator/prose_gate.py \\
        --old 'lifted += 1' --new 'pass' --test tests/test_prose_gate.py
    .venv/bin/python3 tools/mutate.py --plan mutations.json

A plan is a JSON list of {"file", "old", "new", "tests": [...], "k": optional}.
Each mutation must match exactly once. RED means a test caught the break.
MISSED means every test still passed, so the guard has no test. Exit 0 when
every mutation was RED, 1 when any was MISSED, 2 on a bad mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys


@dataclass
class Mutation:
    file: str
    old: str
    new: str
    tests: list[str]
    k: str | None = None


class BadMutation(ValueError):
    pass


def run_one(mutation: Mutation, *, cwd: Path, python: str = sys.executable) -> tuple[str, str]:
    """('RED' or 'MISSED', pytest's last line). The file is restored even on Ctrl-C."""
    path = cwd / mutation.file
    original = path.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    text = original.decode()
    if text.count(mutation.old) != 1:
        raise BadMutation(f"{mutation.file}: --old matches {text.count(mutation.old)} times, needs exactly 1")
    try:
        path.write_text(text.replace(mutation.old, mutation.new))
        command = [python, "-m", "pytest", *mutation.tests, "-q", "-p", "no:cacheprovider"]
        if mutation.k:
            command += ["-k", mutation.k]
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    finally:
        path.write_bytes(original)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"{mutation.file} was not restored byte for byte")
    last = (done.stdout.strip().splitlines() or ["(no output)"])[-1]
    return ("RED" if done.returncode else "MISSED"), last


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file")
    parser.add_argument("--old")
    parser.add_argument("--new", default="")
    parser.add_argument("--test", action="append", default=[], help="test file or node id; repeatable")
    parser.add_argument("-k", dest="k")
    parser.add_argument("--plan", type=Path, help="JSON list of mutations")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    if args.plan:
        mutations = [Mutation(m["file"], m["old"], m.get("new", ""), m["tests"], m.get("k"))
                     for m in json.loads(args.plan.read_text())]
    elif args.file and args.old is not None and args.test:
        mutations = [Mutation(args.file, args.old, args.new, args.test, args.k)]
    else:
        parser.error("give --plan, or --file, --old and at least one --test")

    missed = 0
    for mutation in mutations:
        try:
            verdict, last = run_one(mutation, cwd=args.cwd)
        except BadMutation as exc:
            print(f"BAD     {exc}")
            return 2
        missed += verdict == "MISSED"
        print(f"{verdict:7} {mutation.file}: {mutation.old[:60]!r} -> {last}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())

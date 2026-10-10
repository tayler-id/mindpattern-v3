"""Run every check in devtools/checks.json and write a receipt for the commit.

    bin/mpdev check                     every check, in order
    bin/mpdev check --only layers,tests
    bin/mpdev check --list

Each check's full output goes to .scratch/checks/<commit>/<id>.log. A failed
check prints its last lines. The receipt, .scratch/checks/<commit>.json, names
the commit, whether the tree was dirty, and each check's outcome and time.
Exits 0 when every check passed and 1 when any failed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHECKS = PROJECT_ROOT / "devtools" / "checks.json"
RECEIPTS = PROJECT_ROOT / ".scratch" / "checks"
TAIL_LINES = 25


class CheckFileError(ValueError):
    """devtools/checks.json is missing a field or holds a bad one."""


@dataclass(frozen=True)
class Check:
    id: str
    command: tuple[str, ...]
    about: str


@dataclass(frozen=True)
class Result:
    id: str
    passed: bool
    exit_code: int
    seconds: float
    log: str


def load(path: Path = CHECKS) -> list[Check]:
    try:
        rows = json.loads(path.read_text())["checks"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CheckFileError(f"cannot read the checks in {path}: {exc}") from exc
    checks: list[Check] = []
    for n, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CheckFileError(f"check {n} is not an object")
        cid, command, about = row.get("id"), row.get("command"), row.get("about")
        if not isinstance(cid, str) or not cid.strip():
            raise CheckFileError(f"check {n} has no id")
        if any(c.id == cid for c in checks):
            raise CheckFileError(f"check id {cid!r} appears twice")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise CheckFileError(f"check {cid!r} needs a command as a non-empty list of strings")
        if not isinstance(about, str) or not about.strip():
            raise CheckFileError(f"check {cid!r} needs an about line")
        checks.append(Check(cid, tuple(command), about))
    return checks


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return done.stdout.strip()


def run_check(check: Check, *, log_dir: Path, python: str = sys.executable) -> Result:
    command = [python if part == "{python}" else part for part in check.command]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(PROJECT_ROOT), os.environ.get("PYTHONPATH")]))}
    log = log_dir / f"{check.id}.log"
    start = time.monotonic()
    with log.open("w") as handle:
        done = subprocess.run(command, cwd=PROJECT_ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
    return Result(check.id, done.returncode == 0, done.returncode, round(time.monotonic() - start, 1), str(log))


def receipt(results: list[Result], *, commit: str, dirty: bool) -> dict:
    return {
        "commit": commit,
        "dirty": dirty,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "outcome": "pass" if results and all(r.passed for r in results) else "fail",
        "checks": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mpdev check", description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated check ids")
    parser.add_argument("--list", action="store_true", help="print the checks and exit")
    parser.add_argument("--checks", type=Path, default=CHECKS, help=argparse.SUPPRESS)
    parser.add_argument("--receipts", type=Path, default=RECEIPTS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        checks = load(args.checks)
    except CheckFileError as exc:
        print(f"mpdev check: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for check in checks:
            print(f"{check.id:<12} {check.about}")
        return 0
    if args.only:
        wanted = [name.strip() for name in args.only.split(",") if name.strip()]
        unknown = sorted(set(wanted) - {c.id for c in checks})
        if unknown:
            print(f"mpdev check: no check named {', '.join(unknown)}", file=sys.stderr)
            return 2
        checks = [c for c in checks if c.id in wanted]

    commit = _git("rev-parse", "HEAD") or "no-commit"
    dirty = bool(_git("status", "--porcelain"))
    log_dir = args.receipts / commit
    log_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for check in checks:
        result = run_check(check, log_dir=log_dir)
        results.append(result)
        print(f"{'PASS' if result.passed else 'FAIL'}  {check.id:<12} {result.seconds:>6.1f}s", flush=True)
        if not result.passed:
            tail = Path(result.log).read_text().splitlines()[-TAIL_LINES:]
            print("\n".join(f"      {line}" for line in tail))
            print(f"      full log: {result.log}")
    record = receipt(results, commit=commit, dirty=dirty)
    path = args.receipts / f"{commit}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"{record['outcome']}: {sum(r.passed for r in results)}/{len(results)} checks, "
          f"commit {commit[:10]}{' (dirty tree)' if dirty else ''}. Receipt {path}")
    return 0 if record["outcome"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

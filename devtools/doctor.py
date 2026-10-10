"""Is this machine ready to work on the codebase and run its checks? Read-only.

    bin/mpdev doctor          every probe
    bin/mpdev doctor --ci     skip what CI doesn't have: the model CLIs, live data, the local code graph
    bin/mpdev doctor --json

Each blocked probe prints its fix. It never installs, writes, or changes
anything. CI mode is also on when the CI environment variable is "true", as
GitHub Actions sets it. Exits 0 when every probe passes and 1 when any is
blocked.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 14)
CLIS = ("claude", "codex", "gh")
DEV_PACKAGES = ("pytest",)
_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass(frozen=True)
class Probe:
    id: str
    ok: bool
    detail: str
    fix: str = ""
    blocking: bool = True  # False: reported as a warning and never fails the doctor


def _git(*args: str, cwd: Path = PROJECT_ROOT) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def probe_python(version: tuple[int, ...] = tuple(sys.version_info[:3])) -> Probe:
    shown = ".".join(map(str, version))
    if version[:2] >= MIN_PYTHON:
        return Probe("python", True, shown)
    return Probe("python", False, f"Python {shown}, need {'.'.join(map(str, MIN_PYTHON))} or newer",
                 "Run mpdev with the project venv: .venv/bin/python3, or set MP_PYTHON.")


def probe_packages(requirements: Path = PROJECT_ROOT / "requirements.txt",
                   version: Callable[[str], str] = metadata.version) -> Probe:
    names = [m.group(1) for line in requirements.read_text().splitlines()
             if not line.lstrip().startswith("#") and (m := _REQUIREMENT.match(line))]
    missing = []
    for name in [*names, *DEV_PACKAGES]:
        try:
            version(name)
        except metadata.PackageNotFoundError:
            missing.append(name)
    if missing:
        return Probe("packages", False, f"missing {', '.join(missing)}",
                     "pip install -r requirements.txt pytest (in the venv mpdev runs with)")
    return Probe("packages", True, f"{len(names) + len(DEV_PACKAGES)} installed")


def probe_clis(which: Callable[[str], str | None] = shutil.which) -> Probe:
    missing = [name for name in CLIS if not which(name)]
    if missing:
        return Probe("clis", False, f"not on PATH: {', '.join(missing)}",
                     "Install them, or run with --ci where model calls and GitHub access aren't needed.")
    return Probe("clis", True, ", ".join(CLIS))


def state_root(user: str, project_root: Path = PROJECT_ROOT) -> Path:
    """The checkout that holds the user's databases: this one, or the main checkout when this is a worktree."""
    if (project_root / "data" / user / "memory.db").exists():
        return project_root
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=project_root)
    return Path(common).parent if common else project_root


def probe_data(user: str, root: Path) -> Probe:
    opened = []
    for name in ("memory.db", "traces.db"):
        path = root / "data" / user / name
        if not path.exists():
            return Probe("data", False, f"no {path}", "Run from the live checkout or one of its worktrees, or use --ci.")
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            return Probe("data", False, f"{path} unreadable: {exc}", "Check the file isn't locked or corrupt.")
        opened.append(name)
    return Probe("data", True, f"{' and '.join(opened)} readable in {root / 'data' / user}")


def probe_graph(project_root: Path = PROJECT_ROOT, code_time: int | None = None) -> Probe:
    """Advisory. The hooks rebuild the graph in the background after a code commit, so it lags for a while."""
    graph = project_root / "graphify-out" / "graph.json"
    if not graph.exists():
        return Probe("graph", False, "no graphify-out/graph.json", "graphify update .", blocking=False)
    if code_time is None:
        code_time = int(_git("log", "-1", "--format=%ct", "--", "*.py", cwd=project_root) or 0)
    if graph.stat().st_mtime + 1 < code_time:
        return Probe("graph", False, "graphify-out/graph.json is older than the last commit to Python code",
                     "graphify update .  (the post-commit hook does this in the background)", blocking=False)
    flags = _git("ls-files", "-v", "graphify-out", cwd=project_root).splitlines()
    tracked = [line for line in flags if line]
    if tracked and not all(line.startswith("S ") for line in tracked):
        return Probe("graph", False, "graphify-out/ is fresh but git shows its changes",
                     "git ls-files graphify-out | xargs git update-index --skip-worktree", blocking=False)
    return Probe("graph", True, "fresh, and kept out of git status", blocking=False)


def run(*, ci: bool, user: str) -> list[Probe]:
    probes = [probe_python(), probe_packages()]
    if not ci:
        probes += [probe_clis(), probe_data(user, state_root(user)), probe_graph()]
    return probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mpdev doctor", description=__doc__.splitlines()[0])
    parser.add_argument("--ci", action="store_true", help="skip the model CLIs, live data, and the code graph")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--user", default=os.environ.get("MP_USER_ID", "ramsay"))
    args = parser.parse_args(argv)
    ci = args.ci or os.environ.get("CI") == "true"
    probes = run(ci=ci, user=args.user)
    ok = all(p.ok for p in probes if p.blocking)
    if args.json:
        print(json.dumps({"outcome": "pass" if ok else "blocked", "ci": ci, "probes": [asdict(p) for p in probes]}))
    else:
        for p in probes:
            label = "ok" if p.ok else ("BLOCKED" if p.blocking else "warn")
            print(f"{label:<8} {p.id:<9} {p.detail}" + (f"\n         fix: {p.fix}" if p.fix else ""))
        print(("pass" if ok else "blocked") + (" (CI mode)" if ci else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

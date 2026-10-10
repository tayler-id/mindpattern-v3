"""mpdev: one command for every developer tool. `bin/mpdev help` lists them."""

from __future__ import annotations

import importlib
import sys

# name -> (module with main(argv), what it does). Model calls and live writes are named here
# so an agent sees the cost before it runs anything.
COMMANDS: dict[str, tuple[str, str]] = {
    "check": ("devtools.check", "run every check in devtools/checks.json and write a receipt"),
    "doctor": ("devtools.doctor", "read-only: is this machine ready to work and run the checks?"),
    "replay": ("devtools.replay_day", "rerun a past day's stage in a scratch copy (model calls unless --dry-run)"),
    "rerun": ("devtools.rerun_call", "rerun one traced call with another system prompt (model calls)"),
    "bakeoff": ("devtools.bakeoff", "blind side by side of two issues"),
    "mutate": ("devtools.mutate", "break a guard, watch its tests fail, restore it byte for byte"),
    "health": ("devtools.health", "how the daily run has gone, one row per day"),
    "trace": ("orchestrator.trace", "every model call in a run, its steps, and its cost"),
    "usage": ("devtools.usage_report", "model usage for a day from Claude transcripts"),
    "site-backfill": ("devtools.site_backfill", "write past issues' missing site stories (model calls, live writes)"),
}


def usage() -> str:
    width = max(map(len, COMMANDS))
    rows = "\n".join(f"  {name:<{width}}  {about}" for name, (_, about) in COMMANDS.items())
    return (f"usage: mpdev <command> [args]\n\n{rows}\n\n"
            "`mpdev <command> --help` shows a command's flags. docs/tools.md explains each tool.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in {"help", "-h", "--help"}:
        print(usage())
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"mpdev: no command {name!r}. `mpdev help` lists them.", file=sys.stderr)
        return 2
    sys.argv[0] = f"mpdev {name}"  # argparse names the command in its usage line
    return importlib.import_module(COMMANDS[name][0]).main(rest)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Healthcheck: can tomorrow's 7 AM pipeline actually run?

(Named healthcheck, not preflight — preflight/ is the data-collection package.)

Checks the things that silently break between runs — Claude auth (which
changes whenever the subscription is swapped), Fly auth (a separate login,
scoped to a specific account), the launchd agent, and the wake event.

Every check runs; the exit code is 1 if any REQUIRED check failed.

    python3 scripts/healthcheck.py
    python3 scripts/healthcheck.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FLY_APP = "mindpattern"
LAUNCHD_LABEL = "com.mindpattern.pipeline"

# launchd hands children a minimal environment. Reproduce it so an auth check
# here means the same thing it will mean at 8 AM — a bare `claude -p` from an
# interactive shell can pass while the scheduled run fails.
LAUNCHD_PATH = (
    "/Users/taylerramsay/.local/bin:/Users/taylerramsay/.fly/bin:"
    "/Users/taylerramsay/.local/node/bin:/usr/bin:/bin:/usr/sbin:/sbin"
)


@dataclass
class Result:
    name: str
    ok: bool
    required: bool
    detail: str


def _launchd_env() -> dict[str, str]:
    """The environment launchd actually gives a LaunchAgent child."""
    keep = ("HOME", "USER", "LOGNAME", "TMPDIR", "SHELL")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PATH"] = LAUNCHD_PATH
    return env


def check_claude_auth() -> Result:
    """Does `claude -p` authenticate under the launchd environment?

    This is the check that catches a subscription swap that didn't take.
    """
    claude = shutil.which("claude", path=LAUNCHD_PATH)
    if not claude:
        return Result("claude-auth", False, True, "claude not on the launchd PATH")
    try:
        proc = subprocess.run(
            [claude, "-p", "Reply with exactly: AUTH_OK"],
            env=_launchd_env(),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return Result("claude-auth", False, True, "timed out after 180s")
    out = (proc.stdout + proc.stderr).strip()
    if "AUTH_OK" in out:
        return Result("claude-auth", True, True, "authenticated under launchd env")
    # "Not logged in · Please run /login" is what a dead/blank credential gives.
    return Result("claude-auth", False, True, out.splitlines()[-1][:120] if out else "no output")


def check_claude_account() -> Result:
    """Report which subscription is active. Informational — either is valid."""
    cfg = Path.home() / ".claude.json"
    if not cfg.exists():
        return Result("claude-account", False, False, "~/.claude.json missing")
    try:
        acct = json.loads(cfg.read_text()).get("oauthAccount") or {}
    except (json.JSONDecodeError, OSError) as exc:
        return Result("claude-account", False, False, f"unreadable: {exc}")
    email = acct.get("emailAddress", "?")
    tier = acct.get("organizationRateLimitTier", "?")
    return Result("claude-account", True, False, f"{email} ({tier})")


def _flyctl() -> str | None:
    return shutil.which("flyctl") or shutil.which(
        "flyctl", path=os.path.expanduser("~/.fly/bin")
    )


def check_fly_app_access() -> Result:
    """Is flyctl logged into the account that can actually see the app?

    `auth whoami` succeeding is not enough: the wrong Fly account authenticates
    fine and then cannot find the app, which is how a sync breaks silently.
    """
    fly = _flyctl()
    if not fly:
        return Result("fly-app-access", False, True, "flyctl not found")
    try:
        proc = subprocess.run(
            [fly, "status", "-a", FLY_APP],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return Result("fly-app-access", False, True, "flyctl status timed out")
    if proc.returncode == 0:
        return Result("fly-app-access", True, True, f"{FLY_APP} visible")
    err = (proc.stderr or proc.stdout).strip().splitlines()
    msg = next((ln for ln in err if "Error" in ln), err[-1] if err else "unknown")
    if "no access token" in msg:
        msg = "logged out — run: flyctl auth login"
    elif "Could not find App" in msg:
        msg = f"logged into a Fly account that cannot see {FLY_APP}"
    return Result("fly-app-access", False, True, msg[:120])


def check_launchd_agent() -> Result:
    """Is the LaunchAgent loaded?"""
    try:
        proc = subprocess.run(
            ["launchctl", "list", LAUNCHD_LABEL],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Result("launchd-agent", False, True, str(exc))
    if proc.returncode != 0:
        return Result("launchd-agent", False, True, f"{LAUNCHD_LABEL} not loaded")
    return Result("launchd-agent", True, True, "loaded")


def check_wake_event() -> Result:
    """A sleeping Mac runs nothing. Needs a repeating wake AND AC power."""
    try:
        sched = subprocess.run(
            ["pmset", "-g", "sched"], capture_output=True, text=True, timeout=15
        ).stdout
        batt = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=15
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Result("wake-event", False, False, str(exc))
    has_repeat = "wakepoweron" in sched or "wakeorpoweron" in sched
    on_ac = "AC Power" in batt
    if has_repeat and on_ac:
        return Result("wake-event", True, False, "repeating wake set, on AC")
    missing = []
    if not has_repeat:
        missing.append("no repeating wake event")
    if not on_ac:
        missing.append("on battery (macOS will skip the RTC wake)")
    return Result("wake-event", False, False, "; ".join(missing))


def check_venv() -> Result:
    py = REPO / ".venv" / "bin" / "python3"
    if not py.exists():
        return Result("venv", False, True, f"missing {py}")
    return Result("venv", True, True, str(py))


CHECKS = (
    check_claude_account,
    check_claude_auth,
    check_fly_app_access,
    check_launchd_agent,
    check_wake_event,
    check_venv,
)


def run_all() -> list[Result]:
    return [check() for check in CHECKS]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    results = run_all()

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        for r in results:
            if r.ok:
                mark = "PASS"
            else:
                mark = "FAIL" if r.required else "WARN"
            print(f"[{mark}] {r.name:<16} {r.detail}")

    failed = [r for r in results if not r.ok and r.required]
    if failed and not args.json:
        print(f"\n{len(failed)} required check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

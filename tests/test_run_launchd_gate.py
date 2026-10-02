"""run-launchd.sh must not start a run the Mac cannot finish.

On 2026-09-28 and 2026-09-29 launchd fired the wrapper inside a two-second
dark wake on battery. The Mac slept again at once, and the run crawled through
DNS failures for 14 hours on each day.
"""
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "run-launchd.sh"
REAL_LOCK = 'LOCK="/tmp/mindpattern-pipeline.lock"'
# The live checkout the script hardcodes, not this checkout: CI and worktrees
# live elsewhere and must still prove the copy never touches the real one.
LIVE_ROOT = re.search(r"^cd (/\S+)$", SCRIPT.read_text(), re.M).group(1)


def _exe(path: Path, body: str) -> None:
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path: Path, *, power: str, capabilities: str, curl_exit: int) -> str:
    work = tmp_path / "repo"
    (work / "reports").mkdir(parents=True)
    (work / ".venv" / "bin").mkdir(parents=True)
    _exe(work / ".venv" / "bin" / "python3", 'echo "PIPELINE STARTED"')

    fakes = tmp_path / "bin"
    fakes.mkdir()
    _exe(fakes / "pmset", f"""case "$2" in
  ps) echo "Now drawing from '{power}'" ;;
  systemstate) echo "Current System Capabilities are: {capabilities}" ;;
esac""")
    _exe(fakes / "curl", f"exit {curl_exit}")
    _exe(fakes / "date", '[ "$1" = "+%H" ] && echo 08 || /bin/date "$@"')
    _exe(fakes / "git", "echo test-branch")
    _exe(fakes / "caffeinate", "exit 0")

    source = SCRIPT.read_text()
    assert LIVE_ROOT in source and REAL_LOCK in source
    script = source.replace(LIVE_ROOT, str(work)).replace(
        REAL_LOCK, f'LOCK="{tmp_path}/pipeline.lock"')
    assert LIVE_ROOT not in script, "copy must never touch the real repo"
    (tmp_path / "run-launchd.sh").write_text(script)

    env = {"PATH": f"{fakes}:/usr/bin:/bin", "HOME": str(tmp_path),
           "MP_RAN_MARKER_DIR": str(tmp_path)}
    done = subprocess.run(["/bin/bash", str(tmp_path / "run-launchd.sh")],
                          env=env, capture_output=True, text=True, timeout=30)
    return done.stdout


@pytest.mark.parametrize("power,capabilities,curl_exit,expected", [
    ("Battery Power", "CPU Network", 0, "SKIP: Dark wake on battery"),
    ("AC Power", "CPU Graphics Audio Network", 6, "SKIP: api.anthropic.com unreachable"),
])
def test_skips_a_run_it_cannot_finish(tmp_path, power, capabilities, curl_exit, expected):
    out = _run(tmp_path, power=power, capabilities=capabilities, curl_exit=curl_exit)
    assert expected in out
    assert "PIPELINE STARTED" not in out


@pytest.mark.parametrize("power,capabilities", [
    ("AC Power", "CPU Network"),
    ("Battery Power", "CPU Graphics Audio Network"),
])
def test_starts_when_the_mac_stays_up(tmp_path, power, capabilities):
    out = _run(tmp_path, power=power, capabilities=capabilities, curl_exit=0)
    assert "PIPELINE STARTED" in out

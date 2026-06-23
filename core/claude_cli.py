"""Shared process boundary for Claude CLI calls."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import signal
import subprocess

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaudeProcessResult:
    """Completed Claude CLI process state."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False
    error: str | None = None


def kill_process_group(popen: subprocess.Popen) -> None:
    """Kill a Popen-owned process group, falling back to the direct child."""
    try:
        os.killpg(os.getpgid(popen.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError, PermissionError):
        try:
            popen.kill()
        except OSError:
            pass


def run_claude_process(
    cmd: Sequence[str],
    *,
    timeout: int,
    input_text: str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ClaudeProcessResult:
    """Run one Claude CLI process in a killable process group."""
    popen = None
    try:
        popen = subprocess.Popen(
            list(cmd),
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            start_new_session=True,
        )
        stdout, stderr = popen.communicate(input=input_text, timeout=timeout)
        return ClaudeProcessResult(
            stdout=stdout,
            stderr=stderr,
            returncode=popen.returncode,
        )
    except subprocess.TimeoutExpired:
        if popen is not None:
            kill_process_group(popen)
            try:
                popen.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        message = f"Timed out after {timeout}s"
        logger.warning("claude call timed out after %ds, process group killed", timeout)
        return ClaudeProcessResult("", "", 1, timed_out=True, error=message)
    except Exception as e:
        logger.error("claude process failed to start: %s", e)
        return ClaudeProcessResult("", "", 1, error=str(e))

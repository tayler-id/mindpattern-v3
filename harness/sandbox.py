"""Fail-closed side-effect isolation for autonomous routines.

Every autonomous routine (crash fuzzers, logic fixers, dead-code sweeps)
runs inside `sandbox()` and calls `assert_sandbox()` before touching
anything. The sandbox:

- copies `memory.db` and `traces.db` into a temp directory (sqlite backup
  API, so a live WAL never produces a torn copy) and hands the routine
  those paths;
- exports the guard environment: ``MP_SANDBOX=1`` plus the existing
  pipeline kill switches ``MP_DRY_RUN=1`` and ``MP_SKIP_SOCIAL=1``;
- meters the routine's own `claude` usage through a call budget.

The outbound side-effect boundaries (Resend send, social HTTP, Fly
sync/ssh/restart) carry inline guards that raise when ``MP_SANDBOX=1``.
Those guards deliberately do NOT import this module: `harness/` is not in
the Fly container image, so boundary modules check ``os.environ``
directly and raise a plain RuntimeError whose message starts with
``MP_SANDBOX=1:``. `is_violation()` recognizes both forms.

Design rule (harness/CLAUDE.md): deterministic Python, no LLM.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "ramsay"

ENV_FLAG = "MP_SANDBOX"
VIOLATION_PREFIX = "MP_SANDBOX=1:"

# Everything a sandbox forces into the environment. MP_DRY_RUN,
# MP_SKIP_SOCIAL, and MP_DISABLE_OUTBOUND are the pipeline's own kill
# switches (soft skips); MP_SANDBOX is the hard guard the side-effect
# boundaries check and raise on. Layered on purpose: the soft switches
# turn phases into no-ops, the hard guard makes any boundary that is
# reached anyway fail loudly.
GUARD_ENV: dict[str, str] = {
    ENV_FLAG: "1",
    "MP_DRY_RUN": "1",
    "MP_SKIP_SOCIAL": "1",
    "MP_DISABLE_OUTBOUND": "1",
}

# Databases copied into every sandbox.
SANDBOXED_DBS = ("memory.db", "traces.db")


class SandboxViolation(RuntimeError):
    """A routine crossed a line: exhausted its budget or hit a boundary."""


class SandboxNotActive(RuntimeError):
    """assert_sandbox() ran outside an active sandbox."""


def sandbox_active() -> bool:
    return os.environ.get(ENV_FLAG) == "1"


def assert_sandbox() -> None:
    """Every routine's first call. Raises unless the guard env is up."""
    if not sandbox_active():
        raise SandboxNotActive(
            "Routine started outside a sandbox. Wrap the routine in "
            "harness.sandbox.sandbox() before doing anything."
        )
    for key, value in GUARD_ENV.items():
        if os.environ.get(key) != value:
            raise SandboxNotActive(
                f"Sandbox env incomplete: {key} != {value!r}. "
                "Refusing to run with partial isolation."
            )


def is_violation(exc: BaseException) -> bool:
    """True for budget/boundary violations, including the dependency-free
    inline guards in orchestrator/ and social/ (message-prefix form)."""
    if isinstance(exc, SandboxViolation):
        return True
    return isinstance(exc, RuntimeError) and str(exc).startswith(VIOLATION_PREFIX)


@dataclass
class Budget:
    """Meter for the routine's own `claude` calls. Fail-closed: the call
    that would exceed the budget raises before it runs."""

    max_claude_calls: int
    spent: int = 0

    def charge(self, calls: int = 1) -> None:
        if self.spent + calls > self.max_claude_calls:
            raise SandboxViolation(
                f"claude budget exhausted: {self.spent} spent, "
                f"{calls} requested, {self.max_claude_calls} allowed"
            )
        self.spent += calls

    def remaining(self) -> int:
        return self.max_claude_calls - self.spent


@dataclass
class Sandbox:
    """Handle a routine receives: temp DB paths and the budget."""

    root: Path
    memory_db: Path
    traces_db: Path
    budget: Budget
    _saved_env: dict[str, str | None] = field(default_factory=dict, repr=False)


def _backup_db(source: Path, dest: Path) -> None:
    """Consistent copy via the sqlite backup API. A missing source yields
    an empty database, so routines always get a real file to open."""
    dest_conn = sqlite3.connect(dest)
    try:
        if source.exists():
            src_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            try:
                src_conn.backup(dest_conn)
            finally:
                src_conn.close()
    finally:
        dest_conn.close()


@contextmanager
def sandbox(*, max_claude_calls: int = 20, data_dir: Path | None = None):
    """Context manager for one routine run.

    Sets the guard environment, snapshots the databases into a temp
    directory, and restores the previous environment on exit — including
    after an exception, so a crashed routine cannot leave the guards up
    or (worse) half up.
    """
    source_dir = data_dir if data_dir is not None else DEFAULT_DATA_DIR
    saved: dict[str, str | None] = {}

    with TemporaryDirectory(prefix="mp-sandbox-") as tmp:
        root = Path(tmp)
        box = Sandbox(
            root=root,
            memory_db=root / "memory.db",
            traces_db=root / "traces.db",
            budget=Budget(max_claude_calls=max_claude_calls),
        )
        for name in SANDBOXED_DBS:
            _backup_db(source_dir / name, root / name)

        for key, value in GUARD_ENV.items():
            saved[key] = os.environ.get(key)
            os.environ[key] = value
        box._saved_env = saved

        logger.info(
            "sandbox up: root=%s budget=%d claude calls", root, max_claude_calls
        )
        try:
            yield box
        finally:
            for key, previous in saved.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
            logger.info("sandbox down: root=%s", root)

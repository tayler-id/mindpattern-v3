"""Autonomous nightly routines.

Each routine is a deterministic finder: it produces `Finding` objects from a
mechanical signal (a crash, a broken layer rule, a same-SHA test flake) — never
from a model's opinion. Findings carry a repro command so `/verify` can prove
any proposed fix actually flips it.

Design rules (docs/autonomous-routines-plan.md, harness/CLAUDE.md):
- Signals are deterministic. LLMs may later WRITE a fix; they never decide that
  a finding exists.
- Every routine runs inside `harness.sandbox.sandbox()` and calls
  `assert_sandbox()` first.
- Routines never push, never merge, never touch the network.
"""

from harness.routines.base import Finding, Routine, RoutineResult

__all__ = ["Finding", "Routine", "RoutineResult"]
